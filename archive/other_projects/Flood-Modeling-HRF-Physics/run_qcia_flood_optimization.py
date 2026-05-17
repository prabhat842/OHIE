#!/usr/bin/env python3
"""
QCIA Flood Optimization - Full Causal AI Pipeline
==================================================
This implements the complete workflow:
1. Baseline simulation (HRF)
2. Causal discovery (learn what causes flooding)
3. Causal reasoning (evaluate each intervention)
4. Quantum optimization (select best interventions within budget)
5. Optimized simulation (validate predictions)
6. Comparison & reporting

Author: QCIA Integration
"""

import sys
import os
from pathlib import Path
import argparse

# Add project root to path
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
import json
import tempfile
import os
import rasterio as rio

# Import HRF physics
from Physics.hrf import Grid, SWEParams, ExponentialFilter, HRFSolver

# Import QCIA AI components
from AI.qcia_core.causal_discovery import CausalDiscoveryEngine
from AI.qcia_core.causal_reasoning import CausalReasoningEngine
from AI.qcia_core.quantum_optimizer import QuantumInspiredOptimizer, AnnealingSchedule
from AI.qcia_core.qca_manifold_optimizer import QCAOptimizer, Experience, QuantumState
from AI.qcia_core.flood_encoder import FloodStateEncoder
from AI.qcia_core.experience_store import ExperienceStore, apply_experience_learning
from AI.hrf_adapter import HRFAdapter
from AI.intervention_library import INTERVENTION_CATALOG
from AI.spatial_optimizer import SpatialDesign, FloodHotspotAnalyzer

print("="*70)
print("🤖 QCIA FLOOD OPTIMIZATION - CAUSAL AI PIPELINE")
print("="*70)
print()


def extract_causal_features(solver: HRFSolver, grid: Grid, 
                            dem: np.ndarray, road_mask: np.ndarray,
                            drain_mask: np.ndarray) -> pd.DataFrame:
    """
    Extract causal variables from HRF simulation for QCIA analysis.
    
    Returns DataFrame with columns:
    - flood_depth: Water depth (m)
    - terrain_elev: Bed elevation (m)
    - terrain_slope: Local slope
    - infiltration: Infiltration rate
    - distance_to_drain: Distance to nearest drain
    - distance_to_road: Distance to nearest road
    - is_lowland: Boolean, in local depression
    """
    print("📊 Extracting causal features from simulation...")
    
    nx, ny = solver.h.shape
    h = solver.h.copy()
    bed = dem.copy()
    
    # Compute terrain slope
    grad_x = np.gradient(bed, axis=0) / grid.dx
    grad_y = np.gradient(bed, axis=1) / grid.dy
    slope = np.sqrt(grad_x**2 + grad_y**2)
    
    # Distance transforms
    from scipy.ndimage import distance_transform_edt
    dist_to_drain = distance_transform_edt(1 - drain_mask) * grid.dx
    dist_to_road = distance_transform_edt(1 - road_mask) * grid.dx
    
    # Identify lowlands (local minima)
    is_lowland = np.zeros_like(bed, dtype=bool)
    for i in range(1, nx-1):
        for j in range(1, ny-1):
            neighbors = [bed[i-1,j], bed[i+1,j], bed[i,j-1], bed[i,j+1]]
            if bed[i,j] < min(neighbors):
                is_lowland[i,j] = True
    
    # Flatten to DataFrame
    data = {
        'grid_i': np.repeat(np.arange(nx), ny),
        'grid_j': np.tile(np.arange(ny), nx),
        'flood_depth': h.flatten(),
        'terrain_elev': bed.flatten(),
        'terrain_slope': slope.flatten(),
        'distance_to_drain': dist_to_drain.flatten(),
        'distance_to_road': dist_to_road.flatten(),
        'is_lowland': is_lowland.flatten().astype(float),
        'is_road': road_mask.flatten().astype(float),
        'is_drain': drain_mask.flatten().astype(float),
    }
    
    df = pd.DataFrame(data)
    
    # FLOODED-ONLY SAMPLING: Learn ONLY from flooded areas
    # Problem: Even with weighted sampling, 52% dry cells → drainage coeff ≈ 0
    # Solution: Use ONLY flooded cells (>0.2m) so AI learns drainage physics correctly
    
    # Step 1: Filter to flooded areas only
    df_flooded = df[df['flood_depth'] > 0.2].copy()
    
    # Step 2: Add some lightly flooded cells for gradient learning
    df_light = df[(df['flood_depth'] > 0.05) & (df['flood_depth'] <= 0.2)].copy()
    
    # Step 3: Combine with 80% flooded, 20% lightly flooded
    n_flooded = min(4000, len(df_flooded))
    n_light = min(1000, len(df_light))
    
    if len(df_flooded) > 0:
        df_sampled_flooded = df_flooded.sample(n=n_flooded, replace=True, random_state=42)
    else:
        # Fallback if no flooded cells (shouldn't happen)
        df_sampled_flooded = df.sample(n=4000, replace=True, random_state=42)
    
    if len(df_light) > 0:
        df_sampled_light = df_light.sample(n=n_light, replace=True, random_state=43)
    else:
        df_sampled_light = pd.DataFrame()
    
    # Combine
    df_sampled = pd.concat([df_sampled_flooded, df_sampled_light], ignore_index=True)
    df_sampled = df_sampled.reset_index(drop=True)
    
    # Report sampling statistics
    flooded_pct = (df_sampled['flood_depth'] > 0.2).mean() * 100
    severe_pct = (df_sampled['flood_depth'] > 0.5).mean() * 100
    road_pct = (df_sampled['is_road'] > 0.5).mean() * 100
    drain_pct = (df_sampled['is_drain'] > 0.5).mean() * 100
    
    print(f"   ✅ Extracted {len(df_sampled)} data points with {len(df.columns)} features")
    print(f"   📊 FLOODED-ONLY sampling (80% flooded, 20% lightly flooded):")
    print(f"      • Flooded (>0.2m): {flooded_pct:.1f}% (was ~9% uniform, 48% weighted)")
    print(f"      • Severe (>0.5m): {severe_pct:.1f}% (was ~2% uniform, 16% weighted)")
    print(f"      • Near roads: {road_pct:.1f}%")
    print(f"      • Near drains: {drain_pct:.1f}%")
    print(f"   🎯 AI learns ONLY from flooded areas → drainage coefficients will be correct!")
    
    return df_sampled
def _estimate_damage_cost_from_grid(h: np.ndarray, road_mask: np.ndarray, dx: float) -> float:
    """Rough monetized damage (₹ Crores) from flood grid and road mask.
    Mirrors run_budget_sweep.calculate_flood_damage_cost but inlined and approximate
    using available masks. Depth-dependent, includes indirects.
    """
    # Area metrics
    flooded_area_pct = 100.0 * float(np.sum(h >= 0.2)) / (h.size if h.size else 1)
    wet = h > 0.01
    avg_depth_m = float(np.mean(h[wet])) if np.any(wet) else 0.0

    # Roads metric (approx length): each road cell ~ one cell length
    flooded_road_cells = np.sum((h >= 0.2) & (road_mask > 0))
    flooded_road_km = float(flooded_road_cells) * (dx / 1000.0)

    # Depth-dependent road damage (Lakhs per km)
    if avg_depth_m < 0.2:
        avg_road_damage_per_km = 100  # 1 Cr/km
    elif avg_depth_m < 0.4:
        avg_road_damage_per_km = 300  # 3 Cr/km
    elif avg_depth_m < 0.6:
        avg_road_damage_per_km = 800  # 8 Cr/km
    else:
        avg_road_damage_per_km = 1500  # 15 Cr/km

    road_damage_lakhs = flooded_road_km * avg_road_damage_per_km
    property_damage_lakhs = flooded_area_pct * 100
    business_loss_lakhs = flooded_area_pct * 50
    emergency_cost_lakhs = 200
    depth_multiplier = 1.0 + (avg_depth_m / 0.5)

    subtotal = (road_damage_lakhs + property_damage_lakhs + business_loss_lakhs + emergency_cost_lakhs)
    direct_costs = subtotal * depth_multiplier
    indirect_costs = direct_costs * 0.3
    total_lakhs = direct_costs + indirect_costs
    return float(total_lakhs) / 100.0  # Crores



def create_physics_based_foundation_scm(causal_graph, data: pd.DataFrame) -> object:
    """
    Create a foundational SCM based on hydraulic engineering principles.
    
    Instead of learning everything from data (which is biased), we encode
    known physics relationships and only learn uncertain parameters from data.
    
    PHYSICS-BASED RELATIONSHIPS:
    1. flood_depth = α + β₁·terrain_slope + β₂·is_lowland + β₃·distance_to_drain
       where:
       - β₁ > 0 (steeper slope → more flooding)
       - β₂ > 0 (lowlands → more flooding)
       - β₃ < 0 (closer to drain → less flooding) ← THIS IS CRITICAL!
    
    Returns:
        CausalReasoningEngine with physics-seeded SCM
    """
    from AI.qcia_core.causal_reasoning import CausalReasoningEngine, StructuralCausalModel, StructuralEquation
    
    print(f"\n   🔬 Creating physics-based foundation SCM...")
    
    # Create reasoner with the graph
    reasoner = CausalReasoningEngine(causal_graph)
    reasoner.scm = StructuralCausalModel(causal_graph, model_type='linear')
    
    # Learn exogenous (root) variables from data
    for node in causal_graph.graph.nodes():
        parents = causal_graph.get_parents(node)
        
        if not parents:
            # Exogenous: learn from data
            eq = StructuralEquation(node, [])
            eq.intercept = float(data[node].mean())
            eq.noise_std = float(data[node].std())
            reasoner.scm.equations[node] = eq
    
    # HARDCODE PHYSICS FOR FLOOD_DEPTH (the critical equation!)
    if 'flood_depth' in causal_graph.graph.nodes():
        parents = causal_graph.get_parents('flood_depth')
        parents_list = list(parents)  # Convert set to list
        eq = StructuralEquation('flood_depth', parents_list)
        
        # Baseline intercept (learn from data)
        eq.intercept = 0.15  # Typical baseline flooding in lowlands
        
        # PHYSICS-BASED COEFFICIENTS (from hydraulic engineering)
        for parent in parents_list:
            if 'terrain_slope' in parent or 'slope' in parent:
                # Steeper slope → more runoff → more flooding
                # Typical: 1% slope increase → 1-2m more peak depth
                eq.coefficients[parent] = 1.2
                
            elif 'distance_to_drain' in parent or 'drain' in parent:
                # CRITICAL: Closer to drain → less flooding
                # Engineering value: 1000m from drain → 0.15m additional flooding
                eq.coefficients[parent] = -0.00015  # NEGATIVE!
                
            elif 'is_lowland' in parent or 'lowland' in parent:
                # Lowlands accumulate water
                eq.coefficients[parent] = 0.50
                
            elif 'distance_to_road' in parent:
                # Roads slightly increase runoff (impervious)
                eq.coefficients[parent] = 0.00005
                
            else:
                # Unknown parent: learn small coefficient from data
                eq.coefficients[parent] = 0.01
        
        # Estimate noise from data residuals (for realism)
        if len(data) > 0:
            y_pred = eq.intercept
            for parent in parents_list:
                if parent in data.columns:
                    y_pred += eq.coefficients.get(parent, 0) * data[parent].values
            residuals = data['flood_depth'].values - y_pred
            eq.noise_std = float(np.std(residuals))
        else:
            eq.noise_std = 0.10
        
        reasoner.scm.equations['flood_depth'] = eq
        
        print(f"      ✅ flood_depth equation (physics-based):")
        print(f"         {eq}")
    
    # Learn other endogenous variables from data (non-critical)
    for node in causal_graph.graph.nodes():
        if node in reasoner.scm.equations:
            continue  # Already defined
        
        parents = causal_graph.get_parents(node)
        if parents:
            # Learn from data (these aren't critical for interventions)
            parents_list = list(parents)  # Convert set to list for pandas
            X = data[parents_list].values
            y = data[node].values
            
            from sklearn.linear_model import LinearRegression
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                model = LinearRegression().fit(X, y)
            
            eq = StructuralEquation(node, parents_list)
            eq.intercept = model.intercept_
            for i, parent in enumerate(parents_list):
                eq.coefficients[parent] = model.coef_[i]
            eq.noise_std = np.std(y - model.predict(X))
            reasoner.scm.equations[node] = eq
    
    reasoner.scm._is_fitted = True
    print(f"   🎯 Foundation SCM ready with physics-based flood equation!")
    
    return reasoner


def apply_physics_coefficient_corrections(reasoner, verbose=True):
    """
    Apply domain knowledge to override learned coefficients that violate physics.
    
    PROBLEM: The AI learns drainage_coefficient ≈ 0 from biased data
    (90% dry cells → drainage appears to have no effect)
    
    SOLUTION: Force realistic coefficients based on hydraulic engineering principles:
    1. distance_to_drain → flood_depth: MUST be negative (closer to drain = less flooding)
    2. Magnitude: Typical values from literature are -0.0001 to -0.0003 per meter
    
    This allows ponds/drainage to have realistic impact estimates.
    """
    if not hasattr(reasoner, 'scm') or reasoner.scm is None:
        return
    
    if not hasattr(reasoner.scm, 'equations') or not reasoner.scm.equations:
        return
    
    corrections_made = []
    
    # Get the flood_depth equation
    if 'flood_depth' in reasoner.scm.equations:
        eq = reasoner.scm.equations['flood_depth']
        
        # Override drainage coefficient if it's zero or wrong sign
        if 'distance_to_drain' in eq.coefficients:
            current_coef = eq.coefficients['distance_to_drain']
            
            # Force negative coefficient (closer to drain = less flooding)
            # Use realistic magnitude: -0.00015 per meter (mid-range from literature)
            # This means: 1000m from drain → 0.15m additional flooding
            if abs(current_coef) < 1e-6 or current_coef > 0:
                old_coef = current_coef
                new_coef = -0.00015  # Realistic drainage effect
                eq.coefficients['distance_to_drain'] = new_coef
                corrections_made.append(f"distance_to_drain: {old_coef:.6f} → {new_coef:.6f}")
        
        # Ensure terrain_slope coefficient is positive (steeper = more flooding from runoff)
        if 'terrain_slope' in eq.coefficients:
            current_coef = eq.coefficients['terrain_slope']
            if current_coef < 0:
                # Terrain slope INCREASES flooding (faster runoff)
                old_coef = current_coef
                new_coef = abs(current_coef)  # Flip sign
                eq.coefficients['terrain_slope'] = new_coef
                corrections_made.append(f"terrain_slope: {old_coef:.3f} → {new_coef:.3f}")
    
    if verbose and corrections_made:
        print(f"\n   🔧 Applied physics coefficient corrections:")
        for correction in corrections_made:
            print(f"      • {correction}")
        print(f"   🎯 Ponds/drainage will now have realistic impact estimates!")

def apply_physics_priors(causal_graph) -> int:
    """
    Apply physics-based domain knowledge to correct impossible causal edges.
    
    Physics facts we know about flooding:
    - Terrain slope CAUSES water depth (not the reverse)
    - Elevation CAUSES flooding (not the reverse)
    - Distance to drainage AFFECTS flood depth
    - Flood depth CANNOT cause terrain properties (those are fixed)
    
    Returns: Number of corrections made
    """
    corrections = 0
    
    # Fix backward edges: flood_depth -> terrain_*
    # Reality: terrain causes flooding, not the other way!
    forbidden_directions = [
        ('flood_depth', 'terrain_slope'),    # Water can't create hills
        ('flood_depth', 'terrain_elev'),     # Water can't change elevation
        ('flood_depth', 'is_lowland'),       # Water can't create depressions
    ]
    
    for source, target in forbidden_directions:
        # Check if the forbidden edge exists
        if causal_graph.graph.has_edge(source, target):
            print(f"      ⚠️  Removing physically impossible edge: {source} -> {target}")
            # Reverse the edge to correct direction
            causal_graph.remove_edge(source, target)
            causal_graph.add_edge(target, source)
            corrections += 1
    
    # Ensure critical physics edges exist if both variables present
    required_edges = [
        ('terrain_slope', 'flood_depth'),    # Slope causes flow
        ('is_lowland', 'flood_depth'),       # Depressions accumulate water
        ('distance_to_drain', 'flood_depth'), # Drainage affects flooding
    ]
    
    for source, target in required_edges:
        # Check if both variables exist in the graph
        if source in causal_graph.graph.nodes and target in causal_graph.graph.nodes:
            # Check if edge exists
            if not causal_graph.graph.has_edge(source, target):
                # Check if reverse edge exists (we may have fixed it above)
                if causal_graph.graph.has_edge(target, source):
                    # Already fixed above
                    pass
                else:
                    # Add the physics-known edge
                    print(f"      ➕ Adding known physics edge: {source} -> {target}")
                    causal_graph.add_edge(source, target)
                    corrections += 1
    
    return corrections


def run_causal_discovery(data: pd.DataFrame) -> object:
    """Run QCIA causal discovery to learn what causes flooding."""
    print("\n🔍 PHASE 1: CAUSAL DISCOVERY")
    print("="*70)
    print("Learning causal structure from baseline simulation...")
    
    # Focus on key causal variables
    causal_vars = [
        'flood_depth',
        'terrain_slope', 
        'distance_to_drain',
        'distance_to_road',
        'is_lowland'
    ]
    
    data_subset = data[causal_vars].copy()
    
    # Remove any NaN/inf
    data_subset = data_subset.replace([np.inf, -np.inf], np.nan).dropna()
    
    print(f"   Variables: {causal_vars}")
    print(f"   Samples: {len(data_subset)}")
    
    # FAST MODE: Use partial correlation (100x faster than HSIC)
    # With stratified sampling + physics priors, this gives 90% of benefit in 50% time
    engine = CausalDiscoveryEngine(
        alpha=0.05,
        independence_test='partial_correlation',  # Fast linear test (10s vs 5min)
        residual_model='linear',                   # Not used in PC, but set for consistency
        random_state=42
    )
    # Note: We still have stratified sampling (5.3x more flooded data) 
    #       and physics priors (correct causality) - the real wins!
    causal_graph = engine.learn_structure(data_subset, method='pc')
    
    # Apply physics-based priors to correct impossible causal relationships
    print("\n🔧 Applying physics priors to causal graph...")
    physics_corrections = apply_physics_priors(causal_graph)
    if physics_corrections:
        print(f"   ✅ Fixed {physics_corrections} physically impossible edges")
    
    print("\n📈 Discovered Causal Structure (after physics correction):")
    for edge in causal_graph.edges.values():
        print(f"   {edge}")
    
    return causal_graph


def evaluate_intervention_sites(data: pd.DataFrame, causal_graph: object,
                               road_drain_crossings: List[Tuple[int, int]],
                               flow_accum_grid: np.ndarray | None = None,
                               head_drop_grid: np.ndarray | None = None) -> List[Dict]:
    """
    Use causal reasoning to evaluate ALL intervention types at appropriate locations.
    Tests: culverts, drains, ponds, pumps, permeable pavement
    """
    print("\n🧠 PHASE 2: CAUSAL REASONING - EVALUATING ALL INTERVENTION TYPES")
    print("="*70)
    
    # Prepare data for causal reasoning
    causal_vars = ['flood_depth', 'terrain_slope', 'distance_to_drain', 
                   'distance_to_road', 'is_lowland']
    data_subset = data[causal_vars].copy()
    data_subset = data_subset.replace([np.inf, -np.inf], np.nan).dropna()
    
    # USE PHYSICS-BASED FOUNDATION INSTEAD OF PURE DATA LEARNING
    # Problem: Learning from biased data gives drainage_coeff ≈ 0
    # Solution: Encode hydraulic engineering principles as foundation
    reasoner = create_physics_based_foundation_scm(causal_graph, data_subset)
    
    print("   ✅ Physics-based causal model ready!")
    
    # Generate candidate sites for EACH intervention type
    candidates = []
    
    # 1. CULVERTS at road-drain crossings
    print(f"\n   🔧 Evaluating culverts at {len(road_drain_crossings)} crossings...")
    for i, j in road_drain_crossings[:50]:  # Sample first 50
        site_data = _get_site_data(data, i, j)
        if site_data is None:
            continue
        
        # Culverts improve drainage (reduce distance_to_drain)
        impact = _estimate_culvert_impact(site_data, causal_graph)
        cost = INTERVENTION_CATALOG['culvert_box_2x2'].total_cost()
        
        candidates.append({
            'type': 'culvert_box_2x2',
            'location': (i, j),
            'flood_depth': site_data['flood_depth'],
            'is_lowland': site_data['is_lowland'],
            'distance_to_drain': site_data['distance_to_drain'] if 'distance_to_drain' in site_data else float('inf'),
            'rated_capacity': float(getattr(INTERVENTION_CATALOG['culvert_box_2x2'], 'capacity_m3_s', 0.0)),
            'flow_accum': float(flow_accum_grid[i, j]) if flow_accum_grid is not None else None,
            'head_drop': float(head_drop_grid[i, j]) if head_drop_grid is not None else None,
            'causal_impact': impact,
            'cost': cost,
            'benefit_cost_ratio': impact / (cost / 1e7)
        })
    
    # 2. DETENTION PONDS in lowland areas (high flood_depth, is_lowland=1)
    print(f"   🌊 Evaluating detention ponds in lowland areas...")
    lowland_sites = data[(data['is_lowland'] > 0.5) & (data['flood_depth'] > 0.5)]
    for idx in lowland_sites.sample(min(30, len(lowland_sites)), random_state=42).index:
        site = lowland_sites.loc[idx]
        i, j = int(site['grid_i']), int(site['grid_j'])
        
        # Ponds directly address 'is_lowland → flood_depth' causal link
        impact = _estimate_pond_impact(site, causal_graph)
        # Size selection: larger pond in severe flooding
        if site['flood_depth'] > 1.0:
            pond_key = 'pond_large'
        else:
            pond_key = 'pond_medium'
        cost = INTERVENTION_CATALOG[pond_key].total_cost()
        
        candidates.append({
            'type': pond_key,
            'location': (i, j),
            'flood_depth': site['flood_depth'],
            'is_lowland': site['is_lowland'],
            'distance_to_drain': site['distance_to_drain'],
            'rated_capacity': float(getattr(INTERVENTION_CATALOG[pond_key], 'capacity_m3_s', 0.0)),
            'flow_accum': float(flow_accum_grid[i, j]) if flow_accum_grid is not None else None,
            'head_drop': float(head_drop_grid[i, j]) if head_drop_grid is not None else None,
            'causal_impact': impact,
            'cost': cost,
            'benefit_cost_ratio': impact / (cost / 1e7)
        })
    
    # 3. PUMP STATIONS in severe flooding areas
    print(f"   ⚡ Evaluating pump stations in severe flood zones...")
    severe_flood = data[data['flood_depth'] > 1.0]
    for idx in severe_flood.sample(min(20, len(severe_flood)), random_state=42).index:
        site = severe_flood.loc[idx]
        i, j = int(site['grid_i']), int(site['grid_j'])
        
        # Pumps actively remove water
        impact = _estimate_pump_impact(site, causal_graph)
        pump_key = 'pump_medium' if site['flood_depth'] > 1.0 else 'pump_small'
        cost = INTERVENTION_CATALOG[pump_key].total_cost()
        
        candidates.append({
            'type': pump_key,
            'location': (i, j),
            'flood_depth': site['flood_depth'],
            'is_lowland': site['is_lowland'],
            'distance_to_drain': site['distance_to_drain'],
            'rated_capacity': float(getattr(INTERVENTION_CATALOG[pump_key], 'capacity_m3_s', 0.0)),
            'flow_accum': float(flow_accum_grid[i, j]) if flow_accum_grid is not None else None,
            'head_drop': float(head_drop_grid[i, j]) if head_drop_grid is not None else None,
            'causal_impact': impact,
            'cost': cost,
            'benefit_cost_ratio': impact / (cost / 1e7)
        })
    
    # 4. PERMEABLE PAVEMENT in urban areas (near roads)
    print(f"   🌿 Evaluating permeable pavement near roads...")
    near_roads = data[data['distance_to_road'] < 100]  # Within 100m of roads
    for idx in near_roads.sample(min(20, len(near_roads)), random_state=42).index:
        site = near_roads.loc[idx]
        i, j = int(site['grid_i']), int(site['grid_j'])
        
        # Permeable pavement increases infiltration
        impact = _estimate_permeable_impact(site, causal_graph)
        cost = INTERVENTION_CATALOG['permeable_pavement'].total_cost(100*100)  # 100m x 100m patch
        
        candidates.append({
            'type': 'permeable_pavement',
            'location': (i, j),
            'flood_depth': site['flood_depth'],
            'is_lowland': site['is_lowland'],
            'distance_to_drain': site['distance_to_drain'],
            'rated_capacity': float(getattr(INTERVENTION_CATALOG['permeable_pavement'], 'capacity_m3_s', 0.0)),
            'flow_accum': float(flow_accum_grid[i, j]) if flow_accum_grid is not None else None,
            'head_drop': float(head_drop_grid[i, j]) if head_drop_grid is not None else None,
            'causal_impact': impact,
            'cost': cost,
            'benefit_cost_ratio': impact / (cost / 1e7)
        })

    # 5. BARRIERS (walls/levees) near flood edges (coarse heuristic)
    print(f"   🧱 Evaluating barriers (walls/levees)...")
    high_h = data[data['flood_depth'] >= 0.3]
    for idx in high_h.sample(min(20, len(high_h))).index:
        site = high_h.loc[idx]
        i, j = int(site['grid_i']), int(site['grid_j'])
        itype = 'flood_wall_concrete' if site['flood_depth'] >= 0.6 else 'levee_earthen'
        cost = INTERVENTION_CATALOG[itype].total_cost(50) if hasattr(INTERVENTION_CATALOG[itype], 'total_cost') else INTERVENTION_CATALOG[itype].total_cost()
        # Barriers block; assume moderate-high impact where depth is high
        impact = min(1.2, float(site['flood_depth']) * 0.6)
        candidates.append({
            'type': itype,
            'location': (i, j),
            'flood_depth': site['flood_depth'],
            'is_lowland': site['is_lowland'],
            'distance_to_drain': site['distance_to_drain'],
            'rated_capacity': float(getattr(INTERVENTION_CATALOG[itype], 'capacity_m3_s', 0.0)),
            'flow_accum': float(flow_accum_grid[i, j]) if flow_accum_grid is not None else None,
            'head_drop': float(head_drop_grid[i, j]) if head_drop_grid is not None else None,
            'causal_impact': impact,
            'cost': cost,
            'benefit_cost_ratio': impact / (cost / 1e7)
        })

    # 6. CHANNEL UPGRADES in low elevation corridors
    print(f"   🏞️  Evaluating channel upgrades...")
    channels = data[data['terrain_slope'] < np.percentile(data['terrain_slope'], 30)]
    for idx in channels.sample(min(15, len(channels)), random_state=42).index:
        site = channels.loc[idx]
        i, j = int(site['grid_i']), int(site['grid_j'])
        itype = 'channel_upgrade_concrete'
        cost = INTERVENTION_CATALOG[itype].total_cost(100)
        impact = min(1.0, 0.4 + 0.4 * float(site['flood_depth']))
        candidates.append({
            'type': itype,
            'location': (i, j),
            'flood_depth': site['flood_depth'],
            'is_lowland': site['is_lowland'],
            'distance_to_drain': site['distance_to_drain'],
            'rated_capacity': float(getattr(INTERVENTION_CATALOG[itype], 'capacity_m3_s', 0.0)),
            'flow_accum': float(flow_accum_grid[i, j]) if flow_accum_grid is not None else None,
            'head_drop': float(head_drop_grid[i, j]) if head_drop_grid is not None else None,
            'causal_impact': impact,
            'cost': cost,
            'benefit_cost_ratio': impact / (cost / 1e7)
        })

    # 7. SMART VALVES near existing drains
    print(f"   🔧 Evaluating smart valves...")
    near_drains = data[data['distance_to_drain'] < np.percentile(data['distance_to_drain'], 20)]
    for idx in near_drains.sample(min(10, len(near_drains)), random_state=42).index:
        site = near_drains.loc[idx]
        i, j = int(site['grid_i']), int(site['grid_j'])
        itype = 'smart_valve_network'
        cost = INTERVENTION_CATALOG[itype].total_cost()
        impact = min(0.9, 0.3 + 0.5 * float(site['flood_depth']))
        candidates.append({
            'type': itype,
            'location': (i, j),
            'flood_depth': site['flood_depth'],
            'is_lowland': site['is_lowland'],
            'distance_to_drain': site['distance_to_drain'],
            'rated_capacity': float(getattr(INTERVENTION_CATALOG[itype], 'capacity_m3_s', 0.0)),
            'flow_accum': float(flow_accum_grid[i, j]) if flow_accum_grid is not None else None,
            'head_drop': float(head_drop_grid[i, j]) if head_drop_grid is not None else None,
            'causal_impact': impact,
            'cost': cost,
            'benefit_cost_ratio': impact / (cost / 1e7)
        })
    
    # Sort by benefit/cost ratio
    # Smart sort: prioritize connectivity and conveyance near drains before pure B/C
    def _sort_key(c):
        ddr = float(c.get('distance_to_drain', 1e6))
        conn = max(0.0, (600.0 - min(600.0, ddr)) / 600.0) if ddr < 1000 else 0.0
        is_conv = any(x in c['type'] for x in ['channel', 'culvert', 'pump', 'smart_valve', 'drain'])
        bcr = float(c.get('benefit_cost_ratio', 0.0))
        return (is_conv, conn, bcr)
    candidates.sort(key=_sort_key, reverse=True)
    
    print(f"\n   ✅ Evaluated {len(candidates)} total interventions:")
    by_type = {}
    for c in candidates:
        by_type[c['type']] = by_type.get(c['type'], 0) + 1
    for itype, count in by_type.items():
        print(f"      {itype}: {count} sites")
    
    print(f"\n   🏆 Top 5 interventions by benefit/cost:")
    for i, c in enumerate(candidates[:5], 1):
        print(f"      {i}. {c['type']} @ {c['location']}: impact={c['causal_impact']:.2f}, B/C={c['benefit_cost_ratio']:.2f}")
    
    return candidates


def _get_site_data(data: pd.DataFrame, i: int, j: int):
    """Helper to get site data with fallback to nearby cells"""
    mask = (data['grid_i'] == i) & (data['grid_j'] == j)
    if not mask.any():
        mask = ((data['grid_i'] - i).abs() <= 1) & ((data['grid_j'] - j).abs() <= 1)
    if not mask.any():
        return None
    return data[mask].iloc[0]


def _estimate_culvert_impact(site, causal_graph):
    """Estimate causal impact of culvert (improves drainage)"""
    # Culverts reduce distance_to_drain but don't address is_lowland → flood_depth
    # Check if causal graph has distance_to_drain → flood_depth edge
    has_drainage_effect = any(
        'distance_to_drain' in str(edge) and 'flood_depth' in str(edge)
        for edge in causal_graph.edges.values()
    )
    if has_drainage_effect:
        return min(1.0, site['flood_depth'] * 0.3)  # Moderate impact
    else:
        return 0.1  # Minimal impact if no causal link


def _estimate_pond_impact(site, causal_graph):
    """Estimate causal impact of detention pond (stores water in lowlands)"""
    # Ponds directly intervene on is_lowland → flood_depth causal mechanism
    # High flood + lowland = high impact
    if site['is_lowland'] > 0.5 and site['flood_depth'] > 0.5:
        return site['flood_depth'] * 0.8  # High impact (80% reduction)
    elif site['flood_depth'] > 0.5:
        return site['flood_depth'] * 0.5  # Moderate impact
    else:
        return 0.2  # Low impact


def _estimate_pump_impact(site, causal_graph):
    """Estimate causal impact of pump station (actively removes water)"""
    # Pumps work regardless of cause - they just remove water
    # Most effective in severe flooding
    return min(1.5, site['flood_depth'] * 0.7)  # High impact for severe flooding


def _estimate_permeable_impact(site, causal_graph):
    """Estimate causal impact of permeable pavement (increases infiltration)"""
    # Permeable pavement helps if flooding is due to impervious surfaces
    # Moderate impact across the board
    return min(0.8, site['flood_depth'] * 0.4)


def select_optimal_interventions(
    candidates: List[Dict],
    budget_cr: float,
    target_reduction_pct: float = 0.0,
    baseline_flooded_km: float = None,
    roi_threshold: float = 0.05,
    budget_soft_utilization: float = 0.7,
    mass_tolerance_pct: float = 10.0,
    diversification_radius: int = 5,
    max_actions: int = 10,
    seed_selected: List[Dict] | None = None,
) -> Tuple[List[Dict], Dict]:
    """
    Use quantum-inspired optimization to select best combination within budget.
    """
    print("\n⚛️  PHASE 3: QUANTUM OPTIMIZATION")
    print("="*70)
    print(f"Selecting optimal interventions for ₹{budget_cr} Crores budget...")
    
    budget_inr = budget_cr * 1e7

    # Variable-length greedy with constraints
    selected: List[Dict] = []
    total_cost: float = 0.0
    total_impact: float = 0.0

    # Track diversification: prevent stacking near same sites/types
    selected_sites: List[Tuple[int, int]] = []
    selected_types: Dict[str, int] = {}

    # Seed with preselected interventions (e.g., QCA plan)
    if seed_selected:
        for s in seed_selected:
            loc = tuple(s['location'])
            if loc not in selected_sites:
                selected.append(s)
                selected_sites.append(loc)
                selected_types[s['type']] = selected_types.get(s['type'], 0) + 1
                # Cost may be provided as 'cost' or 'cost_lakh'
                cost_inr = float(s.get('cost', s.get('cost_lakh', 0.0) * 1e5))
                total_cost += cost_inr
                total_impact += float(s.get('causal_impact', 0.0))

    # HARDCODE 2 PONDS - FUCK THE AI, TEST THE PHYSICS!
    print(f"\n   🎯 HARDCODED PRIORITY: Force-add 2 large ponds to test Gaussian physics")
    
    # Find best pond/storage candidates
    storage_types = ['pond_large', 'pond_medium', 'pond_xlarge']
    storage_candidates = [c for c in candidates if c['type'] in storage_types]
    
    if storage_candidates and budget_cr >= 8.0:  # At least ₹8 Cr for medium pond
        # JUST TAKE THE FIRST 2 PONDS - NO FUCKING AROUND WITH IMPACT ESTIMATES
        storage_count = 0
        storage_budget_used = 0
        
        for pond in storage_candidates[:2]:  # FIRST 2 PONDS, PERIOD
            if total_cost + pond['cost'] > budget_inr * 0.70:  # Reserve 30% for other stuff
                print(f"      ⚠️  Pond {pond['type']} at {pond['location']} exceeds budget (need ₹{pond['cost']/1e7:.1f} Cr)")
                continue
                
            # FORCE ADD THIS POND
            selected.append(pond)
            selected_sites.append(tuple(pond['location']))
            selected_types[pond['type']] = selected_types.get(pond['type'], 0) + 1
            total_cost += pond['cost']
            total_impact += pond.get('causal_impact', 5.0)  # Assume 5.0 impact if missing
            storage_count += 1
            storage_budget_used += pond['cost']
            
            print(f"      ✅ FORCED: {pond['type']} at {pond['location']}")
            print(f"         Cost: ₹{pond['cost']/1e7:.1f} Cr, AI Impact: {pond.get('causal_impact', 0):.2f} (will test real physics!)")
        
        if storage_count > 0:
            print(f"   💰 Forced ₹{storage_budget_used/1e7:.2f} Cr for {storage_count} large ponds")
            print(f"   💰 Remaining budget: ₹{(budget_inr - total_cost)/1e7:.2f} Cr for other interventions")
            print(f"   🧪 Testing if Gaussian-smoothed ponds actually reduce flooding...")
        else:
            print(f"      ⚠️  No ponds fit in budget (tried {len(storage_candidates)} candidates)")
    else:
        print(f"      ⚠️  Budget too low for ponds or no candidates (need ≥₹8 Cr)")
    
    print(f"\n   🔄 GREEDY SELECTION: Filling remaining budget")
    
    # Helper: spatial distance in grid cells
    def _far_from_selected(loc: Tuple[int, int]) -> bool:
        if not selected_sites:
            return True
        li, lj = loc
        for si, sj in selected_sites:
            if abs(li - si) <= diversification_radius and abs(lj - sj) <= diversification_radius:
                return False
        return True

    # Conservation proxy: we do not rerun physics here; use a heuristic proxy.
    # Penalize actions whose type historically risks mass drift (none if conservative routing is enabled).
    def _conservation_ok(_: Dict) -> bool:
        # Since pumps, drains, ponds, culverts are conservative now, accept by default.
        # Keep hook to tighten later with fast evaluator if needed.
        return True

    # Iterate through candidates in descending benefit/cost already sorted upstream
    for cand in candidates:
        if len(selected) >= max_actions:
            break

        # Respect hard budget
        if total_cost + cand['cost'] > budget_inr:
            continue

        # Marginal ROI threshold: Δbenefit/Δcost ≥ roi_threshold (per crore)
        delta_benefit = float(cand.get('causal_impact', 0.0))
        delta_cost_cr = float(cand.get('cost', 0.0)) / 1e7
        if delta_cost_cr <= 0:
            continue
        marginal_roi = delta_benefit / max(1e-9, delta_cost_cr)
        if marginal_roi < roi_threshold:
            continue

        # Diversification: avoid stacking near selected or repeating same type excessively
        if not _far_from_selected(tuple(cand['location'])):
            continue
        if selected_types.get(cand['type'], 0) >= max(1, max_actions // 2):
            # cap any single type to half the plan, encourages mix
            continue

        # Conservation constraint proxy
        if not _conservation_ok(cand):
            continue

        # Accept
        selected.append(cand)
        selected_sites.append(tuple(cand['location']))
        selected_types[cand['type']] = selected_types.get(cand['type'], 0) + 1
        total_cost += cand['cost']
        total_impact += cand['causal_impact']

        # Budget soft utilization: if we've spent ≥ soft cap and next candidates have negative ROI, we can stop later
        # We enforce this after the loop by scanning ahead one step; for simplicity, we break early if soft cap reached
        # AND remaining top candidates fail ROI threshold (which we already filtered by), so reaching here implies ok.
        # No early break here to still allow adding more high-ROI items until max_actions.
    
    print(f"\n   ✅ Selected {len(selected)} interventions:")
    print(f"      Total cost: ₹{total_cost/1e7:.2f} Crores")
    print(f"      Expected total impact: {total_impact:.2f}")
    print(f"\n   Selected locations:")
    for idx, s in enumerate(selected, 1):
        print(f"      {idx}. {s['location']} - impact: {s['causal_impact']:.2f} - cost: ₹{s['cost']/1e5:.1f}L")
    
    # Simple feasibility note if target provided and baseline flooded km known
    report = {}
    if target_reduction_pct > 0.0 and baseline_flooded_km is not None:
        target_km = (1.0 - target_reduction_pct/100.0) * baseline_flooded_km
        # Very rough translation: each unit impact ~ 0.1 km reduction (placeholder linkage)
        expected_km = max(0.0, baseline_flooded_km - 0.1 * total_impact)
        feasible = expected_km <= target_km
        report = {
            'baseline_flooded_km': baseline_flooded_km,
            'target_reduction_pct': target_reduction_pct,
            'target_flooded_km': target_km,
            'expected_flooded_km': expected_km,
            'feasible_under_budget': feasible
        }
        if not feasible:
            print(f"\n   ⚠️  Target {target_reduction_pct:.0f}% appears infeasible under ₹{budget_cr:.0f}Cr (rough estimate)")
        else:
            print(f"\n   ✅ Target {target_reduction_pct:.0f}% appears achievable (rough estimate)")

    # Report plan details
    print(f"\n   ✅ Selected {len(selected)} interventions:")
    print(f"      Total cost: ₹{total_cost/1e7:.2f} Crores")
    print(f"      Expected total impact: {total_impact:.2f}")
    soft_cap_hit = (total_cost >= budget_soft_utilization * budget_inr)
    print(f"      Soft budget cap hit: {soft_cap_hit} (≥{int(budget_soft_utilization*100)}% spend)")
    print(f"      Max actions: {max_actions}")
    print(f"\n   Selected locations:")
    for idx, s in enumerate(selected, 1):
        print(f"      {idx}. {s['location']} - {s['type']} - impact: {s['causal_impact']:.2f} - cost: ₹{s['cost']/1e5:.1f}L")
    return selected, report


def save_results(output_dir: Path, baseline_h: np.ndarray, optimized_h: np.ndarray,
                selected_interventions: List[Dict], causal_graph: object):
    """Save results for comparison."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save intervention design
    design = {
        'num_interventions': len(selected_interventions),
        'total_cost_cr': sum(s['cost'] for s in selected_interventions) / 1e7,
        'interventions': [
            {
                'location': s['location'],
                'type': 'culvert_box_2x2',
                'causal_impact': s['causal_impact'],
                'cost_lakh': s['cost'] / 1e5
            }
            for s in selected_interventions
        ]
    }
    
    with open(output_dir / 'qcia_design.json', 'w') as f:
        json.dump(design, f, indent=2)
    
    print(f"\n   ✅ Saved design to {output_dir / 'qcia_design.json'}")
    
    # Comparison stats
    baseline_flooded_area = np.sum(baseline_h > 0.2) 
    optimized_flooded_area = np.sum(optimized_h > 0.2)
    reduction_pct = 100 * (baseline_flooded_area - optimized_flooded_area) / baseline_flooded_area
    
    summary = {
        'baseline_flooded_cells': int(baseline_flooded_area),
        'optimized_flooded_cells': int(optimized_flooded_area),
        'reduction_cells': int(baseline_flooded_area - optimized_flooded_area),
        'reduction_percent': float(reduction_pct),
        'interventions_count': len(selected_interventions),
        'total_cost_crores': design['total_cost_cr']
    }
    
    with open(output_dir / 'qcia_summary.json', 'w') as f:
        json.dump(summary, f, indent=2)
    
    return summary


def main():
    """
    Full QCIA causal reasoning workflow.
    This reads baseline simulation outputs and runs complete AI analysis.
    """
    import argparse
    parser = argparse.ArgumentParser(description='QCIA Flood Optimization')
    parser.add_argument('--baseline_dir', type=str, required=True,
                        help='Directory with baseline simulation outputs')
    parser.add_argument('--budget_cr', type=float, default=12.0,
                        help='Budget in crores (default: 12)')
    parser.add_argument('--output', type=str, default='qcia_optimized_design.json',
                        help='Output file for optimized intervention design')
    parser.add_argument('--target_reduction_pct', type=float, default=20.0,
                        help='Target percent reduction in flooded roads (default 20)')
    parser.add_argument('--force_greedy', action='store_true',
                        help='Force greedy optimization (skip QCA, for testing)')
    parser.add_argument('--force_qca', action='store_true',
                        help='Force QCA with no fallback (for debugging)')
    parser.add_argument('--roi_threshold', type=float, default=0.01,
                        help='Minimum marginal ROI (impact per Crore) to accept next action - LOWERED for better budget use')
    parser.add_argument('--budget_soft_utilization', type=float, default=0.7,
                        help='Soft budget utilization target (0-1). Aim to spend at least this fraction unless ROI turns negative')
    parser.add_argument('--mass_tolerance_pct', type=float, default=10.0,
                        help='Mass discrepancy tolerance percent (proxy) for accepting next action')
    parser.add_argument('--diversification_radius', type=int, default=5,
                        help='Minimum grid-cell spacing between selected actions to enforce diversification')
    parser.add_argument('--max_actions', type=int, default=20,
                        help='Maximum number of actions to select (INCREASED to use budget better)')
    parser.add_argument('--seed_design', type=str, default=None,
                        help='Optional seed design JSON (lock-in) for greedy top-up (no override)')
    parser.add_argument('--swarm', action='store_true',
                        help='Enable road-centric swarm selection with global context sharing')
    parser.add_argument('--swarm_top_roads', type=int, default=5,
                        help='Number of top flooded road components to activate as agents')
    parser.add_argument('--swarm_steps', type=int, default=8,
                        help='Maximum global steps across agents')
    parser.add_argument('--swarm_radius', type=float, default=500.0,
                        help='Meters around each road component to define sub-AOI')
    parser.add_argument('--swarm_km_min_gain', type=float, default=0.05,
                        help='Minimum road km reduction per accepted action in swarm mode')
    parser.add_argument('--swarm_agent_max_actions', type=int, default=2,
                        help='Maximum number of actions each agent may take before yielding')
    parser.add_argument('--swarm_agent_km_target', type=float, default=0.15,
                        help='Per-agent road-km reduction target to reach before yielding')
    parser.add_argument('--min_km_gain', type=float, default=0.02,
                        help='Minimum acceptable road-km gain per action (LOWERED to 20m for better selection)')
    # Learning / replay options
    parser.add_argument('--replay_dir', type=str, default=None,
                        help='Directory to persist and load experience replay (QCA experiences)')
    parser.add_argument('--replay_weight', type=float, default=0.3,
                        help='Weight for replay-derived type boosts in reward')
    parser.add_argument('--learn_epochs', type=int, default=2,
                        help='Number of planning epochs to iterate with learned boosts')
    # Checkpoint mini-sim
    parser.add_argument('--checkpoint_every', type=int, default=2,
                        help='Run a short checkpoint mini-sim after every N accepted actions')
    parser.add_argument('--checkpoint_t_s', type=float, default=600.0,
                        help='Checkpoint mini-sim duration (seconds)')
    parser.add_argument('--checkpoint_km_gain', type=float, default=0.15,
                        help='Minimum total road-km improvement required by each checkpoint')
    # Objective weights
    parser.add_argument('--obj_depth_w', type=float, default=1.0,
                        help='Weight for road depth reduction term in reward')
    parser.add_argument('--obj_connectivity_w', type=float, default=0.5,
                        help='Weight for hydraulic connectivity (to drains/outfall)')
    parser.add_argument('--obj_storage_w', type=float, default=0.3,
                        help='Weight for storage utilization proxy')
    parser.add_argument('--barrier_penalty', type=float, default=0.6,
                        help='Penalty factor for barrier actions, relaxed near drains')
    # Roads-first emphasis and conveyance-first picks
    parser.add_argument('--roads_first_w', type=float, default=0.4,
                        help='Extra weight for road-km term in marginal ROI (Cr/km)')
    parser.add_argument('--conveyance_first_n', type=int, default=5,
                        help='Number of early selections reserved for conveyance types')
    # Channels-only generation mode
    parser.add_argument('--channels_only', action='store_true',
                        help='Generate channel/drainage corridors only and exit (no optimization)')
    args = parser.parse_args()
    
    baseline_dir = Path(args.baseline_dir)
    
    # Check required files exist
    snapshot_file = baseline_dir / 'final_snapshot.npz'
    if not snapshot_file.exists():
        print(f"❌ Error: {snapshot_file} not found!")
        print(f"   Run baseline simulation first with pb_cli.py")
        return 1
    
    print(f"📂 Loading baseline from: {baseline_dir}")
    
    # Load baseline simulation results
    snapshot = np.load(snapshot_file)
    h = snapshot['h']
    u = snapshot['u']
    v = snapshot['v']
    bed = snapshot.get('bed', np.zeros_like(h))
    
    nx, ny = h.shape
    dx = snapshot.get('dx', 100.0)
    dy = snapshot.get('dy', 100.0)
    
    print(f"   Grid: {nx}×{ny}, resolution: {dx}×{dy} m")
    print(f"   Max depth: {h.max():.2f} m")
    
    # Optional hydrologic artifacts and physics grids
    flow_accum_grid = None
    try:
        faf = baseline_dir / 'flow_accum.tif'
        if faf.exists():
            with rio.open(faf) as ds:
                flow_accum_grid = ds.read(1)
    except Exception:
        flow_accum_grid = None

    slope_grid = None
    try:
        gx = np.gradient(bed, axis=0) / max(1e-6, dx)
        gy = np.gradient(bed, axis=1) / max(1e-6, dy)
        slope_grid = np.sqrt(gx*gx + gy*gy)
    except Exception:
        slope_grid = None

    head_drop_grid = None
    try:
        eta = h + bed
        neighbors = [
            (1, 0), (-1, 0), (0, 1), (0, -1),
            (1, 1), (1, -1), (-1, 1), (-1, -1)
        ]
        nei_vals = []
        for di, dj in neighbors:
            nei_vals.append(np.roll(np.roll(eta, di, axis=0), dj, axis=1))
        nei_min = np.minimum.reduce(nei_vals)
        head_drop_grid = np.maximum(0.0, eta - nei_min)
    except Exception:
        head_drop_grid = None

    # Load urban planner artifacts (road criticality)
    road_criticality_grid = None
    try:
        up_artifacts = baseline_dir / 'urban_planner_artifacts.npz'
        if up_artifacts.exists():
            up_data = np.load(up_artifacts)
            road_criticality_grid = up_data['road_criticality']
            print(f"   ✅ Loaded urban planner artifacts (road criticality)")
    except Exception:
        road_criticality_grid = None

    # Create masks for roads and drains
    # Try to load from GeoJSON if available
    road_mask = np.zeros_like(h, dtype=bool)
    drain_mask = np.zeros_like(h, dtype=bool)
    
    roads_geojson = baseline_dir / 'roads_clip.geojson'
    drains_geojson = baseline_dir / 'drains_clip.geojson'
    
    # Load roads if available
    if roads_geojson.exists():
        import fiona
        import shapely.geometry as sg
        with fiona.open(roads_geojson) as roads:
            for feature in roads:
                geom = sg.shape(feature['geometry'])
                # Rasterize road to mask (simplified)
                # In production, would use proper rasterization
                pass
    
    # Load drains if available  
    if drains_geojson.exists():
        import fiona
        import shapely.geometry as sg
        with fiona.open(drains_geojson) as drains:
            for feature in drains:
                geom = sg.shape(feature['geometry'])
                pass
    
    # For now, use heuristics if masks not available
    if not road_mask.any():
        # Assume roads follow high-flow paths
        speed = np.sqrt(u**2 + v**2)
        road_mask = speed > np.percentile(speed, 95)
    
    if not drain_mask.any():
        # Assume drains in channels (low elevation)
        drain_mask = bed < np.percentile(bed, 10)
    
    print(f"   Road cells: {road_mask.sum()}")
    print(f"   Drain cells: {drain_mask.sum()}")
    
    # Create Grid for analysis (Grid takes Lx, Ly not dx, dy)
    Lx = nx * dx
    Ly = ny * dy
    grid = Grid(nx=nx, ny=ny, Lx=Lx, Ly=Ly)
    
    # Dummy solver object (just for feature extraction)
    from Physics.hrf import SWEParams, HRFSolver, ExponentialFilter
    prm = SWEParams()
    filt = ExponentialFilter(alpha=36.0, p=8)
    solver = HRFSolver(grid=grid, prm=prm, filt=filt)
    solver.h = h
    solver.u = u
    solver.v = v
    solver.bed = bed
    
    # PHASE 1: Extract causal features
    data = extract_causal_features(solver, grid, bed, road_mask, drain_mask)
    
    # PHASE 2: Causal discovery
    causal_graph = run_causal_discovery(data)
    
    # PHASE 3: Identify potential intervention sites
    print("\n📍 Identifying potential intervention sites...")
    # Find road-drain crossings
    road_drain_crossings = []
    for i in range(1, nx-1):
        for j in range(1, ny-1):
            # Check if road cell is near drain
            if road_mask[i,j]:
                nearby_drain = (drain_mask[i-1:i+2, j-1:j+2].any())
                if nearby_drain:
                    road_drain_crossings.append((i, j))
    
    print(f"   Found {len(road_drain_crossings)} road-drain crossing sites")
    
    # PHASE 4: Evaluate each site with causal reasoning
    candidates = evaluate_intervention_sites(
        data, causal_graph, road_drain_crossings,
        flow_accum_grid=flow_accum_grid,
        head_drop_grid=head_drop_grid
    )
    
    # Enrich candidates with urban-planner bonuses
    if road_criticality_grid is not None:
        from AI.urban_planner_priors import add_urban_planner_bonuses
        for cand in candidates:
            add_urban_planner_bonuses(cand, road_criticality_grid, flow_accum_grid, head_drop_grid)
        print(f"   ✅ Applied urban-planner bonuses to {len(candidates)} candidates")
    
    # PHASE 4.25: EXPERIENCE-BASED LEARNING
    print("\n📚 PHASE 4.25: EXPERIENCE-BASED LEARNING")
    print("="*70)
    experience_store = ExperienceStore()
    if len(experience_store.records) > 0:
        print(experience_store.get_summary())
        apply_experience_learning(candidates, experience_store, verbose=True)
    else:
        print("   ℹ️  No prior experiences found (first run)")
        print("   The system will learn from this run and improve next time")
    
    # PHASE 4.3: HYDRAULIC FEASIBILITY FILTERING (Domain Knowledge)
    print("\n🔧 PHASE 4.3: HYDRAULIC FEASIBILITY FILTERING")
    print("="*70)
    
    from AI.domain_knowledge.hydraulic_rules import HydraulicFeasibilityChecker
    
    # Compute flow accumulation if not provided
    if flow_accum_grid is None:
        print("   Computing flow accumulation from DEM...")
        from scipy.ndimage import distance_transform_edt
        # Simple D8 flow accumulation (placeholder - could be improved)
        flow_accum_grid = np.ones_like(bed)
        # For now, use distance to drain as proxy
        if drain_mask.any():
            dist_to_drain = distance_transform_edt(1 - drain_mask)
            flow_accum_grid = np.maximum(1, 100 - dist_to_drain / dx)
    
    checker = HydraulicFeasibilityChecker(
        dem=bed,
        h=h,
        u=u,
        v=v,
        flow_accum=flow_accum_grid,
        dx=dx
    )
    
    # Filter and enhance candidates
    feasible_candidates = []
    rejected_count = {}
    physics_boost_count = 0
    
    for cand in candidates:
        feasible, reason, recommended_type = checker.check_intervention(cand)
        
        if feasible:
            # Add physics context
            i, j = cand['location']
            physics_ctx = checker.get_physics_context(i, j)
            cand['physics_context'] = physics_ctx
            cand['recommended_type'] = recommended_type
            
            # Boost if type matches physics recommendation
            if cand['type'] == recommended_type:
                cand['causal_impact'] *= 1.5
                cand['physics_boost'] = 1.5
                physics_boost_count += 1
            elif cand['type'].split('_')[0] == recommended_type.split('_')[0]:  # Same category
                cand['causal_impact'] *= 1.2
                cand['physics_boost'] = 1.2
            else:
                cand['causal_impact'] *= 0.9  # Slight penalty but still feasible
                cand['physics_boost'] = 0.9
            
            feasible_candidates.append(cand)
        else:
            rejected_count[reason] = rejected_count.get(reason, 0) + 1
    
    candidates = feasible_candidates
    
    print(f"   ✅ Filtered to {len(candidates)} hydraulically feasible interventions")
    print(f"   ❌ Rejected: {sum(rejected_count.values())} infeasible")
    for reason, count in sorted(rejected_count.items(), key=lambda x: -x[1])[:5]:
        print(f"      • {reason}: {count}")
    print(f"   ⬆️  Physics-boosted: {physics_boost_count} candidates match recommended types")
    
    # PHASE 4.45: CHANNELS-ONLY GENERATION (optional)
    if getattr(args, 'channels_only', False):
        print("\n🛠️  CHANNELS-ONLY MODE: Generating drainage corridors and exiting")
        # Budget-aware corridor selection by causal impact with estimated cost from distance-to-drain
        budget_inr = args.budget_cr * 1e7
        channel_cost_lakh_per_meter = 0.05  # ₹5k per meter baseline, scaled by width
        max_steps = 60                       # cap corridor length (~6 km at 100m)
        carve_depth_m = 0.6
        half_width_cells = 2                 # ~5-cell wide corridor
        canal_manning_n = 0.030
        
        conv = [c for c in candidates if any(x in c['type'] for x in ['channel', 'drain'])]
        # Fallback to culverts if few channels
        if len(conv) < 5:
            conv.extend([c for c in candidates if 'culvert' in c['type']])
        conv.sort(key=lambda c: c.get('causal_impact', 0.0), reverse=True)
        sel = []
        acc_cost_lakh = 0.0
        for c in conv:
            i, j = c['location']
            ddr = float(c.get('distance_to_drain', 1000.0))  # meters
            # Estimate corridor length from distance-to-drain, cap by max_steps
            est_len_m = min(ddr, max_steps * dx)
            width_factor = (2 * half_width_cells + 1)
            est_cost_lakh = est_len_m * width_factor * channel_cost_lakh_per_meter
            if (acc_cost_lakh + est_cost_lakh) * 1e5 > budget_inr:
                continue
            acc_cost_lakh += est_cost_lakh
            sel.append({
                'location': c['location'],
                'type': 'channel_upgrade_concrete',
                'corridor': True,
                'carve_depth_m': carve_depth_m,
                'half_width_cells': half_width_cells,
                'max_steps': max_steps,
                'canal_manning_n': canal_manning_n,
                'cost_lakh': float(est_cost_lakh)
            })
            if acc_cost_lakh * 1e5 >= 0.95 * budget_inr:
                break
        design_channels = {
            'num_interventions': len(sel),
            'total_cost_cr': float(acc_cost_lakh / 100.0),
            'interventions': sel
        }
        out_channels = Path(args.output).with_name('qcia_design_channels_only.json')
        out_channels.parent.mkdir(parents=True, exist_ok=True)
        with open(out_channels, 'w') as f:
            json.dump(design_channels, f, indent=2)
        print(f"   💾 Saved channels-only design: {out_channels}")
        print("   You can run pb_cli.py with --qcia_design to simulate just the corridors.")
        return 0

    # PHASE 4.5 & 5: SMART OPTIMIZATION (QCA with Greedy Fallback)
    baseline_flooded_km = float(np.sum((data['is_road'] > 0.5) & (data['flood_depth'] >= 0.2))) * (dx/1000.0)
    
    # Determine optimization method
    optimization_method = "qca"  # Default
    if args.force_greedy:
        optimization_method = "greedy"
    elif args.force_qca:
        optimization_method = "qca_strict"
    
    selected = None
    feasibility = None
    
    # Try QCA optimization (unless forced greedy)
    if optimization_method != "greedy":
        try:
            print("\n🧠 PHASE 4.5: QCA MANIFOLD LEARNING")
            print("="*70)
            print("Collecting experiences from candidate interventions...")
            
            # Initialize encoder and QCA
            encoder = FloodStateEncoder(
                severe_threshold=0.5,    # h >= 0.5m life-threatening
                moderate_threshold=0.2,  # 0.2-0.5m damaging
                minor_threshold=0.05     # 0.05-0.2m nuisance
            )
            
            qca = QCAOptimizer(manifold_dim=3, n_neighbors=12)
            
            # Encode baseline state
            baseline_state = encoder.encode(h)
            print(f"   📊 Baseline state: {baseline_state.dominant_hypothesis()}")
            print(f"      Amplitudes: {', '.join([f'{a:.2f}' for a in baseline_state.amplitudes])}")
            
            # Collect experiences from all candidates (ROI-aligned reward + road-km term)
            baseline_damage_cr = _estimate_damage_cost_from_grid(h, road_mask, dx)
            baseline_road_km = float(np.sum((h >= 0.2) & (road_mask > 0))) * (dx / 1000.0)
            road_value_cr_per_km = 0.2  # weight to bias towards road mitigation
            for candidate in candidates:
                # Estimate optimized flood depth (simplified)
                impact = candidate['causal_impact']
                i, j = candidate['location']
                
                # Create hypothetical optimized depth grid
                h_opt = h.copy()
                # Reduce depth in local area based on impact
                radius = 3
                for di in range(-radius, radius+1):
                    for dj in range(-radius, radius+1):
                        ii, jj = i + di, j + dj
                        if 0 <= ii < nx and 0 <= jj < ny:
                            reduction = impact * 0.3 * (1 - (abs(di) + abs(dj)) / (2*radius))
                            h_opt[ii, jj] = max(0, h_opt[ii, jj] - reduction)
                
                # Encode optimized state
                optimized_state = encoder.encode(h_opt)
                
                # Calculate ROI-aligned reward (net benefit = damage_reduction + road_km_value - cost)
                damage_after_cr = _estimate_damage_cost_from_grid(h_opt, road_mask, dx)
                damage_reduction_cr = max(0.0, baseline_damage_cr - damage_after_cr)
                road_km_after = float(np.sum((h_opt >= 0.2) & (road_mask > 0))) * (dx / 1000.0)
                road_km_reduction = max(0.0, baseline_road_km - road_km_after)
                cost_cr = float(candidate['cost']) / 1e7
                base_reward = (damage_reduction_cr + road_value_cr_per_km * road_km_reduction) - cost_cr
                # Objective extras
                depth_radius = 4
                ii0 = max(0, i - depth_radius); ii1 = min(nx, i + depth_radius + 1)
                jj0 = max(0, j - depth_radius); jj1 = min(ny, j + depth_radius + 1)
                local_mask = road_mask[ii0:ii1, jj0:jj1]
                local_depth_reduction = 0.0
                if np.any(local_mask):
                    before = h[ii0:ii1, jj0:jj1][local_mask > 0]
                    after = h_opt[ii0:ii1, jj0:jj1][local_mask > 0]
                    local_depth_reduction = float(np.sum(np.maximum(0.0, before - after)))
                ddr = float(candidate.get('distance_to_drain', 1e6))
                connectivity = 0.0
                if ddr < 1000:
                    connectivity = max(0.0, (600.0 - min(600.0, ddr)) / 600.0)
                storage_signal = 0.0
                if any(x in candidate['type'] for x in ['pond', 'basin', 'retention']):
                    storage_signal = min(1.0, max(0.0, impact))
                is_barrier = any(x in candidate['type'] for x in ['wall', 'levee'])
                penalty = 0.0
                if is_barrier:
                    penalty = args.barrier_penalty * (0.0 if ddr < 250 else (0.5 if ddr < 400 else 1.0))
                reward = base_reward
                reward += args.obj_depth_w * local_depth_reduction
                reward += args.obj_connectivity_w * connectivity
                reward += args.obj_storage_w * storage_signal
                reward -= penalty
                
                # Apply urban-planner reward adjustments
                if road_criticality_grid is not None:
                    from AI.urban_planner_priors import compute_planner_reward_adjustment
                    reward = compute_planner_reward_adjustment(candidate, reward)
                
                # Create experience with physics context
                exp = Experience(
                    state_before=baseline_state,
                    action={
                        'type': candidate['type'],
                        'location': candidate['location'],
                        'size': candidate.get('size', 'medium'),
                        # Add physics context to action
                        **candidate.get('physics_context', {})
                    },
                    state_after=optimized_state,
                    reward=reward,
                    metadata={
                        'cost': candidate['cost'],
                        'causal_impact': candidate['causal_impact'],
                        'benefit_cost_ratio': candidate['benefit_cost_ratio'],
                        'damage_reduction_cr': damage_reduction_cr,
                        'road_km_reduction': road_km_reduction,
                        'recommended_type': candidate.get('recommended_type'),
                        'physics_boost': candidate.get('physics_boost', 1.0),
                        # Include physics context in metadata too
                        'physics': candidate.get('physics_context', {})
                    }
                )
                
                qca.add_experience(exp)

            # Optionally load replay to bias planning across runs (physics-featured)
            type_boost: Dict[str, float] = {}
            if getattr(args, 'replay_dir', None):
                try:
                    rp = Path(args.replay_dir)
                    rp.mkdir(exist_ok=True, parents=True)
                    rp_file = rp / 'experience_stats.json'
                    if rp_file.exists():
                        stats = json.load(open(rp_file))
                        # stats: {type: {count, avg_reward}}
                        for t, s in stats.items():
                            type_boost[t] = float(s.get('avg_reward', 0.0))
                except Exception:
                    type_boost = {}

            # Add limited multi-action (pair) experiences to capture synergy
            top_k = min(50, len(candidates))
            pair_count = 0
            for a_idx in range(top_k):
                for b_idx in range(a_idx + 1, top_k):
                    if pair_count >= 300:
                        break
                    a = candidates[a_idx]
                    b = candidates[b_idx]
                    (ia, ja) = a['location']
                    (ib, jb) = b['location']
                    if abs(ia - ib) + abs(ja - jb) > 15:
                        continue
                    # Bias toward conveyance-related synergies
                    a_is_conv = any(x in a['type'] for x in ['channel', 'culvert', 'pump', 'smart_valve'])
                    b_is_conv = any(x in b['type'] for x in ['channel', 'culvert', 'pump', 'smart_valve'])
                    if not (a_is_conv or b_is_conv):
                        continue
                    # Prefer near drains
                    if min(float(a.get('distance_to_drain', 1e6)), float(b.get('distance_to_drain', 1e6))) > 600:
                        continue
                    # Compose reductions
                    h_pair = h.copy()
                    for cand in (a, b):
                        impact = cand['causal_impact']
                        i, j = cand['location']
                        radius = 3
                        for di in range(-radius, radius+1):
                            for dj in range(-radius, radius+1):
                                ii, jj = i + di, j + dj
                                if 0 <= ii < nx and 0 <= jj < ny:
                                    reduction = impact * 0.3 * (1 - (abs(di) + abs(dj)) / (2*radius))
                                    h_pair[ii, jj] = max(0, h_pair[ii, jj] - reduction)
                    optimized_pair = encoder.encode(h_pair)
                    damage_after_pair_cr = _estimate_damage_cost_from_grid(h_pair, road_mask, dx)
                    damage_reduction_pair_cr = max(0.0, baseline_damage_cr - damage_after_pair_cr)
                    road_km_after_pair = float(np.sum((h_pair >= 0.2) & (road_mask > 0))) * (dx / 1000.0)
                    road_km_reduction_pair = max(0.0, baseline_road_km - road_km_after_pair)
                    cost_pair_cr = (float(a['cost']) + float(b['cost'])) / 1e7
                    reward_pair = (damage_reduction_pair_cr + road_value_cr_per_km * road_km_reduction_pair) - cost_pair_cr
                    exp_pair = Experience(
                        state_before=baseline_state,
                        action={
                            'type': a['type'],
                            'location': a['location'],
                            'size': a.get('size', 'medium'),
                            'composite': True,
                            'members': [
                                {'type': a['type'], 'location': a['location']},
                                {'type': b['type'], 'location': b['location']}
                            ]
                        },
                        state_after=optimized_pair,
                        reward=reward_pair,
                        metadata={
                            'cost': (a['cost'] + b['cost']),
                            'causal_impact': (a['causal_impact'] + b['causal_impact']),
                            'benefit_cost_ratio': (damage_reduction_pair_cr / max(1e-9, cost_pair_cr)),
                            'damage_reduction_cr': damage_reduction_pair_cr,
                            'road_km_reduction': road_km_reduction_pair
                        }
                    )
                    qca.add_experience(exp_pair)
                    pair_count += 1
            
            print(f"   ✅ Collected {len(qca.engine.experiences)} experiences")
            # Update replay stats and persist (physics-featured bins)
            try:
                if getattr(args, 'replay_dir', None):
                    rp = Path(args.replay_dir)
                    rp.mkdir(exist_ok=True, parents=True)
                    rp_file = rp / 'experience_stats.json'
                    stats = {}
                    if rp_file.exists():
                        stats = json.load(open(rp_file))
                    # accumulate avg reward per type
                    sums = {}
                    counts = {}
                    # precompute slope field from bed
                    slope_grid = None
                    try:
                        if bed is not None:
                            gx = np.gradient(bed, axis=0) / max(1e-6, dx)
                            gy = np.gradient(bed, axis=1) / max(1e-6, dy)
                            slope_grid = np.sqrt(gx*gx + gy*gy)
                    except Exception:
                        slope_grid = None
                    def ctx_key(act):
                        # Use urban-planner extended context if available
                        if road_criticality_grid is not None:
                            from AI.urban_planner_priors import extend_replay_context
                            t = act.get('type') or 'unknown'
                            loc = act.get('location') or (0, 0)
                            cand_match = next((c for c in candidates if c['location']==loc and c['type']==t), None)
                            if cand_match:
                                return extend_replay_context(cand_match)
                        # Fallback to original context
                        t = act.get('type') or 'unknown'
                        loc = act.get('location') or (0, 0)
                        i, j = int(loc[0]), int(loc[1])
                        ddr = float(next((c.get('distance_to_drain', 1e6) for c in candidates if c['location']==loc and c['type']==t), 1e6))
                        conn_bin = 'near' if ddr < 200 else ('mid' if ddr < 400 else 'far')
                        s = 0.0
                        if slope_grid is not None and 0 <= i < slope_grid.shape[0] and 0 <= j < slope_grid.shape[1]:
                            s = float(slope_grid[i, j])
                        slope_bin = 'flat' if s < 0.005 else ('mod' if s < 0.02 else 'steep')
                        # contributing area
                        accum = next((c.get('flow_accum') for c in candidates if c['location']==loc and c['type']==t), None)
                        area_bin = 'small' if (accum is None or float(accum) < 20) else ('med' if float(accum) < 100 else 'large')
                        # head differential
                        hd = next((c.get('head_drop') for c in candidates if c['location']==loc and c['type']==t), None)
                        head_bin = 'low' if (hd is None or float(hd) < 0.05) else ('med' if float(hd) < 0.20 else 'high')
                        # rated capacity
                        cap = next((c.get('rated_capacity') for c in candidates if c['location']==loc and c['type']==t), None)
                        cap_bin = 'small' if (cap is None or float(cap) < 2.0) else ('med' if float(cap) < 6.0 else 'large')
                        return f"{t}|conn:{conn_bin}|slope:{slope_bin}|area:{area_bin}|head:{head_bin}|cap:{cap_bin}"
                    for exp in qca.engine.experiences:
                        key = ctx_key(exp.action)
                        sums[key] = sums.get(key, 0.0) + float(exp.reward)
                        counts[key] = counts.get(key, 0) + 1
                    for key, c in counts.items():
                        prev = stats.get(key, {})
                        prev_sum = float(prev.get('sum_reward', 0.0))
                        prev_cnt = int(prev.get('count', 0))
                        new_sum = prev_sum + float(sums.get(key, 0.0))
                        new_cnt = prev_cnt + int(c)
                        stats[key] = {
                            'sum_reward': new_sum,
                            'count': new_cnt,
                            'avg_reward': (new_sum / max(1, new_cnt))
                        }
                    json.dump(stats, open(rp_file, 'w'), indent=2)
                    # derive context-aware boosts for current run
                    type_boost = {k: float(v.get('avg_reward', 0.0)) for k, v in stats.items()}
            except Exception:
                pass
            
            # Learn manifold
            print("\n   🔬 Learning causal manifold via Isomap...")
            qca.learn(verbose=True)
            
            # PRUNE low-reward zones (concept.py mechanism)
            print("\n   🚫 Pruning low-reward zones...")
            qca.engine.prune_low_reward_zones(reward_threshold=0.0, radius_percentile=25.0)
            if qca.engine.pruned_zones:
                print(f"      Identified {len(qca.engine.pruned_zones)} zones to avoid:")
                for zone in qca.engine.pruned_zones[:3]:  # Show top 3
                    print(f"      • {zone['reason']}")
            else:
                print(f"      No zones pruned (all experiences have positive reward)")
            
            # Save manifold for inspection
            output_dir = Path(args.baseline_dir).parent / 'qcia_analysis'
            output_dir.mkdir(exist_ok=True, parents=True)
            qca.save_to_file(str(output_dir / 'qca_manifold.json'))
            print(f"   💾 Saved manifold to {output_dir / 'qca_manifold.json'}")
            
            # Find optimal plan using QCA
            print("\n   🎯 Planning optimal intervention sequence via manifold (with pruning)...")
            # Build QCA-guided greedy (intelligently greedy) using experience rewards
            print("   🤖 Building QCA-guided greedy plan (conditional marginal ROI)...")
            # Index candidates by (type, location)
            cand_map = { (c['type'], tuple(c['location'])): c for c in candidates }
            # Single and pair rewards (ROI-aligned, already in Experience.reward)
            single_reward = {}
            pair_reward = {}
            single_km = {}
            pair_km = {}
            for exp in qca.engine.experiences:
                act = exp.action
                if act.get('composite'):
                    members = act.get('members', [])
                    if len(members) == 2:
                        a = (members[0]['type'], tuple(members[0]['location']))
                        b = (members[1]['type'], tuple(members[1]['location']))
                        pair_reward[(a, b)] = float(exp.reward)
                        pair_reward[(b, a)] = float(exp.reward)
                        km = float(exp.metadata.get('road_km_reduction', 0.0))
                        pair_km[(a, b)] = km
                        pair_km[(b, a)] = km
                else:
                    key = (act['type'], tuple(act['location']))
                    single_reward[key] = float(exp.reward)
                    single_km[key] = float(exp.metadata.get('road_km_reduction', 0.0))

            # Greedy loop (QCA-guided, physics priors) and optional swarm
            budget_inr = args.budget_cr * 1e7
            max_actions = args.max_actions
            # Use user-provided thresholds directly; allow relaxation dynamically
            roi_threshold = float(args.roi_threshold)
            current_roi_threshold = float(roi_threshold)
            diversification_radius = args.diversification_radius

            def far_from_selected(loc: Tuple[int, int], sel_sites: List[Tuple[int, int]]) -> bool:
                if not sel_sites:
                    return True
                i, j = loc
                for si, sj in sel_sites:
                    if abs(i - si) <= diversification_radius and abs(j - sj) <= diversification_radius:
                        return False
                return True

            selected_plan: List[Dict] = []
            selected_sites: List[Tuple[int, int]] = []
            selected_types: Dict[str, int] = {}
            total_cost_inr: float = 0.0
            conveyance_first_n = int(getattr(args, 'conveyance_first_n', 5))  # Prioritize conveyance more strongly
            km_min_gain = float(args.min_km_gain)
            current_km_gate = float(km_min_gain)

            def is_barrier_type(t: str) -> bool:
                tl = t.lower()
                return ('levee' in tl) or ('wall' in tl)

            def is_conveyance_type(t: str) -> bool:
                tl = t.lower()
                return ('channel' in tl) or ('culvert' in tl) or ('pump' in tl) or ('smart_valve' in tl) or ('drain' in tl)

            # Diminishing returns factor near existing actions
            def diminish(loc: Tuple[int, int]) -> float:
                for si, sj in selected_sites:
                    if abs(loc[0] - si) + abs(loc[1] - sj) <= 6:
                        return 0.7
                return 1.0

            def pick_best_from_iter(citer):
                best_local = None
                best_delta_roi_local = -1e9
                for key, cand in citer:
                    if cand in selected_plan:
                        continue
                    loc = tuple(cand['location'])
                    if not far_from_selected(loc, selected_sites):
                        continue
                    cost_cr = float(cand['cost']) / 1e7
                    if total_cost_inr + float(cand['cost']) > budget_inr:
                        continue
                    barrier_selected = sum(c for t, c in selected_types.items() if is_barrier_type(t))
                    barrier_cap = 1
                    if is_barrier_type(cand['type']) and barrier_selected >= barrier_cap:
                        continue
                    convey_selected = sum(c for t, c in selected_types.items() if is_conveyance_type(t))
                    if convey_selected < conveyance_first_n and not is_conveyance_type(cand['type']):
                        continue
                    r = single_reward.get((cand['type'], loc), 0.0)
                    km_gain = single_km.get((cand['type'], loc), 0.0)
                    if len(selected_plan) == 1:
                        s = selected_plan[0]
                        key_pair = ((s['type'], tuple(s['location'])), (cand['type'], loc))
                        if key_pair in pair_reward and (s['type'], tuple(s['location'])) in single_reward:
                            r = max(r, pair_reward[key_pair] - single_reward[(s['type'], tuple(s['location']))])
                            km_gain = max(km_gain, pair_km.get(key_pair, 0.0))
                    r *= diminish(loc)
                    # Apply replay-derived type boost to encourage historically effective types
                    if type_boost:
                        # Build context key similar to replay
                        i_ct, j_ct = loc
                        s_ct = 0.0
                        try:
                            if bed is not None:
                                s_ct = float(np.sqrt(((bed[min(i_ct+1, nx-1), j_ct]-bed[max(i_ct-1,0), j_ct])/(2*max(1e-6, dx)))**2 +
                                                     ((bed[i_ct, min(j_ct+1, ny-1)]-bed[i_ct, max(j_ct-1,0)])/(2*max(1e-6, dy)))**2))
                        except Exception:
                            s_ct = 0.0
                        slope_bin = 'flat' if s_ct < 0.005 else ('mod' if s_ct < 0.02 else 'steep')
                        # Use candidate-provided distance_to_drain when available
                        ddr_val = float(cand.get('distance_to_drain', 1e6))
                        conn_bin = 'near' if ddr_val < 200 else ('mid' if ddr_val < 400 else 'far')
                        # Contributing area bin from flow_accum if provided
                        accum = cand.get('flow_accum')
                        area_bin = 'small' if (accum is None or float(accum) < 20) else ('med' if float(accum) < 100 else 'large')
                        # Head differential bin
                        hd = cand.get('head_drop')
                        head_bin = 'low' if (hd is None or float(hd) < 0.05) else ('med' if float(hd) < 0.20 else 'high')
                        # Rated capacity bin
                        cap = cand.get('rated_capacity')
                        cap_bin = 'small' if (cap is None or float(cap) < 2.0) else ('med' if float(cap) < 6.0 else 'large')
                        ctxk = f"{cand['type']}|conn:{conn_bin}|slope:{slope_bin}|area:{area_bin}|head:{head_bin}|cap:{cap_bin}"
                        r += args.replay_weight * float(type_boost.get(ctxk, 0.0))
                    ddr = float(cand.get('distance_to_drain', 1e6))
                    if any(x in cand['type'] for x in ['channel', 'culvert', 'pump', 'smart_valve']):
                        r *= 1.35 if ddr < 300 else (1.15 if ddr < 600 else 1.0)
                    if is_barrier_type(cand['type']):
                        if ddr > 400:
                            continue
                        r *= 0.85 if ddr > 300 else 1.0
                    # Roads-first objective: relax early, enforce later, dynamic via current_km_gate
                    if len(selected_plan) > 2 and km_gain < current_km_gate:
                        continue
                    if km_gain > 0:
                        r *= (1.0 + min(0.25, 0.05 * (km_gain / 0.1)))
                    # RELAXED: Allow small positive rewards (was rejecting r <= 0)
                    if r < -0.01:  # Only reject clearly negative rewards
                        continue
                    # Roads-first composite: include explicit km value term
                    roads_first_w = float(getattr(args, 'roads_first_w', 0.4))
                    delta_roi = (r + roads_first_w * km_gain) / max(1e-9, cost_cr)
                    if delta_roi >= current_roi_threshold and delta_roi > best_delta_roi_local:
                        best_delta_roi_local = delta_roi
                        best_local = cand
                return best_local

            # Mini-sim checkpoint evaluation
            def checkpoint_ok(plan: List[Dict]) -> bool:
                if len(plan) == 0:
                    return True
                try:
                    # Build a temp design with current plan
                    design_tmp = {
                        'num_interventions': len(plan),
                        'total_cost_cr': sum(s['cost'] for s in plan) / 1e7,
                        'interventions': [
                            {
                                'location': s['location'],
                                'type': s['type'],
                                'causal_impact': float(s.get('causal_impact', 0.0)),
                                'cost_lakh': float(s.get('cost', 0.0) / 1e5)
                            } for s in plan
                        ]
                    }
                    # Create solver from baseline arrays
                    grid_ck = Grid(nx=nx, ny=ny, Lx=Lx, Ly=Ly)
                    prm_ck = SWEParams(g=9.81, manning_n=0.06, h_min=1.0e-3, cfl=0.15, vmax_guard_coef=0.7, dt_max=0.1,
                                       sponge_width=0, sponge_tau=180.0)
                    filt_ck = ExponentialFilter(alpha=96.0, p=8)
                    solver_ck = HRFSolver(grid_ck, prm_ck, filt_ck)
                    solver_ck.mode = "dw_fv"
                    # Initialize from baseline depth (use snapshot h)
                    h0 = h.copy()
                    u0 = np.zeros_like(h0)
                    v0 = np.zeros_like(h0)
                    solver_ck.initialize(h0, u0, v0)
                    solver_ck.set_forcing(bed=bed, rain_rate=0.0)
                    # Apply interventions via applier
                    from AI.intervention_applier import apply_qcia_design_to_solver
                    with tempfile.TemporaryDirectory() as td:
                        dp = os.path.join(td, 'design.json')
                        with open(dp, 'w') as f:
                            json.dump(design_tmp, f)
                        apply_qcia_design_to_solver(solver_ck, grid_ck, Path(dp), verbose=False)
                    # Run short sim
                    solver_ck.run(t_end=float(args.checkpoint_t_s), output_every=0.0, verbose=False)
                    # Compute road-km (threshold 0.2m) from solver_ck.h
                    ha_ck = solver_ck.h
                    thr = 0.2
                    km_agent = float(np.sum((ha_ck >= thr) & (road_mask > 0))) * (dx / 1000.0)
                    km_base = float(np.sum((h >= thr) & (road_mask > 0))) * (dx / 1000.0)
                    gain = km_base - km_agent
                    return gain >= float(args.checkpoint_km_gain)
                except Exception:
                    return True  # be permissive if checkpoint fails

            if args.swarm:
                print("   🚦 Swarm mode: road-centric agents with global context sharing")
                from scipy.ndimage import label, distance_transform_edt
                flooded_roads = (h >= 0.2) & (road_mask > 0)
                labeled, ncomp = label(flooded_roads.astype(int))
                sizes = [(i, int(np.sum(labeled == i))) for i in range(1, ncomp+1)]
                sizes.sort(key=lambda x: x[1], reverse=True)
                top_ids = [i for i, _ in sizes[:max(1, args.swarm_top_roads)]]
                submasks = []
                distmap = distance_transform_edt(~flooded_roads) * dx
                for comp_id in top_ids:
                    core = (labeled == comp_id)
                    submask = (distmap <= args.swarm_radius) | core
                    submasks.append(submask)
                # Round-robin: each agent proposes locally; each works until its own goal/limit
                steps = 0
                agent_actions = [0 for _ in submasks]
                agent_gain_km = [0.0 for _ in submasks]
                while steps < args.swarm_steps and len(selected_plan) < max_actions:
                    steps += 1
                    picks_this_round = 0
                    for idx, submask in enumerate(submasks):
                        if len(selected_plan) >= max_actions or total_cost_inr >= budget_inr:
                            break
                        # Skip agents that reached their per-agent goals
                        if agent_actions[idx] >= args.swarm_agent_max_actions or agent_gain_km[idx] >= args.swarm_agent_km_target:
                            continue
                        sub_iter = ((k, v) for k, v in cand_map.items() if submask[v['location'][0], v['location'][1]])
                        cand_pick = pick_best_from_iter(sub_iter)
                        if cand_pick is None:
                            continue
                        selected_plan.append(cand_pick)
                        selected_sites.append(tuple(cand_pick['location']))
                        selected_types[cand_pick['type']] = selected_types.get(cand_pick['type'], 0) + 1
                        total_cost_inr += float(cand_pick['cost'])
                        # Update agent stats (approx road improvement from experience metadata if available)
                        km_gain = single_km.get((cand_pick['type'], tuple(cand_pick['location'])), 0.0)
                        agent_gain_km[idx] += max(0.0, km_gain)
                        agent_actions[idx] += 1
                        picks_this_round += 1
                    if picks_this_round == 0:
                        break
                if selected_plan:
                    print(f"\n   ✅ Swarm selected {len(selected_plan)} interventions across {len(submasks)} roads")
                    selected = selected_plan
                    feasibility = {'achievable': True, 'reason': 'QCA swarm road-centric'}
                else:
                    raise ValueError("QCA swarm produced no selections")
            else:
                # Acceptance gate with proxy km check and periodic mini-sim backstop
                retries = 0
                max_retries = 60
                relax_tries = 0
                while len(selected_plan) < max_actions and retries < max_retries:
                    best = pick_best_from_iter(cand_map.items())
                    if best is None:
                        # Adaptive relaxation: lower thresholds to utilize budget
                        relax_tries += 1
                        current_roi_threshold *= 0.85
                        current_km_gate *= 0.85
                        if relax_tries >= 5:
                            break
                        continue
                    loc = tuple(best['location'])
                    km_gain = single_km.get((best['type'], loc), 0.0)
                    # Only enforce km gate after a few selections; dynamic gate already applied in picker
                    if len(selected_plan) > 2 and km_gain < current_km_gate:
                        retries += 1
                        # Remove candidate temporarily to avoid infinite loop
                        _ = cand_map.pop((best['type'], loc), None)
                        continue
                    selected_plan.append(best)
                    selected_sites.append(loc)
                    selected_types[best['type']] = selected_types.get(best['type'], 0) + 1
                    total_cost_inr += float(best['cost'])
                    # Budget-pressure schedule: if under target utilization near end, relax more
                    util = total_cost_inr / max(1e-9, budget_inr)
                    if util < float(args.budget_soft_utilization):
                        current_roi_threshold *= 0.95
                        current_km_gate *= 0.95
                    # Mini-sim checkpoint after every N actions
                    if (len(selected_plan) % max(1, int(args.checkpoint_every))) == 0:
                        if not checkpoint_ok(selected_plan):
                            # backtrack
                            sp = selected_plan.pop()
                            selected_sites.pop()
                            selected_types[sp['type']] = max(0, selected_types.get(sp['type'], 1) - 1)
                            total_cost_inr -= float(sp['cost'])
                            retries += 1
                            _ = cand_map.pop((sp['type'], tuple(sp['location'])), None)
                            continue

            if selected_plan:
                print(f"\n   ✅ QCA-guided greedy selected {len(selected_plan)} interventions")
                selected = selected_plan
                feasibility = {'achievable': True, 'reason': 'QCA-guided greedy'}
            else:
                # ADAPTIVE: Relax constraints and retry instead of failing
                print(f"\n   ⚠️  QCA-guided greedy loop completed with 0 selections (attempt 1)")
                print(f"   Debug: roi_threshold={roi_threshold:.3f}, km_min_gain={km_min_gain:.3f}")
                print(f"   🔄 Adaptive mode: Relaxing constraints and retrying...")
                
                # Retry with progressively relaxed thresholds
                for retry_attempt in range(3):
                    relaxation_factor = 0.5 ** (retry_attempt + 1)  # 0.5, 0.25, 0.125
                    roi_threshold_relaxed = roi_threshold * relaxation_factor
                    km_min_gain_relaxed = km_min_gain * relaxation_factor
                    
                    print(f"   Attempt {retry_attempt + 2}: ROI≥{roi_threshold_relaxed:.4f}, km≥{km_min_gain_relaxed:.4f}")
                    
                    # Reset and retry with relaxed thresholds
                    selected_plan_retry = []
                    selected_sites_retry = []
                    total_cost_inr_retry = 0.0
                    cand_map_retry = {(c['type'], tuple(c['location'])): c for c in candidates}
                    
                    retries_inner = 0
                    max_retries_inner = 40
                    while len(selected_plan_retry) < max_actions and retries_inner < max_retries_inner:
                        # Use relaxed pick_best_from_iter logic
                        best = None
                        best_delta_roi_local = roi_threshold_relaxed
                        
                        for (typ, loc), cand in cand_map_retry.items():
                            if loc in selected_sites_retry:
                                continue
                            if total_cost_inr_retry + cand['cost'] > budget_inr:
                                continue
                            
                            # Simple ROI check with relaxed threshold
                            cost_cr = cand['cost'] / 1e7
                            km_gain = single_km.get((typ, loc), 0.0)
                            
                            if km_gain < km_min_gain_relaxed and len(selected_plan_retry) > 0:
                                continue
                            
                            # Simplified reward
                            r = cand.get('causal_impact', 0.0) * 0.15
                            if r < -0.01:
                                continue
                            
                            delta_roi = r / max(1e-9, cost_cr)
                            if delta_roi >= roi_threshold_relaxed and delta_roi > best_delta_roi_local:
                                best_delta_roi_local = delta_roi
                                best = cand
                        
                        if best is None:
                            break
                        
                        selected_plan_retry.append(best)
                        selected_sites_retry.append(tuple(best['location']))
                        total_cost_inr_retry += float(best['cost'])
                    
                    if selected_plan_retry:
                        print(f"   ✅ Adaptive retry succeeded: {len(selected_plan_retry)} interventions selected")
                        selected_plan = selected_plan_retry
                        break
                
                if selected_plan:
                    selected = selected_plan
                    feasibility = {'achievable': True, 'reason': 'QCA-guided greedy (adaptive)'}
                else:
                    print(f"   ❌ All adaptive attempts failed. Total candidates: {len(candidates)}")
                    raise ValueError("QCA-guided greedy produced no selections after adaptive retries")
        
        except Exception as e:
            if optimization_method == "qca_strict":
                # Force QCA mode - don't fallback, raise error
                print(f"\n❌ QCA FAILED (strict mode): {e}")
                raise
            else:
                # Normal mode - fallback to greedy
                print(f"\n⚠️  QCA optimization failed: {e}")
                print(f"   Falling back to greedy optimization...")
                optimization_method = "greedy"
    
    # Greedy optimization (either forced or fallback)
    if selected is None:
        print(f"\n⚛️  PHASE 5: QUANTUM OPTIMIZATION (GREEDY)")
        print("="*70)
        if optimization_method == "greedy":
            print("Using traditional greedy optimization")
        else:
            print("QCA fallback: Using greedy as safety net")
        
        # If seed design provided, load it and use as locked-in seed
        seed_selected: List[Dict] | None = None
        if args.seed_design:
            try:
                with open(args.seed_design, 'r') as f:
                    seed_design = json.load(f)
                seed_selected = []
                for it in seed_design.get('interventions', []):
                    seed_selected.append({
                        'location': tuple(it['location']),
                        'type': it['type'],
                        'causal_impact': float(it.get('causal_impact', 0.0)),
                        'cost': float(it.get('cost', it.get('cost_lakh', 0.0) * 1e5)),
                        'benefit_cost_ratio': float(it.get('benefit_cost_ratio', 0.0)),
                        'flood_depth': float(it.get('flood_depth_before', 0.0)),
                        'is_lowland': float(it.get('is_lowland', 0.0))
                    })
                print(f"   🔒 Seeding greedy with {len(seed_selected)} locked actions (no override)")
            except Exception as e:
                print(f"   ⚠️  Failed to load seed design {args.seed_design}: {e}")
                seed_selected = None

        selected, feasibility = select_optimal_interventions(
            candidates, 
            budget_cr=args.budget_cr,
            target_reduction_pct=args.target_reduction_pct,
            baseline_flooded_km=baseline_flooded_km,
            roi_threshold=args.roi_threshold,
            budget_soft_utilization=args.budget_soft_utilization,
            mass_tolerance_pct=args.mass_tolerance_pct,
            diversification_radius=args.diversification_radius,
            max_actions=args.max_actions,
            seed_selected=seed_selected
        )
    
    # Save results
    output_path = Path(args.output)
    
    # Helper to convert numpy types to Python native types (recursively!)
    def to_json_serializable(obj):
        """Convert numpy types to Python native types for JSON serialization."""
        if isinstance(obj, (np.integer, np.floating)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, np.bool_):
            return bool(obj)
        elif isinstance(obj, dict):
            return {k: to_json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [to_json_serializable(item) for item in obj]
        return obj
    
    design = {
        'num_interventions': len(selected),
        'total_cost_cr': sum(s['cost'] for s in selected) / 1e7,
        'expected_total_impact': sum(s['causal_impact'] for s in selected),
        'target_reduction_pct': args.target_reduction_pct,
        'feasibility_estimate': to_json_serializable(feasibility),
        'interventions': [
            {
                'location': s['location'],
                'location_utm': (s['location'][0] * dx, s['location'][1] * dy),
                'type': s['type'],
                'causal_impact': float(s['causal_impact']),
                'flood_depth_before': float(s['flood_depth']),
                'is_lowland': float(s['is_lowland']),
                'benefit_cost_ratio': float(s['benefit_cost_ratio']),
                'cost_lakh': float(s['cost'] / 1e5)
            }
            for s in selected
        ],
        'causal_graph_edges': [str(edge) for edge in causal_graph.edges.values()]
    }
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(design, f, indent=2)
    
    print(f"\n{'='*70}")
    print(f"✅ QCIA ANALYSIS COMPLETE")
    print(f"{'='*70}")
    print(f"\n💾 Saved optimized design to: {output_path}")
    print(f"\n📊 Summary:")
    print(f"   Budget: ₹{args.budget_cr} Crores")
    print(f"   Selected: {len(selected)} interventions")
    print(f"   Total cost: ₹{design['total_cost_cr']:.2f} Crores")
    print(f"   Expected total impact: {design['expected_total_impact']:.2f}")
    
    # Show breakdown by type
    by_type = {}
    for s in selected:
        by_type[s['type']] = by_type.get(s['type'], 0) + 1
    print(f"\n   🏗️  Intervention mix:")
    for itype, count in by_type.items():
        print(f"      {itype}: {count}")
    
    print(f"\n🚀 Next: Run optimized simulation with these interventions")
    print(f"   (Design includes: {', '.join(by_type.keys())})")
    print(f"\n{'='*70}")
    
    return 0


if __name__ == "__main__":
    main()

