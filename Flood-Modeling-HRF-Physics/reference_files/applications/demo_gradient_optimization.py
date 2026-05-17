#!/usr/bin/env python3
"""
Gradient-Optimized Flood Mitigation Demo

Uses gradient descent to optimize intervention parameters instead of grid search.
Much faster and more effective than LEVEL 2 iterative learning.

Author: QCIA Gradient Optimization Layer
"""
from __future__ import annotations

import sys
import json
import argparse
from pathlib import Path
import numpy as np

# Setup paths
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "AI"))
sys.path.insert(0, str(_ROOT / "Flood_Resilience_Demo"))

from Flood_Resilience_Demo.Physics.hrf import Grid, SWEParams, ExponentialFilter, HRFSolver
from AI.applications.flood_analyzer import FloodAnalyzer
from AI.applications.intervention_applier import apply_qcia_design_to_solver
from AI.applications.gradient_optimizer import AdamOptimizer
from AI.applications.hydrological_analyzer import HydrologicalAnalyzer


def create_terrain(nx: int, ny: int, Lx: float, Ly: float) -> np.ndarray:
    """Create synthetic terrain with flood-prone depression."""
    x = np.linspace(0, Lx, nx)
    y = np.linspace(0, Ly, ny)
    X, Y = np.meshgrid(x, y, indexing='ij')
    
    base = 10.0 - 0.005 * X - 0.005 * Y
    center_x, center_y = Lx / 2, Ly / 2
    depression_r = Lx * 0.15
    dist_to_center = np.sqrt((X - center_x)**2 + (Y - center_y)**2)
    depression = -2.0 * np.exp(-((dist_to_center / depression_r)**2))
    roughness = 0.2 * np.random.randn(nx, ny)
    
    terrain = base + depression + roughness
    return terrain - np.min(terrain)


def run_simulation(dem: np.ndarray, grid: Grid, interventions: list = None) -> dict:
    """Run HRF simulation with optional interventions."""
    nx, ny = grid.nx, grid.ny
    prm = SWEParams(g=9.81, manning_n=0.06, h_min=1e-3, cfl=0.15, vmax_guard_coef=0.7, dt_max=0.5)
    filt = ExponentialFilter(alpha=96.0, p=8)
    solver = HRFSolver(grid, prm, filt)
    solver.mode = "dw_fv"
    
    h0 = np.full((nx, ny), 0.0)
    u0 = np.zeros_like(h0)
    v0 = np.zeros_like(h0)
    solver.initialize(h0, u0, v0)
    
    rain_rate_mps = (50.0 / 1000.0) / 3600.0
    infil_rate_mps = 1e-8
    solver.set_forcing(bed=dem.copy(), rain_rate=rain_rate_mps, infil_rate=infil_rate_mps)
    
    if interventions:
        design_temp = {'interventions': interventions}
        temp_path = Path("/tmp/qcia_design_gradient.json")
        with open(temp_path, 'w') as f:
            json.dump(design_temp, f)
        apply_qcia_design_to_solver(solver, grid, temp_path, verbose=False)
    
    solver.run(t_end=5400.0, output_every=1800.0, verbose=False)
    
    final_h = solver.h.copy()
    max_depth = float(np.max(final_h))
    flooded_area = float(np.sum(final_h > 0.1)) * (grid.dx * grid.dy)
    total_volume = float(np.sum(final_h)) * (grid.dx * grid.dy)
    
    return {
        'final_h': final_h,
        'bed': solver.bed,
        'max_depth': max_depth,
        'flooded_area_m2': flooded_area,
        'total_volume_m3': total_volume
    }


def main():
    parser = argparse.ArgumentParser(description="Gradient-Optimized Flood Mitigation")
    parser.add_argument('--nx', type=int, default=80, help='Grid cells x')
    parser.add_argument('--ny', type=int, default=80, help='Grid cells y')
    parser.add_argument('--dx', type=float, default=25.0, help='Cell size (m)')
    parser.add_argument('--output', type=str, default='outputs/gradient_optimization_demo', help='Output directory')
    args = parser.parse_args()
    
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'#'*70}")
    print(f"#  GRADIENT-OPTIMIZED FLOOD MITIGATION")
    print(f"#  Using Adam optimizer for fast, effective design")
    print(f"{'#'*70}\n")
    
    # Setup
    nx, ny = args.nx, args.ny
    dx, dy = args.dx, args.dx
    Lx, Ly = nx * dx, ny * dy
    
    print(f"[1/5] Creating terrain...")
    dem = create_terrain(nx, ny, Lx, Ly)
    grid = Grid(nx=nx, ny=ny, Lx=Lx, Ly=Ly)
    
    print(f"\n[2/5] Running baseline simulation...")
    baseline = run_simulation(dem, grid, interventions=None)
    print(f"   Baseline max depth: {baseline['max_depth']:.2f}m")
    print(f"   Baseline flooded area: {baseline['flooded_area_m2']:.0f}m²")
    
    print(f"\n[3/5] Identifying hotspots and computing upstream interception points...")
    analyzer = FloodAnalyzer(grid, baseline['final_h'], baseline['bed'], verbose=False)
    hotspots = analyzer.identify_hotspots(threshold_m=0.2, top_n=2)
    print(f"   Found {len(hotspots)} major hotspots")
    
    # NEW: Use hydrological analysis to find UPSTREAM locations
    hydro_analyzer = HydrologicalAnalyzer(baseline['bed'], grid.dx, grid.dy, verbose=True)
    interception_points = hydro_analyzer.find_upstream_interception_points(
        hotspots, 
        n_points=1,  # 1 interception point per hotspot
        min_distance_m=50.0,
        min_accumulation=50.0
    )
    
    if not interception_points:
        print("   ⚠️  No suitable upstream locations found, falling back to hotspot centers")
        interception_points = None
    
    if not hotspots:
        print("   No hotspots found!")
        return
    
    # For each hotspot, optimize intervention parameters at UPSTREAM locations
    print(f"\n[4/5] Optimizing intervention designs with Adam...")
    
    optimized_interventions = []
    
    # Decide whether to use upstream locations or hotspot centers
    use_upstream = interception_points is not None and len(interception_points) > 0
    
    for idx, hotspot in enumerate(hotspots):
        print(f"\n--- Optimizing intervention {idx+1} for hotspot {hotspot['id']} ---")
        
        # Use UPSTREAM interception point if available, otherwise hotspot center
        if use_upstream and idx < len(interception_points):
            point = interception_points[idx]
            intervention_i = point.grid_i
            intervention_j = point.grid_j
            placement_strategy = "UPSTREAM"
            print(f"    Strategy: {placement_strategy} interception")
            print(f"    Reasoning: {point.reasoning}")
        else:
            intervention_i = hotspot['grid_indices']['i']
            intervention_j = hotspot['grid_indices']['j']
            placement_strategy = "HOTSPOT"
            print(f"    Strategy: {placement_strategy} (fallback)")
        
        # Convert grid to lat/lon (approximate)
        ref_lat, ref_lon = 23.18, 79.99
        intervention_lat = ref_lat + (intervention_i - grid.nx/2) * (grid.dx / 111000.0)
        intervention_lon = ref_lon + (intervention_j - grid.ny/2) * (grid.dy / 111000.0)
        
        # Define objective function for THIS intervention location
        def objective_function(params):
            """Objective: minimize max flood depth (physics simulation)."""
            # Create intervention from parameters
            intervention = {
                'type': 'detention_basin',
                'id': f'basin_opt_{idx+1}',
                'location': {
                    'lat': intervention_lat,
                    'lon': intervention_lon
                },
                'grid_indices': {
                    'i': intervention_i,
                    'j': intervention_j
                },
                'volume_m3': params['volume_m3'],
                'diameter_m': params['diameter_m'],
                'depth_m': params['depth_m'],
                'storage_volume_m3': params['volume_m3']
            }
            
            # Run simulation
            result = run_simulation(dem, grid, interventions=[intervention])
            
            # Return max depth (minimize)
            return result['max_depth']
        
        # Initial guess (based on hotspot size with randomization)
        hotspot_area = hotspot['area_m2']
        estimated_volume = hotspot_area * hotspot['mean_depth_m'] * 0.5  # Conservative
        estimated_volume = max(2000.0, min(10000.0, estimated_volume))
        
        # Add randomization to avoid local minima
        volume_noise = np.random.uniform(0.8, 1.2)
        
        initial_params = {
            'volume_m3': estimated_volume * volume_noise,
            'diameter_m': 2.0 * np.sqrt(estimated_volume / (np.pi * 2.0 / 4)),
            'depth_m': 2.0 + np.random.uniform(-0.5, 0.5)
        }
        
        # Parameter bounds
        param_bounds = {
            'volume_m3': (1000.0, 20000.0),
            'diameter_m': (20.0, 150.0),
            'depth_m': (1.0, 5.0)
        }
        
        # Optimize with Adam
        optimizer = AdamOptimizer(
            objective_function=objective_function,
            learning_rate=500.0,     # Larger for faster convergence
            max_iterations=20,       # More iterations
            convergence_tol=0.001,   # Tighter tolerance
            finite_diff_epsilon=1000.0,  # Larger epsilon for better gradients
            verbose=True
        )
        
        result = optimizer.optimize(initial_params, param_bounds)
        
        # Create optimized intervention with upstream placement
        optimized_intervention = {
            'type': 'detention_basin',
            'id': f'basin_optimized_{idx+1}',
            'location': {'lat': intervention_lat, 'lon': intervention_lon},
            'grid_indices': {'i': intervention_i, 'j': intervention_j},
            'placement_strategy': placement_strategy,
            'volume_m3': result.optimal_params['volume_m3'],
            'diameter_m': result.optimal_params['diameter_m'],
            'depth_m': result.optimal_params['depth_m'],
            'storage_volume_m3': result.optimal_params['volume_m3'],
            'optimization_iterations': result.iterations,
            'initial_objective': result.convergence_history[0],
            'final_objective': result.optimal_objective
        }
        
        optimized_interventions.append(optimized_intervention)
        
        print(f"\n✅ Optimized intervention {idx+1}:")
        print(f"   Volume: {result.optimal_params['volume_m3']:.0f}m³")
        print(f"   Diameter: {result.optimal_params['diameter_m']:.1f}m")
        print(f"   Depth: {result.optimal_params['depth_m']:.1f}m")
        print(f"   Objective improvement: {result.convergence_history[0]:.3f} → {result.optimal_objective:.3f}")
    
    print(f"\n[5/5] Testing optimized design...")
    optimized_result = run_simulation(dem, grid, interventions=optimized_interventions)
    
    print(f"\n{'='*70}")
    print(f"RESULTS")
    print(f"{'='*70}")
    print(f"Baseline:")
    print(f"  Max depth: {baseline['max_depth']:.2f}m")
    print(f"  Flooded area: {baseline['flooded_area_m2']:.0f}m²")
    print(f"\nOptimized Design:")
    print(f"  Max depth: {optimized_result['max_depth']:.2f}m")
    print(f"  Flooded area: {optimized_result['flooded_area_m2']:.0f}m²")
    
    depth_improvement = ((baseline['max_depth'] - optimized_result['max_depth']) / baseline['max_depth']) * 100
    area_improvement = ((baseline['flooded_area_m2'] - optimized_result['flooded_area_m2']) / baseline['flooded_area_m2']) * 100
    
    print(f"\nImprovement:")
    print(f"  Max depth: {depth_improvement:+.1f}%")
    print(f"  Flooded area: {area_improvement:+.1f}%")
    
    # Save results
    design_output = {
        'project': 'Gradient-Optimized Flood Mitigation',
        'baseline_max_depth_m': baseline['max_depth'],
        'optimized_max_depth_m': optimized_result['max_depth'],
        'depth_improvement_pct': depth_improvement,
        'area_improvement_pct': area_improvement,
        'interventions': optimized_interventions
    }
    
    with open(output_dir / 'optimized_design.json', 'w') as f:
        json.dump(design_output, f, indent=2)
    
    print(f"\n✅ Saved optimized design to: {output_dir / 'optimized_design.json'}")
    
    if depth_improvement > 0:
        print(f"\n🎉 SUCCESS! Gradient optimization reduced flooding by {depth_improvement:.1f}%")
    else:
        print(f"\n⚠️  Design needs refinement. Try adjusting learning rate or bounds.")
    
    print(f"\n{'#'*70}\n")


if __name__ == "__main__":
    main()
