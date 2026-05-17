#!/usr/bin/env python3
"""
Test upstream placement on REAL Jabalpur data.

This script:
1. Loads real DEM from Jabalpur AOI
2. Runs baseline HRF simulation
3. Uses HydrologicalAnalyzer to find PROPER upstream interception points
4. Optimizes basin designs for those locations
5. Tests mitigated scenario
"""
import sys
from pathlib import Path
import numpy as np
import json

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "AI"))
sys.path.insert(0, str(_ROOT / "Flood_Resilience_Demo"))

from Flood_Resilience_Demo.Physics.hrf import Grid, SWEParams, ExponentialFilter, HRFSolver
from AI.applications.flood_analyzer import FloodAnalyzer
from AI.applications.intervention_applier import apply_qcia_design_to_solver
from AI.applications.hydrological_analyzer import HydrologicalAnalyzer

print("\n" + "="*70)
print("REAL JABALPUR TEST: PROPER UPSTREAM PLACEMENT")
print("="*70)

# Load Jabalpur data from previous baseline run
print("\n[1/6] Loading Jabalpur baseline simulation...")
baseline_path = _ROOT / "Flood_Resilience_Demo/outputs/jabalpur_aoi_baseline/final_snapshot.npz"
baseline = np.load(baseline_path)

h_baseline = baseline['h']
u_baseline = baseline['u']
v_baseline = baseline['v']
bed = baseline['bed']
dx = float(baseline['dx_m'])
dy = float(baseline['dy_m'])
nx, ny = h_baseline.shape[1], h_baseline.shape[0]

print(f"   Grid: {ny} x {nx} cells")
print(f"   Resolution: {dx:.1f}m x {dy:.1f}m")
print(f"   Baseline max depth: {np.max(h_baseline):.2f}m")
print(f"   Baseline flooded area: {np.sum(h_baseline > 0.1) * dx * dy:.0f}m²")

# Create grid object for solver
grid = Grid(nx=nx, ny=ny, Lx=nx*dx, Ly=ny*dy)

# Identify hotspots
print("\n[2/6] Analyzing flood hotspots...")
analyzer = FloodAnalyzer(grid, h_baseline, bed, verbose=True)
hotspots = analyzer.identify_hotspots(threshold_m=0.5, top_n=3)  # Top 3 hotspots

if not hotspots:
    print("❌ No hotspots found!")
    sys.exit(1)

# CRITICAL: Use hydrological analysis to find UPSTREAM interception points
print("\n[3/6] Computing upstream interception points (this is the KEY step)...")
hydro = HydrologicalAnalyzer(bed, dx, dy, verbose=True)
interception_points = hydro.find_upstream_interception_points(
    hotspots,
    n_points=2,  # 2 interception points per hotspot
    min_distance_m=50.0,  # At least 50m upstream (relaxed for dense urban)
    min_accumulation=10.0  # Must intercept some flow (relaxed - max is only 229 cells)
)

if not interception_points:
    print("❌ No suitable upstream points found!")
    sys.exit(1)

print(f"\n✅ Found {len(interception_points)} upstream interception points")

# Design basins for these upstream locations
print("\n[4/6] Sizing detention basins for upstream locations...")

# Reference coordinates (approximate Jabalpur center)
ref_lat, ref_lon = 23.18, 79.99

interventions = []
for idx, point in enumerate(interception_points):
    # Size basin based on upstream catchment area
    # Rule of thumb: store ~30mm of runoff from catchment
    runoff_depth_m = 0.03  # 30mm
    required_volume_m3 = point.upstream_area_m2 * runoff_depth_m
    
    # Practical constraints
    volume_m3 = min(max(required_volume_m3, 500.0), 5000.0)  # 500-5000 m³
    depth_m = 3.0  # Standard depth
    diameter_m = np.sqrt(4 * volume_m3 / (np.pi * depth_m))
    
    # Convert grid indices to lat/lon (approximate)
    lat = ref_lat + (point.grid_i - ny/2) * (dy / 111000.0)
    lon = ref_lon + (point.grid_j - nx/2) * (dx / 111000.0)
    
    intervention = {
        'type': 'detention_basin',
        'id': f'basin_upstream_{idx+1}',
        'location': {'lat': float(lat), 'lon': float(lon)},
        'grid_indices': {'i': int(point.grid_i), 'j': int(point.grid_j)},
        'volume_m3': float(volume_m3),
        'diameter_m': float(diameter_m),
        'depth_m': float(depth_m),
        'storage_volume_m3': float(volume_m3),
        'upstream_area_m2': float(point.upstream_area_m2),
        'reasoning': point.reasoning
    }
    
    interventions.append(intervention)
    
    print(f"\n   Basin {idx+1}:")
    print(f"      Location: ({point.grid_i}, {point.grid_j})")
    print(f"      Volume: {volume_m3:.0f}m³")
    print(f"      Diameter: {diameter_m:.1f}m")
    print(f"      Upstream catchment: {point.upstream_area_m2:.0f}m²")
    print(f"      Reasoning: {point.reasoning}")

# Save design
output_dir = _ROOT / "outputs/upstream_placement_demo"
output_dir.mkdir(parents=True, exist_ok=True)

design_file = output_dir / "upstream_design.json"
with open(design_file, 'w') as f:
    json.dump({'interventions': interventions}, f, indent=2)

print(f"\n✅ Saved design to: {design_file}")

# Apply to solver and simulate
print("\n[5/6] Running mitigated simulation...")

# Initialize solver with same parameters as baseline
params = SWEParams(g=9.81, manning_n=0.0, cfl=0.3)
filt = ExponentialFilter(alpha=0.5)
solver = HRFSolver(grid=grid, prm=params, filt=filt)
solver.mode = "swe"

# Set terrain
solver.bed = bed.copy()

# Initialize infiltration field (IMPORTANT: must be array before intervention_applier modifies it)
solver.infil_rate = np.zeros_like(bed)

# Initialize state
solver.initialize(h0=np.zeros_like(bed), u0=np.zeros_like(bed), v0=np.zeros_like(bed))

# Apply rain (same as baseline - matching pb_cli.py)
rain_rate_mm_hr = 50.0
solver.rain_rate = np.full_like(bed, rain_rate_mm_hr / (1000.0 * 3600.0))

# Apply UPSTREAM interventions
applied_interventions = apply_qcia_design_to_solver(solver, grid, design_file, verbose=True)

if len(applied_interventions) == 0:
    print("❌ No interventions were applied!")
    sys.exit(1)

print(f"\n✅ Successfully applied {len(applied_interventions)}/{len(interventions)} interventions")

# Run simulation
print("\n   Running HRF solver (this will take ~60 seconds)...")
t_end = 3600.0  # 1 hour
solver.run(t_end=t_end, output_every=0.0, verbose=True)

# Convert result to numpy if needed
if hasattr(solver.h, 'get'):
    h_mitigated = solver.h.get()
else:
    h_mitigated = np.array(solver.h)

# Compare results
print("\n[6/6] RESULTS")
print("="*70)

max_depth_baseline = np.max(h_baseline)
max_depth_mitigated = np.max(h_mitigated)
flooded_area_baseline = np.sum(h_baseline > 0.1) * dx * dy
flooded_area_mitigated = np.sum(h_mitigated > 0.1) * dx * dy
critical_baseline = np.sum(h_baseline > 2.0)
critical_mitigated = np.sum(h_mitigated > 2.0)

print(f"\nBASELINE:")
print(f"  Max depth: {max_depth_baseline:.2f}m")
print(f"  Flooded area: {flooded_area_baseline:.0f}m²")
print(f"  Critical cells (>2m): {critical_baseline}")

print(f"\nUPSTREAM MITIGATION ({len(interventions)} basins):")
print(f"  Max depth: {max_depth_mitigated:.2f}m")
print(f"  Flooded area: {flooded_area_mitigated:.0f}m²")
print(f"  Critical cells (>2m): {critical_mitigated}")

max_depth_improvement = ((max_depth_baseline - max_depth_mitigated) / max_depth_baseline) * 100
area_improvement = ((flooded_area_baseline - flooded_area_mitigated) / flooded_area_baseline) * 100
critical_improvement = critical_baseline - critical_mitigated

print(f"\n{'='*70}")
print(f"IMPROVEMENTS:")
print(f"{'='*70}")
print(f"  Max depth: {max_depth_improvement:+.1f}%")
print(f"  Flooded area: {area_improvement:+.1f}%")
print(f"  Critical cells eliminated: {critical_improvement}")

if max_depth_improvement > 10:
    print(f"\n🎉 SUCCESS! Upstream placement achieved {max_depth_improvement:.1f}% flood reduction!")
elif max_depth_improvement > 5:
    print(f"\n✅ MODERATE SUCCESS! {max_depth_improvement:.1f}% improvement.")
else:
    print(f"\n⚠️  Limited improvement. May need more basins or different strategy.")

print("="*70 + "\n")

# Save output
np.savez(
    output_dir / 'mitigated_snapshot.npz',
    h=h_mitigated,
    u=solver.u,
    v=solver.v,
    bed=solver.bed,
    dx_m=dx,
    dy_m=dy
)

print(f"✅ Saved mitigated snapshot to: {output_dir}")
