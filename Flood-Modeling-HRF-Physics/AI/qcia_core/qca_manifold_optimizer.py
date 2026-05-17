#!/usr/bin/env python3
"""
QCA Manifold Optimizer - Geometric Causal Engine
=================================================
Adapted from Project Chimera V17 (opt.py.bak)

This implements quantum-inspired causal learning on a manifold:
1. Encode flood states as quantum superpositions
2. Learn causal manifold via Isomap (non-linear dimensionality reduction)
3. Plan intervention sequences via Dijkstra on causal graph

Key Insight: Intervention effectiveness is NOT linear in parameter space.
The manifold captures this non-linearity and enables discovery of synergies.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from sklearn.manifold import Isomap
from scipy.spatial.distance import pdist, squareform
from scipy.sparse.csgraph import dijkstra
import json


@dataclass
class QuantumState:
    """
    Quantum-inspired encoding of flood state.
    Amplitudes represent probability of different flood severity regimes.
    """
    amplitudes: np.ndarray  # Shape: (n_hypotheses,)
    hypotheses: List[str]
    
    def __repr__(self):
        return " + ".join([
            f"({amp:.2f} | \"{hyp}\")" 
            for amp, hyp in zip(self.amplitudes, self.hypotheses)
        ])
    
    def dominant_hypothesis(self) -> str:
        """Return hypothesis with highest amplitude."""
        return self.hypotheses[np.argmax(self.amplitudes)]


@dataclass
class Experience:
    """
    A single intervention experience: (state_before, action, state_after, reward).
    This is the fundamental unit of learning in the QCA engine.
    """
    state_before: QuantumState
    action: Dict[str, Any]  # e.g., {'type': 'pump_medium', 'location': (50, 30), 'size': 3.0}
    state_after: QuantumState
    reward: float = 0.0  # Flood reduction (positive = good)
    
    metadata: Dict[str, Any] = field(default_factory=dict)  # Cost, site conditions, etc.


class GeometricCausalEngine:
    """
    Learns the manifold structure of causality in flood intervention space.
    
    Uses Isomap to embed high-dimensional (state_before, state_after) vectors
    into a low-dimensional manifold where causal distances are preserved.
    
    This enables:
    1. Finding similar past experiences (nearest neighbors on manifold)
    2. Planning intervention sequences (paths on manifold)
    3. Discovering synergies (clusters on manifold)
    4. PRUNING low-reward regions (stop exploring failures)
    """
    
    def __init__(self, manifold_dim: int = 3, n_neighbors: int = 5):
        """
        Args:
            manifold_dim: Dimension of learned causal manifold (3D for visualization)
            n_neighbors: Isomap neighborhood size (affects manifold smoothness)
        """
        self.manifold_dim = manifold_dim
        self.n_neighbors = n_neighbors
        
        self.experiences: List[Experience] = []
        self.manifold_coordinates: Optional[np.ndarray] = None
        self.isomap = Isomap(n_components=self.manifold_dim, n_neighbors=self.n_neighbors)
        self.manifold_is_stale = True
        
        # PRUNING: Track low-reward zones to avoid re-exploring
        self.pruned_zones: List[Dict] = []  # List of {center, radius, reason}
        self.min_zone_samples = 3  # Minimum experiences before pruning a zone
    
    def _get_transition_vectors(self) -> np.ndarray:
        """
        Convert experiences to feature vectors for manifold learning.
        
        Each experience → concatenate [state_before.amplitudes, state_after.amplitudes]
        This captures the causal transition (before → after).
        
        Returns:
            Array of shape (n_experiences, 2 * n_hypotheses)
        """
        vectors = []
        for exp in self.experiences:
            vec = np.concatenate([exp.state_before.amplitudes, exp.state_after.amplitudes])
            vectors.append(vec)
        return np.array(vectors)
    
    def learn_manifold(self, verbose: bool = False):
        """
        Learn the causal manifold from all accumulated experiences.
        
        Uses Isomap to find a low-dimensional embedding that preserves
        geodesic distances in the high-dimensional transition space.
        """
        if len(self.experiences) < max(7, self.n_neighbors + 2):
            if verbose:
                print(f"⚠️  Not enough experiences ({len(self.experiences)}) for manifold learning (need {max(7, self.n_neighbors + 2)})")
            return
        
        if verbose:
            print(f"🧠 Learning causal manifold from {len(self.experiences)} experiences...")
        
        transition_vectors = self._get_transition_vectors()
        
        try:
            self.manifold_coordinates = self.isomap.fit_transform(transition_vectors)
            self.manifold_is_stale = False
            
            if verbose:
                print(f"   ✅ Manifold learned: {len(self.experiences)} experiences → {self.manifold_dim}D")
                # Report reconstruction error (stress)
                stress = self.isomap.reconstruction_error()
                print(f"   Reconstruction error: {stress:.4f}")
        except Exception as e:
            if verbose:
                print(f"   ❌ Manifold learning failed: {e}")
            self.manifold_is_stale = True
    
    def add_experience(self, exp: Experience):
        """Add a new experience and mark manifold as stale."""
        self.experiences.append(exp)
        self.manifold_is_stale = True
    
    def find_closest_experience(self, query_state: QuantumState, by_reward: bool = False) -> Optional[int]:
        """
        Find the experience most similar to query_state.
        
        Args:
            query_state: State to match
            by_reward: If True, return highest-reward experience. If False, return nearest in state space.
        
        Returns:
            Index of closest experience, or None if no experiences
        """
        if not self.experiences:
            return None
        
        if by_reward:
            # Return experience with highest reward
            return int(np.argmax([exp.reward for exp in self.experiences]))
        else:
            # Return experience with closest state_before
            distances = [
                np.linalg.norm(query_state.amplitudes - exp.state_before.amplitudes)
                for exp in self.experiences
            ]
            return int(np.argmin(distances))
    
    def get_manifold_coordinates(self) -> Optional[np.ndarray]:
        """Return manifold coordinates (for visualization)."""
        return self.manifold_coordinates
    
    def get_experience_clusters(self, n_clusters: int = 3) -> List[List[int]]:
        """
        Cluster experiences on the manifold (for finding synergies).
        
        Args:
            n_clusters: Number of clusters
        
        Returns:
            List of lists of experience indices (one list per cluster)
        """
        if self.manifold_coordinates is None:
            return []
        
        from sklearn.cluster import KMeans
        kmeans = KMeans(n_clusters=n_clusters, random_state=42)
        labels = kmeans.fit_predict(self.manifold_coordinates)
        
        clusters = [[] for _ in range(n_clusters)]
        for idx, label in enumerate(labels):
            clusters[label].append(idx)
        
        return clusters
    
    def prune_low_reward_zones(self, reward_threshold: float = 0.0, radius_percentile: float = 25.0):
        """
        Identify and mark zones on the manifold with consistently low rewards.
        
        PRUNING STRATEGY (from concept.py):
        1. Find experiences with reward < threshold
        2. Cluster them in manifold space
        3. Mark cluster centers as "avoid zones"
        4. Future candidates near these zones get penalized
        
        Args:
            reward_threshold: Experiences below this are considered failures
            radius_percentile: Percentile of inter-point distances to use as zone radius
        """
        if self.manifold_coordinates is None or len(self.experiences) < self.min_zone_samples:
            return
        
        # Find low-reward experiences
        low_reward_indices = [
            i for i, exp in enumerate(self.experiences) 
            if exp.reward < reward_threshold
        ]
        
        if len(low_reward_indices) < self.min_zone_samples:
            return  # Not enough failures to define zones
        
        # Get their manifold coordinates
        low_reward_coords = self.manifold_coordinates[low_reward_indices]
        
        # Compute characteristic distance scale
        if len(low_reward_coords) > 1:
            from scipy.spatial.distance import pdist
            pairwise_dists = pdist(low_reward_coords)
            zone_radius = float(np.percentile(pairwise_dists, radius_percentile))
        else:
            zone_radius = 0.1  # Default small radius
        
        # Cluster low-reward points
        from sklearn.cluster import DBSCAN
        clustering = DBSCAN(eps=zone_radius * 1.5, min_samples=self.min_zone_samples)
        labels = clustering.fit_predict(low_reward_coords)
        
        # Create pruned zones around cluster centers
        unique_labels = set(labels) - {-1}  # Exclude noise
        for label in unique_labels:
            cluster_mask = labels == label
            cluster_coords = low_reward_coords[cluster_mask]
            cluster_center = np.mean(cluster_coords, axis=0)
            
            # Count experiences in this zone
            cluster_experience_ids = [low_reward_indices[i] for i, m in enumerate(cluster_mask) if m]
            avg_reward = np.mean([self.experiences[i].reward for i in cluster_experience_ids])
            
            self.pruned_zones.append({
                'center': cluster_center,
                'radius': zone_radius,
                'avg_reward': avg_reward,
                'count': len(cluster_experience_ids),
                'reason': f'Low reward cluster (avg={avg_reward:.3f}, n={len(cluster_experience_ids)})'
            })
    
    def is_in_pruned_zone(self, manifold_point: np.ndarray) -> bool:
        """
        Check if a point on the manifold is in a pruned (avoid) zone.
        
        Args:
            manifold_point: Coordinates on the learned manifold (shape: manifold_dim,)
        
        Returns:
            True if point is in any pruned zone
        """
        for zone in self.pruned_zones:
            distance = np.linalg.norm(manifold_point - zone['center'])
            if distance < zone['radius']:
                return True
        return False
    
    def get_pruning_penalty(self, manifold_point: np.ndarray) -> float:
        """
        Get a penalty multiplier for points near pruned zones.
        
        Returns value in [0, 1]:
        - 1.0: Far from pruned zones (no penalty)
        - 0.0: Inside pruned zone (maximum penalty)
        - (0, 1): Near pruned zone (gradual falloff)
        
        Args:
            manifold_point: Coordinates on manifold
        
        Returns:
            Multiplier for reward/score (0=avoid, 1=okay)
        """
        if not self.pruned_zones:
            return 1.0
        
        min_penalty = 1.0
        for zone in self.pruned_zones:
            distance = np.linalg.norm(manifold_point - zone['center'])
            radius = zone['radius']
            
            if distance < radius:
                # Inside zone: strong penalty
                penalty = distance / radius  # 0 at center, 1 at edge
            elif distance < radius * 2.0:
                # Near zone: gradual falloff
                penalty = 0.5 + 0.5 * ((distance - radius) / radius)  # 0.5→1.0
            else:
                # Far from zone: no penalty
                penalty = 1.0
            
            min_penalty = min(min_penalty, penalty)
        
        return min_penalty


class Planner:
    """
    Plans intervention sequences by finding paths on the causal manifold.
    
    Given:
    - Current state (where we are)
    - Goal state (where we want to be)
    
    Find:
    - Sequence of actions (path on manifold from current → goal)
    
    Uses Dijkstra's algorithm on the manifold distance graph.
    """
    
    def plan(
        self, 
        engine: GeometricCausalEngine, 
        start_experience_idx: int, 
        goal_experience_idx: int,
        max_path_length: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find shortest path from start to goal experience on causal manifold.
        
        Args:
            engine: GeometricCausalEngine with learned manifold
            start_experience_idx: Index of starting experience
            goal_experience_idx: Index of goal experience
            max_path_length: Maximum path length to prevent runaway search
        
        Returns:
            List of actions (intervention dicts) to execute in sequence
        """
        if engine.manifold_coordinates is None or start_experience_idx is None or goal_experience_idx is None:
            return []
        
        if start_experience_idx == goal_experience_idx:
            # Already at goal
            return [engine.experiences[goal_experience_idx].action]
        
        # Build distance matrix on manifold
        dist_matrix = squareform(pdist(engine.manifold_coordinates, 'euclidean'))
        
        # Run Dijkstra from start
        distances, predecessors = dijkstra(
            csgraph=dist_matrix, 
            directed=False, 
            indices=start_experience_idx, 
            return_predecessors=True
        )
        
        # Reconstruct path
        path_indices = []
        current_node = goal_experience_idx
        
        while current_node != start_experience_idx and current_node != -9999 and len(path_indices) < max_path_length:
            path_indices.append(current_node)
            current_node = predecessors[current_node]
        
        if current_node == -9999:
            # No path found, return direct action to goal
            return [engine.experiences[goal_experience_idx].action]
        
        path_indices.append(start_experience_idx)
        path_indices.reverse()
        
        if not path_indices or len(path_indices) < 2:
            # Trivial path, return goal action
            return [engine.experiences[goal_experience_idx].action]
        
        # Extract actions from path
        return [engine.experiences[i].action for i in path_indices]


class QCAOptimizer:
    """
    Main QCA optimizer that combines causal learning with manifold planning.
    
    Workflow:
    1. Collect experiences (run simulations with different interventions)
    2. Learn causal manifold (Isomap embedding)
    3. Find optimal plan (Dijkstra on manifold)
    4. Execute plan (apply interventions in sequence)
    """
    
    def __init__(self, manifold_dim: int = 3, n_neighbors: int = 5):
        """
        Args:
            manifold_dim: Dimension of causal manifold
            n_neighbors: Isomap neighborhood size
        """
        self.engine = GeometricCausalEngine(manifold_dim=manifold_dim, n_neighbors=n_neighbors)
        self.planner = Planner()
    
    def add_experience(self, exp: Experience):
        """Add a new intervention experience to the learning database."""
        self.engine.add_experience(exp)
    
    def learn(self, verbose: bool = False):
        """Learn the causal manifold from all experiences."""
        if self.engine.manifold_is_stale:
            self.engine.learn_manifold(verbose=verbose)
    
    def find_optimal_plan(
        self, 
        current_state: QuantumState,
        verbose: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Find optimal intervention plan given current flood state.
        
        Args:
            current_state: Current flood state (encoded as QuantumState)
            verbose: Print search details
        
        Returns:
            List of intervention actions to execute
        """
        # Learn manifold if stale
        self.learn(verbose=verbose)
        
        if not self.engine.experiences:
            if verbose:
                print("⚠️  No experiences yet, cannot plan")
            return []
        
        # Find closest experience to current state
        start_idx = self.engine.find_closest_experience(current_state, by_reward=False)
        
        # Find highest-reward experience (goal)
        goal_idx = self.engine.find_closest_experience(current_state, by_reward=True)
        
        if start_idx is None or goal_idx is None:
            return []
        
        if verbose:
            print(f"🗺️  Planning path from experience {start_idx} → {goal_idx} on manifold...")
        
        # Plan path on manifold
        plan = self.planner.plan(self.engine, start_idx, goal_idx)
        
        if verbose:
            print(f"   ✅ Plan found: {len(plan)} actions")
        
        return plan
    
    def get_best_intervention(self, current_state: QuantumState) -> Optional[Dict[str, Any]]:
        """
        Get single best intervention (first action in optimal plan).
        
        Args:
            current_state: Current flood state
        
        Returns:
            Best intervention dict, or None if no experiences
        """
        plan = self.find_optimal_plan(current_state, verbose=False)
        if plan:
            return plan[0]
        return None
    
    def save_to_file(self, filepath: str):
        """Save learned manifold and experiences to file."""
        data = {
            'experiences': [
                {
                    'state_before': exp.state_before.amplitudes.tolist(),
                    'state_after': exp.state_after.amplitudes.tolist(),
                    'action': exp.action,
                    'reward': exp.reward,
                    'metadata': exp.metadata
                }
                for exp in self.engine.experiences
            ],
            'manifold_dim': self.engine.manifold_dim,
            'n_neighbors': self.engine.n_neighbors,
            'n_experiences': len(self.engine.experiences)
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
    
    def load_from_file(self, filepath: str, hypotheses: List[str]):
        """Load experiences from file (manifold will be re-learned)."""
        with open(filepath) as f:
            data = json.load(f)
        
        for exp_data in data['experiences']:
            exp = Experience(
                state_before=QuantumState(
                    amplitudes=np.array(exp_data['state_before']),
                    hypotheses=hypotheses
                ),
                state_after=QuantumState(
                    amplitudes=np.array(exp_data['state_after']),
                    hypotheses=hypotheses
                ),
                action=exp_data['action'],
                reward=exp_data['reward'],
                metadata=exp_data.get('metadata', {})
            )
            self.engine.add_experience(exp)
        
        # Re-learn manifold from loaded experiences
        self.learn(verbose=False)


# ==============================================================================
# Utility Functions
# ==============================================================================

def visualize_manifold(optimizer: QCAOptimizer, save_path: str = 'manifold_3d.png'):
    """
    Visualize the 3D causal manifold with experiences colored by reward.
    
    Args:
        optimizer: QCAOptimizer with learned manifold
        save_path: Where to save the plot
    """
    if optimizer.engine.manifold_coordinates is None:
        print("⚠️  No manifold learned yet")
        return
    
    if optimizer.engine.manifold_dim != 3:
        print(f"⚠️  Manifold is {optimizer.engine.manifold_dim}D, need 3D for visualization")
        return
    
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d import Axes3D
    
    coords = optimizer.engine.manifold_coordinates
    rewards = np.array([exp.reward for exp in optimizer.engine.experiences])
    
    fig = plt.figure(figsize=(12, 8))
    ax = fig.add_subplot(111, projection='3d')
    
    # Color by reward
    scatter = ax.scatter(
        coords[:, 0], coords[:, 1], coords[:, 2],
        c=rewards, cmap='RdYlGn', s=100, alpha=0.7,
        edgecolors='black', linewidth=0.5
    )
    
    ax.set_xlabel('Manifold Dim 1', fontsize=12)
    ax.set_ylabel('Manifold Dim 2', fontsize=12)
    ax.set_zlabel('Manifold Dim 3', fontsize=12)
    ax.set_title('Causal Manifold of Flood Interventions', fontsize=14, fontweight='bold')
    
    cbar = plt.colorbar(scatter, ax=ax, pad=0.1)
    cbar.set_label('Reward (Flood Reduction)', fontsize=11)
    
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    print(f"✅ Manifold visualization saved: {save_path}")


if __name__ == "__main__":
    # Example usage
    print("="*70)
    print("QCA MANIFOLD OPTIMIZER - Example")
    print("="*70)
    
    # Create optimizer
    qca = QCAOptimizer(manifold_dim=3, n_neighbors=5)
    
    # Simulate some experiences (normally from real flood simulations)
    hypotheses = ['severe_flood', 'moderate_flood', 'minor_flood', 'dry']
    
    for i in range(20):
        # Random before/after states (in real use, from flood encoder)
        before = QuantumState(
            amplitudes=np.random.dirichlet([1, 1, 1, 1]),
            hypotheses=hypotheses
        )
        after = QuantumState(
            amplitudes=np.random.dirichlet([1, 1, 1, 2]),  # Slightly drier
            hypotheses=hypotheses
        )
        
        exp = Experience(
            state_before=before,
            state_after=after,
            action={'type': f'intervention_{i%3}', 'location': (i*5, i*3)},
            reward=np.random.rand() * 0.5  # Random reward 0-0.5
        )
        
        qca.add_experience(exp)
    
    # Learn manifold
    print(f"\n📊 Added {len(qca.engine.experiences)} experiences")
    qca.learn(verbose=True)
    
    # Find optimal plan for a new state
    current_state = QuantumState(
        amplitudes=np.array([0.4, 0.3, 0.2, 0.1]),
        hypotheses=hypotheses
    )
    
    print(f"\n🎯 Finding optimal plan for state: {current_state.dominant_hypothesis()}")
    plan = qca.find_optimal_plan(current_state, verbose=True)
    
    if plan:
        print(f"\n📋 Recommended actions:")
        for i, action in enumerate(plan, 1):
            print(f"   {i}. {action['type']} at {action['location']}")
    
    print("\n" + "="*70)

