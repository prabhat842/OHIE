#!/usr/bin/env python3
"""
Intervention Generator
======================
Converts QCIA optimization results into HRF solver modifications.

This module takes abstract optimization outputs (e.g., "add 10 culverts")
and translates them into concrete HRF solver parameters (structures, infiltration).

Usage:
    generator = InterventionGenerator(grid, dem, road_mask)
    
    # From spatial design
    generator.apply_spatial_design(solver, spatial_design)
    
    # Or from simple parameters
    generator.apply_simple_scenario(solver, culvert_count=10, pond_count=2)
"""

from __future__ import annotations
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from pathlib import Path


class InterventionGenerator:
    """
    Generates HRF solver modifications from optimization results.
    Does NOT modify your existing HRF code - only configures it.
    """
    
    def __init__(self, 
                 grid_shape: Tuple[int, int],
                 dem: np.ndarray,
                 road_mask: Optional[np.ndarray] = None):
        """
        Initialize generator with terrain data.
        
        Args:
            grid_shape: (nx, ny) grid dimensions
            dem: Digital elevation model (nx, ny)
            road_mask: Binary mask of roads (optional)
        """
        self.grid_shape = grid_shape
        self.dem = dem
        self.road_mask = road_mask if road_mask is not None else np.zeros(grid_shape)
        
        # Cache for hotspot analysis
        self._culvert_candidates = None
        self._pond_candidates = None
    
    def apply_spatial_design(self, solver: Any, spatial_design: Any):
        """
        Apply a SpatialDesign (from spatial_optimizer.py) to HRF solver.
        
        Args:
            solver: HRFSolver instance
            spatial_design: SpatialDesign object with interventions
        """
        # Import structures from HRF (avoid top-level to prevent import errors)
        try:
            from Physics.hrf import Culvert, FaceIndex
        except ImportError:
            print("⚠️  Could not import HRF structures. Using mock objects.")
            # Create mock classes for testing
            class FaceIndex:
                def __init__(self, i, j, dir): 
                    self.i = i; self.j = j; self.dir = dir
            class Culvert:
                def __init__(self, faces, area, **kwargs):
                    self.faces = faces; self.area = area
        
        # Process each intervention
        for interv in spatial_design.interventions:
            i, j = interv.location
            type_key = interv.type_key
            
            if 'culvert' in type_key:
                # Add culvert at this location
                # Create face in steepest gradient direction
                sx = abs(self.dem[min(i+1, self.grid_shape[0]-1), j] - self.dem[max(i-1, 0), j])
                sy = abs(self.dem[i, min(j+1, self.grid_shape[1]-1)] - self.dem[i, max(j-1, 0)])
                
                if sx >= sy and i < self.grid_shape[0]-1:
                    face = FaceIndex(i=i, j=j, dir='x')
                elif j < self.grid_shape[1]-1:
                    face = FaceIndex(i=i, j=j, dir='y')
                else:
                    continue  # Skip edge cases
                
                # Estimate area from type
                if '3x3' in type_key:
                    area = 9.0  # m²
                elif '2x2' in type_key:
                    area = 4.0
                else:
                    area = 2.0
                
                culvert = Culvert(faces=[face], area=area)
                solver.structures['culverts'].append(culvert)
            
            elif 'pond' in type_key:
                # Depress bed at pond location (creates detention basin)
                pond_radius = 3  # cells
                for di in range(-pond_radius, pond_radius+1):
                    for dj in range(-pond_radius, pond_radius+1):
                        pi, pj = i + di, j + dj
                        if 0 <= pi < self.grid_shape[0] and 0 <= pj < self.grid_shape[1]:
                            dist = np.sqrt(di**2 + dj**2)
                            if dist <= pond_radius:
                                # Gaussian depression
                                depth = 2.0 * np.exp(-(dist/pond_radius)**2)
                                if solver.bed is not None:
                                    try:
                                        solver.bed[pi, pj] -= depth
                                    except:
                                        pass  # Bed might be read-only
    
    def apply_simple_scenario(self,
                              solver: Any,
                              culvert_count: int = 0,
                              pond_count: int = 0,
                              drainage_multiplier: float = 1.0,
                              base_infiltration: Optional[np.ndarray] = None):
        """
        Apply simple scenario parameters to HRF solver.
        
        This is a simplified interface that doesn't require spatial optimization.
        It places interventions at automatically detected hotspots.
        
        Args:
            solver: HRFSolver instance
            culvert_count: Number of culverts to add
            pond_count: Number of detention ponds
            drainage_multiplier: Factor to increase infiltration (simulates better drainage)
            base_infiltration: Base infiltration array (will be multiplied)
        """
        # Import HRF structures
        try:
            from Physics.hrf import Culvert, FaceIndex
        except ImportError:
            class FaceIndex:
                def __init__(self, i, j, dir): 
                    self.i = i; self.j = j; self.dir = dir
            class Culvert:
                def __init__(self, faces, area, **kwargs):
                    self.faces = faces; self.area = area
        
        # 1. Add culverts at hotspots
        if culvert_count > 0:
            locations = self._find_culvert_hotspots(culvert_count)
            
            for i, j in locations:
                # Determine face direction by gradient
                sx = abs(self.dem[min(i+1, self.grid_shape[0]-1), j] - self.dem[max(i-1, 0), j])
                sy = abs(self.dem[i, min(j+1, self.grid_shape[1]-1)] - self.dem[i, max(j-1, 0)])
                
                if sx >= sy and i < self.grid_shape[0]-1:
                    face = FaceIndex(i=int(i), j=int(j), dir='x')
                elif j < self.grid_shape[1]-1:
                    face = FaceIndex(i=int(i), j=int(j), dir='y')
                else:
                    continue
                
                culvert = Culvert(faces=[face], area=4.0)  # 2x2m culvert
                solver.structures['culverts'].append(culvert)
        
        # 2. Add detention ponds
        if pond_count > 0 and solver.bed is not None:
            locations = self._find_pond_hotspots(pond_count)
            
            for i, j in locations:
                # Create depression (3-cell radius)
                for di in range(-3, 4):
                    for dj in range(-3, 4):
                        pi, pj = i + di, j + dj
                        if 0 <= pi < self.grid_shape[0] and 0 <= pj < self.grid_shape[1]:
                            dist = np.sqrt(di**2 + dj**2)
                            if dist <= 3:
                                depth = 2.0 * np.exp(-(dist/3)**2)
                                try:
                                    solver.bed[pi, pj] -= depth
                                except:
                                    pass
        
        # 3. Improve drainage (increase infiltration)
        if drainage_multiplier > 1.0 and base_infiltration is not None:
            improved_infiltration = base_infiltration * drainage_multiplier
            solver.set_forcing(infil_rate=improved_infiltration)
    
    def _find_culvert_hotspots(self, n: int) -> List[Tuple[int, int]]:
        """
        Find best locations for culverts based on terrain.
        
        Strategy: Low elevation + near roads + spaced apart
        """
        if self._culvert_candidates is not None:
            return self._culvert_candidates[:n]
        
        nx, ny = self.grid_shape
        
        # Score: low elevation (good for drainage) + near roads
        score = 1.0 / (self.dem + 1e-6)  # Lower elevation = higher score
        score = score * (1 + self.road_mask * 2.0)  # Prefer near roads
        
        # Find top locations with spacing constraint
        flat_indices = np.argsort(score.ravel())[::-1]
        locations = []
        
        min_spacing = 5  # cells
        for idx in flat_indices:
            i, j = np.unravel_index(idx, score.shape)
            
            # Check spacing
            too_close = False
            for (li, lj) in locations:
                if abs(i - li) < min_spacing and abs(j - lj) < min_spacing:
                    too_close = True
                    break
            
            # Check not on boundary
            if not too_close and 2 < i < nx-2 and 2 < j < ny-2:
                locations.append((int(i), int(j)))
            
            if len(locations) >= n * 2:  # Cache extra
                break
        
        self._culvert_candidates = locations
        return locations[:n]
    
    def _find_pond_hotspots(self, n: int) -> List[Tuple[int, int]]:
        """
        Find best locations for detention ponds.
        
        Strategy: Local elevation minima (natural depressions)
        """
        if self._pond_candidates is not None:
            return self._pond_candidates[:n]
        
        nx, ny = self.grid_shape
        locations = []
        
        # Find local minima
        for i in range(5, nx-5, 5):
            for j in range(5, ny-5, 5):
                # Check if local minimum
                window = self.dem[i-2:i+3, j-2:j+3]
                if self.dem[i, j] == np.min(window):
                    # Check spacing
                    too_close = False
                    for (li, lj) in locations:
                        dist = np.sqrt((i-li)**2 + (j-lj)**2)
                        if dist < 10:
                            too_close = True
                            break
                    
                    if not too_close:
                        locations.append((int(i), int(j)))
        
        # Sort by depth of depression
        depths = []
        for i, j in locations:
            window = self.dem[i-2:i+3, j-2:j+3]
            depth = np.mean(window) - self.dem[i, j]
            depths.append(depth)
        
        sorted_locs = [loc for _, loc in sorted(zip(depths, locations), reverse=True)]
        self._pond_candidates = sorted_locs
        return sorted_locs[:n]
    
    def estimate_scenario_cost(self,
                              culvert_count: int = 0,
                              pond_count: int = 0,
                              drain_length_km: float = 0.0) -> float:
        """
        Estimate total cost of scenario in rupees.
        
        Args:
            culvert_count: Number of culverts
            pond_count: Number of ponds
            drain_length_km: Length of new drains
        
        Returns:
            Estimated cost in rupees
        """
        # Unit costs (rough estimates for India)
        CULVERT_COST = 35e5  # ₹35 lakh per 2x2m box culvert
        POND_COST = 180e5    # ₹180 lakh per medium detention pond
        DRAIN_COST_PER_KM = 500e5  # ₹500 lakh per km of RCC drain
        
        total = (
            culvert_count * CULVERT_COST +
            pond_count * POND_COST +
            drain_length_km * DRAIN_COST_PER_KM
        )
        
        return total
    
    def get_summary(self, solver: Any) -> str:
        """Get human-readable summary of interventions applied."""
        lines = [
            "="*60,
            "Intervention Summary",
            "="*60,
        ]
        
        # Count structures
        culvert_count = len(solver.structures.get('culverts', []))
        weir_count = len(solver.structures.get('weirs', []))
        bridge_count = len(solver.structures.get('bridges', []))
        
        lines.append(f"Culverts: {culvert_count}")
        lines.append(f"Weirs: {weir_count}")
        lines.append(f"Bridges: {bridge_count}")
        
        # Estimate cost
        cost = self.estimate_scenario_cost(culvert_count=culvert_count)
        lines.append(f"Estimated cost: ₹{cost/1e7:.1f} Crores")
        
        lines.append("="*60)
        return "\n".join(lines)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def quick_apply(solver, culvert_count: int = 0, pond_count: int = 0, **kwargs):
    """
    Quick application without creating generator instance.
    
    Usage:
        from AI.intervention_generator import quick_apply
        quick_apply(solver, culvert_count=10, pond_count=2)
    """
    nx, ny = solver.grid.nx, solver.grid.ny
    
    # Get DEM from solver
    if hasattr(solver, 'bed') and solver.bed is not None:
        try:
            dem = solver.bed.cpu().numpy() if hasattr(solver.bed, 'cpu') else np.asarray(solver.bed)
        except:
            dem = np.random.rand(nx, ny) * 100  # Fallback
    else:
        dem = np.random.rand(nx, ny) * 100
    
    generator = InterventionGenerator((nx, ny), dem)
    generator.apply_simple_scenario(solver, culvert_count, pond_count, **kwargs)


if __name__ == "__main__":
    # Demo / Test
    print("Intervention Generator Module")
    print("="*60)
    print("Converts optimization results into HRF solver modifications.")
    print("")
    print("Usage:")
    print("  from AI.intervention_generator import InterventionGenerator")
    print("  generator = InterventionGenerator(grid_shape, dem, road_mask)")
    print("  generator.apply_simple_scenario(solver, culvert_count=10)")
    print("")
    print("Or use quick helper:")
    print("  from AI.intervention_generator import quick_apply")
    print("  quick_apply(solver, culvert_count=10, pond_count=2)")
    print("="*60)



