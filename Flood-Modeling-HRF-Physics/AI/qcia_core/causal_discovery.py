"""
Causal Discovery Engine

This module implements algorithms for learning causal structure from observational data:
- PC Algorithm: Constraint-based causal discovery using conditional independence tests
- Helper methods for independence testing

The PC algorithm is the foundational algorithm in causal discovery, published by
Peter Spirtes and Clark Glymour in 1991.
"""

import pandas as pd
import numpy as np
from typing import Set, List, Optional, Tuple
from itertools import combinations
from scipy.stats import pearsonr
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
import warnings
import logging

from .causal_graph import CausalGraph


class CausalDiscoveryEngine:
    """
    Learns causal structure from observational data using the PC algorithm.
    
    The PC algorithm works in two phases:
    1. Skeleton Phase: Find undirected edges by testing conditional independence
    2. Orientation Phase: Orient edges using collider detection and propagation rules
    
    Example:
        >>> engine = CausalDiscoveryEngine(alpha=0.05)
        >>> causal_graph = engine.learn_structure(data, method='pc')
    """
    
    def __init__(self, alpha: float = 0.05,
                 independence_test: str = 'partial_correlation',
                 hsic_num_permutations: int = 100,
                 hsic_sigma: Optional[float] = None,
                 residual_model: str = 'linear',
                 random_state: Optional[int] = 42):
        """
        Initialize the causal discovery engine.
        
        Args:
            alpha: Significance level for independence tests (default 0.05)
                   Lower alpha = more conservative (fewer edges)
                   Higher alpha = more liberal (more edges)
        """
        self.alpha = alpha
        self.data: Optional[pd.DataFrame] = None
        self.separation_sets: dict = {}  # Stores which variables separate X and Y
        # New options
        self.independence_test = independence_test  # 'partial_correlation' | 'hsic'
        self.hsic_num_permutations = hsic_num_permutations
        self.hsic_sigma = hsic_sigma
        self.residual_model = residual_model  # 'linear' | 'random_forest'
        self.random_state = random_state
        self.logger = logging.getLogger(__name__)
        
    def learn_structure(self, data: pd.DataFrame, 
                       method: str = 'pc') -> CausalGraph:
        """
        Learn causal graph from data.
        
        Args:
            data: DataFrame where columns are variables, rows are observations
            method: 'pc' (constraint-based) or 'ges' (score-based, not implemented yet)
        
        Returns:
            CausalGraph representing learned causal structure
        """
        self.data = data
        
        if method == 'pc':
            return self._pc_algorithm()
        elif method == 'ges':
            raise NotImplementedError("GES algorithm not yet implemented. Use method='pc'")
        else:
            raise ValueError(f"Unknown method: {method}. Use 'pc' or 'ges'")
    
    def _pc_algorithm(self) -> CausalGraph:
        """
        PC (Peter-Clark) Algorithm for causal discovery.
        
        Steps:
        1. Start with fully connected undirected graph
        2. Remove edges based on conditional independence tests
        3. Orient edges using collider detection (V-structures)
        4. Apply Meek's rules to orient more edges
        
        Returns:
            CausalGraph with discovered causal structure
        """
        variables = list(self.data.columns)
        n_vars = len(variables)
        
        print(f"\n🔍 PC Algorithm: Learning causal structure from {len(self.data)} observations")
        print(f"   Variables: {variables}")
        print(f"   Significance level α = {self.alpha}")
        if self.independence_test == 'hsic':
            print(f"   Independence test: HSIC (permutations={self.hsic_num_permutations}, residual_model={self.residual_model})")
        else:
            print(f"   Independence test: Partial correlation")
        
        # Phase 1: Build skeleton (undirected graph)
        print("\n📊 Phase 1: Building skeleton (testing independence)...")
        skeleton = self._build_skeleton(variables)
        print(f"   Found {len(skeleton)} edges in skeleton")
        
        # Phase 2: Orient edges
        print("\n🎯 Phase 2: Orienting edges...")
        causal_graph = self._orient_edges(skeleton, variables)
        print(f"   Result: {causal_graph.graph.number_of_edges()} directed edges")
        
        return causal_graph
    
    def _build_skeleton(self, variables: List[str]) -> Set[Tuple[str, str]]:
        """
        Phase 1: Build skeleton by removing edges based on conditional independence.
        
        We start with a complete graph and progressively test larger conditioning sets.
        If X ⊥ Y | Z (X independent of Y given Z), we remove edge X-Y.
        
        Args:
            variables: List of variable names
        
        Returns:
            Set of undirected edges (as tuples) that remain
        """
        # Start with complete undirected graph
        edges = set()
        for i, X in enumerate(variables):
            for Y in variables[i+1:]:
                edges.add((X, Y))
        
        print(f"   Starting with {len(edges)} possible edges")
        
        # Test independence conditioning on subsets of increasing size
        max_conditioning_size = min(len(variables) - 2, 3)  # Limit for computational efficiency
        
        for l in range(max_conditioning_size + 1):
            if not edges:
                break
                
            print(f"   Testing with conditioning set size = {l}...")
            edges_to_remove = set()
            
            for (X, Y) in list(edges):  # Use list() to avoid modification during iteration
                # Find potential conditioning sets (adjacent variables)
                adjacents = self._get_adjacents(X, Y, edges, variables)
                
                # Test all possible conditioning sets of size l
                if l > len(adjacents):
                    continue
                
                for Z_subset in combinations(adjacents, l):
                    Z_list = list(Z_subset)
                    
                    # Test conditional independence
                    if self._is_independent(X, Y, Z_list):
                        edges_to_remove.add((X, Y))
                        self.separation_sets[(X, Y)] = Z_list
                        self.separation_sets[(Y, X)] = Z_list  # Symmetric
                        break
            
            edges -= edges_to_remove
            if edges_to_remove:
                print(f"     Removed {len(edges_to_remove)} edges, {len(edges)} remain")
        
        return edges
    
    def _is_independent(self, X: str, Y: str, Z: List[str]) -> bool:
        """
        Test if X ⊥ Y | Z (X independent of Y given Z).
        
        If independence_test == 'partial_correlation' (default):
            1) Regress X on Z (linear) → residuals r_X
            2) Regress Y on Z (linear) → residuals r_Y
            3) Test if r_X and r_Y are uncorrelated (Pearson)
        If independence_test == 'hsic':
            Unconditional (Z empty): HSIC-Gaussian kernel with permutation p-value
            Conditional (Z non-empty): residualize X,Y on Z (linear or RF), then HSIC
        
        Args:
            X: First variable
            Y: Second variable
            Z: Conditioning set (variables to control for)
        
        Returns:
            True if X and Y are independent given Z (p-value > alpha)
        """
        # Option 1: Partial correlation (existing default)
        if self.independence_test == 'partial_correlation':
            if len(Z) == 0:
                # Unconditional independence: just test correlation
                try:
                    _, p_value = pearsonr(self.data[X], self.data[Y])
                    return p_value > self.alpha
                except Exception:
                    return False
            # Conditional independence using partial correlation
            try:
                Z_data = self.data[Z].values
                X_data = self.data[X].values.reshape(-1, 1)
                Y_data = self.data[Y].values.reshape(-1, 1)
                
                # Check for constant columns
                if np.std(X_data) < 1e-10 or np.std(Y_data) < 1e-10:
                    return False
                
                # Regress out Z from both X and Y
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    model_X = LinearRegression().fit(Z_data, X_data)
                    model_Y = LinearRegression().fit(Z_data, Y_data)
                
                resid_X = X_data - model_X.predict(Z_data)
                resid_Y = Y_data - model_Y.predict(Z_data)
                
                # Test independence of residuals
                _, p_value = pearsonr(resid_X.flatten(), resid_Y.flatten())
                
                return p_value > self.alpha
                
            except Exception:
                # If test fails, assume dependent (conservative)
                return False
        
        # Option 2: HSIC with Gaussian kernel (nonlinear)
        if self.independence_test == 'hsic':
            try:
                x = self.data[X].values.reshape(-1, 1)
                y = self.data[Y].values.reshape(-1, 1)
                
                if len(Z) > 0:
                    Z_data = self.data[Z].values
                    # Residualize X and Y on Z using chosen model
                    if self.residual_model == 'random_forest':
                        model_X = RandomForestRegressor(n_estimators=200, random_state=self.random_state)
                        model_Y = RandomForestRegressor(n_estimators=200, random_state=self.random_state)
                    else:
                        model_X = LinearRegression()
                        model_Y = LinearRegression()
                    
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        model_X.fit(Z_data, x.ravel())
                        model_Y.fit(Z_data, y.ravel())
                    rx = x.ravel() - model_X.predict(Z_data)
                    ry = y.ravel() - model_Y.predict(Z_data)
                    x_test = rx.reshape(-1, 1)
                    y_test = ry.reshape(-1, 1)
                else:
                    x_test = x
                    y_test = y
                
                p_value = self._hsic_p_value(x_test, y_test,
                                             num_permutations=self.hsic_num_permutations,
                                             sigma=self.hsic_sigma,
                                             random_state=self.random_state)
                return p_value > self.alpha
            except Exception:
                return False
        
        # Unknown test option → fallback conservative
        return False

    # ---------- HSIC utilities ----------
    def _gaussian_kernel(self, X: np.ndarray, sigma: Optional[float]) -> np.ndarray:
        """Compute Gaussian RBF kernel Gram matrix."""
        # Pairwise squared Euclidean distances
        XX = np.sum(X**2, axis=1).reshape(-1, 1)
        distances = XX + XX.T - 2 * (X @ X.T)
        # Median heuristic for sigma if not provided
        if sigma is None:
            # Avoid zeros on diagonal by adding large number mask
            tri = distances[np.triu_indices_from(distances, k=1)]
            med = np.median(tri) if tri.size > 0 else 1.0
            sigma = np.sqrt(0.5 * med) if med > 1e-12 else 1.0
        K = np.exp(-distances / (2 * sigma**2))
        return K

    def _center_gram(self, K: np.ndarray) -> np.ndarray:
        n = K.shape[0]
        H = np.eye(n) - np.ones((n, n)) / n
        return H @ K @ H

    def _hsic_stat(self, X: np.ndarray, Y: np.ndarray, sigma: Optional[float]) -> float:
        K = self._center_gram(self._gaussian_kernel(X, sigma))
        L = self._center_gram(self._gaussian_kernel(Y, sigma))
        n = K.shape[0]
        return (1.0 / (n - 1) ** 2) * np.trace(K @ L)

    def _hsic_p_value(self, X: np.ndarray, Y: np.ndarray,
                      num_permutations: int = 100,
                      sigma: Optional[float] = None,
                      random_state: Optional[int] = None) -> float:
        """Permutation test p-value for HSIC."""
        rng = np.random.default_rng(random_state)
        stat = self._hsic_stat(X, Y, sigma)
        count = 1  # add-one smoothing
        for _ in range(max(1, num_permutations)):
            perm = rng.permutation(Y.shape[0])
            stat_perm = self._hsic_stat(X, Y[perm], sigma)
            if stat_perm >= stat:
                count += 1
        return count / (num_permutations + 1)
    
    def _orient_edges(self, skeleton: Set[Tuple[str, str]], 
                     variables: List[str]) -> CausalGraph:
        """
        Phase 2: Orient edges using collider detection and propagation rules.
        
        Args:
            skeleton: Set of undirected edges from Phase 1
            variables: List of variable names
        
        Returns:
            CausalGraph with oriented (directed) edges
        """
        graph = CausalGraph()
        
        # Add all nodes
        for v in variables:
            graph.add_node(v)
        
        # Initially add all edges as bidirected (both directions)
        for (X, Y) in skeleton:
            graph.add_edge(X, Y, strength=1.0, confidence=0.8)
            graph.add_edge(Y, X, strength=1.0, confidence=0.8)
        
        # Step 1: Orient colliders (v-structures): X → Z ← Y
        n_colliders = self._orient_colliders(graph, skeleton, variables)
        print(f"     Oriented {n_colliders} colliders (v-structures)")
        
        # Step 2: Apply Meek's rules to orient more edges
        n_meek = self._apply_meek_rules(graph)
        print(f"     Applied Meek's rules: oriented {n_meek} additional edges")
        
        return graph
    
    def _orient_colliders(self, graph: CausalGraph, 
                         skeleton: Set[Tuple[str, str]], 
                         variables: List[str]) -> int:
        """
        Detect and orient colliders (v-structures): X → Z ← Y.
        
        A collider exists when:
        - X and Y are both adjacent to Z (edges X-Z and Y-Z exist)
        - X and Y are NOT adjacent (no edge X-Y)
        - Z is NOT in the separating set of X and Y
        
        Then we orient as X → Z ← Y.
        
        Returns:
            Number of colliders oriented
        """
        n_oriented = 0
        
        for Z in variables:
            # Find all variables adjacent to Z
            neighbors = []
            for (A, B) in skeleton:
                if A == Z:
                    neighbors.append(B)
                elif B == Z:
                    neighbors.append(A)
            
            # Check all pairs of neighbors
            for i, X in enumerate(neighbors):
                for Y in neighbors[i+1:]:
                    # Check if X and Y are not adjacent
                    if (X, Y) not in skeleton and (Y, X) not in skeleton:
                        # Check if Z is NOT in the separating set of X and Y
                        sep_set = self.separation_sets.get((X, Y), [])
                        
                        if Z not in sep_set:
                            # We have a collider: X → Z ← Y
                            # Orient by removing the reverse edges
                            if graph.graph.has_edge(Z, X):
                                graph.remove_edge(Z, X)
                            if graph.graph.has_edge(Z, Y):
                                graph.remove_edge(Z, Y)
                            n_oriented += 1
        
        return n_oriented
    
    def _apply_meek_rules(self, graph: CausalGraph) -> int:
        """
        Apply Meek's orientation rules to orient more edges.
        
        These rules propagate orientations while avoiding new colliders or cycles.
        
        Rule 1: If X → Y - Z and X and Z not adjacent, then Y → Z
        Rule 2: If X → Y → Z and X - Z, then X → Z
        Rule 3: More complex patterns...
        
        Returns:
            Number of edges oriented
        """
        n_oriented = 0
        changed = True
        
        while changed:
            changed = False
            
            # Rule 1: Orient X-Y into X→Y whenever there is Z→X and Z,Y not adjacent
            for node in list(graph.graph.nodes()):
                # Check if this node has any undirected edges
                for neighbor in list(graph.graph.neighbors(node)):
                    # Check if edge is undirected (exists in both directions)
                    if graph.graph.has_edge(neighbor, node):
                        # This is an undirected edge node-neighbor
                        
                        # Look for directed edges pointing to node
                        for parent in list(graph.graph.predecessors(node)):
                            if not graph.graph.has_edge(node, parent):  # Directed edge
                                # Check if parent and neighbor are not adjacent
                                if not graph.graph.has_edge(parent, neighbor) and \
                                   not graph.graph.has_edge(neighbor, parent):
                                    # Orient: remove neighbor → node, keep node → neighbor
                                    graph.remove_edge(neighbor, node)
                                    changed = True
                                    n_oriented += 1
        
        return n_oriented
    
    def _get_adjacents(self, X: str, Y: str, edges: Set[Tuple[str, str]], 
                      variables: List[str]) -> List[str]:
        """
        Get variables adjacent to both X or Y (but not X or Y themselves).
        
        Args:
            X: First variable
            Y: Second variable
            edges: Current set of edges
            variables: All variables
        
        Returns:
            List of adjacent variables
        """
        adj = set()
        
        # Find all variables connected to X or Y
        for (A, B) in edges:
            if A == X or A == Y:
                adj.add(B)
            if B == X or B == Y:
                adj.add(A)
        
        # Remove X and Y themselves
        adj.discard(X)
        adj.discard(Y)
        
        return list(adj)

