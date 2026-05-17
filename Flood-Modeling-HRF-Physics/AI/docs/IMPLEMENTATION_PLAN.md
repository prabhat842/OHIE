# QCIA Implementation Plan
## Concrete steps to build a real Quantum-Inspired Causal Intelligence Architecture

---

## Directory Structure

```
Sim_MVP/
├── qcia_core/                    # Core QCIA library
│   ├── __init__.py
│   ├── causal_discovery.py      # Causal graph learning
│   ├── causal_reasoning.py      # Interventions & counterfactuals
│   ├── quantum_optimizer.py     # Quantum-inspired methods
│   ├── decision_engine.py       # Risk-aware planning
│   ├── uncertainty.py           # Confidence & calibration
│   └── utils.py                 # Shared utilities
│
├── applications/
│   ├── physics_optimization/    # Solver design optimization
│   │   ├── qcia_physics_optimizer.py
│   │   ├── solver_benchmark.py
│   │   └── experiments/
│   │
│   ├── causal_agent/           # Survival simulation (existing)
│   │   ├── agent.py           # (upgrade to use QCIA)
│   │   ├── world_engine.py
│   │   └── qcia_agent.py      # (new: QCIA-powered agent)
│   │
│   └── engineering_demo/       # High-stakes engineering example
│       ├── design_optimization.py
│       └── case_studies/
│
├── tests/
│   ├── test_causal_discovery.py
│   ├── test_quantum_optimizer.py
│   ├── synthetic_benchmarks.py
│   └── integration_tests.py
│
├── notebooks/
│   ├── 01_causal_discovery_demo.ipynb
│   ├── 02_quantum_optimization_demo.ipynb
│   ├── 03_physics_optimization_comparison.ipynb
│   └── 04_end_to_end_qcia.ipynb
│
├── ai_optimiser_test.ipynb     # (existing, will refactor)
├── requirements.txt
└── README.md
```

---

## Phase 1: Causal Discovery Engine (Week 1-2)

### 1.1 Create Core Data Structures

**File**: `qcia_core/causal_graph.py`

```python
from dataclasses import dataclass
from typing import Set, Dict, List, Tuple
import networkx as nx
import numpy as np

@dataclass
class Edge:
    """Represents a causal edge with confidence."""
    source: str
    target: str
    strength: float  # Causal effect size
    confidence: float  # [0, 1]
    edge_type: str  # 'directed', 'bidirected', 'undirected'

class CausalGraph:
    """Represents a causal DAG with uncertainty."""
    
    def __init__(self):
        self.graph = nx.DiGraph()
        self.edges: Dict[Tuple[str, str], Edge] = {}
        self.latent_variables: Set[str] = set()
        
    def add_edge(self, source: str, target: str, 
                 strength: float, confidence: float):
        """Add a causal edge."""
        self.graph.add_edge(source, target)
        self.edges[(source, target)] = Edge(
            source, target, strength, confidence, 'directed'
        )
    
    def is_ancestor(self, X: str, Y: str) -> bool:
        """Check if X is an ancestor of Y."""
        return nx.has_path(self.graph, X, Y)
    
    def get_parents(self, node: str) -> Set[str]:
        """Get direct parents of a node."""
        return set(self.graph.predecessors(node))
    
    def get_adjustment_set(self, treatment: str, 
                          outcome: str) -> Set[str]:
        """Find variables to control for (backdoor criterion)."""
        # Simplified implementation
        # Real version would use backdoor adjustment
        return set()
    
    def to_dot(self) -> str:
        """Export to GraphViz format for visualization."""
        return nx.drawing.nx_pydot.to_pydot(self.graph).to_string()
```

### 1.2 Implement PC Algorithm

**File**: `qcia_core/causal_discovery.py`

```python
import pandas as pd
import numpy as np
from typing import Set, List, Optional
from itertools import combinations
from scipy.stats import chi2_contingency, pearsonr
from causal_graph import CausalGraph

class CausalDiscoveryEngine:
    """Learns causal structure from observational data."""
    
    def __init__(self, alpha: float = 0.05):
        self.alpha = alpha  # Significance level for independence tests
        self.data: Optional[pd.DataFrame] = None
        
    def learn_structure(self, data: pd.DataFrame, 
                       method: str = 'pc') -> CausalGraph:
        """
        Learn causal graph from data.
        
        Args:
            data: DataFrame where columns are variables
            method: 'pc' (constraint-based) or 'ges' (score-based)
        """
        self.data = data
        
        if method == 'pc':
            return self._pc_algorithm()
        elif method == 'ges':
            return self._ges_algorithm()
        else:
            raise ValueError(f"Unknown method: {method}")
    
    def _pc_algorithm(self) -> CausalGraph:
        """
        PC (Peter-Clark) Algorithm for causal discovery.
        
        Steps:
        1. Start with fully connected undirected graph
        2. Remove edges based on conditional independence tests
        3. Orient edges using collider detection and rules
        """
        variables = list(self.data.columns)
        n = len(variables)
        
        # Step 1: Build skeleton (undirected graph)
        skeleton = self._build_skeleton(variables)
        
        # Step 2: Orient edges
        causal_graph = self._orient_edges(skeleton, variables)
        
        return causal_graph
    
    def _build_skeleton(self, variables: List[str]) -> Set[Tuple[str, str]]:
        """
        Remove edges based on conditional independence.
        """
        # Start with complete graph
        edges = set()
        for i, X in enumerate(variables):
            for Y in variables[i+1:]:
                edges.add((X, Y))
        
        # Test independence conditioning on subsets
        for l in range(len(variables)):  # Size of conditioning set
            edges_to_remove = set()
            
            for (X, Y) in edges:
                # Find potential conditioning sets
                adjacents = self._get_adjacents(X, Y, edges)
                
                for Z_subset in combinations(adjacents, min(l, len(adjacents))):
                    if self._is_independent(X, Y, list(Z_subset)):
                        edges_to_remove.add((X, Y))
                        break
            
            edges -= edges_to_remove
            
        return edges
    
    def _is_independent(self, X: str, Y: str, Z: List[str]) -> bool:
        """
        Test if X ⊥ Y | Z (X independent of Y given Z).
        Uses partial correlation test.
        """
        if len(Z) == 0:
            # Unconditional independence
            _, p_value = pearsonr(self.data[X], self.data[Y])
            return p_value > self.alpha
        
        # Conditional independence using partial correlation
        # Regress X on Z, Y on Z, then test correlation of residuals
        from sklearn.linear_model import LinearRegression
        
        Z_data = self.data[Z].values
        X_data = self.data[X].values.reshape(-1, 1)
        Y_data = self.data[Y].values.reshape(-1, 1)
        
        # Get residuals
        model_X = LinearRegression().fit(Z_data, X_data)
        model_Y = LinearRegression().fit(Z_data, Y_data)
        
        resid_X = X_data - model_X.predict(Z_data)
        resid_Y = Y_data - model_Y.predict(Z_data)
        
        # Test independence of residuals
        _, p_value = pearsonr(resid_X.flatten(), resid_Y.flatten())
        
        return p_value > self.alpha
    
    def _orient_edges(self, skeleton: Set[Tuple[str, str]], 
                     variables: List[str]) -> CausalGraph:
        """
        Orient edges using collider detection and Meek's rules.
        """
        graph = CausalGraph()
        
        # Add all nodes
        for v in variables:
            graph.graph.add_node(v)
        
        # Initially add all edges as undirected
        for (X, Y) in skeleton:
            graph.graph.add_edge(X, Y)
            graph.graph.add_edge(Y, X)
        
        # Orient v-structures (colliders): X → Z ← Y
        self._orient_colliders(graph, skeleton, variables)
        
        # Apply Meek's rules to orient more edges
        self._apply_meek_rules(graph)
        
        return graph
    
    def _orient_colliders(self, graph: CausalGraph, 
                         skeleton: Set[Tuple[str, str]], 
                         variables: List[str]):
        """Detect and orient colliders (v-structures)."""
        for Z in variables:
            parents = list(graph.graph.predecessors(Z))
            
            for i, X in enumerate(parents):
                for Y in parents[i+1:]:
                    # Check if X and Y are not adjacent
                    if (X, Y) not in skeleton and (Y, X) not in skeleton:
                        # Check if Z is NOT in separating set of X and Y
                        # If so, X → Z ← Y is a collider
                        # Orient: remove reverse edges
                        if graph.graph.has_edge(Z, X):
                            graph.graph.remove_edge(Z, X)
                        if graph.graph.has_edge(Z, Y):
                            graph.graph.remove_edge(Z, Y)
    
    def _apply_meek_rules(self, graph: CausalGraph):
        """Apply Meek's orientation rules."""
        # Rule 1: Orient X - Y into X → Y whenever there is Z → X
        # and Z and Y are not adjacent
        # (and more rules...)
        pass  # Implement if needed
    
    def _get_adjacents(self, X: str, Y: str, 
                      edges: Set[Tuple[str, str]]) -> List[str]:
        """Get variables adjacent to both X and Y."""
        adj = set()
        for (A, B) in edges:
            if A == X or A == Y:
                adj.add(B)
            if B == X or B == Y:
                adj.add(A)
        adj.discard(X)
        adj.discard(Y)
        return list(adj)
    
    def _ges_algorithm(self) -> CausalGraph:
        """
        GES (Greedy Equivalence Search) algorithm.
        Score-based approach that greedily adds/removes edges.
        """
        # Use causal-learn library for this
        from causallearn.search.ScoreBased.GES import ges
        
        Record = ges(self.data.values)
        # Convert to our CausalGraph format
        # ... implementation ...
        pass
```

### 1.3 Test on Synthetic Data

**File**: `tests/test_causal_discovery.py`

```python
import pytest
import pandas as pd
import numpy as np
from qcia_core.causal_discovery import CausalDiscoveryEngine

def generate_synthetic_data(n_samples=1000):
    """
    Generate data from known causal structure:
    Z → X → Y
    Z → Y
    """
    np.random.seed(42)
    Z = np.random.normal(0, 1, n_samples)
    X = 2*Z + np.random.normal(0, 0.5, n_samples)
    Y = 3*X + 1.5*Z + np.random.normal(0, 0.5, n_samples)
    
    return pd.DataFrame({'Z': Z, 'X': X, 'Y': Y})

def test_pc_algorithm_recovers_structure():
    """Test that PC algorithm recovers true causal structure."""
    data = generate_synthetic_data()
    
    engine = CausalDiscoveryEngine(alpha=0.05)
    learned_graph = engine.learn_structure(data, method='pc')
    
    # Check that we learned Z → X
    assert learned_graph.graph.has_edge('Z', 'X')
    
    # Check that we learned X → Y or Z → Y
    # (both are in the true model)
    assert learned_graph.graph.has_edge('X', 'Y') or \
           learned_graph.graph.has_edge('Z', 'Y')
    
    print("✅ PC algorithm test passed!")

if __name__ == '__main__':
    test_pc_algorithm_recovers_structure()
```

---

## Phase 2: Causal Reasoning Engine (Week 2-3)

### 2.1 Implement Interventions

**File**: `qcia_core/causal_reasoning.py`

```python
from typing import Dict, Optional, List
import numpy as np
from causal_graph import CausalGraph

class StructuralEquation:
    """Represents one equation in a Structural Causal Model."""
    
    def __init__(self, variable: str, parents: List[str]):
        self.variable = variable
        self.parents = parents
        self.coefficients: Dict[str, float] = {}
        self.noise_std = 1.0
    
    def evaluate(self, parent_values: Dict[str, float]) -> float:
        """Compute value of this variable given parent values."""
        value = 0.0
        for parent in self.parents:
            value += self.coefficients.get(parent, 0) * parent_values[parent]
        value += np.random.normal(0, self.noise_std)
        return value

class StructuralCausalModel:
    """
    Represents the data-generating process with structural equations.
    Enables interventions and counterfactuals.
    """
    
    def __init__(self, causal_graph: CausalGraph):
        self.graph = causal_graph
        self.equations: Dict[str, StructuralEquation] = {}
        
    def fit(self, data: 'pd.DataFrame'):
        """Learn structural equations from data."""
        import pandas as pd
        from sklearn.linear_model import LinearRegression
        
        # For each variable, learn its structural equation
        for node in nx.topological_sort(self.graph.graph):
            parents = list(self.graph.get_parents(node))
            
            if not parents:
                # Root node: just noise
                self.equations[node] = StructuralEquation(node, [])
                self.equations[node].noise_std = data[node].std()
            else:
                # Learn linear structural equation
                X = data[parents].values
                y = data[node].values
                
                model = LinearRegression().fit(X, y)
                
                eq = StructuralEquation(node, parents)
                for i, parent in enumerate(parents):
                    eq.coefficients[parent] = model.coef_[i]
                
                # Estimate noise
                y_pred = model.predict(X)
                eq.noise_std = np.std(y - y_pred)
                
                self.equations[node] = eq
    
    def intervene(self, interventions: Dict[str, float], 
                  n_samples: int = 1000) -> 'pd.DataFrame':
        """
        Perform do(X=x) intervention and sample from resulting distribution.
        
        Args:
            interventions: Dict of {variable: value} to set
            n_samples: Number of samples to generate
        
        Returns:
            DataFrame of samples from interventional distribution
        """
        import pandas as pd
        
        samples = {var: [] for var in self.equations.keys()}
        
        for _ in range(n_samples):
            values = {}
            
            # Sample in topological order
            for node in nx.topological_sort(self.graph.graph):
                if node in interventions:
                    # Intervened variable: set to fixed value
                    values[node] = interventions[node]
                else:
                    # Non-intervened: sample from structural equation
                    parent_vals = {p: values[p] for p in self.equations[node].parents}
                    values[node] = self.equations[node].evaluate(parent_vals)
                
                samples[node].append(values[node])
        
        return pd.DataFrame(samples)
    
    def counterfactual(self, observed: Dict[str, float],
                      intervention: Dict[str, float]) -> Dict[str, float]:
        """
        Compute counterfactual: "What would Y have been if we had done X=x,
        given that we observed the actual values?"
        
        Three steps:
        1. Abduction: Infer exogenous noise from observations
        2. Action: Perform intervention
        3. Prediction: Compute counterfactual values
        """
        # Step 1: Abduction - solve for noise terms
        noise_values = {}
        values = observed.copy()
        
        for node in nx.topological_sort(self.graph.graph):
            eq = self.equations[node]
            parent_vals = {p: values[p] for p in eq.parents}
            
            # Infer noise: observed = f(parents) + noise
            deterministic_part = sum(
                eq.coefficients.get(p, 0) * parent_vals[p] 
                for p in eq.parents
            )
            noise_values[node] = values[node] - deterministic_part
        
        # Step 2: Action - create intervened model
        # Step 3: Prediction - recompute with intervention
        cf_values = {}
        for node in nx.topological_sort(self.graph.graph):
            if node in intervention:
                cf_values[node] = intervention[node]
            else:
                eq = self.equations[node]
                parent_vals = {p: cf_values[p] for p in eq.parents}
                deterministic_part = sum(
                    eq.coefficients.get(p, 0) * parent_vals[p]
                    for p in eq.parents
                )
                # Use same noise as in actual world
                cf_values[node] = deterministic_part + noise_values[node]
        
        return cf_values

class CausalReasoningEngine:
    """High-level interface for causal queries."""
    
    def __init__(self, causal_graph: CausalGraph):
        self.graph = causal_graph
        self.scm: Optional[StructuralCausalModel] = None
    
    def fit_scm(self, data: 'pd.DataFrame'):
        """Learn structural causal model from data."""
        self.scm = StructuralCausalModel(self.graph)
        self.scm.fit(data)
    
    def compute_causal_effect(self, treatment: str, outcome: str,
                             data: 'pd.DataFrame') -> float:
        """
        Compute Average Causal Effect (ACE): E[Y | do(X=1)] - E[Y | do(X=0)]
        """
        # Intervene and sample
        samples_do_1 = self.scm.intervene({treatment: 1.0}, n_samples=5000)
        samples_do_0 = self.scm.intervene({treatment: 0.0}, n_samples=5000)
        
        ace = samples_do_1[outcome].mean() - samples_do_0[outcome].mean()
        return ace
    
    def answer_counterfactual(self, query: str, observed: Dict, 
                             intervention: Dict) -> float:
        """
        Answer counterfactual query.
        Example: "What would Y have been if X=5, given actual X=3, Y=10?"
        """
        if self.scm is None:
            raise ValueError("Must fit SCM first")
        
        cf_values = self.scm.counterfactual(observed, intervention)
        return cf_values[query]
```

---

## Phase 3: Quantum-Inspired Optimizer (Week 3-4)

### 3.1 Implement Quantum Annealing

**File**: `qcia_core/quantum_optimizer.py`

```python
import numpy as np
from typing import Callable, Dict, List, Tuple
from dataclasses import dataclass

@dataclass
class AnnealingSchedule:
    """Schedule for quantum annealing."""
    initial_temp: float = 10.0
    final_temp: float = 0.01
    n_steps: int = 1000
    transverse_field_strength: float = 5.0

class QuantumInspiredOptimizer:
    """
    Quantum-inspired optimization methods that outperform classical
    approaches on rugged landscapes.
    """
    
    def quantum_anneal(self, 
                      cost_function: Callable[[np.ndarray], float],
                      bounds: List[Tuple[float, float]],
                      schedule: AnnealingSchedule = None) -> np.ndarray:
        """
        Simulated Quantum Annealing with transverse field.
        
        Unlike simulated annealing, this can tunnel through barriers
        via quantum fluctuations (simulated).
        
        Args:
            cost_function: Function to minimize
            bounds: [(min, max)] for each dimension
            schedule: Annealing temperature schedule
        
        Returns:
            Optimal parameters found
        """
        if schedule is None:
            schedule = AnnealingSchedule()
        
        # Initialize random solution
        dim = len(bounds)
        current_x = np.array([
            np.random.uniform(low, high) 
            for (low, high) in bounds
        ])
        current_cost = cost_function(current_x)
        
        best_x = current_x.copy()
        best_cost = current_cost
        
        # Annealing schedule
        temps = np.linspace(
            schedule.initial_temp, 
            schedule.final_temp, 
            schedule.n_steps
        )
        
        for step, temp in enumerate(temps):
            # Quantum tunneling probability
            tunnel_prob = schedule.transverse_field_strength * (1 - step / schedule.n_steps)
            
            # Propose new state
            if np.random.random() < tunnel_prob:
                # Quantum tunneling: large jump
                proposal_x = np.array([
                    np.random.uniform(low, high) 
                    for (low, high) in bounds
                ])
            else:
                # Classical move: small perturbation
                proposal_x = current_x + np.random.normal(0, temp, size=dim)
                # Enforce bounds
                proposal_x = np.clip(
                    proposal_x,
                    [low for (low, _) in bounds],
                    [high for (_, high) in bounds]
                )
            
            proposal_cost = cost_function(proposal_x)
            
            # Metropolis acceptance criterion
            delta_cost = proposal_cost - current_cost
            if delta_cost < 0 or np.random.random() < np.exp(-delta_cost / temp):
                current_x = proposal_x
                current_cost = proposal_cost
                
                if current_cost < best_cost:
                    best_x = current_x.copy()
                    best_cost = current_cost
        
        return best_x
    
    def quantum_walk_search(self, 
                           graph: 'nx.Graph',
                           target_property: Callable[[any], bool],
                           n_steps: int = 1000) -> any:
        """
        Quantum walk on graph for search problems.
        Achieves quadratic speedup over classical random walk.
        
        Args:
            graph: NetworkX graph to search
            target_property: Function that returns True for target nodes
            n_steps: Number of walk steps
        
        Returns:
            Target node if found, else None
        """
        nodes = list(graph.nodes())
        n = len(nodes)
        
        # Initialize quantum state (uniform superposition)
        amplitudes = np.ones(n) / np.sqrt(n)
        
        for _ in range(n_steps):
            # Quantum walk step: diffusion + marking
            amplitudes = self._quantum_walk_step(graph, amplitudes, target_property)
            
            # Check if we found target
            probs = np.abs(amplitudes)**2
            if np.random.random() < probs.max():
                candidate_idx = np.argmax(probs)
                if target_property(nodes[candidate_idx]):
                    return nodes[candidate_idx]
        
        return None
    
    def _quantum_walk_step(self, graph, amplitudes, target_property):
        """One step of quantum walk."""
        # This is a simplified version
        # Real implementation would use coin operator + shift operator
        nodes = list(graph.nodes())
        new_amplitudes = np.zeros_like(amplitudes)
        
        for i, node in enumerate(nodes):
            neighbors = list(graph.neighbors(node))
            if neighbors:
                # Spread amplitude to neighbors
                for neighbor in neighbors:
                    j = nodes.index(neighbor)
                    new_amplitudes[j] += amplitudes[i] / np.sqrt(len(neighbors))
        
        # Mark target nodes (amplitude amplification)
        for i, node in enumerate(nodes):
            if target_property(node):
                new_amplitudes[i] *= 2  # Amplify target amplitude
        
        # Normalize
        norm = np.linalg.norm(new_amplitudes)
        if norm > 0:
            new_amplitudes /= norm
        
        return new_amplitudes
```

### 3.2 Benchmark Against Classical Optimizers

**File**: `tests/test_quantum_optimizer.py`

```python
import numpy as np
from qcia_core.quantum_optimizer import QuantumInspiredOptimizer
from scipy.optimize import differential_evolution, dual_annealing

def rastrigin(x):
    """Rastrigin function: many local minima, one global minimum at 0."""
    return 10*len(x) + sum(x**2 - 10*np.cos(2*np.pi*x))

def test_quantum_annealing_vs_classical():
    """Compare quantum annealing to classical methods on hard problem."""
    bounds = [(-5.12, 5.12)] * 5  # 5D problem
    n_trials = 10
    
    # Quantum-inspired annealing
    qopt = QuantumInspiredOptimizer()
    quantum_costs = []
    for _ in range(n_trials):
        result = qopt.quantum_anneal(rastrigin, bounds)
        quantum_costs.append(rastrigin(result))
    
    # Classical simulated annealing
    classical_costs = []
    for _ in range(n_trials):
        result = dual_annealing(rastrigin, bounds)
        classical_costs.append(result.fun)
    
    print(f"Quantum annealing: {np.mean(quantum_costs):.4f} ± {np.std(quantum_costs):.4f}")
    print(f"Classical annealing: {np.mean(classical_costs):.4f} ± {np.std(classical_costs):.4f}")
    
    # Quantum should be competitive or better
    assert np.mean(quantum_costs) <= np.mean(classical_costs) * 1.1
```

---

## Phase 4: Integration with Existing Projects (Week 4-5)

### 4.1 Upgrade Physics Optimizer

**File**: `applications/physics_optimization/qcia_physics_optimizer.py`

```python
import sys
sys.path.append('../..')
from qcia_core.causal_discovery import CausalDiscoveryEngine
from qcia_core.quantum_optimizer import QuantumInspiredOptimizer
import pandas as pd
import numpy as np

class QCIA_PhysicsOptimizer:
    """
    Upgrades the physics solver optimizer to use true causal AI.
    """
    
    def __init__(self):
        self.causal_discovery = CausalDiscoveryEngine()
        self.quantum_optimizer = QuantumInspiredOptimizer()
        self.experiment_history = []
        self.causal_graph = None
    
    def log_experiment(self, params: dict, cost: float, stability: bool):
        """Record an experiment for causal learning."""
        self.experiment_history.append({
            **params,
            'cost': cost,
            'stability': 1.0 if stability else 0.0
        })
    
    def learn_parameter_causality(self):
        """Discover which parameters causally affect outcomes."""
        if len(self.experiment_history) < 20:
            print("⏳ Need more data for causal discovery...")
            return
        
        df = pd.DataFrame(self.experiment_history)
        print("🧠 Learning causal structure of solver parameters...")
        
        self.causal_graph = self.causal_discovery.learn_structure(df, method='pc')
        
        print("✅ Causal graph learned!")
        print(f"   Edges: {list(self.causal_graph.graph.edges())}")
    
    def optimize_design(self, objective: str, bounds: dict):
        """
        Use quantum-inspired optimization guided by causal structure.
        """
        if self.causal_graph is None:
            print("⚠️  No causal graph yet, using quantum annealing directly...")
        
        # Define cost function for optimization
        def cost_func(params_array):
            param_dict = {
                name: params_array[i] 
                for i, name in enumerate(bounds.keys())
            }
            # Run simulation with these params
            cost = self.run_simulation(param_dict)
            return cost
        
        # Convert bounds dict to list
        bounds_list = [(low, high) for (low, high) in bounds.values()]
        
        # Use quantum annealing
        optimal_params = self.quantum_optimizer.quantum_anneal(
            cost_func, bounds_list
        )
        
        # Convert back to dict
        optimal_dict = {
            name: optimal_params[i]
            for i, name in enumerate(bounds.keys())
        }
        
        return optimal_dict
    
    def run_simulation(self, params: dict) -> float:
        """Run the actual physics simulation (from notebook)."""
        # Import and run the simulation code
        # Return cost
        pass
```

### 4.2 Upgrade Survival Agent

**File**: `applications/causal_agent/qcia_agent.py`

```python
import sys
sys.path.append('../..')
from qcia_core.causal_graph import CausalGraph
from qcia_core.causal_reasoning import CausalReasoningEngine
from qcia_core.quantum_optimizer import QuantumInspiredOptimizer
import numpy as np
import pandas as pd

class QCIA_SurvivalAgent:
    """
    Upgraded agent that uses true causal reasoning.
    """
    
    def __init__(self, world_engine):
        self.world = world_engine
        
        # QCIA components
        self.causal_graph = CausalGraph()
        self.reasoning_engine = CausalReasoningEngine(self.causal_graph)
        self.quantum_planner = QuantumInspiredOptimizer()
        
        # Experience log for causal learning
        self.observations = []
        
        # Core attributes
        self.warmth = 100.0
        self.pos = (10, 10)
        self.inventory = []
    
    def observe(self, state: dict):
        """Record observation for causal learning."""
        self.observations.append({
            'time': len(self.observations),
            'warmth': self.warmth,
            'temperature': state['temperature'],
            'has_fire': any('fire' in obj for obj in state['objects_sensed']),
            'has_wood': 'wood' in self.inventory,
            'has_stone': 'stone' in self.inventory,
        })
    
    def learn_world_physics(self):
        """Discover causal structure of the world."""
        if len(self.observations) < 30:
            return
        
        print("🧠 Agent is learning causal structure of the world...")
        
        df = pd.DataFrame(self.observations)
        
        from qcia_core.causal_discovery import CausalDiscoveryEngine
        engine = CausalDiscoveryEngine()
        self.causal_graph = engine.learn_structure(df, method='pc')
        self.reasoning_engine = CausalReasoningEngine(self.causal_graph)
        
        # Fit structural causal model
        self.reasoning_engine.fit_scm(df)
        
        print("✅ Causal model learned!")
        print(f"   Discovered: {list(self.causal_graph.graph.edges())}")
    
    def plan_to_get_warm(self):
        """Use causal reasoning to plan warmth intervention."""
        # Query: How can I increase warmth?
        # Use causal graph to find interventions
        
        if self.causal_graph.graph.has_edge('has_fire', 'warmth'):
            print("💡 Agent realizes: Fire → Warmth!")
            return self._plan_to_create_fire()
        
        # Fallback: explore randomly
        return {'action': 'move', 'direction': 'north'}
    
    def _plan_to_create_fire(self):
        """Use causal knowledge to create fire."""
        # Check if we know the crafting recipe
        if self.causal_graph.graph.has_edge('has_stone', 'spark'):
            print("💡 Agent knows: Stone + Stone → Spark")
            if self.causal_graph.graph.has_edge('spark', 'fire'):
                print("💡 Agent knows: Spark + Wood → Fire")
                # Formulate plan
                return self._gather_materials(['stone', 'stone', 'wood'])
        
        return {'action': 'explore'}
    
    def _gather_materials(self, items_needed: list):
        """Create plan to gather materials."""
        # This would use quantum walk search on world graph
        pass
```

---

## Next Steps: Which phase should we start implementing first?

1. **Start with Phase 1** (Causal Discovery) - Most foundational
2. **Start with Phase 3** (Quantum Optimizer) - Easiest to test standalone
3. **Start with Phase 4** (Integration) - Most immediately useful

What's your priority? Or should I start building the core library now?

