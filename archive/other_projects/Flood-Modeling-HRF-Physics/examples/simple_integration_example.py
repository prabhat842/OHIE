#!/usr/bin/env python3
"""
Simple Integration Example
===========================
Demonstrates how to use the AI-Physics integration without breaking existing code.

This example shows the 3 key integration components in action.
"""

import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np

# Import existing physics (unchanged)
from Physics.hrf import Grid, SWEParams, ExponentialFilter, HRFSolver

# Import new integration layer
from AI.hrf_adapter import HRFAdapter
from AI.intervention_generator import InterventionGenerator

print("="*70)
print("SIMPLE INTEGRATION EXAMPLE")
print("="*70)

# ============================================================================
# STEP 1: Create a simple flood scenario (existing HRF code)
# ============================================================================

print("\n[1/5] Setting up HRF solver (existing code, unchanged)...")

# Grid
nx, ny = 100, 100
Lx, Ly = 5000, 5000  # 5km × 5km
grid = Grid(nx=nx, ny=ny, Lx=Lx, Ly=Ly)

# Solver parameters
prm = SWEParams(manning_n=0.06, h_min=0.02, cfl=0.15, dt_max=0.1)
filt = ExponentialFilter(alpha=36.0, p=8)
solver = HRFSolver(grid=grid, prm=prm, filt=filt, mode="dw_fv")

# Terrain (synthetic)
x = np.linspace(0, Lx, nx)
y = np.linspace(0, Ly, ny)
X, Y = np.meshgrid(x, y)
dem = 400 + 10 * np.sin(X / 1000) + 5 * np.cos(Y / 800)  # Wavy terrain
dem = dem.T  # HRF uses (nx, ny) indexing

# Initial conditions
h0 = np.full((nx, ny), 0.01)
u0 = np.zeros((nx, ny))
v0 = np.zeros((nx, ny))
solver.initialize(h0, u0, v0)

# Rainfall event (200mm in 6 hours)
rain_rate = (200 / 1000.0) / (6 * 3600.0)  # m/s
infil_rate = rain_rate * 0.15  # 15% infiltration

solver.set_forcing(bed=dem, rain_rate=rain_rate, infil_rate=infil_rate)

print(f"✅ Solver ready: {nx}×{ny} grid, {Lx/1000:.1f}×{Ly/1000:.1f}km")

# ============================================================================
# STEP 2: Run baseline simulation (existing HRF code)
# ============================================================================

print("\n[2/5] Running baseline simulation...")

solver.run(t_end=6*3600, output_every=1800, verbose=False)

print(f"✅ Simulation complete")
print(f"   Max depth: {float(np.max(solver.h)):.2f}m")

# ============================================================================
# STEP 3: Extract metrics using NEW adapter (no changes to HRF!)
# ============================================================================

print("\n[3/5] Extracting metrics with HRF Adapter...")

adapter = HRFAdapter()

baseline_metrics = adapter.extract_causal_variables(
    solver=solver,
    scenario_params={
        'budget_cr': 0.0,
        'culvert_count': 0,
        'pond_count': 0,
        'drainage_multiplier': 1.0,
    },
    scenario_id='baseline'
)

print(f"✅ Baseline metrics extracted:")
print(f"   Flooded area: {baseline_metrics['flooded_area_05m_km2']:.2f} km²")
print(f"   Max depth: {baseline_metrics['max_depth_m']:.2f} m")
print(f"   Damage estimate: ₹{baseline_metrics['damage_lakh']:.0f} lakh")

# ============================================================================
# STEP 4: Apply interventions using NEW generator (no changes to HRF!)
# ============================================================================

print("\n[4/5] Creating optimized scenario with interventions...")

# Create new solver for optimized scenario
solver2 = HRFSolver(grid=grid, prm=prm, filt=filt, mode="dw_fv")
solver2.initialize(h0, u0, v0)
solver2.set_forcing(bed=dem, rain_rate=rain_rate, infil_rate=infil_rate)

# Apply interventions using generator
generator = InterventionGenerator(
    grid_shape=(nx, ny),
    dem=dem.T,  # Generator uses (ny, nx)
    road_mask=None
)

generator.apply_simple_scenario(
    solver=solver2,
    culvert_count=10,
    pond_count=2,
    drainage_multiplier=1.5,
    base_infiltration=np.full((nx, ny), infil_rate)
)

print(f"✅ Interventions applied:")
print(f"   Culverts: {len(solver2.structures['culverts'])}")
print(f"   Improved drainage: 1.5x")

# Run optimized scenario
print("\n   Running optimized simulation...")
solver2.run(t_end=6*3600, output_every=1800, verbose=False)

# Extract optimized metrics
optimized_metrics = adapter.extract_causal_variables(
    solver=solver2,
    scenario_params={
        'budget_cr': 12.0,
        'culvert_count': 10,
        'pond_count': 2,
        'drainage_multiplier': 1.5,
    },
    scenario_id='optimized'
)

print(f"✅ Optimized metrics extracted:")
print(f"   Flooded area: {optimized_metrics['flooded_area_05m_km2']:.2f} km²")
print(f"   Max depth: {optimized_metrics['max_depth_m']:.2f} m")
print(f"   ROI: {optimized_metrics['roi']:.1f}x")

# ============================================================================
# STEP 5: Compare scenarios using adapter
# ============================================================================

print("\n[5/5] Comparing scenarios...")

comparison = adapter.compare_scenarios('baseline', 'optimized')

print(f"✅ Comparison:")
print(f"   Flood reduction: {comparison['flood_reduction_pct']:.1f}%")
print(f"   Depth reduction: {comparison['depth_reduction_pct']:.1f}%")
print(f"   Damage avoided: ₹{comparison['damage_avoided_lakh']:.0f} lakh")
print(f"   ROI: {comparison['roi']:.1f}x")

# ============================================================================
# SUMMARY
# ============================================================================

print("\n" + "="*70)
print("✅ INTEGRATION SUCCESSFUL")
print("="*70)
print("\nKey Points:")
print("  1. HRF code was NOT modified - it works exactly as before")
print("  2. New adapter extracts metrics in QCIA-compatible format")
print("  3. New generator applies interventions without changing HRF")
print("  4. You can now connect this to QCIA for AI optimization")
print("\nNext Steps:")
print("  • Use adapter.get_dataframe() to feed QCIA causal discovery")
print("  • Use QCIA quantum optimizer to find optimal interventions")
print("  • Validate optimized designs with HRF physics")
print("="*70)



