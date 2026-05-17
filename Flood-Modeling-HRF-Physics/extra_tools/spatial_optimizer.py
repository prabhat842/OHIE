#!/usr/bin/env python3
"""
Spatial QCIA - GPS-Precise Intervention Design
Finds optimal locations for flood mitigation infrastructure
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../fast-solver'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import numpy as np
import random
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass
import json

from intervention_library import INTERVENTION_CATALOG, get_intervention, estimate_cost_scenario

@dataclass
class Intervention:
    """A specific intervention placed at a location"""
    type_key: str  # Key from INTERVENTION_CATALOG
    location: Tuple[int, int]  # (i, j) grid coordinates
    lat_lon: Optional[Tuple[float, float]] = None  # GPS coordinates
    size: float = 1.0  # Length for drains, count for culverts
    cost: float = 0
    
    def __post_init__(self):
        spec = get_intervention(self.type_key)
        self.cost = spec.total_cost(self.size)


class SpatialDesign:
    """A complete spatial design with multiple interventions"""
    
    def __init__(self, grid_shape, bounds):
        self.grid_shape = grid_shape  # (ny, nx)
        self.bounds = bounds  # (minx, miny, maxx, maxy) in lat/lon
        self.interventions: List[Intervention] = []
        self._compute_transform()
    
    def _compute_transform(self):
        """Compute grid to lat/lon transform"""
        ny, nx = self.grid_shape
        minx, miny, maxx, maxy = self.bounds
        self.dy = (maxy - miny) / ny
        self.dx = (maxx - minx) / nx
    
    def grid_to_latlon(self, i, j):
        """Convert grid (i,j) to (lat, lon)"""
        minx, miny, maxx, maxy = self.bounds
        lon = minx + j * self.dx
        lat = maxy - i * self.dy  # Note: i=0 is top
        return (lat, lon)
    
    def add_intervention(self, type_key: str, location: Tuple[int, int], size: float = 1.0):
        """Add intervention at grid location"""
        lat_lon = self.grid_to_latlon(*location)
        interv = Intervention(
            type_key=type_key,
            location=location,
            lat_lon=lat_lon,
            size=size
        )
        self.interventions.append(interv)
    
    def total_cost(self) -> float:
        """Total capital cost of design"""
        return sum(i.cost for i in self.interventions)
    
    def copy(self):
        """Deep copy of design"""
        new_design = SpatialDesign(self.grid_shape, self.bounds)
        for interv in self.interventions:
            new_design.add_intervention(interv.type_key, interv.location, interv.size)
        return new_design
    
    def to_dict(self):
        """Convert to JSON-serializable dict"""
        return {
            'total_cost_cr': self.total_cost() / 1e7,
            'num_interventions': len(self.interventions),
            'interventions': [
                {
                    'type': get_intervention(i.type_key).name,
                    'type_key': i.type_key,
                    'location_grid': i.location,
                    'lat_lon': i.lat_lon,
                    'size': i.size,
                    'cost_lakh': i.cost / 1e5
                }
                for i in self.interventions
            ]
        }


class FloodHotspotAnalyzer:
    """Identifies critical flood locations from simulation"""
    
    def __init__(self, flood_depth: np.ndarray, dem: np.ndarray, road_mask: np.ndarray):
        self.flood_depth = flood_depth
        self.dem = dem
        self.road_mask = road_mask
        self.ny, self.nx = flood_depth.shape
    
    def find_culvert_locations(self, n_locations: int = 10) -> List[Tuple[int, int]]:
        """
        Find best locations for culverts
        Strategy: Low elevation + high flooding + NOT on existing roads
        """
        # Criteria: deep flooding + low elevation
        score = self.flood_depth * (1.0 / (self.dem + 1e-6))
        
        # Penalize existing roads (culverts go under roads, not random places)
        # Actually, culverts SHOULD be near roads for drainage
        score = score * (1 + self.road_mask * 2.0)  # Prefer near roads
        
        # Find top N locations
        flat_indices = np.argsort(score.ravel())[::-1]
        locations = []
        
        min_spacing = 5  # Min 5 cells apart
        for idx in flat_indices:
            i, j = np.unravel_index(idx, score.shape)
            
            # Check spacing constraint
            too_close = False
            for (li, lj) in locations:
                if abs(i - li) < min_spacing and abs(j - lj) < min_spacing:
                    too_close = True
                    break
            
            if not too_close and 2 < i < self.ny-2 and 2 < j < self.nx-2:  # Not on boundary
                locations.append((int(i), int(j)))
            
            if len(locations) >= n_locations:
                break
        
        return locations
    
    def find_drain_routes(self, n_routes: int = 5) -> List[List[Tuple[int, int]]]:
        """
        Find best routes for drains
        Strategy: Place drains along flooded roads (simplified but effective)
        """
        routes = []
        
        # Find flooded road segments
        flooded_roads = (self.flood_depth > 0.5) & (self.road_mask == 1)
        
        if not np.any(flooded_roads):
            return routes
        
        # Get connected components of flooded roads
        from scipy import ndimage
        labeled, num_features = ndimage.label(flooded_roads)
        
        # For each connected component, create a drain route
        for label in range(1, min(num_features + 1, n_routes + 1)):
            route_cells = np.where(labeled == label)
            if len(route_cells[0]) > 10:  # Min 10 cells = 500m
                route = list(zip(route_cells[0], route_cells[1]))
                routes.append(route)
        
        # If scipy not available or no routes found, create simple routes
        if len(routes) == 0:
            # Find flooded road cells
            flooded_indices = np.where(flooded_roads)
            if len(flooded_indices[0]) > 0:
                # Group into linear routes (simple heuristic)
                for start_idx in range(0, min(len(flooded_indices[0]), 50), 10):
                    route = []
                    for offset in range(10):
                        idx = start_idx + offset
                        if idx < len(flooded_indices[0]):
                            i, j = flooded_indices[0][idx], flooded_indices[1][idx]
                            route.append((int(i), int(j)))
                    if len(route) > 5:
                        routes.append(route)
                        if len(routes) >= n_routes:
                            break
        
        return routes
    
    def find_pond_locations(self, n_locations: int = 3) -> List[Tuple[int, int]]:
        """
        Find best locations for detention ponds
        Strategy: Natural depressions (local minima) with high flooding
        """
        locations = []
        
        # Find local minima in DEM
        for i in range(5, self.ny-5, 5):  # Sample grid
            for j in range(5, self.nx-5, 5):
                # Check if local minimum
                window = self.dem[i-2:i+3, j-2:j+3]
                if self.dem[i, j] == np.min(window):
                    # Check if flooded
                    if self.flood_depth[i, j] > 0.5:
                        # Check spacing
                        too_close = False
                        for (li, lj) in locations:
                            dist = np.sqrt((i - li)**2 + (j - lj)**2)
                            if dist < 10:  # Min 10 cells = 500m apart
                                too_close = True
                                break
                        
                        if not too_close:
                            locations.append((int(i), int(j)))
        
        # Sort by flooding depth
        locations = sorted(locations, key=lambda loc: self.flood_depth[loc], reverse=True)
        
        return locations[:n_locations]


class SpatialQCIA:
    """
    Quantum-Inspired Causal Intelligence for Spatial Optimization
    """
    
    def __init__(self, 
                 baseline_flood: np.ndarray,
                 dem: np.ndarray,
                 road_mask: np.ndarray,
                 bounds: Tuple[float, float, float, float],
                 budget_max: float):
        """
        Initialize spatial optimizer
        
        Args:
            baseline_flood: Flood depth map (baseline scenario)
            dem: Digital elevation model
            road_mask: Binary mask of roads
            bounds: (minx, miny, maxx, maxy) in lat/lon
            budget_max: Maximum budget in rupees
        """
        self.baseline_flood = baseline_flood
        self.dem = dem
        self.road_mask = road_mask
        self.bounds = bounds
        self.budget_max = budget_max
        
        self.ny, self.nx = baseline_flood.shape
        
        # Analyze hotspots
        self.analyzer = FloodHotspotAnalyzer(baseline_flood, dem, road_mask)
        
        # Candidate locations
        self.culvert_candidates = self.analyzer.find_culvert_locations(15)
        self.drain_candidates = self.analyzer.find_drain_routes(5)
        self.pond_candidates = self.analyzer.find_pond_locations(5)
        
        print(f"\n📍 Identified Candidate Locations:")
        print(f"   Culverts: {len(self.culvert_candidates)} locations")
        print(f"   Drains: {len(self.drain_candidates)} routes")
        print(f"   Ponds: {len(self.pond_candidates)} locations")
    
    def generate_random_design(self, target_cost_fraction: float = 0.8) -> SpatialDesign:
        """Generate a random feasible design"""
        design = SpatialDesign(self.baseline_flood.shape, self.bounds)
        
        target_cost = self.budget_max * target_cost_fraction
        
        # IMPROVED: Weighted intervention selection (more balanced)
        intervention_pool = (
            ['culvert'] * 4 +      # 40% culverts
            ['drain'] * 3 +        # 30% drains
            ['pond'] * 2 +         # 20% ponds
            ['pump'] * 1           # 10% pumps
        )
        
        attempts = 0
        max_attempts = 50
        
        # Randomly add interventions until budget reached
        while design.total_cost() < target_cost and attempts < max_attempts:
            attempts += 1
            choice = random.choice(intervention_pool)
            
            if choice == 'culvert' and self.culvert_candidates:
                loc = random.choice(self.culvert_candidates)
                culvert_type = random.choice(['culvert_box_2x2', 'culvert_box_3x3'])
                design.add_intervention(culvert_type, loc, size=1.0)
            
            elif choice == 'drain' and self.drain_candidates:
                route = random.choice(self.drain_candidates)
                if len(route) > 5:
                    drain_type = random.choice(['drain_rcc_1m', 'drain_rcc_1.5m'])
                    start = route[0]
                    length = min(len(route) * 50, 2000)  # Max 2km per drain
                    design.add_intervention(drain_type, start, size=length)
            
            elif choice == 'pond' and self.pond_candidates:
                loc = random.choice(self.pond_candidates)
                pond_type = random.choice(['pond_medium', 'pond_large'])
                design.add_intervention(pond_type, loc, size=1.0)
            
            elif choice == 'pump' and self.culvert_candidates:
                # Place pumps at low elevation points
                loc = random.choice(self.culvert_candidates[:5])  # Top 5 low points
                pump_type = random.choice(['pump_small', 'pump_medium'])
                design.add_intervention(pump_type, loc, size=1.0)
            
            # Stop if over budget
            if design.total_cost() > self.budget_max:
                # Remove last intervention
                if len(design.interventions) > 0:
                    design.interventions.pop()
                break
        
        return design
    
    def optimize(self, n_steps: int = 100, verbose: bool = True) -> SpatialDesign:
        """
        Find optimal spatial design using quantum-inspired annealing
        """
        if verbose:
            print(f"\n{'='*70}")
            print(f"SPATIAL OPTIMIZATION - QUANTUM ANNEALING")
            print(f"{'='*70}")
            print(f"  Budget: ₹{self.budget_max/1e7:.1f} Crores")
            print(f"  Search steps: {n_steps}")
        
        # Initialize with aggressive design (use 85% of budget)
        current_design = self.generate_random_design(0.85)
        current_score = self._evaluate_design(current_design)
        
        best_design = current_design.copy()
        best_score = current_score
        
        # Annealing parameters
        T_init = 100.0
        T_final = 0.1
        gamma_init = 50.0
        
        history = []
        
        for step in range(n_steps):
            t = step / n_steps
            T = T_init * (T_final / T_init) ** t
            gamma = gamma_init * (1 - t)
            
            # Quantum tunneling probability
            tunnel_prob = gamma / T_init
            
            # Generate new design
            if random.random() < tunnel_prob:
                # Quantum jump: completely new design (use 70-95% of budget)
                new_design = self.generate_random_design(random.uniform(0.7, 0.95))
                move_type = "🌀 QUANTUM JUMP"
            else:
                # Local perturbation
                new_design = self._perturb_design(current_design)
                move_type = "🔧 Local move"
            
            # Evaluate
            new_score = self._evaluate_design(new_design)
            
            # Metropolis acceptance
            delta = new_score - current_score
            if delta < 0 or random.random() < np.exp(-delta / T):
                current_design = new_design
                current_score = new_score
                
                if current_score < best_score:
                    best_design = current_design.copy()
                    best_score = current_score
                    
                    if verbose and step % 10 == 0:
                        print(f"\nStep {step:3d}: {move_type}")
                        print(f"  ✅ NEW BEST! Score: {best_score:.2f}")
                        print(f"  Cost: ₹{best_design.total_cost()/1e7:.2f} Cr")
                        print(f"  Interventions: {len(best_design.interventions)}")
            
            history.append({
                'step': step,
                'score': current_score,
                'best_score': best_score,
                'temperature': T
            })
        
        if verbose:
            print(f"\n{'='*70}")
            print(f"✅ OPTIMIZATION COMPLETE")
            print(f"{'='*70}")
            print(f"  Final Score: {best_score:.2f}")
            print(f"  Total Cost: ₹{best_design.total_cost()/1e7:.2f} Cr")
            print(f"  Interventions: {len(best_design.interventions)}")
        
        return best_design
    
    def _perturb_design(self, design: SpatialDesign) -> SpatialDesign:
        """Make small modification to design"""
        new_design = design.copy()
        
        action = random.choice(['add', 'remove', 'replace'])
        
        if action == 'add' and new_design.total_cost() < self.budget_max * 0.9:
            # Add random intervention
            choice = random.choice(['culvert', 'drain', 'pond'])
            if choice == 'culvert' and self.culvert_candidates:
                loc = random.choice(self.culvert_candidates)
                new_design.add_intervention('culvert_box_2x2', loc)
        
        elif action == 'remove' and len(new_design.interventions) > 1:
            # Remove random intervention
            idx = random.randint(0, len(new_design.interventions) - 1)
            del new_design.interventions[idx]
        
        elif action == 'replace' and len(new_design.interventions) > 0:
            # Replace one intervention
            idx = random.randint(0, len(new_design.interventions) - 1)
            del new_design.interventions[idx]
            
            if self.culvert_candidates:
                loc = random.choice(self.culvert_candidates)
                new_design.add_intervention('culvert_box_2x2', loc)
        
        return new_design
    
    def _evaluate_design(self, design: SpatialDesign) -> float:
        """
        Evaluate design quality
        (Simplified: in full version, would re-run flood simulation)
        
        Lower score = better design
        """
        # Cost tracking
        cost = design.total_cost()
        cost_cr = cost / 1e7
        budget_cr = self.budget_max / 1e7
        
        # Estimate flood reduction (heuristic based on intervention types)
        flood_reduction = 0
        for interv in design.interventions:
            spec = get_intervention(interv.type_key)
            
            # Capacity-based estimates
            if spec.type == 'culvert':
                capacity = spec.capacity_m3_s
                flood_reduction += capacity * 0.01  # Each m³/s reduces ~1% flooding
            elif spec.type == 'drain':
                # Drains are very effective per cost
                drain_km = interv.size / 1000
                flood_reduction += drain_km * 0.05  # 5% per km
            elif spec.type == 'storage':
                # Ponds reduce peak flooding significantly
                flood_reduction += 0.08  # 8% per pond
            elif spec.type == 'active':
                # Pumps are effective but need power
                capacity = spec.capacity_m3_s
                flood_reduction += capacity * 0.015  # 1.5% per m³/s
        
        # Cap reduction at realistic max (40%)
        flood_reduction = min(flood_reduction, 0.40)
        
        # OBJECTIVE COMPONENTS:
        
        # 1. Flood score (want low flooding)
        flood_score = (1.0 - flood_reduction) * 60  # Scale: 0-60
        
        # 2. Cost efficiency (want to use budget effectively)
        budget_utilization = cost_cr / budget_cr
        if budget_utilization < 0.7:
            # PENALTY for under-spending
            under_spend_penalty = (0.7 - budget_utilization) * 50
        else:
            under_spend_penalty = 0
        
        if budget_utilization > 1.0:
            # PENALTY for over-spending
            over_spend_penalty = (budget_utilization - 1.0) * 100
        else:
            over_spend_penalty = 0
        
        # 3. Diversity bonus (reward using multiple intervention types)
        types_used = len(set(get_intervention(i.type_key).type for i in design.interventions))
        diversity_bonus = -types_used * 2  # Negative = good (we're minimizing)
        
        # TOTAL SCORE (lower = better)
        total_score = (
            flood_score +                # Want low flooding (60 = baseline, 0 = perfect)
            cost_cr * 0.3 +             # Small cost penalty (prefer cheaper if equal flood reduction)
            under_spend_penalty +        # Penalize not using budget
            over_spend_penalty +         # Penalize over-budget
            diversity_bonus              # Reward diverse solutions
        )
        
        return total_score


# =============================================================================
# EXAMPLE USAGE
# =============================================================================

if __name__ == "__main__":
    print("="*70)
    print("SPATIAL QCIA - DEMO")
    print("="*70)
    
    # Create synthetic baseline flood
    ny, nx = 100, 100
    baseline_flood = np.random.rand(ny, nx) * 2.0  # Random flooding
    dem = np.random.rand(ny, nx) * 100 + 400  # Elevation 400-500m
    road_mask = np.zeros((ny, nx))
    road_mask[20:80, 45:55] = 1  # Vertical road
    road_mask[45:55, 20:80] = 1  # Horizontal road
    
    bounds = (79.98, 22.98, 80.02, 23.02)  # Jabalpur-like
    budget = 12e7  # ₹12 Crores
    
    # Run optimization
    optimizer = SpatialQCIA(baseline_flood, dem, road_mask, bounds, budget)
    optimal_design = optimizer.optimize(n_steps=50, verbose=True)
    
    # Print result
    print("\n" + "="*70)
    print("OPTIMAL DESIGN")
    print("="*70)
    
    design_dict = optimal_design.to_dict()
    print(f"\n💰 Total Cost: ₹{design_dict['total_cost_cr']:.2f} Crores")
    print(f"📍 Interventions: {design_dict['num_interventions']}")
    
    print("\n📋 Intervention List:")
    for i, interv in enumerate(design_dict['interventions'], 1):
        print(f"\n  [{i}] {interv['type']}")
        print(f"      Location: ({interv['lat_lon'][0]:.4f}°N, {interv['lat_lon'][1]:.4f}°E)")
        print(f"      Grid: {interv['location_grid']}")
        if interv['size'] > 1:
            print(f"      Size: {interv['size']:.0f} units")
        print(f"      Cost: ₹{interv['cost_lakh']:.1f} lakh")
    
    # Save to JSON
    with open('optimal_design_demo.json', 'w') as f:
        json.dump(design_dict, f, indent=2)
    
    print(f"\n✅ Design saved to: optimal_design_demo.json")
    print("="*70)

