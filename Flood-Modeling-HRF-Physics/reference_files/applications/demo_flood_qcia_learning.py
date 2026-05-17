#!/usr/bin/env python3
"""
QCIA Iterative Learning Demo: Shows AI improving flood mitigation designs over multiple iterations.

This demonstrates the complete learning loop:
1. Generate intervention designs (initially random/heuristic)
2. Test designs with HRF simulation
3. Collect experience (features + outcomes)
4. Learn causal graph from accumulated experiences
5. Use learned knowledge to generate BETTER designs
6. Repeat → AI gets smarter each iteration

This is the key innovation: QCIA LEARNS what works from physics simulations.

Author: QCIA Learning Loop
"""
from __future__ import annotations

import sys
import json
import argparse
from pathlib import Path
from typing import Dict, List
import numpy as np

# Setup paths
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "AI"))
sys.path.insert(0, str(_ROOT / "Flood_Resilience_Demo"))

from Flood_Resilience_Demo.Physics.hrf import Grid, SWEParams, ExponentialFilter, HRFSolver

# Import AI modules
from AI.applications.flood_analyzer import FloodAnalyzer
from AI.applications.intervention_applier import apply_qcia_design_to_solver
from AI.applications.flood_experience_collector import FloodExperienceCollector
from AI.applications.flood_causal_discovery import FloodCausalDiscovery


def create_terrain(nx: int, ny: int, Lx: float, Ly: float) -> np.ndarray:
    """Create synthetic terrain."""
    x = np.linspace(0, Lx, nx)
    y = np.linspace(0, Ly, ny)
    X, Y = np.meshgrid(x, y, indexing='ij')
    
    # Overall slope
    base = 10.0 - 0.005 * X - 0.005 * Y
    
    # Depression
    center_x, center_y = Lx / 2, Ly / 2
    depression_r = Lx * 0.15
    dist_to_center = np.sqrt((X - center_x)**2 + (Y - center_y)**2)
    depression = -2.0 * np.exp(-((dist_to_center / depression_r)**2))
    
    # Roughness
    roughness = 0.2 * np.random.randn(nx, ny)
    
    terrain = base + depression + roughness
    terrain = terrain - np.min(terrain)
    
    return terrain


def run_simulation(dem: np.ndarray, 
                   grid: Grid,
                   interventions: List[Dict] = None,
                   verbose: bool = False) -> Dict:
    """Run flood simulation (with or without interventions)."""
    nx, ny = grid.nx, grid.ny
    
    prm = SWEParams(
        g=9.81, manning_n=0.06, h_min=1e-3, cfl=0.15,
        vmax_guard_coef=0.7, dt_max=0.5
    )
    
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
    
    # Apply interventions if provided
    if interventions:
        design_temp = {'interventions': interventions}
        temp_path = Path(f"/tmp/qcia_design_temp.json")
        with open(temp_path, 'w') as f:
            json.dump(design_temp, f)
        apply_qcia_design_to_solver(solver, grid, temp_path, verbose=False)
    
    logs = solver.run(t_end=5400.0, output_every=600.0, verbose=verbose)
    
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


def generate_interventions_heuristic(hotspots: List[Dict], 
                                     exploration_rate: float = 0.2) -> List[Dict]:
    """
    Generate interventions using simple heuristics + random exploration.
    
    This is used in early iterations before causal model is learned.
    """
    interventions = []
    
    for h in hotspots:
        # Base sizing on hotspot characteristics
        volume_needed = h['area_m2'] * h['mean_depth_m'] * 0.8
        
        # Add random exploration
        if np.random.rand() < exploration_rate:
            volume_needed *= np.random.uniform(0.5, 1.5)
        
        depth = 2.0
        diameter = 2.0 * np.sqrt(volume_needed / (np.pi * depth / 4))
        
        intervention = {
            'type': 'detention_basin',
            'id': f"basin_{h['id']:03d}",
            'location': h['location'],
            'grid_indices': h['grid_indices'],
            'diameter_m': float(diameter),
            'depth_m': float(depth),
            'storage_volume_m3': float(volume_needed)
        }
        
        interventions.append(intervention)
    
    return interventions


def generate_interventions_from_causal_model(hotspots: List[Dict],
                                             causal_discovery: FloodCausalDiscovery,
                                             grid: Grid,
                                             dem: np.ndarray) -> List[Dict]:
    """
    Generate interventions using learned causal model.
    
    This is used after causal graph is learned from previous iterations.
    """
    interventions = []
    
    for h in hotspots:
        i = h['grid_indices']['i']
        j = h['grid_indices']['j']
        
        # Build spatial context
        spatial_context = {
            'elevation_m': float(dem[i, j]),
            'slope': 0.01,  # Placeholder
            'flow_accumulation': float(np.max(dem) - dem[i, j]),
            'baseline_flood_depth_m': h['mean_depth_m']
        }
        
        # Use causal model to recommend parameters
        recommended_params = causal_discovery.recommend_optimal_intervention_params(
            spatial_context,
            target_depth_reduction_m=h['mean_depth_m'] * 0.8
        )
        
        # If model recommends something, use it; otherwise fall back to heuristic
        if recommended_params:
            volume = recommended_params.get('intervention_volume_m3', 5000.0)
            diameter = recommended_params.get('intervention_diameter_m', 50.0)
            depth = recommended_params.get('intervention_depth_m', 2.0)
        else:
            volume = h['area_m2'] * h['mean_depth_m'] * 0.8
            depth = 2.0
            diameter = 2.0 * np.sqrt(volume / (np.pi * depth / 4))
        
        intervention = {
            'type': 'detention_basin',
            'id': f"basin_{h['id']:03d}",
            'location': h['location'],
            'grid_indices': h['grid_indices'],
            'diameter_m': float(diameter),
            'depth_m': float(depth),
            'storage_volume_m3': float(volume)
        }
        
        interventions.append(intervention)
    
    return interventions


def main():
    """Main iterative learning loop."""
    parser = argparse.ArgumentParser(description="QCIA Iterative Learning Demo")
    parser.add_argument('--nx', type=int, default=80, help='Grid cells in x')
    parser.add_argument('--ny', type=int, default=80, help='Grid cells in y')
    parser.add_argument('--dx', type=float, default=25.0, help='Cell size (m)')
    parser.add_argument('--iterations', type=int, default=5, help='Learning iterations')
    parser.add_argument('--hotspots', type=int, default=3, help='Number of hotspots per iteration')
    parser.add_argument('--output', type=str, default='outputs/qcia_learning_demo', help='Output directory')
    args = parser.parse_args()
    
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'#'*70}")
    print(f"#  QCIA ITERATIVE LEARNING DEMO")
    print(f"#  AI learns to design better flood interventions over time")
    print(f"{'#'*70}\n")
    
    # Create terrain and grid
    nx, ny = args.nx, args.ny
    dx, dy = args.dx, args.dx
    Lx, Ly = nx * dx, ny * dy
    
    print(f"[Setup] Creating {nx}x{ny} grid ({Lx:.0f}m x {Ly:.0f}m)...")
    dem = create_terrain(nx, ny, Lx, Ly)
    grid = Grid(nx=nx, ny=ny, Lx=Lx, Ly=Ly)
    
    # Run baseline simulation once
    print(f"\n[Baseline] Running simulation without interventions...")
    baseline_results = run_simulation(dem, grid, interventions=None, verbose=True)
    print(f"   Max depth: {baseline_results['max_depth']:.2f}m")
    print(f"   Flooded area: {baseline_results['flooded_area_m2']:.0f}m²")
    
    # Initialize learning components
    experience_collector = FloodExperienceCollector(verbose=True)
    causal_discovery = FloodCausalDiscovery(alpha=0.10, verbose=True)  # Higher alpha = more edges
    
    # Track performance over iterations
    iteration_history = []
    
    # Iterative learning loop
    for iteration in range(1, args.iterations + 1):
        print(f"\n{'='*70}")
        print(f"ITERATION {iteration}/{args.iterations}")
        print(f"{'='*70}\n")
        
        # Identify hotspots
        print(f"[{iteration}.1] Identifying flood hotspots...")
        analyzer = FloodAnalyzer(grid, baseline_results['final_h'], baseline_results['bed'], verbose=False)
        hotspots = analyzer.identify_hotspots(threshold_m=0.2, top_n=args.hotspots)
        print(f"   Found {len(hotspots)} hotspots")
        
        if not hotspots:
            print("   No hotspots found. Stopping.")
            break
        
        # Generate interventions
        print(f"\n[{iteration}.2] Generating intervention designs...")
        
        if iteration == 1 or len(experience_collector.experiences) < 2:
            # First iteration: use heuristics
            print(f"   Strategy: Heuristic (no causal model yet)")
            interventions = generate_interventions_heuristic(hotspots, exploration_rate=0.3)
        else:
            # Later iterations: use causal model
            print(f"   Strategy: Causal model-guided")
            interventions = generate_interventions_from_causal_model(
                hotspots, causal_discovery, grid, dem
            )
        
        print(f"   Generated {len(interventions)} interventions")
        
        # Run simulation with interventions
        print(f"\n[{iteration}.3] Testing interventions with HRF simulation...")
        mitigated_results = run_simulation(dem, grid, interventions=interventions, verbose=False)
        print(f"   Max depth: {mitigated_results['max_depth']:.2f}m")
        print(f"   Flooded area: {mitigated_results['flooded_area_m2']:.0f}m²")
        
        # Calculate improvement
        depth_improvement = ((baseline_results['max_depth'] - mitigated_results['max_depth']) / 
                            baseline_results['max_depth'] * 100)
        area_improvement = ((baseline_results['flooded_area_m2'] - mitigated_results['flooded_area_m2']) / 
                           baseline_results['flooded_area_m2'] * 100)
        
        print(f"\n   📊 Improvement:")
        print(f"      Max depth: {depth_improvement:+.1f}%")
        print(f"      Flooded area: {area_improvement:+.1f}%")
        
        # Collect experience
        print(f"\n[{iteration}.4] Collecting experience for learning...")
        experience = experience_collector.collect_experience(
            grid=grid,
            baseline_results=baseline_results,
            mitigated_results=mitigated_results,
            interventions=interventions,
            design_storm_mm_hr=50.0,
            duration_hr=1.5
        )
        
        # Learn causal graph (if enough data)
        if len(experience_collector.experiences) >= 2:
            print(f"\n[{iteration}.5] Learning causal relationships...")
            features_matrix, feature_names = experience_collector.get_feature_matrix_for_causal_discovery()
            
            if features_matrix.shape[0] >= 3:  # Need at least 3 samples
                causal_graph = causal_discovery.discover_from_experiences(features_matrix, feature_names)
                
                # Save causal graph
                causal_discovery.export_causal_graph(
                    output_dir / f"causal_graph_iteration_{iteration}.json"
                )
                causal_discovery.visualize_causal_graph(
                    output_dir / f"causal_graph_iteration_{iteration}.png"
                )
            else:
                print(f"   ⚠️  Not enough samples yet ({features_matrix.shape[0]}/3)")
        
        # Track history
        iteration_history.append({
            'iteration': iteration,
            'baseline_max_depth': baseline_results['max_depth'],
            'mitigated_max_depth': mitigated_results['max_depth'],
            'depth_improvement_pct': depth_improvement,
            'area_improvement_pct': area_improvement,
            'num_interventions': len(interventions),
            'strategy': 'heuristic' if iteration == 1 else 'causal'
        })
    
    # Save final results
    print(f"\n{'='*70}")
    print(f"LEARNING COMPLETE")
    print(f"{'='*70}\n")
    
    # Save experiences
    experience_collector.save_experiences(output_dir / "all_experiences.json")
    
    # Save iteration history
    with open(output_dir / "iteration_history.json", 'w') as f:
        json.dump({'iterations': iteration_history}, f, indent=2)
    
    # Print summary
    print(f"ITERATION SUMMARY:")
    print(f"{'-'*70}")
    print(f"{'Iter':<6} {'Strategy':<12} {'Max Depth (m)':<15} {'Improvement':<12}")
    print(f"{'-'*70}")
    
    for hist in iteration_history:
        print(f"{hist['iteration']:<6} {hist['strategy']:<12} "
              f"{hist['mitigated_max_depth']:<15.2f} {hist['depth_improvement_pct']:+.1f}%")
    
    print(f"{'-'*70}\n")
    
    # Check if AI improved over iterations
    if len(iteration_history) >= 2:
        first_improvement = iteration_history[0]['depth_improvement_pct']
        last_improvement = iteration_history[-1]['depth_improvement_pct']
        learning_gain = last_improvement - first_improvement
        
        print(f"🎯 LEARNING OUTCOME:")
        print(f"   First iteration: {first_improvement:+.1f}% improvement")
        print(f"   Last iteration:  {last_improvement:+.1f}% improvement")
        print(f"   Learning gain:   {learning_gain:+.1f} percentage points")
        
        if learning_gain > 5:
            print(f"   ✅ AI learned to design better interventions!")
        elif learning_gain > 0:
            print(f"   📈 AI showed modest improvement")
        else:
            print(f"   ⚠️  AI did not improve (may need more iterations or better features)")
    
    print(f"\n✅ Results saved to: {output_dir}")
    print(f"\n{'#'*70}\n")


if __name__ == "__main__":
    main()

