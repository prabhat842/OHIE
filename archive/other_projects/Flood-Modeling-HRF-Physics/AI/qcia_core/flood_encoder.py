#!/usr/bin/env python3
"""
Flood State Encoder - Convert flood grids to Quantum States
============================================================

Encodes 2D flood depth grids as quantum superposition states.
Each amplitude represents the "probability" of a flood severity regime.

This enables the QCA manifold optimizer to reason about flood states
in a low-dimensional, semantically meaningful space.
"""

import numpy as np
from typing import Tuple, Dict
from .qca_manifold_optimizer import QuantumState


class FloodStateEncoder:
    """
    Encodes flood depth grids as quantum superposition states.
    
    The encoding strategy:
    - Divide grid into severity regimes (severe, moderate, minor, dry)
    - Calculate fraction of cells in each regime
    - Normalize to get "amplitudes" (sum to 1)
    
    This gives a compact representation: 2D grid (10k cells) → 4D vector
    """
    
    def __init__(self, 
                 severe_threshold: float = 0.5,
                 moderate_threshold: float = 0.2,
                 minor_threshold: float = 0.05):
        """
        Args:
            severe_threshold: Depth (m) for severe flooding
            moderate_threshold: Depth (m) for moderate flooding
            minor_threshold: Depth (m) for minor flooding
        """
        self.severe_threshold = severe_threshold
        self.moderate_threshold = moderate_threshold
        self.minor_threshold = minor_threshold
        
        self.hypotheses = [
            'severe_flood',    # h >= 0.5m (life-threatening)
            'moderate_flood',  # 0.2m <= h < 0.5m (damaging)
            'minor_flood',     # 0.05m <= h < 0.2m (nuisance)
            'dry'              # h < 0.05m (safe)
        ]
    
    def encode(self, h_grid: np.ndarray, mask: np.ndarray = None) -> QuantumState:
        """
        Encode flood depth grid as quantum state.
        
        Args:
            h_grid: 2D array of flood depths (meters)
            mask: Optional boolean mask (True = include, False = ignore)
        
        Returns:
            QuantumState with amplitudes for each severity regime
        """
        if mask is not None:
            h_grid = h_grid[mask]
        else:
            h_grid = h_grid.flatten()
        
        # Remove NaN/inf values
        h_grid = h_grid[np.isfinite(h_grid)]
        
        if len(h_grid) == 0:
            # Empty grid, return uniform distribution
            return QuantumState(
                amplitudes=np.ones(4) / 4.0,
                hypotheses=self.hypotheses
            )
        
        # Count cells in each regime
        n_severe = np.sum(h_grid >= self.severe_threshold)
        n_moderate = np.sum((h_grid >= self.moderate_threshold) & (h_grid < self.severe_threshold))
        n_minor = np.sum((h_grid >= self.minor_threshold) & (h_grid < self.moderate_threshold))
        n_dry = np.sum(h_grid < self.minor_threshold)
        
        # Convert counts to fractions (amplitudes)
        total = len(h_grid)
        amplitudes = np.array([
            n_severe / total,
            n_moderate / total,
            n_minor / total,
            n_dry / total
        ], dtype=np.float64)
        
        # Ensure normalization (handle floating point errors)
        amplitudes /= (amplitudes.sum() + 1e-12)
        
        return QuantumState(amplitudes=amplitudes, hypotheses=self.hypotheses)
    
    def encode_local(self, h_grid: np.ndarray, center: Tuple[int, int], radius: int = 5) -> QuantumState:
        """
        Encode local flood state around a specific location.
        
        Useful for site-specific intervention planning.
        
        Args:
            h_grid: 2D array of flood depths
            center: (i, j) grid coordinates
            radius: Radius in cells around center
        
        Returns:
            QuantumState encoding local flood severity
        """
        i, j = center
        nx, ny = h_grid.shape
        
        # Extract local patch
        i0 = max(0, i - radius)
        i1 = min(nx, i + radius + 1)
        j0 = max(0, j - radius)
        j1 = min(ny, j + radius + 1)
        
        h_local = h_grid[i0:i1, j0:j1]
        
        return self.encode(h_local)
    
    def decode_severity(self, state: QuantumState) -> str:
        """
        Get dominant flood severity from quantum state.
        
        Args:
            state: QuantumState to decode
        
        Returns:
            String like 'severe_flood', 'moderate_flood', etc.
        """
        return state.dominant_hypothesis()
    
    def compute_distance(self, state1: QuantumState, state2: QuantumState) -> float:
        """
        Compute distance between two flood states.
        
        Uses L2 norm in amplitude space.
        
        Args:
            state1: First state
            state2: Second state
        
        Returns:
            Distance (0 = identical, sqrt(2) = maximally different)
        """
        return np.linalg.norm(state1.amplitudes - state2.amplitudes)


class SpatialFloodEncoder:
    """
    Encodes spatial flood patterns (not just global severity).
    
    Divides grid into regions and encodes each separately,
    then concatenates into a higher-dimensional state vector.
    
    This captures spatial heterogeneity: "north flooded, south dry"
    """
    
    def __init__(self, 
                 n_regions: int = 4,
                 severe_threshold: float = 0.5,
                 moderate_threshold: float = 0.2,
                 minor_threshold: float = 0.05):
        """
        Args:
            n_regions: Number of spatial regions (2x2 grid by default)
            severe_threshold, moderate_threshold, minor_threshold: As in FloodStateEncoder
        """
        self.n_regions = n_regions
        self.encoder = FloodStateEncoder(severe_threshold, moderate_threshold, minor_threshold)
        
        # For n_regions=4, we use 2x2 grid
        self.n_rows = int(np.sqrt(n_regions))
        self.n_cols = n_regions // self.n_rows
        
        # Create hypothesis names like "NW_severe_flood", "NE_moderate_flood", etc.
        region_names = []
        for r in range(self.n_rows):
            for c in range(self.n_cols):
                region_names.append(f"R{r}{c}")
        
        self.region_names = region_names
        self.hypotheses = [
            f"{region}_{hyp}"
            for region in region_names
            for hyp in self.encoder.hypotheses
        ]
    
    def encode(self, h_grid: np.ndarray) -> QuantumState:
        """
        Encode flood grid with spatial resolution.
        
        Args:
            h_grid: 2D flood depth grid
        
        Returns:
            QuantumState with amplitudes for each (region, severity) combination
        """
        nx, ny = h_grid.shape
        
        # Divide grid into regions
        region_states = []
        
        for r in range(self.n_rows):
            for c in range(self.n_cols):
                # Extract region
                i0 = (r * nx) // self.n_rows
                i1 = ((r + 1) * nx) // self.n_rows
                j0 = (c * ny) // self.n_cols
                j1 = ((c + 1) * ny) // self.n_cols
                
                h_region = h_grid[i0:i1, j0:j1]
                
                # Encode region
                region_state = self.encoder.encode(h_region)
                region_states.append(region_state.amplitudes)
        
        # Concatenate all region amplitudes
        amplitudes = np.concatenate(region_states)
        
        # Renormalize (each region was already normalized, so sum = n_regions)
        amplitudes /= amplitudes.sum()
        
        return QuantumState(amplitudes=amplitudes, hypotheses=self.hypotheses)
    
    def get_region_severity(self, state: QuantumState, region_idx: int) -> str:
        """
        Get severity for a specific region.
        
        Args:
            state: Spatial QuantumState
            region_idx: Which region (0 to n_regions-1)
        
        Returns:
            Severity string for that region
        """
        # Extract amplitudes for this region
        n_hyp_per_region = len(self.encoder.hypotheses)
        start = region_idx * n_hyp_per_region
        end = start + n_hyp_per_region
        
        region_amps = state.amplitudes[start:end]
        
        # Find dominant hypothesis
        dominant_idx = np.argmax(region_amps)
        return self.encoder.hypotheses[dominant_idx]


# ==============================================================================
# Utility Functions
# ==============================================================================

def visualize_quantum_state(state: QuantumState, save_path: str = None):
    """
    Visualize quantum state as bar chart.
    
    Args:
        state: QuantumState to visualize
        save_path: Optional path to save figure
    """
    import matplotlib.pyplot as plt
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    x = np.arange(len(state.hypotheses))
    ax.bar(x, state.amplitudes, color=['red', 'orange', 'yellow', 'green'][:len(state.hypotheses)])
    
    ax.set_xticks(x)
    ax.set_xticklabels(state.hypotheses, rotation=45, ha='right')
    ax.set_ylabel('Amplitude (Probability)', fontsize=12)
    ax.set_title('Flood State Quantum Superposition', fontsize=14, fontweight='bold')
    ax.set_ylim([0, 1.0])
    ax.grid(axis='y', alpha=0.3)
    
    # Add values on bars
    for i, amp in enumerate(state.amplitudes):
        ax.text(i, amp + 0.02, f'{amp:.2f}', ha='center', fontsize=10)
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"✅ State visualization saved: {save_path}")
    else:
        plt.show()


if __name__ == "__main__":
    print("="*70)
    print("FLOOD STATE ENCODER - Example")
    print("="*70)
    
    # Create sample flood grid (100x100)
    np.random.seed(42)
    nx, ny = 100, 100
    
    # Simulate flood: high in center, low at edges
    x = np.linspace(-1, 1, nx)
    y = np.linspace(-1, 1, ny)
    X, Y = np.meshgrid(x, y, indexing='ij')
    
    # Gaussian flood peak
    h_grid = 0.8 * np.exp(-(X**2 + Y**2) / 0.5) + 0.05 * np.random.rand(nx, ny)
    
    print(f"\n📊 Flood grid: {nx}×{ny}")
    print(f"   Depth range: {h_grid.min():.2f}m - {h_grid.max():.2f}m")
    print(f"   Mean depth: {h_grid.mean():.2f}m")
    
    # Encode as quantum state
    encoder = FloodStateEncoder()
    state = encoder.encode(h_grid)
    
    print(f"\n🌀 Quantum State:")
    print(f"   {state}")
    print(f"   Dominant: {encoder.decode_severity(state)}")
    
    # Encode with spatial resolution
    print(f"\n🗺️  Spatial Encoding (2×2 regions):")
    spatial_encoder = SpatialFloodEncoder(n_regions=4)
    spatial_state = spatial_encoder.encode(h_grid)
    
    for r in range(4):
        severity = spatial_encoder.get_region_severity(spatial_state, r)
        print(f"   Region {r}: {severity}")
    
    # Visualize
    visualize_quantum_state(state, save_path='flood_quantum_state.png')
    
    print("\n" + "="*70)



