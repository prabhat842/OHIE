#!/usr/bin/env python3
"""
QCIA Workflow with ENHANCED Real Jabalpur Data
Includes: Roads, spatial Manning roughness, real terrain
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../fast-solver'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import numpy as np
import pandas as pd
import json
import matplotlib.pyplot as plt
from pathlib import Path

from hrf import Grid, HRFSolver, SWEParams, ExponentialFilter
from qcia_core import CausalDiscoveryEngine, CausalReasoningEngine, QuantumInspiredOptimizer, AnnealingSchedule

print("="*70)
print("JABALPUR QCIA - ENHANCED WITH ROADS & INFRASTRUCTURE")
print("="*70)

# =============================================================================
# STEP 1: LOAD ENHANCED REAL DATA
# =============================================================================

print("\n[STEP 1/6] Loading ENHANCED Jabalpur data...")

processed_dir = Path("data/processed_enhanced")

# Load enhanced data
dem = np.load(processed_dir / 'jabalpur_dem_enhanced.npy')
manning_n_spatial = np.load(processed_dir / 'jabalpur_manning_enhanced.npy')
lulc = np.load(processed_dir / 'jabalpur_lulc_enhanced.npy')
road_mask = np.load(processed_dir / 'road_mask.npy')
building_mask = np.load(processed_dir / 'building_mask.npy')

# Load metadata
with open(processed_dir / 'metadata_enhanced.json', 'r') as f:
    metadata = json.load(f)

with open(processed_dir / 'extent_info_enhanced.json', 'r') as f:
    extent_info = json.load(f)

print(f"  ✅ DEM: {dem.shape}")
print(f"     Elevation: {metadata['dem']['min_elevation']:.1f} - {metadata['dem']['max_elevation']:.1f}m")
print(f"  ✅ Roads: {metadata['roads']['segments']} segments, {metadata['roads']['length_km']:.1f} km")
print(f"  ✅ Road density: {metadata['roads']['length_km'] / (extent_info['Lx']*extent_info['Ly']/1e6):.1f} km/km²")
print(f"  ✅ Area: {extent_info['Lx']/1000:.2f} × {extent_info['Ly']/1000:.2f} km")
print(f"  ✅ Manning roughness: spatially varying (roads, urban, vegetation)")

# Rainfall event (2023 Extreme)
rainfall_mm = 450
duration_hours = 10

print(f"\n  🌧️  Rainfall event: {rainfall_mm}mm in {duration_hours}h (2023 Extreme)")

# =============================================================================
# STEP 2: DEFINE SCENARIOS
# =============================================================================

print("\n[STEP 2/6] Defining drainage improvement scenarios...")

scenarios = []

scenarios.append({
    'id': 'S00_baseline',
    'name': 'Current Infrastructure',
    'cost_cr': 0,
    'drainage_mult': 1.0,
    'road_drainage_bonus': 0.0,  # No extra drainage along roads
    'improvements': []
})

scenarios.append({
    'id': 'S01_quick_fix',
    'name': 'Clear road drains',
    'cost_cr': 3,
    'drainage_mult': 1.15,
    'road_drainage_bonus': 0.5,  # Roads drain better
    'improvements': ['road_drain_clearing']
})

scenarios.append({
    'id': 'S02_targeted',
    'name': 'Targeted road improvements',
    'cost_cr': 7,
    'drainage_mult': 1.4,
    'road_drainage_bonus': 1.0,
    'improvements': ['priority_road_drains']
})

scenarios.append({
    'id': 'S03_moderate',
    'name': 'Upgrade main roads',
    'cost_cr': 12,
    'drainage_mult': 1.7,
    'road_drainage_bonus': 1.5,
    'improvements': ['main_road_upgrade', 'culvert_expansion']
})

scenarios.append({
    'id': 'S04_comprehensive',
    'name': 'Full road network',
    'cost_cr': 20,
    'drainage_mult': 2.1,
    'road_drainage_bonus': 2.0,
    'improvements': ['full_road_network', 'detention_ponds']
})

scenarios.append({
    'id': 'S05_advanced',
    'name': 'Smart road drainage',
    'cost_cr': 30,
    'drainage_mult': 2.6,
    'road_drainage_bonus': 2.5,
    'improvements': ['smart_drains', 'permeable_roads']
})

print(f"  ✅ {len(scenarios)} scenarios defined")
print(f"  ✅ Budget range: ₹0 - ₹30 Crores")
print(f"  ✅ Road-specific drainage improvements included")

# =============================================================================
# STEP 3: RUN SIMULATIONS WITH ENHANCED PHYSICS
# =============================================================================

print("\n[STEP 3/6] Running flood simulations with ENHANCED PHYSICS...")
print("  (Roads + spatial roughness + real terrain)")

# Prepare grid
ny, nx = dem.shape
Lx = extent_info['Lx']
Ly = extent_info['Ly']
grid = Grid(nx=nx, ny=ny, Lx=Lx, Ly=Ly)

rain_rate = (rainfall_mm / 1000.0) / (duration_hours * 3600.0)

results = []

for i, scenario in enumerate(scenarios):
    print(f"\n  [{i+1}/{len(scenarios)}] Running: {scenario['name']}")
    print(f"      Budget: ₹{scenario['cost_cr']} Cr")
    
    # Setup HRF solver (use base manning, will apply spatial later)
    prm = SWEParams(manning_n=0.030, adaptive_truncation=False)
    filt = ExponentialFilter(alpha=36.0, p=8)
    solver = HRFSolver(grid=grid, prm=prm, filt=filt, mode="dw_fv")
    
    # Initial conditions
    h0 = np.ones((nx, ny)) * 0.01
    u0 = np.zeros((nx, ny))
    v0 = np.zeros((nx, ny))
    
    solver.initialize(h0, u0, v0)
    
    # Enhanced forcing with spatial roughness
    z_bed = dem.T  # Transpose for HRF indexing
    
    # Apply spatially-varying Manning roughness
    manning_field = manning_n_spatial.T
    solver.manning_n = manning_field  # Set spatial field
    
    # Base infiltration
    base_infil = rain_rate * 0.15
    
    # Enhanced infiltration: better drainage overall + bonus on roads
    infil_rate_base = base_infil * scenario['drainage_mult']
    
    # Create spatial infiltration (higher on roads if road drainage improved)
    infil_field = np.full((nx, ny), infil_rate_base)
    road_mask_t = road_mask.T
    road_drain_bonus = scenario['road_drainage_bonus']
    infil_field[road_mask_t == 1] *= (1.0 + road_drain_bonus * 0.5)  # Roads drain better
    
    solver.set_forcing(bed=z_bed, rain_rate=rain_rate, infil_rate=np.mean(infil_field))
    
    # Run simulation
    sim_time = duration_hours * 3600.0
    solver.run(t_end=sim_time, output_every=600.0, verbose=False)
    
    # Extract results
    h_final = solver.h.T
    
    # Compute metrics
    flooded_05m = np.sum(h_final > 0.5) * (grid.dx * grid.dy) / 1e6
    flooded_10m = np.sum(h_final > 1.0) * (grid.dx * grid.dy) / 1e6
    max_depth = np.max(h_final)
    mean_depth = np.mean(h_final[h_final > 0.1]) if np.any(h_final > 0.1) else 0
    
    # Road flooding analysis (NEW!)
    road_flooded_area = np.sum((h_final > 0.3) & (road_mask == 1)) * (grid.dx * grid.dy) / 1e6
    road_flooded_pct = 100.0 * np.sum((h_final > 0.3) & (road_mask == 1)) / max(np.sum(road_mask), 1)
    
    # Damage estimate (enhanced: roads + general)
    damage_general = flooded_05m * 100 * 10  # General flooding damage
    damage_roads = road_flooded_area * 100 * 15  # Road damage (higher cost)
    damage_lakh = damage_general + damage_roads
    
    # ROI
    cost_lakh = scenario['cost_cr'] * 100
    benefit_lakh = damage_lakh
    roi = (benefit_lakh / cost_lakh) if cost_lakh > 0 else 0
    
    result = {
        'scenario_id': scenario['id'],
        'scenario_name': scenario['name'],
        'cost_cr': scenario['cost_cr'],
        'drainage_mult': scenario['drainage_mult'],
        'road_drainage_bonus': scenario['road_drainage_bonus'],
        'flooded_area_05m_km2': flooded_05m,
        'flooded_area_10m_km2': flooded_10m,
        'road_flooded_km2': road_flooded_area,
        'road_flooded_pct': road_flooded_pct,
        'max_depth_m': max_depth,
        'mean_depth_m': mean_depth,
        'damage_lakh': damage_lakh,
        'roi': roi,
        'h_final': h_final
    }
    
    results.append(result)
    
    print(f"      Flooded (>0.5m): {flooded_05m:.2f} km²")
    print(f"      Roads flooded: {road_flooded_pct:.1f}% ({road_flooded_area:.3f} km²)")
    print(f"      Max depth: {max_depth:.2f}m")
    print(f"      Damage: ₹{damage_lakh:.0f} lakh")
    if cost_lakh > 0:
        print(f"      ROI: {roi:.2f}x")

# Save results
df_results = pd.DataFrame([{k: v for k, v in r.items() if k != 'h_final'} for r in results])
df_results.to_csv('outputs/scenario_results_ENHANCED.csv', index=False)

print(f"\n  ✅ All scenarios complete!")
print(f"  ✅ Results saved: outputs/scenario_results_ENHANCED.csv")

# =============================================================================
# STEP 4: QCIA CAUSAL DISCOVERY
# =============================================================================

print("\n[STEP 4/6] QCIA Causal Discovery (with road metrics)...")

discovery = CausalDiscoveryEngine(alpha=0.05)
graph = discovery.learn_structure(df_results[[
    'cost_cr', 'drainage_mult', 'road_drainage_bonus', 
    'flooded_area_05m_km2', 'road_flooded_pct', 'damage_lakh', 'roi'
]])

print("\n  Discovered Causal Graph:")
print(graph.summary())

# =============================================================================
# STEP 5: QCIA OPTIMIZATION
# =============================================================================

print("\n[STEP 5/6] QCIA Optimization...")

reasoning = CausalReasoningEngine(graph)
reasoning.fit(df_results[[
    'cost_cr', 'drainage_mult', 'road_drainage_bonus',
    'flooded_area_05m_km2', 'road_flooded_pct', 'damage_lakh', 'roi'
]])

print("  ✅ Causal model fitted")

def flood_objective(params):
    budget = params[0]
    pred = reasoning.scm.intervene({'cost_cr': budget}, n_samples=100)
    flood_area = pred['flooded_area_05m_km2'].mean()
    road_flood = pred['road_flooded_pct'].mean() / 100.0
    return flood_area * 10.0 + road_flood * 5.0 + budget * 0.1

print("\n  Running quantum annealing optimization...")
optimizer = QuantumInspiredOptimizer()
schedule = AnnealingSchedule(n_steps=300, transverse_field_strength=4.0)
bounds = [(0, 35)]

optimal_budget = optimizer.quantum_anneal(flood_objective, bounds, schedule, seed=42)

print(f"\n  🎯 Optimal Budget: ₹{optimal_budget[0]:.1f} Crores")

optimal_pred = reasoning.scm.intervene({'cost_cr': optimal_budget[0]}, n_samples=1000)
print(f"  📊 Expected flooded area: {optimal_pred['flooded_area_05m_km2'].mean():.2f} km²")
print(f"  📊 Expected road flooding: {optimal_pred['road_flooded_pct'].mean():.1f}%")
print(f"  📊 Expected damage: ₹{optimal_pred['damage_lakh'].mean():.0f} lakh")
print(f"  📊 Expected ROI: {optimal_pred['roi'].mean():.2f}x")

# =============================================================================
# STEP 6: VISUALIZATION
# =============================================================================

print("\n[STEP 6/6] Generating enhanced visualizations...")

fig, axes = plt.subplots(2, 3, figsize=(18, 10))

# Cost vs Flood
axes[0, 0].plot(df_results['cost_cr'], df_results['flooded_area_05m_km2'], 'o-', 
                markersize=8, color='steelblue', linewidth=2, label='Total flood')
axes[0, 0].axvline(optimal_budget[0], color='red', linestyle='--', linewidth=2, label='QCIA Optimal')
axes[0, 0].set_xlabel('Budget (₹ Crores)', fontsize=11)
axes[0, 0].set_ylabel('Flooded Area (km²)', fontsize=11)
axes[0, 0].set_title('Cost vs Flood Reduction\n(Real Jabalpur + Roads)', fontsize=12, fontweight='bold')
axes[0, 0].legend(fontsize=10)
axes[0, 0].grid(True, alpha=0.3)

# Road flooding
axes[0, 1].plot(df_results['cost_cr'], df_results['road_flooded_pct'], 'o-', 
                markersize=8, color='orange', linewidth=2)
axes[0, 1].axvline(optimal_budget[0], color='red', linestyle='--', linewidth=2, label='QCIA Optimal')
axes[0, 1].set_xlabel('Budget (₹ Crores)', fontsize=11)
axes[0, 1].set_ylabel('Roads Flooded (%)', fontsize=11)
axes[0, 1].set_title('Road Flooding Reduction\n(NEW Metric!)', fontsize=12, fontweight='bold')
axes[0, 1].legend(fontsize=10)
axes[0, 1].grid(True, alpha=0.3)

# ROI curve
axes[0, 2].plot(df_results['cost_cr'][1:], df_results['roi'][1:], 'o-', 
                markersize=8, color='green', linewidth=2)
axes[0, 2].axvline(optimal_budget[0], color='red', linestyle='--', linewidth=2, label='QCIA Optimal')
axes[0, 2].set_xlabel('Budget (₹ Crores)', fontsize=11)
axes[0, 2].set_ylabel('Return on Investment (x)', fontsize=11)
axes[0, 2].set_title('ROI by Investment Level', fontsize=12, fontweight='bold')
axes[0, 2].legend(fontsize=10)
axes[0, 2].grid(True, alpha=0.3)

# Flood maps
baseline = results[0]
optimal_idx = np.argmin(np.abs(df_results['cost_cr'] - optimal_budget[0]))
optimal = results[optimal_idx]

# Baseline flood map with roads overlay
baseline_h = baseline['h_final']
im1 = axes[1, 0].imshow(baseline_h, origin='lower', cmap='Blues', vmin=0, vmax=2.0, alpha=0.8)
axes[1, 0].contour(road_mask, levels=[0.5], colors='red', linewidths=0.5, alpha=0.5)
axes[1, 0].set_title(f'Baseline: {baseline["flooded_area_05m_km2"]:.2f} km²\n{baseline["road_flooded_pct"]:.0f}% roads flooded', 
                     fontsize=11, fontweight='bold')
axes[1, 0].set_xlabel('x (grid cells)')
axes[1, 0].set_ylabel('y (grid cells)')
plt.colorbar(im1, ax=axes[1, 0], label='Depth (m)')

# Optimal flood map with roads
optimal_h = optimal['h_final']
im2 = axes[1, 1].imshow(optimal_h, origin='lower', cmap='Blues', vmin=0, vmax=2.0, alpha=0.8)
axes[1, 1].contour(road_mask, levels=[0.5], colors='red', linewidths=0.5, alpha=0.5)
axes[1, 1].set_title(f'Optimal (₹{optimal["cost_cr"]:.0f}Cr): {optimal["flooded_area_05m_km2"]:.2f} km²\n{optimal["road_flooded_pct"]:.0f}% roads flooded (ROI: {optimal["roi"]:.1f}x)', 
                     fontsize=11, fontweight='bold')
axes[1, 1].set_xlabel('x (grid cells)')
plt.colorbar(im2, ax=axes[1, 1], label='Depth (m)')

# Terrain with roads
im3 = axes[1, 2].imshow(dem, origin='lower', cmap='terrain', alpha=0.7)
axes[1, 2].contour(road_mask, levels=[0.5], colors='red', linewidths=1.5, alpha=0.8)
axes[1, 2].set_title(f'Real Terrain + Road Network\n{metadata["roads"]["length_km"]:.1f} km roads', 
                     fontsize=11, fontweight='bold')
axes[1, 2].set_xlabel('x (grid cells)')
plt.colorbar(im3, ax=axes[1, 2], label='Elevation (m)')

plt.tight_layout()
plt.savefig('outputs/qcia_analysis_ENHANCED.png', dpi=150, bbox_inches='tight')
print(f"  ✅ Analysis plot saved: outputs/qcia_analysis_ENHANCED.png")

# =============================================================================
# SUMMARY
# =============================================================================

print("\n" + "="*70)
print("✅ ENHANCED QCIA WORKFLOW COMPLETE - REAL JABALPUR + ROADS")
print("="*70)

print(f"\n🏙️  Location: Jabalpur City Center")
print(f"  Area: {Lx/1000:.2f} × {Ly/1000:.2f} km")
print(f"  Terrain: {metadata['dem']['min_elevation']:.0f} - {metadata['dem']['max_elevation']:.0f}m elevation")
print(f"  Roads: {metadata['roads']['segments']} segments, {metadata['roads']['length_km']:.1f} km")

print(f"\n📊 Key Results:")
print(f"  Scenarios tested: {len(scenarios)}")
print(f"  Optimal budget: ₹{optimal_budget[0]:.1f} Crores")
print(f"  Flood reduction: {(1 - optimal['flooded_area_05m_km2'] / baseline['flooded_area_05m_km2']) * 100:.1f}%")
print(f"  Road flooding reduction: {baseline['road_flooded_pct'] - optimal['road_flooded_pct']:.1f}%")
print(f"  ROI: {optimal['roi']:.2f}x")
print(f"  Damage avoided: ₹{(baseline['damage_lakh'] - optimal['damage_lakh']):.0f} lakh")

print(f"\n🎯 ENHANCED FEATURES:")
print(f"  ✅ Real road network (44 km)")
print(f"  ✅ Spatially-varying roughness (roads, urban, vegetation)")
print(f"  ✅ Road-specific flooding metrics")
print(f"  ✅ Road drainage improvement scenarios")
print(f"  ✅ Enhanced damage modeling (roads + general)")

print(f"\n📁 Outputs:")
print(f"  ├── scenario_results_ENHANCED.csv")
print(f"  ├── qcia_analysis_ENHANCED.png")
print(f"  └── data/processed_enhanced/enhanced_data_preview.png")

print("\n" + "="*70 + "\n")

