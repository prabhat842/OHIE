#!/usr/bin/env python3
"""
Run Spatial QCIA on REAL Jabalpur Data
GPS-precise intervention design using actual flood simulation results
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../fast-solver'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import numpy as np
import json
from pathlib import Path

from hrf import Grid, HRFSolver, SWEParams, ExponentialFilter
from spatial_optimizer import SpatialQCIA, SpatialDesign
from intervention_library import get_intervention

print("="*70)
print("SPATIAL QCIA - REAL JABALPUR DATA")
print("GPS-Precise Flood Mitigation Design")
print("="*70)

# =============================================================================
# LOAD REAL JABALPUR DATA
# =============================================================================

print("\n[1/5] Loading real Jabalpur data...")

processed_dir = Path("data/processed_enhanced")

dem = np.load(processed_dir / 'jabalpur_dem_enhanced.npy')
manning_n_spatial = np.load(processed_dir / 'jabalpur_manning_enhanced.npy')
road_mask = np.load(processed_dir / 'road_mask.npy')

with open(processed_dir / 'metadata_enhanced.json', 'r') as f:
    metadata = json.load(f)

with open(processed_dir / 'extent_info_enhanced.json', 'r') as f:
    extent_info = json.load(f)

bounds = tuple(metadata['spatial']['bounds'])  # (minx, miny, maxx, maxy)

print(f"  ✅ DEM: {dem.shape}, {metadata['dem']['min_elevation']:.0f}-{metadata['dem']['max_elevation']:.0f}m")
print(f"  ✅ Roads: {metadata['roads']['length_km']:.1f} km")
print(f"  ✅ Area: {extent_info['Lx']/1000:.2f} × {extent_info['Ly']/1000:.2f} km")
print(f"  ✅ Bounds: {bounds}")

# =============================================================================
# RUN BASELINE FLOOD SIMULATION
# =============================================================================

print("\n[2/5] Running baseline flood simulation...")

ny, nx = dem.shape
Lx = extent_info['Lx']
Ly = extent_info['Ly']
grid = Grid(nx=nx, ny=ny, Lx=Lx, Ly=Ly)

# Rainfall event
rainfall_mm = 450
duration_hours = 10
rain_rate = (rainfall_mm / 1000.0) / (duration_hours * 3600.0)

# Setup solver
prm = SWEParams(manning_n=0.030, adaptive_truncation=False)
filt = ExponentialFilter(alpha=36.0, p=8)
solver = HRFSolver(grid=grid, prm=prm, filt=filt, mode="dw_fv")

# Initial conditions
h0 = np.ones((nx, ny)) * 0.01
u0 = np.zeros((nx, ny))
v0 = np.zeros((nx, ny))
solver.initialize(h0, u0, v0)

# Forcing
z_bed = dem.T
base_infil = rain_rate * 0.15
solver.set_forcing(bed=z_bed, rain_rate=rain_rate, infil_rate=base_infil)

# Run
print(f"  Simulating {rainfall_mm}mm rainfall over {duration_hours}h...")
sim_time = duration_hours * 3600.0
solver.run(t_end=sim_time, output_every=600.0, verbose=False)

baseline_flood = solver.h.T  # Transpose back to (ny, nx)

print(f"  ✅ Baseline simulation complete")
print(f"     Max depth: {np.max(baseline_flood):.2f}m")
print(f"     Mean depth: {np.mean(baseline_flood[baseline_flood > 0.1]):.2f}m")

flooded_area_km2 = np.sum(baseline_flood > 0.5) * (grid.dx * grid.dy) / 1e6
print(f"     Flooded area (>0.5m): {flooded_area_km2:.2f} km²")

# Save baseline
np.save('outputs/baseline_flood_for_optimization.npy', baseline_flood)

# =============================================================================
# RUN SPATIAL OPTIMIZATION
# =============================================================================

print("\n[3/5] Running spatial QCIA optimization...")

# Budget scenarios
budgets = [
    (8e7, "₹8 Crores (Conservative)"),
    (12e7, "₹12 Crores (Moderate)"),
    (20e7, "₹20 Crores (Comprehensive)")
]

optimal_designs = []

for budget, label in budgets:
    print(f"\n{'='*70}")
    print(f"OPTIMIZING FOR: {label}")
    print(f"{'='*70}")
    
    optimizer = SpatialQCIA(
        baseline_flood=baseline_flood,
        dem=dem,
        road_mask=road_mask,
        bounds=bounds,
        budget_max=budget
    )
    
    optimal_design = optimizer.optimize(n_steps=100, verbose=True)
    
    optimal_designs.append({
        'budget': budget,
        'label': label,
        'design': optimal_design
    })

# =============================================================================
# SAVE RESULTS
# =============================================================================

print("\n[4/5] Saving optimal designs...")

for item in optimal_designs:
    design = item['design']
    budget_label = item['label'].replace(' ', '_').replace('(', '').replace(')', '')
    
    # Save as JSON
    design_dict = design.to_dict()
    design_dict['budget'] = item['budget'] / 1e7
    design_dict['budget_label'] = item['label']
    design_dict['location'] = 'Jabalpur City Center'
    design_dict['area_km2'] = {
        'Lx': Lx / 1000,
        'Ly': Ly / 1000
    }
    
    filename = f"outputs/optimal_design_{budget_label}.json"
    with open(filename, 'w') as f:
        json.dump(design_dict, f, indent=2)
    
    print(f"  ✅ Saved: {filename}")

# =============================================================================
# SUMMARY
# =============================================================================

print("\n[5/5] SUMMARY")
print("="*70)

for item in optimal_designs:
    design = item['design']
    design_dict = design.to_dict()
    
    print(f"\n{item['label']}:")
    print(f"  Total Cost: ₹{design_dict['total_cost_cr']:.2f} Crores")
    print(f"  Interventions: {design_dict['num_interventions']}")
    
    # Count by type
    culverts = sum(1 for i in design_dict['interventions'] if 'Culvert' in i['type'])
    drains = sum(1 for i in design_dict['interventions'] if 'Drain' in i['type'])
    ponds = sum(1 for i in design_dict['interventions'] if 'Pond' in i['type'])
    pumps = sum(1 for i in design_dict['interventions'] if 'Pump' in i['type'])
    
    print(f"    • Culverts: {culverts}")
    print(f"    • Drains: {drains}")
    print(f"    • Ponds: {ponds}")
    print(f"    • Pumps: {pumps}")
    
    print(f"\n  Sample Interventions:")
    for i, interv in enumerate(design_dict['interventions'][:3], 1):
        lat, lon = interv['lat_lon']
        print(f"    [{i}] {interv['type']}")
        print(f"        GPS: ({lat:.5f}°N, {lon:.5f}°E)")
        print(f"        Cost: ₹{interv['cost_lakh']:.1f} lakh")

print("\n" + "="*70)
print("✅ SPATIAL QCIA COMPLETE - REAL JABALPUR")
print("="*70)
print("\n📍 All designs have GPS coordinates for contractors")
print("📊 Ready for interactive visualization")
print("🗺️  Next: Run visualization script to see interventions on map")
print("\n" + "="*70)

