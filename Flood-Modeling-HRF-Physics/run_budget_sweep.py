#!/usr/bin/env python3
"""
Budget Sweep & ROI Optimizer
=============================
Evaluates multiple budget scenarios to find best value for money.

Includes:
- Flood damage cost monetization
- Infrastructure cost vs. damage reduction trade-off
- ROI curve generation
- Automatic "best value" budget selection
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple
import numpy as np
import matplotlib.pyplot as plt
import argparse
from datetime import datetime

# Add project root to path for imports
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from AI.qcia_core.experience_store import ExperienceStore, InterventionRecord


def record_intervention_experiences(
    design_path: Path,
    baseline_metrics: Dict,
    opt_metrics: Dict,
    baseline_damage_cr: float,
    opt_damage_cr: float,
    actual_cost_cr: float,
    roi: float,
    aoi_name: str = "default"
):
    """
    Record physics-validated intervention experiences to the experience store.
    
    This is called AFTER the optimized simulation completes, so we have real
    physics-validated performance data (not heuristic estimates).
    """
    try:
        # Load the design to get individual interventions
        with open(design_path, 'r') as f:
            design = json.load(f)
        
        interventions = design.get('interventions', [])
        if not interventions:
            return
        
        # Calculate per-intervention metrics (approximate uniform attribution)
        # In reality, interventions interact, but this is a reasonable first-order approximation
        n_interventions = len(interventions)
        damage_reduction_cr = baseline_damage_cr - opt_damage_cr
        road_km_reduction = baseline_metrics['flooded_road_km'] - opt_metrics['flooded_road_km']
        
        per_intervention_damage_reduction = damage_reduction_cr / n_interventions
        per_intervention_road_km_reduction = road_km_reduction / n_interventions
        
        # Create records
        experience_store = ExperienceStore()
        timestamp = datetime.now().isoformat()
        
        records = []
        for intervention in interventions:
            # Extract intervention cost (in INR)
            cost_inr = intervention.get('cost_lakh', 0) * 1e5
            per_intervention_roi = (per_intervention_damage_reduction / (cost_inr / 1e7)) if cost_inr > 0 else 0.0
            
            record = InterventionRecord(
                type=intervention['type'],
                location=tuple(intervention['location']),
                cost_inr=cost_inr,
                damage_reduction_cr=per_intervention_damage_reduction,
                road_km_reduction=per_intervention_road_km_reduction,
                roi=per_intervention_roi,
                success=(per_intervention_roi > 0),
                aoi_name=aoi_name,
                timestamp=timestamp
            )
            records.append(record)
        
        # Save to store
        experience_store.add_batch(records)
        experience_store.save()
        
        print(f"\n   💾 Recorded {len(records)} intervention experiences for future learning")
        
        # Show learning insights if enough data
        if len(experience_store.records) >= 5:
            stats = experience_store.get_type_statistics()
            print(f"   📊 Experience store now has {len(experience_store.records)} interventions")
            print(f"      Types tracked: {', '.join(stats.keys())}")
        
    except Exception as e:
        print(f"   ⚠️  Could not record experiences: {e}")


def calculate_flood_damage_cost(
    flooded_road_km: float,
    flooded_area_pct: float,
    avg_depth_m: float
) -> float:
    """
    Realistic depth-dependent flood damage cost model (₹ Lakhs).
    REFINED: 5-10x higher baseline to reflect true economic impact.
    
    Components:
    1. Road damage (depth-dependent):
       - Light (0.1-0.3m): ₹2 Cr/km (surface repair, debris removal)
       - Moderate (0.3-0.5m): ₹5 Cr/km (structural damage, utilities)
       - Severe (>0.5m): ₹15 Cr/km (complete reconstruction)
    2. Property damage: ₹100 Lakhs per % of AOI flooded (buildings, contents)
    3. Business interruption: ₹50 Lakhs per % (lost productivity, closures)
    4. Emergency response: ₹2 Cr base (rescue, medical, temporary shelter)
    5. Indirect costs: 30% multiplier (long-term health, displacement)
    
    Returns cost in Lakhs (₹).
    """
    # 1. DEPTH-DEPENDENT ROAD DAMAGE (most realistic improvement)
    # Assume average depth distribution: 60% light, 30% moderate, 10% severe
    if avg_depth_m < 0.2:
        avg_road_damage_per_km = 100  # ₹1 Cr/km (minor)
    elif avg_depth_m < 0.4:
        avg_road_damage_per_km = 300  # ₹3 Cr/km (moderate)
    elif avg_depth_m < 0.6:
        avg_road_damage_per_km = 800  # ₹8 Cr/km (severe)
    else:
        avg_road_damage_per_km = 1500  # ₹15 Cr/km (catastrophic)
    
    road_damage = flooded_road_km * avg_road_damage_per_km
    
    # 2. PROPERTY DAMAGE (buildings, infrastructure, contents)
    property_damage = flooded_area_pct * 100  # ₹100L per % (was ₹2L)
    
    # 3. BUSINESS INTERRUPTION (productivity loss, closures)
    business_loss = flooded_area_pct * 50  # ₹50L per %
    
    # 4. EMERGENCY RESPONSE (base cost)
    emergency_cost = 200  # ₹2 Cr base
    
    # 5. DEPTH SEVERITY MULTIPLIER
    depth_multiplier = 1.0 + (avg_depth_m / 0.5)  # 1.0x at 0m, 2.0x at 0.5m
    
    # Calculate subtotal
    subtotal = road_damage + property_damage + business_loss + emergency_cost
    
    # Apply depth severity multiplier
    direct_costs = subtotal * depth_multiplier
    
    # Add indirect costs (30% of direct)
    indirect_costs = direct_costs * 0.3
    
    total_lakhs = direct_costs + indirect_costs
    
    return total_lakhs


def extract_flood_metrics(npz_path: Path, roads_overlay_log: str = None) -> Dict:
    """Extract flood metrics from simulation output."""
    metrics = {}
    
    # Load depth grid
    if npz_path.exists():
        data = np.load(npz_path)
        h = data['h']
        
        # Calculate metrics
        flooded_02 = np.sum(h >= 0.2)
        total_cells = h.shape[0] * h.shape[1]
        metrics['flooded_area_pct'] = 100.0 * flooded_02 / total_cells
        
        wet_cells = h > 0.01
        metrics['avg_depth_m'] = float(np.mean(h[wet_cells])) if np.any(wet_cells) else 0.0
        metrics['max_depth_m'] = float(np.max(h))
    else:
        print(f"⚠️  Missing {npz_path}")
        metrics['flooded_area_pct'] = 0.0
        metrics['avg_depth_m'] = 0.0
        metrics['max_depth_m'] = 0.0
    
    # Parse road flooding from overlay log (if available)
    metrics['flooded_road_km'] = 0.0
    if roads_overlay_log and Path(roads_overlay_log).exists():
        with open(roads_overlay_log, 'r') as f:
            for line in f:
                if 'Road flooded length' in line:
                    # Format: "Road flooded length: 12.345 km / 50.000 km"
                    try:
                        flooded = float(line.split(':')[1].split('km')[0].strip())
                        metrics['flooded_road_km'] = flooded
                    except:
                        pass
    
    return metrics


def run_qcia_for_budget(
    baseline_dir: Path,
    budget_cr: float,
    target_reduction_pct: float,
    output_json: Path,
    extra_args: List[str] | None = None
) -> bool:
    """Run QCIA optimization for a specific budget."""
    cmd = [
        'python', 'run_qcia_flood_optimization.py',
        '--baseline_dir', str(baseline_dir),
        '--budget_cr', str(budget_cr),
        '--target_reduction_pct', str(target_reduction_pct),
        '--output', str(output_json)
    ]
    if extra_args:
        cmd.extend(list(extra_args))
    
    try:
        subprocess.run(cmd, check=True, capture_output=False)
        return output_json.exists()
    except subprocess.CalledProcessError as e:
        print(f"⚠️  QCIA failed for budget ₹{budget_cr}Cr: {e}")
        return False


def run_simulation_with_design(
    dem: str, lulc: str, rivers: str, roads: str,
    tile_col: int, tile_row: int,
    nx: int, ny: int,
    rain_mmph: float, t_hours: float,
    qcia_design: Path,
    output_dir: Path
) -> bool:
    """Run HRF simulation with QCIA design."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    cmd = [
        'python', 'Runners/pb_cli.py',
        '--dem', dem,
        '--lulc', lulc,
        '--rivers', rivers,
        '--roads', roads,
        '--tile_col0', str(tile_col),
        '--tile_row0', str(tile_row),
        '--nx', str(nx),
        '--ny', str(ny),
        '--rain_mm_per_hour', str(rain_mmph),
        '--t_hours', str(t_hours),
        '--qcia_design', str(qcia_design),
        '--out', str(output_dir),
        '--plot_vmax', '2.0'
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=False)
        return (output_dir / 'final_snapshot.npz').exists()
    except subprocess.CalledProcessError as e:
        print(f"⚠️  Simulation failed: {e}")
        return False


def run_road_overlay(run_dir: Path, roads: str) -> Path:
    """Generate road overlay and return log path."""
    log_path = run_dir / 'road_overlay.log'
    cmd = [
        'python', 'Runners/kpi_overlay_roads.py',
        '--run_dir', str(run_dir),
        '--roads', roads
    ]
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        # Save stdout to log
        log_path.write_text(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"⚠️  Road overlay failed: {e}")
    
    return log_path


def main():
    parser = argparse.ArgumentParser(description='Budget sweep and ROI optimization')
    parser.add_argument('--baseline_dir', type=str, required=True, help='Baseline simulation directory')
    parser.add_argument('--dem', type=str, required=True)
    parser.add_argument('--lulc', type=str, required=True)
    parser.add_argument('--rivers', type=str, required=True)
    parser.add_argument('--roads', type=str, required=True)
    parser.add_argument('--drains', type=str, required=True)
    parser.add_argument('--tile_col0', type=int, required=True)
    parser.add_argument('--tile_row0', type=int, required=True)
    parser.add_argument('--nx', type=int, default=100)
    parser.add_argument('--ny', type=int, default=100)
    parser.add_argument('--rain_mm_per_hour', type=float, default=60.0)
    parser.add_argument('--t_hours', type=float, default=1.5)
    parser.add_argument('--target_reduction_pct', type=float, default=20.0)
    parser.add_argument('--output_dir', type=str, required=True, help='Output directory for sweep results')
    parser.add_argument('--autonomous', action='store_true', help='Enable closed-loop autonomous plan→simulate→evaluate→refine')
    parser.add_argument('--autonomous_max_steps', type=int, default=5, help='Max refinement steps per budget in autonomous mode')
    
    args = parser.parse_args()
    
    baseline_dir = Path(args.baseline_dir)
    output_root = Path(args.output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    
    print("="*70)
    print("💰 BUDGET SWEEP & ROI OPTIMIZER")
    print("="*70)
    print(f"Baseline: {baseline_dir}")
    print(f"Target reduction: {args.target_reduction_pct}%")
    print(f"Output: {output_root}")
    print("")
    
    # Calculate baseline damage cost
    print("📊 Calculating baseline flood damage...")
    baseline_npz = baseline_dir / 'final_snapshot.npz'
    baseline_road_log = baseline_dir / 'road_overlay.log'
    
    # Generate road overlay if not exists
    if not baseline_road_log.exists():
        baseline_road_log = run_road_overlay(baseline_dir, args.roads)
    
    baseline_metrics = extract_flood_metrics(baseline_npz, str(baseline_road_log))
    baseline_damage_lakhs = calculate_flood_damage_cost(
        baseline_metrics['flooded_road_km'],
        baseline_metrics['flooded_area_pct'],
        baseline_metrics['avg_depth_m']
    )
    baseline_damage_cr = baseline_damage_lakhs / 100  # Convert to Crores
    
    print(f"   Flooded roads: {baseline_metrics['flooded_road_km']:.2f} km")
    print(f"   Flooded area (≥0.2m): {baseline_metrics['flooded_area_pct']:.1f}%")
    print(f"   Avg depth: {baseline_metrics['avg_depth_m']:.2f} m")
    print(f"   💸 Estimated flood damage: ₹{baseline_damage_cr:.2f} Cr")
    print("")
    
    # Budget range to evaluate
    budgets_cr = [5, 8, 12, 16, 20, 25, 30, 40]
    
    print(f"🔄 Evaluating {len(budgets_cr)} budget scenarios...")
    print("")
    
    results = []
    
    for budget_cr in budgets_cr:
        print(f"\n{'─'*70}")
        print(f"Budget: ₹{budget_cr} Cr")
        print(f"{'─'*70}")
        
        # Subdirectory for this budget
        budget_dir = output_root / f"budget_{int(budget_cr):02d}cr"
        budget_dir.mkdir(exist_ok=True)
        
        # Run QCIA optimization
        design_path = budget_dir / 'qcia_design.json'
        print(f"  [1/3] Running QCIA optimization...")
        success = run_qcia_for_budget(baseline_dir, budget_cr, args.target_reduction_pct, design_path)
        
        if not success or not design_path.exists():
            print(f"  ⚠️  QCIA failed for ₹{budget_cr}Cr, skipping...")
            continue
        
        # Parse design to get actual cost
        with open(design_path) as f:
            design = json.load(f)
        
        actual_cost_cr = design.get('total_cost_cr', budget_cr)
        num_interventions = len(design.get('interventions', []))
        
        print(f"  ✅ Selected {num_interventions} interventions (₹{actual_cost_cr:.2f}Cr)")
        
        # Run optimized simulation
        sim_dir = budget_dir / 'simulation'
        print(f"  [2/3] Running optimized simulation...")
        success = run_simulation_with_design(
            args.dem, args.lulc, args.rivers, args.roads,
            args.tile_col0, args.tile_row0,
            args.nx, args.ny,
            args.rain_mm_per_hour, args.t_hours,
            design_path, sim_dir
        )
        
        if not success:
            print(f"  ⚠️  Simulation failed for ₹{budget_cr}Cr, skipping...")
            continue
        
        # Generate road overlay
        print(f"  [3/3] Calculating metrics...")
        road_log = run_road_overlay(sim_dir, args.roads)
        
        # Extract optimized metrics
        opt_npz = sim_dir / 'final_snapshot.npz'
        opt_metrics = extract_flood_metrics(opt_npz, str(road_log))
        opt_damage_lakhs = calculate_flood_damage_cost(
            opt_metrics['flooded_road_km'],
            opt_metrics['flooded_area_pct'],
            opt_metrics['avg_depth_m']
        )
        opt_damage_cr = opt_damage_lakhs / 100
        
        # Calculate ROI
        damage_reduction_cr = baseline_damage_cr - opt_damage_cr
        net_benefit_cr = damage_reduction_cr - actual_cost_cr
        roi = (damage_reduction_cr / actual_cost_cr) if actual_cost_cr > 0 else 0.0

        # Report flood reduction explicitly
        road_km_reduction = baseline_metrics['flooded_road_km'] - opt_metrics['flooded_road_km']
        area_reduction_pct = baseline_metrics['flooded_area_pct'] - opt_metrics['flooded_area_pct']
        avg_depth_delta = baseline_metrics['avg_depth_m'] - opt_metrics['avg_depth_m']
        
        result = {
            'budget_cr': budget_cr,
            'actual_cost_cr': actual_cost_cr,
            'num_interventions': num_interventions,
            'baseline_damage_cr': baseline_damage_cr,
            'opt_damage_cr': opt_damage_cr,
            'damage_reduction_cr': damage_reduction_cr,
            'net_benefit_cr': net_benefit_cr,
            'roi': roi,
            'flood_reduction_road_km': road_km_reduction,
            'flooded_area_reduction_pct': area_reduction_pct,
            'avg_depth_delta_m': avg_depth_delta,
            'baseline_metrics': baseline_metrics,
            'opt_metrics': opt_metrics,
            'design_path': str(design_path),
            'sim_dir': str(sim_dir)
        }
        
        results.append(result)
        
        print(f"  📊 Results:")
        print(f"     Flood damage: ₹{baseline_damage_cr:.2f}Cr → ₹{opt_damage_cr:.2f}Cr")
        print(f"     Damage reduction: ₹{damage_reduction_cr:.2f}Cr")
        print(f"     Net benefit: ₹{net_benefit_cr:.2f}Cr")
        print(f"     ROI: {roi:.2f}x")
        print(f"     Flooded roads: {baseline_metrics['flooded_road_km']:.2f} km → {opt_metrics['flooded_road_km']:.2f} km (Δ {road_km_reduction:+.2f} km)")
        print(f"     Flooded area ≥0.2m: {baseline_metrics['flooded_area_pct']:.1f}% → {opt_metrics['flooded_area_pct']:.1f}% (Δ {area_reduction_pct:+.1f} pp)")
        print(f"     Avg depth (wet cells): {baseline_metrics['avg_depth_m']:.2f} m → {opt_metrics['avg_depth_m']:.2f} m (Δ {avg_depth_delta:+.2f} m)")
        
        # Record experiences for learning
        aoi_name = Path(args.baseline_dir).stem if args.baseline_dir else "default"
        record_intervention_experiences(
            design_path=design_path,
            baseline_metrics=baseline_metrics,
            opt_metrics=opt_metrics,
            baseline_damage_cr=baseline_damage_cr,
            opt_damage_cr=opt_damage_cr,
            actual_cost_cr=actual_cost_cr,
            roi=roi,
            aoi_name=aoi_name
        )

        # Autonomous refinement loop
        if args.autonomous:
            print("  🔁 Autonomous mode: refining plan until ROI≥1 or goal met...")
            step = 0
            best_roi = roi
            best_design = design_path
            best_sim_dir = sim_dir
            best_result = result.copy()
            while (best_roi < 1.0) and (step < args.autonomous_max_steps) and (best_result['actual_cost_cr'] < budget_cr):
                step += 1
                design_path2 = budget_dir / f"qcia_design_step{step}.json"
                print(f"    → Step {step}: greedy top-up seeded from current design")
                success2 = run_qcia_for_budget(
                    baseline_dir, budget_cr, args.target_reduction_pct, design_path2,
                    extra_args=['--force_greedy', '--seed_design', str(best_design), '--max_actions', '10']
                )
                if not (success2 and design_path2.exists()):
                    print("    ⚠️  Top-up optimization failed; stopping autonomy")
                    break
                with open(design_path2) as f:
                    design2 = json.load(f)
                actual_cost_cr2 = design2.get('total_cost_cr', budget_cr)
                sim_dir2 = budget_dir / f"simulation_step{step}"
                success2 = run_simulation_with_design(
                    args.dem, args.lulc, args.rivers, args.roads,
                    args.tile_col0, args.tile_row0,
                    args.nx, args.ny,
                    args.rain_mm_per_hour, args.t_hours,
                    design_path2, sim_dir2
                )
                if not success2:
                    print("    ⚠️  Simulation failed; stopping autonomy")
                    break
                road_log2 = run_road_overlay(sim_dir2, args.roads)
                opt_npz2 = sim_dir2 / 'final_snapshot.npz'
                opt_metrics2 = extract_flood_metrics(opt_npz2, str(road_log2))
                opt_damage_lakhs2 = calculate_flood_damage_cost(
                    opt_metrics2['flooded_road_km'],
                    opt_metrics2['flooded_area_pct'],
                    opt_metrics2['avg_depth_m']
                )
                opt_damage_cr2 = opt_damage_lakhs2 / 100
                damage_reduction_cr2 = baseline_damage_cr - opt_damage_cr2
                net_benefit_cr2 = damage_reduction_cr2 - actual_cost_cr2
                roi2 = (damage_reduction_cr2 / actual_cost_cr2) if actual_cost_cr2 > 0 else 0.0
                road_km_reduction2 = baseline_metrics['flooded_road_km'] - opt_metrics2['flooded_road_km']
                area_reduction_pct2 = baseline_metrics['flooded_area_pct'] - opt_metrics2['flooded_area_pct']
                avg_depth_delta2 = baseline_metrics['avg_depth_m'] - opt_metrics2['avg_depth_m']
                print(f"    📊 Step {step} ROI: {roi2:.2f}x; roads Δ {road_km_reduction2:+.2f} km")
                # Accept only if ROI improves and KPIs do not worsen
                if (roi2 > best_roi) and (opt_metrics2['flooded_road_km'] <= best_result['opt_metrics']['flooded_road_km']):
                    best_roi = roi2
                    best_design = design_path2
                    best_sim_dir = sim_dir2
                    best_result.update({
                        'actual_cost_cr': actual_cost_cr2,
                        'opt_damage_cr': opt_damage_cr2,
                        'damage_reduction_cr': damage_reduction_cr2,
                        'net_benefit_cr': net_benefit_cr2,
                        'roi': roi2,
                        'flood_reduction_road_km': road_km_reduction2,
                        'flooded_area_reduction_pct': area_reduction_pct2,
                        'avg_depth_delta_m': avg_depth_delta2,
                        'opt_metrics': opt_metrics2,
                        'design_path': str(design_path2),
                        'sim_dir': str(sim_dir2)
                    })
                else:
                    print("    ↩️  No improvement; stopping autonomy")
                    break
            # Use best autonomous result
            result = best_result
            design_path = Path(result['design_path'])
            sim_dir = Path(result['sim_dir'])

        # If ROI < 1 and budget headroom exists, attempt greedy fill rerun to incrementally improve
        if roi < 1.0 and actual_cost_cr < budget_cr:
            print("  🔁 ROI < 1.0x. Attempting greedy-fill optimization to add actions incrementally...")
            design_path2 = budget_dir / 'qcia_design_greedy.json'
            success2 = run_qcia_for_budget(
                baseline_dir, budget_cr, args.target_reduction_pct, design_path2,
                extra_args=['--force_greedy', '--roi_threshold', '0.10', '--budget_soft_utilization', '0.90', '--max_actions', '10']
            )
            if success2 and design_path2.exists():
                with open(design_path2) as f:
                    design2 = json.load(f)
                actual_cost_cr2 = design2.get('total_cost_cr', budget_cr)
                num_interventions2 = len(design2.get('interventions', []))
                sim_dir2 = budget_dir / 'simulation_greedy'
                success2 = run_simulation_with_design(
                    args.dem, args.lulc, args.rivers, args.roads,
                    args.tile_col0, args.tile_row0,
                    args.nx, args.ny,
                    args.rain_mm_per_hour, args.t_hours,
                    design_path2, sim_dir2
                )
                if success2:
                    road_log2 = run_road_overlay(sim_dir2, args.roads)
                    opt_npz2 = sim_dir2 / 'final_snapshot.npz'
                    opt_metrics2 = extract_flood_metrics(opt_npz2, str(road_log2))
                    opt_damage_lakhs2 = calculate_flood_damage_cost(
                        opt_metrics2['flooded_road_km'],
                        opt_metrics2['flooded_area_pct'],
                        opt_metrics2['avg_depth_m']
                    )
                    opt_damage_cr2 = opt_damage_lakhs2 / 100
                    damage_reduction_cr2 = baseline_damage_cr - opt_damage_cr2
                    net_benefit_cr2 = damage_reduction_cr2 - actual_cost_cr2
                    roi2 = (damage_reduction_cr2 / actual_cost_cr2) if actual_cost_cr2 > 0 else 0.0
                    road_km_reduction2 = baseline_metrics['flooded_road_km'] - opt_metrics2['flooded_road_km']
                    area_reduction_pct2 = baseline_metrics['flooded_area_pct'] - opt_metrics2['flooded_area_pct']
                    avg_depth_delta2 = baseline_metrics['avg_depth_m'] - opt_metrics2['avg_depth_m']
                    print(f"  🔁 Greedy-fill results: ROI {roi2:.2f}x, cost ₹{actual_cost_cr2:.2f}Cr, Δroads {road_km_reduction2:+.2f} km, Δarea {area_reduction_pct2:+.1f} pp")
                    if roi2 > roi:
                        # Replace with improved result
                        design_path = design_path2
                        sim_dir = sim_dir2
                        result.update({
                            'actual_cost_cr': actual_cost_cr2,
                            'num_interventions': num_interventions2,
                            'opt_damage_cr': opt_damage_cr2,
                            'damage_reduction_cr': damage_reduction_cr2,
                            'net_benefit_cr': net_benefit_cr2,
                            'roi': roi2,
                            'flood_reduction_road_km': road_km_reduction2,
                            'flooded_area_reduction_pct': area_reduction_pct2,
                            'avg_depth_delta_m': avg_depth_delta2,
                            'design_path': str(design_path2),
                            'sim_dir': str(sim_dir2)
                        })
                        print("  ✅ Adopted greedy-fill plan (improved ROI)")
                        
                        # Record greedy-fill experiences
                        record_intervention_experiences(
                            design_path=design_path2,
                            baseline_metrics=baseline_metrics,
                            opt_metrics=opt_metrics2,
                            baseline_damage_cr=baseline_damage_cr,
                            opt_damage_cr=opt_damage_cr2,
                            actual_cost_cr=actual_cost_cr2,
                            roi=roi2,
                            aoi_name=aoi_name
                        )
    
    # Save results
    results_json = output_root / 'budget_sweep_results.json'
    with open(results_json, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n{'='*70}")
    print(f"📊 BUDGET SWEEP COMPLETE")
    print(f"{'='*70}\n")
    
    if not results:
        print("❌ No successful budget scenarios")
        return 1
    
    # Find best value
    best_roi = max(results, key=lambda r: r['roi'])
    best_net = max(results, key=lambda r: r['net_benefit_cr'])
    
    print(f"🏆 BEST VALUE FOR MONEY:")
    print(f"   Budget: ₹{best_roi['budget_cr']} Cr")
    print(f"   ROI: {best_roi['roi']:.2f}x")
    print(f"   Damage reduction: ₹{best_roi['damage_reduction_cr']:.2f} Cr")
    print(f"   Net benefit: ₹{best_roi['net_benefit_cr']:.2f} Cr")
    print("")
    
    print(f"💰 HIGHEST NET BENEFIT:")
    print(f"   Budget: ₹{best_net['budget_cr']} Cr")
    print(f"   Net benefit: ₹{best_net['net_benefit_cr']:.2f} Cr")
    print(f"   ROI: {best_net['roi']:.2f}x")
    print("")
    
    # Generate comparison plots
    print("📈 Generating ROI curves...")
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle('Budget Sweep Analysis', fontsize=16, fontweight='bold')
    
    budgets = [r['budget_cr'] for r in results]
    rois = [r['roi'] for r in results]
    damage_reductions = [r['damage_reduction_cr'] for r in results]
    net_benefits = [r['net_benefit_cr'] for r in results]
    
    # ROI curve
    ax = axes[0, 0]
    ax.plot(budgets, rois, 'o-', linewidth=2, markersize=8, color='#2E86AB')
    ax.axhline(1.0, color='red', linestyle='--', alpha=0.5, label='Break-even (ROI=1)')
    ax.scatter([best_roi['budget_cr']], [best_roi['roi']], 
               s=200, color='gold', edgecolor='black', linewidth=2, zorder=10, label='Best ROI')
    ax.set_xlabel('Budget (₹ Crores)', fontsize=12)
    ax.set_ylabel('Return on Investment (ROI)', fontsize=12)
    ax.set_title('ROI vs Budget', fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.legend()
    
    # Damage reduction
    ax = axes[0, 1]
    ax.plot(budgets, damage_reductions, 'o-', linewidth=2, markersize=8, color='#06A77D')
    ax.scatter([best_roi['budget_cr']], [best_roi['damage_reduction_cr']], 
               s=200, color='gold', edgecolor='black', linewidth=2, zorder=10, label='Best ROI')
    ax.set_xlabel('Budget (₹ Crores)', fontsize=12)
    ax.set_ylabel('Flood Damage Reduction (₹ Cr)', fontsize=12)
    ax.set_title('Damage Reduction vs Budget', fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.legend()
    
    # Net benefit
    ax = axes[1, 0]
    ax.plot(budgets, net_benefits, 'o-', linewidth=2, markersize=8, color='#D4A72C')
    ax.axhline(0, color='red', linestyle='--', alpha=0.5, label='Break-even')
    ax.scatter([best_net['budget_cr']], [best_net['net_benefit_cr']], 
               s=200, color='gold', edgecolor='black', linewidth=2, zorder=10, label='Max Net Benefit')
    ax.set_xlabel('Budget (₹ Crores)', fontsize=12)
    ax.set_ylabel('Net Benefit (₹ Cr)', fontsize=12)
    ax.set_title('Net Benefit vs Budget', fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.legend()
    
    # Summary table
    ax = axes[1, 1]
    ax.axis('off')
    
    table_data = [
        ['Budget (₹Cr)', 'ROI', 'Net Benefit (₹Cr)']
    ]
    for r in results:
        table_data.append([
            f"{r['budget_cr']:.0f}",
            f"{r['roi']:.2f}x",
            f"{r['net_benefit_cr']:.2f}"
        ])
    
    table = ax.table(cellText=table_data, cellLoc='center', loc='center',
                     colWidths=[0.3, 0.3, 0.4])
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 2)
    
    # Highlight header
    for i in range(3):
        table[(0, i)].set_facecolor('#2E86AB')
        table[(0, i)].set_text_props(weight='bold', color='white')
    
    # Highlight best ROI row
    best_row = budgets.index(best_roi['budget_cr']) + 1
    for i in range(3):
        table[(best_row, i)].set_facecolor('#FFD700')
        table[(best_row, i)].set_text_props(weight='bold')
    
    plt.tight_layout()
    plot_path = output_root / 'budget_analysis.png'
    plt.savefig(plot_path, dpi=150, bbox_inches='tight')
    print(f"   ✅ Saved: {plot_path}")
    
    # Save recommendation
    recommendation = {
        'best_roi_budget_cr': best_roi['budget_cr'],
        'best_roi_value': best_roi['roi'],
        'best_net_benefit_budget_cr': best_net['budget_cr'],
        'best_net_benefit_value': best_net['net_benefit_cr'],
        'baseline_damage_cr': baseline_damage_cr,
        'recommendation': f"₹{best_roi['budget_cr']}Cr budget offers best value (ROI: {best_roi['roi']:.2f}x)"
    }
    
    rec_path = output_root / 'recommendation.json'
    with open(rec_path, 'w') as f:
        json.dump(recommendation, f, indent=2)
    
    print(f"   ✅ Saved: {rec_path}")
    print("")
    
    print("="*70)
    print("✅ BUDGET SWEEP ANALYSIS COMPLETE")
    print("="*70)
    print(f"📁 Results: {output_root}/")
    print(f"   • budget_sweep_results.json - Full data")
    print(f"   • budget_analysis.png - ROI curves")
    print(f"   • recommendation.json - Best value budget")
    print(f"   • budget_XXcr/ - Individual scenario outputs")
    print("")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())

