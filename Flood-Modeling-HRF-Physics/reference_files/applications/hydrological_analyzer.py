#!/usr/bin/env python3
"""
Hydrological Analyzer: Proper flow accumulation and upstream analysis for flood intervention placement.

This implements standard civil engineering algorithms:
- D8 flow direction (Deterministic 8-neighbor)
- Flow accumulation (Jenson & Domingue, 1988)
- Upstream tracing for intervention placement
- Catchment delineation

These are NOT learned by AI - they are established engineering methods.

Author: Hydrological Engineering Layer
"""
from __future__ import annotations

import numpy as np
from typing import Tuple, List, Dict, Optional
from dataclasses import dataclass
from scipy import ndimage


@dataclass
class InterceptionPoint:
    """Optimal location for flood intervention based on hydrology."""
    grid_i: int
    grid_j: int
    flow_accumulation: float  # Number of upstream cells
    elevation_m: float
    distance_to_hotspot_m: float
    upstream_area_m2: float
    score: float  # Overall suitability score
    reasoning: str


class HydrologicalAnalyzer:
    """
    Analyzes terrain hydrology to find optimal intervention locations.
    
    Uses standard civil engineering algorithms, not learned AI.
    """
    
    def __init__(self, dem: np.ndarray, dx: float, dy: float, verbose: bool = True):
        """
        Initialize with digital elevation model.
        
        Args:
            dem: 2D array of elevations (meters)
            dx: Cell width (meters)
            dy: Cell height (meters)
            verbose: Print diagnostic messages
        """
        self.dem = dem
        self.dx = dx
        self.dy = dy
        self.verbose = verbose
        
        # Computed products (cached)
        self.flow_direction: Optional[np.ndarray] = None
        self.flow_accumulation: Optional[np.ndarray] = None
        self.slope: Optional[np.ndarray] = None
        
        if verbose:
            print(f"\n{'='*70}")
            print(f"HYDROLOGICAL ANALYSIS")
            print(f"{'='*70}")
            print(f"DEM: {dem.shape[0]} x {dem.shape[1]} cells")
            print(f"Cell size: {dx:.1f}m x {dy:.1f}m")
            print(f"Elevation range: {np.min(dem):.1f}m - {np.max(dem):.1f}m")
    
    def compute_flow_direction(self) -> np.ndarray:
        """
        Compute D8 flow direction for each cell.
        
        D8 Algorithm:
        - Water flows to steepest downhill neighbor (of 8 neighbors)
        - Direction encoded as: 1=E, 2=SE, 4=S, 8=SW, 16=W, 32=NW, 64=N, 128=NE
        
        Returns:
            Flow direction grid (power of 2 encoding)
        """
        if self.flow_direction is not None:
            return self.flow_direction
        
        if self.verbose:
            print("\n[1/3] Computing D8 flow direction...")
        
        ny, nx = self.dem.shape
        flow_dir = np.zeros((ny, nx), dtype=np.uint8)
        
        # D8 neighbor offsets: [E, SE, S, SW, W, NW, N, NE]
        di = np.array([0, 1, 1, 1, 0, -1, -1, -1])
        dj = np.array([1, 1, 0, -1, -1, -1, 0, 1])
        codes = np.array([1, 2, 4, 8, 16, 32, 64, 128], dtype=np.uint8)
        
        # Distances to neighbors
        distances = np.array([self.dx, np.sqrt(self.dx**2 + self.dy**2), self.dy,
                             np.sqrt(self.dx**2 + self.dy**2), self.dx,
                             np.sqrt(self.dx**2 + self.dy**2), self.dy,
                             np.sqrt(self.dx**2 + self.dy**2)])
        
        for i in range(ny):
            for j in range(nx):
                max_slope = -999.0
                best_dir = 0
                
                for k in range(8):
                    ni = i + di[k]
                    nj = j + dj[k]
                    
                    # Check bounds
                    if 0 <= ni < ny and 0 <= nj < nx:
                        # Compute slope to neighbor
                        drop = self.dem[i, j] - self.dem[ni, nj]
                        slope = drop / distances[k]
                        
                        if slope > max_slope:
                            max_slope = slope
                            best_dir = codes[k]
                
                flow_dir[i, j] = best_dir
        
        self.flow_direction = flow_dir
        
        if self.verbose:
            pct_flow = (np.sum(flow_dir > 0) / flow_dir.size) * 100
            print(f"   ✓ Flow direction computed for {pct_flow:.1f}% of cells")
        
        return flow_dir
    
    def compute_flow_accumulation(self) -> np.ndarray:
        """
        Compute flow accumulation (upstream contributing area).
        
        For each cell, counts how many cells drain into it.
        Uses recursive algorithm starting from high elevations.
        
        Returns:
            Flow accumulation grid (number of upstream cells)
        """
        if self.flow_accumulation is not None:
            return self.flow_accumulation
        
        if self.flow_direction is None:
            self.compute_flow_direction()
        
        if self.verbose:
            print("\n[2/3] Computing flow accumulation...")
        
        ny, nx = self.dem.shape
        accum = np.ones((ny, nx), dtype=np.float32)  # Start with 1 (self)
        
        # Sort cells by elevation (high to low)
        flat_idx = np.argsort(-self.dem.ravel())
        
        # D8 direction to offset mapping
        dir_to_offset = {
            1: (0, 1),    # E
            2: (1, 1),    # SE
            4: (1, 0),    # S
            8: (1, -1),   # SW
            16: (0, -1),  # W
            32: (-1, -1), # NW
            64: (-1, 0),  # N
            128: (-1, 1)  # NE
        }
        
        # Process cells from high to low elevation
        for idx in flat_idx:
            i = idx // nx
            j = idx % nx
            
            direction = self.flow_direction[i, j]
            
            if direction > 0 and direction in dir_to_offset:
                di, dj = dir_to_offset[direction]
                ni = i + di
                nj = j + dj
                
                if 0 <= ni < ny and 0 <= nj < nx:
                    # Add this cell's accumulation to downstream cell
                    accum[ni, nj] += accum[i, j]
        
        self.flow_accumulation = accum
        
        if self.verbose:
            max_accum = np.max(accum)
            mean_accum = np.mean(accum)
            print(f"   ✓ Flow accumulation computed")
            print(f"   Max upstream area: {max_accum:.0f} cells ({max_accum * self.dx * self.dy:.0f}m²)")
            print(f"   Mean upstream area: {mean_accum:.1f} cells")
        
        return accum
    
    def compute_slope(self) -> np.ndarray:
        """Compute terrain slope magnitude."""
        if self.slope is not None:
            return self.slope
        
        # Compute gradients
        grad_y, grad_x = np.gradient(self.dem)
        slope = np.sqrt((grad_x / self.dx)**2 + (grad_y / self.dy)**2)
        
        self.slope = slope
        return slope
    
    def find_upstream_interception_points(self,
                                         hotspots: List[Dict],
                                         n_points: int = 5,
                                         min_distance_m: float = 100.0,
                                         min_accumulation: float = 100.0) -> List[InterceptionPoint]:
        """
        Find optimal upstream locations to intercept flow before it reaches hotspots.
        
        Engineering Strategy:
        1. Trace flow BACKWARDS from hotspot to find upstream contributors
        2. Identify high-accumulation points (many cells drain through here)
        3. Select points that are:
           - Upstream of hotspot (higher elevation)
           - High flow accumulation (intercept more water)
           - Sufficient distance from hotspot (time to store water)
        
        Args:
            hotspots: List of flood hotspot dictionaries with grid_indices
            n_points: Number of interception points to find per hotspot
            min_distance_m: Minimum distance upstream from hotspot
            min_accumulation: Minimum flow accumulation threshold
            
        Returns:
            List of InterceptionPoint objects with locations and justification
        """
        if self.flow_direction is None:
            self.compute_flow_direction()
        if self.flow_accumulation is None:
            self.compute_flow_accumulation()
        if self.slope is None:
            self.compute_slope()
        
        if self.verbose:
            print(f"\n[3/3] Finding upstream interception points...")
            print(f"   Analyzing {len(hotspots)} hotspots")
            print(f"   Min distance: {min_distance_m:.0f}m")
            print(f"   Min accumulation: {min_accumulation:.0f} cells")
        
        all_points = []
        
        for hotspot_idx, hotspot in enumerate(hotspots):
            hotspot_i = hotspot['grid_indices']['i']
            hotspot_j = hotspot['grid_indices']['j']
            hotspot_elev = self.dem[hotspot_i, hotspot_j]
            
            if self.verbose:
                print(f"\n   Hotspot {hotspot_idx + 1}: cell ({hotspot_i}, {hotspot_j}), elev {hotspot_elev:.1f}m")
            
            # Trace upstream contributors
            upstream_cells = self._trace_upstream(hotspot_i, hotspot_j, max_cells=5000)
            
            if self.verbose:
                print(f"      Found {len(upstream_cells)} upstream cells")
            
            # Score each upstream cell
            candidates = []
            for ui, uj in upstream_cells:
                # Distance to hotspot
                dist_m = np.sqrt(((ui - hotspot_i) * self.dy)**2 + 
                                ((uj - hotspot_j) * self.dx)**2)
                
                if dist_m < min_distance_m:
                    continue  # Too close
                
                # Flow accumulation (how much water passes through here)
                accum = self.flow_accumulation[ui, uj]
                
                if accum < min_accumulation:
                    continue  # Not enough flow
                
                # Elevation (must be upstream = higher)
                elev = self.dem[ui, uj]
                if elev <= hotspot_elev:
                    continue  # Not actually upstream
                
                elev_diff = elev - hotspot_elev
                
                # Score = weighted combination of factors
                # Higher is better
                score = (
                    accum * 0.5 +                    # More flow = better
                    (dist_m / 100.0) * 0.2 +         # Further upstream = better (to a point)
                    elev_diff * 10.0 +               # Higher elevation = better
                    (1.0 / (self.slope[ui, uj] + 0.01)) * 0.3  # Flatter = better for basin
                )
                
                candidates.append({
                    'i': ui,
                    'j': uj,
                    'accum': accum,
                    'elev': elev,
                    'dist': dist_m,
                    'elev_diff': elev_diff,
                    'score': score
                })
            
            # Sort by score and take top N
            candidates.sort(key=lambda x: x['score'], reverse=True)
            top_candidates = candidates[:n_points]
            
            for rank, cand in enumerate(top_candidates, 1):
                upstream_area_m2 = cand['accum'] * self.dx * self.dy
                
                reasoning = (
                    f"Upstream of hotspot {hotspot_idx + 1} | "
                    f"Intercepts {upstream_area_m2:.0f}m² catchment | "
                    f"{cand['dist']:.0f}m upstream | "
                    f"+{cand['elev_diff']:.1f}m elevation"
                )
                
                point = InterceptionPoint(
                    grid_i=cand['i'],
                    grid_j=cand['j'],
                    flow_accumulation=cand['accum'],
                    elevation_m=cand['elev'],
                    distance_to_hotspot_m=cand['dist'],
                    upstream_area_m2=upstream_area_m2,
                    score=cand['score'],
                    reasoning=reasoning
                )
                
                all_points.append(point)
                
                if self.verbose:
                    print(f"      #{rank}: cell ({cand['i']}, {cand['j']}) | "
                          f"score={cand['score']:.1f} | {cand['accum']:.0f} cells | "
                          f"{cand['dist']:.0f}m upstream")
        
        if self.verbose:
            print(f"\n   ✓ Found {len(all_points)} total interception points")
        
        return all_points
    
    def _trace_upstream(self, start_i: int, start_j: int, max_cells: int = 10000) -> List[Tuple[int, int]]:
        """
        Trace all cells that drain into the starting cell.
        
        Uses reverse flow direction tracking.
        """
        ny, nx = self.dem.shape
        upstream = []
        
        # Direction that would flow TO the starting cell (inverse of flow direction)
        inverse_dir = {
            1: 16,   # If neighbor flows E (1), it's to our W (16)
            2: 32,   # SE -> NW
            4: 64,   # S -> N
            8: 128,  # SW -> NE
            16: 1,   # W -> E
            32: 2,   # NW -> SE
            64: 4,   # N -> S
            128: 8   # NE -> SW
        }
        
        # Offsets for each direction
        offsets = {
            1: (0, 1), 2: (1, 1), 4: (1, 0), 8: (1, -1),
            16: (0, -1), 32: (-1, -1), 64: (-1, 0), 128: (-1, 1)
        }
        
        # BFS to find all upstream cells
        visited = np.zeros((ny, nx), dtype=bool)
        queue = [(start_i, start_j)]
        visited[start_i, start_j] = True
        
        while queue and len(upstream) < max_cells:
            i, j = queue.pop(0)
            
            # Check all 8 neighbors
            for direction, (di, dj) in offsets.items():
                ni = i + di
                nj = j + dj
                
                if 0 <= ni < ny and 0 <= nj < nx and not visited[ni, nj]:
                    # Check if this neighbor flows into current cell
                    neighbor_flow_dir = self.flow_direction[ni, nj]
                    
                    if neighbor_flow_dir == inverse_dir.get(direction, 0):
                        upstream.append((ni, nj))
                        visited[ni, nj] = True
                        queue.append((ni, nj))
        
        return upstream
    
    def export_flow_maps(self, output_dir):
        """Export flow direction and accumulation as numpy arrays for visualization."""
        from pathlib import Path
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        if self.flow_direction is not None:
            np.save(output_dir / 'flow_direction.npy', self.flow_direction)
        if self.flow_accumulation is not None:
            np.save(output_dir / 'flow_accumulation.npy', self.flow_accumulation)
        if self.slope is not None:
            np.save(output_dir / 'slope.npy', self.slope)
        
        if self.verbose:
            print(f"\n✅ Exported flow maps to: {output_dir}")


if __name__ == "__main__":
    print("Hydrological Analyzer - Proper upstream flow analysis for intervention placement")
    print("Import and use HydrologicalAnalyzer class")
