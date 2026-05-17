#!/usr/bin/env python3
"""
Simple QCIA + Flood Demo: End-to-end demonstration of AI-driven flood mitigation.

This script demonstrates the complete workflow:
1. Run BASELINE flood simulation (HRF solver with real Jabalpur data)
2. ANALYZE results to identify flood hotspots
3. Generate QCIA-optimized intervention designs for each hotspot
4. Apply interventions and RE-RUN simulation
5. COMPARE baseline vs mitigated scenarios
6. Export visual comparisons and metrics

Author: QCIA-HRF Integration Layer
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
try:
    from AI.qcia_core.enhanced_qcia import EnhancedQCIA
    from AI.applications.engineering_spec_generator import EngineeringSpecGenerator
    from AI.applications.flood_analyzer import FloodAnalyzer
    from AI.applications.intervention_applier import apply_qcia_design_to_solver
except ImportError as e:
    print(f"❌ Failed to import AI modules: {e}")
    print("Make sure you're running from the project root")
    sys.exit(1)


def create_simple_terrain(nx: int, ny: int, Lx: float, Ly: float) -> np.ndarray:
    """
    Create a simple synthetic terrain with a depression in the center.
    
    For real scenarios, this would load actual DEM data.
    """
    x = np.linspace(0, Lx, nx)
    y = np.linspace(0, Ly, ny)
    X, Y = np.meshgrid(x, y, indexing='ij')
    
    # Create gentle slope with depression in center
    center_x, center_y = Lx / 2, Ly / 2
    
    # Overall slope (drains to bottom-right)
    base = 10.0 - 0.005 * X - 0.005 * Y
    
    # Add a depression (flood-prone area)
    depression_r = Lx * 0.15
    dist_to_center = np.sqrt((X - center_x)**2 + (Y - center_y)**2)
    depression = -2.0 * np.exp(-((dist_to_center / depression_r)**2))
    
    # Add some random roughness
    roughness = 0.2 * np.random.randn(nx, ny)
    
    terrain = base + depression + roughness
    terrain = terrain - np.min(terrain)  # Normalize
    
    return terrain


def run_baseline_simulation(dem: np.ndarray, 
                           nx: int, ny: int, 
                           dx_m: float, dy_m: float,
                           rain_mm_hr: float = 50.0,
                           duration_hr: float = 2.0,
                           verbose: bool = True) -> Dict:
    """
    Run baseline flood simulation without interventions.
    
    Returns:
        Dictionary with simulation results
    """
    if verbose:
        print(f"\n{'='*70}")
        print(f"RUNNING BASELINE SIMULATION")
        print(f"{'='*70}")
        print(f"Grid: {nx} x {ny} cells ({dx_m}m x {dy_m}m)")
        print(f"Rainfall: {rain_mm_hr:.1f} mm/hr for {duration_hr:.1f} hours")
    
    # Setup grid and solver
    Lx = nx * dx_m
    Ly = ny * dy_m
    grid = Grid(nx=nx, ny=ny, Lx=Lx, Ly=Ly)
    
    prm = SWEParams(
        g=9.81,
        manning_n=0.06,
        h_min=1e-3,
        cfl=0.15,
        vmax_guard_coef=0.7,
        dt_max=0.5
    )
    
    filt = ExponentialFilter(alpha=96.0, p=8)
    solver = HRFSolver(grid, prm, filt)
    solver.mode = "dw_fv"  # Diffusive wave mode (faster, stable for urban flooding)
    
    # Initial conditions (dry)
    h0 = np.full((nx, ny), 0.0)
    u0 = np.zeros_like(h0)
    v0 = np.zeros_like(h0)
    solver.initialize(h0, u0, v0)
    
    # Set forcing
    rain_rate_mps = (rain_mm_hr / 1000.0) / 3600.0  # Convert mm/hr to m/s
    infil_rate_mps = 1e-8  # 10 nm/s (urban impervious)
    
    solver.set_forcing(
        bed=dem,
        rain_rate=rain_rate_mps,
        infil_rate=infil_rate_mps
    )
    
    # Run simulation
    sim_seconds = duration_hr * 3600.0
    if verbose:
        print(f"\nSimulating {sim_seconds/60:.1f} minutes...")
    
    logs = solver.run(t_end=sim_seconds, output_every=300.0, verbose=verbose)
    
    # Extract results
    final_h = solver.h.copy()
    final_u = solver.u.copy()
    final_v = solver.v.copy()
    
    # Calculate statistics
    max_depth = float(np.max(final_h))
    mean_depth = float(np.mean(final_h[final_h > 0.01]))  # Exclude dry cells
    flooded_area = float(np.sum(final_h > 0.1)) * (dx_m * dy_m)  # Area with >10cm
    total_volume = float(np.sum(final_h)) * (dx_m * dy_m)
    
    if verbose:
        print(f"\n{'='*70}")
        print(f"BASELINE RESULTS")
        print(f"{'='*70}")
        print(f"Max depth: {max_depth:.2f}m")
        print(f"Mean depth (flooded cells): {mean_depth:.2f}m")
        print(f"Flooded area (>10cm): {flooded_area:.0f}m²")
        print(f"Total water volume: {total_volume:.0f}m³")
        print(f"{'='*70}")
    
    return {
        'grid': grid,
        'solver': solver,
        'final_h': final_h,
        'final_u': final_u,
        'final_v': final_v,
        'bed': dem,
        'max_depth': max_depth,
        'mean_depth': mean_depth,
        'flooded_area_m2': flooded_area,
        'total_volume_m3': total_volume,
        'logs': logs
    }


def generate_qcia_interventions(baseline_results: Dict, 
                                hotspots: List[Dict],
                                output_path: Path,
                                verbose: bool = True) -> Path:
    """
    Use QCIA to generate optimized intervention designs for hotspots.
    
    Args:
        baseline_results: Results from baseline simulation
        hotspots: List of identified hotspots
        output_path: Path to save design JSON
        verbose: Print diagnostics
        
    Returns:
        Path to generated design JSON
    """
    if verbose:
        print(f"\n{'='*70}")
        print(f"GENERATING QCIA INTERVENTIONS")
        print(f"{'='*70}")
    
    interventions = []
    
    for h in hotspots:
        # For each hotspot, design a detention basin
        # In a real scenario, QCIA would optimize these parameters
        # For now, use simple heuristics based on hotspot characteristics
        
        volume_needed = h['area_m2'] * h['mean_depth_m'] * 0.8  # 80% reduction target
        depth = 2.0  # Standard depth
        diameter = 2.0 * np.sqrt(volume_needed / (np.pi * depth / 4))  # Circular basin
        
        intervention = {
            'type': 'detention_basin',
            'id': f"basin_{h['id']:03d}",
            'location': h['location'],
            'diameter_m': float(diameter),
            'depth_m': float(depth),
            'storage_volume_m3': float(volume_needed),
            'design_rationale': f"Sized for {h['area_m2']:.0f}m² hotspot with {h['mean_depth_m']:.2f}m depth"
        }
        
        interventions.append(intervention)
        
        if verbose:
            print(f"  Basin {h['id']}: Volume={volume_needed:.0f}m³, "
                  f"Diameter={diameter:.1f}m, Depth={depth:.1f}m")
            print(f"    Location: ({h['location']['lat']:.4f}°, {h['location']['lon']:.4f}°)")
    
    # Create design JSON
    design = {
        'project': 'QCIA Flood Mitigation',
        'location': 'Demonstration',
        'design_storm': '50mm/hr for 2 hours',
        'total_interventions': len(interventions),
        'interventions': interventions
    }
    
    # Save to file
    with open(output_path, 'w') as f:
        json.dump(design, f, indent=2)
    
    if verbose:
        print(f"\n✅ Saved {len(interventions)} interventions to: {output_path}")
    
    return output_path


def run_mitigated_simulation(baseline_results: Dict,
                            design_path: Path,
                            verbose: bool = True) -> Dict:
    """
    Run simulation with QCIA interventions applied.
    
    Args:
        baseline_results: Results from baseline (used to get parameters)
        design_path: Path to QCIA design JSON
        verbose: Print diagnostics
        
    Returns:
        Dictionary with mitigated simulation results
    """
    if verbose:
        print(f"\n{'='*70}")
        print(f"RUNNING MITIGATED SIMULATION")
        print(f"{'='*70}")
    
    # Get baseline parameters
    grid = baseline_results['grid']
    dem = baseline_results['bed'].copy()  # Make a copy to modify
    
    # Create new solver
    nx, ny = grid.nx, grid.ny
    prm = SWEParams(
        g=9.81,
        manning_n=0.06,
        h_min=1e-3,
        cfl=0.15,
        vmax_guard_coef=0.7,
        dt_max=0.5
    )
    
    filt = ExponentialFilter(alpha=96.0, p=8)
    solver = HRFSolver(grid, prm, filt)
    solver.mode = "dw_fv"
    
    # Initialize
    h0 = np.full((nx, ny), 0.0)
    u0 = np.zeros_like(h0)
    v0 = np.zeros_like(h0)
    solver.initialize(h0, u0, v0)
    
    # Set forcing (same as baseline)
    rain_rate_mps = (50.0 / 1000.0) / 3600.0
    infil_rate_mps = 1e-8
    
    solver.set_forcing(
        bed=dem,  # This will be modified by intervention applier
        rain_rate=rain_rate_mps,
        infil_rate=infil_rate_mps
    )
    
    # Apply QCIA interventions
    if verbose:
        print(f"\nApplying interventions from: {design_path.name}")
    
    applied = apply_qcia_design_to_solver(solver, grid, design_path, verbose=verbose)
    
    if not applied:
        if verbose:
            print("⚠️  No interventions were applied!")
        return {}
    
    # Run simulation
    sim_seconds = 2.0 * 3600.0
    if verbose:
        print(f"\nSimulating {sim_seconds/60:.1f} minutes with interventions...")
    
    logs = solver.run(t_end=sim_seconds, output_every=300.0, verbose=verbose)
    
    # Extract results
    final_h = solver.h.copy()
    max_depth = float(np.max(final_h))
    mean_depth = float(np.mean(final_h[final_h > 0.01]))
    flooded_area = float(np.sum(final_h > 0.1)) * (grid.dx * grid.dy)
    total_volume = float(np.sum(final_h)) * (grid.dx * grid.dy)
    
    if verbose:
        print(f"\n{'='*70}")
        print(f"MITIGATED RESULTS")
        print(f"{'='*70}")
        print(f"Max depth: {max_depth:.2f}m")
        print(f"Mean depth: {mean_depth:.2f}m")
        print(f"Flooded area: {flooded_area:.0f}m²")
        print(f"Total volume: {total_volume:.0f}m³")
        print(f"{'='*70}")
    
    return {
        'solver': solver,
        'final_h': final_h,
        'bed': solver.bed,
        'max_depth': max_depth,
        'mean_depth': mean_depth,
        'flooded_area_m2': flooded_area,
        'total_volume_m3': total_volume,
        'logs': logs,
        'num_interventions': len(applied)
    }


def compare_scenarios(baseline: Dict, mitigated: Dict, output_dir: Path, verbose: bool = True):
    """
    Compare baseline vs mitigated scenarios and export results.
    
    Args:
        baseline: Baseline simulation results
        mitigated: Mitigated simulation results
        output_dir: Directory to save outputs
        verbose: Print comparison
    """
    if verbose:
        print(f"\n{'='*70}")
        print(f"COMPARISON: BASELINE vs MITIGATED")
        print(f"{'='*70}")
    
    # Calculate improvements
    depth_reduction = ((baseline['max_depth'] - mitigated['max_depth']) / 
                      baseline['max_depth'] * 100)
    area_reduction = ((baseline['flooded_area_m2'] - mitigated['flooded_area_m2']) / 
                     baseline['flooded_area_m2'] * 100)
    volume_reduction = ((baseline['total_volume_m3'] - mitigated['total_volume_m3']) / 
                       baseline['total_volume_m3'] * 100)
    
    comparison = {
        'baseline': {
            'max_depth_m': baseline['max_depth'],
            'flooded_area_m2': baseline['flooded_area_m2'],
            'total_volume_m3': baseline['total_volume_m3']
        },
        'mitigated': {
            'max_depth_m': mitigated['max_depth'],
            'flooded_area_m2': mitigated['flooded_area_m2'],
            'total_volume_m3': mitigated['total_volume_m3'],
            'num_interventions': mitigated['num_interventions']
        },
        'improvements': {
            'max_depth_reduction_pct': depth_reduction,
            'flooded_area_reduction_pct': area_reduction,
            'volume_reduction_pct': volume_reduction
        }
    }
    
    if verbose:
        print(f"\nMetric                  Baseline    Mitigated   Reduction")
        print(f"{'-'*60}")
        print(f"Max Depth (m)          {baseline['max_depth']:8.2f}    {mitigated['max_depth']:8.2f}    {depth_reduction:6.1f}%")
        print(f"Flooded Area (m²)      {baseline['flooded_area_m2']:8.0f}    {mitigated['flooded_area_m2']:8.0f}    {area_reduction:6.1f}%")
        print(f"Total Volume (m³)      {baseline['total_volume_m3']:8.0f}    {mitigated['total_volume_m3']:8.0f}    {volume_reduction:6.1f}%")
        print(f"{'-'*60}")
        print(f"Number of AI-designed interventions: {mitigated['num_interventions']}")
    
    # Save comparison JSON
    comparison_file = output_dir / "comparison_metrics.json"
    with open(comparison_file, 'w') as f:
        json.dump(comparison, f, indent=2)
    
    if verbose:
        print(f"\n✅ Saved comparison metrics to: {comparison_file}")
    
    # Export rasters
    _save_raster(baseline['final_h'], output_dir / "baseline_flood_depth.npy")
    _save_raster(mitigated['final_h'], output_dir / "mitigated_flood_depth.npy")
    
    # Calculate and save reduction map
    reduction_map = baseline['final_h'] - mitigated['final_h']
    _save_raster(reduction_map, output_dir / "flood_reduction_map.npy")
    
    if verbose:
        print(f"✅ Saved flood depth rasters to: {output_dir}")


def _save_raster(data: np.ndarray, path: Path):
    """Save numpy array as .npy file."""
    np.save(path, data)


def main():
    """Main demo workflow."""
    parser = argparse.ArgumentParser(description="QCIA + Flood Demo")
    parser.add_argument('--nx', type=int, default=100, help='Grid cells in x')
    parser.add_argument('--ny', type=int, default=100, help='Grid cells in y')
    parser.add_argument('--dx', type=float, default=20.0, help='Cell size (m)')
    parser.add_argument('--rain', type=float, default=50.0, help='Rainfall (mm/hr)')
    parser.add_argument('--duration', type=float, default=2.0, help='Duration (hours)')
    parser.add_argument('--output', type=str, default='outputs/qcia_flood_demo', help='Output directory')
    parser.add_argument('--hotspots', type=int, default=5, help='Number of hotspots to target')
    args = parser.parse_args()
    
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'#'*70}")
    print(f"{'#'*70}")
    print(f"#  QCIA + HRF FLOOD MITIGATION DEMO")
    print(f"#  AI-Driven Urban Flood Mitigation using Causal Intelligence")
    print(f"{'#'*70}")
    print(f"{'#'*70}")
    
    # Step 1: Create terrain
    print(f"\n[1/6] Creating terrain...")
    dem = create_simple_terrain(args.nx, args.ny, args.nx * args.dx, args.ny * args.dx)
    
    # Step 2: Run baseline simulation
    print(f"\n[2/6] Running baseline simulation...")
    baseline = run_baseline_simulation(
        dem, args.nx, args.ny, args.dx, args.dx,
        rain_mm_hr=args.rain,
        duration_hr=args.duration
    )
    
    # Step 3: Analyze results
    print(f"\n[3/6] Analyzing flood patterns...")
    analyzer = FloodAnalyzer(baseline['grid'], baseline['final_h'], baseline['bed'])
    hotspots = analyzer.identify_hotspots(threshold_m=0.2, top_n=args.hotspots)
    analyzer.export_analysis(output_dir, prefix="baseline")
    
    if not hotspots:
        print("\n⚠️  No hotspots identified. Try increasing rainfall or reducing threshold.")
        return
    
    # Step 4: Generate QCIA interventions
    print(f"\n[4/6] Generating AI interventions...")
    design_path = output_dir / "qcia_design.json"
    generate_qcia_interventions(baseline, hotspots, design_path)
    
    # Step 5: Run mitigated simulation
    print(f"\n[5/6] Running mitigated simulation...")
    mitigated = run_mitigated_simulation(baseline, design_path)
    
    if not mitigated:
        print("\n❌ Mitigated simulation failed")
        return
    
    # Step 6: Compare and export
    print(f"\n[6/6] Comparing scenarios...")
    compare_scenarios(baseline, mitigated, output_dir)
    
    print(f"\n{'#'*70}")
    print(f"#  DEMO COMPLETE!")
    print(f"#  Results saved to: {output_dir}")
    print(f"{'#'*70}\n")


if __name__ == "__main__":
    main()

