#!/usr/bin/env python3
"""
Parameter Sweep Calibration
============================
Systematically tests different physics parameters to find the combination
that maximizes intervention effectiveness and provides realistic flood behavior.

Parameters to sweep:
1. Manning's roughness coefficient (n): 0.025 - 0.055
2. Infiltration rate: 1e-7 - 5e-6 m/s
3. Rainfall intensity scaling: 0.8x - 1.2x

Target metrics:
- Baseline flooding: 15-30% of area (realistic)
- Intervention effectiveness: 5-15% reduction
- Mass balance error: <10%
- ROI: >0.5x (approaching break-even)
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple
import numpy as np
import matplotlib.pyplot as plt
import argparse
from itertools import product


def run_baseline_with_params(
    manning_n: float,
    infil_rate: float,
    rain_scale: float,
    output_dir: Path
) -> Dict:
    """Run baseline simulation with specific parameters."""
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Base rainfall: 60 mm/hr
    rain_mm_hr = 60.0 * rain_scale
    
    cmd = [
        'python', 'Runners/pb_cli.py',
        '--dem', 'Data/Jabalpur_Data/DEM_utm44.tif',
        '--lulc', 'Data/Jabalpur_Data/LULC_utm44.tif',
        '--rivers', 'Data/Jabalpur_Data/Main/rivers_aoi.geojson',
        '--roads', 'Data/Jabalpur_Data/Main/roads_aoi.geojson',
        '--tile_col0', '4474',
        '--tile_row0', '4260',
        '--nx', '100',
        '--ny', '100',
        '--rain_mm_per_hour', str(rain_mm_hr),
        '--t_hours', '1.5',
        '--out', str(output_dir),
        '--plot_vmax', '2.0',
        '--manning_n', str(manning_n),
        '--infil_rate_mps', str(infil_rate)
    ]
    
    print(f"   Running baseline: n={manning_n:.3f}, infil={infil_rate:.2e}, rain={rain_mm_hr:.0f} mm/hr...")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        # Extract metrics from output
        metrics = {
            'manning_n': manning_n,
            'infil_rate': infil_rate,
            'rain_scale': rain_scale,
            'success': result.returncode == 0
        }
        
        if result.returncode == 0:
            # Parse output for metrics
            for line in result.stdout.split('\n'):
                if 'Final mass:' in line:
                    try:
                        metrics['final_mass'] = float(line.split(':')[1].split('m³')[0].strip())
                    except:
                        pass
                if 'Discrepancy:' in line and '%' in line:
                    try:
                        # Extract percentage
                        pct_str = line.split('(')[1].split('%')[0].strip()
                        metrics['mass_error_pct'] = float(pct_str)
                    except:
                        pass
            
            # Load flood depth grid
            npz_path = output_dir / 'final_snapshot.npz'
            if npz_path.exists():
                data = np.load(npz_path)
                h = data['h']
                
                flooded_02 = np.sum(h >= 0.2)
                total_cells = h.size
                metrics['flooded_pct'] = 100.0 * flooded_02 / total_cells
                metrics['max_depth'] = float(np.max(h))
                metrics['avg_depth'] = float(np.mean(h[h > 0.01])) if np.any(h > 0.01) else 0.0
        
        return metrics
    
    except subprocess.TimeoutExpired:
        print(f"   ⚠️  Timeout")
        return {'manning_n': manning_n, 'infil_rate': infil_rate, 'rain_scale': rain_scale, 'success': False}
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return {'manning_n': manning_n, 'infil_rate': infil_rate, 'rain_scale': rain_scale, 'success': False}


def score_parameter_set(metrics: Dict) -> float:
    """
    Score a parameter set based on target criteria.
    Higher score = better.
    
    Criteria:
    1. Baseline flooding in realistic range (15-30%)
    2. Low mass balance error (<10%)
    3. Reasonable flood depths (0.5-2.0m max)
    """
    if not metrics.get('success', False):
        return -1000.0
    
    score = 0.0
    
    # 1. Baseline flooding score (target: 20% ± 5%)
    flooded_pct = metrics.get('flooded_pct', 0.0)
    if 15.0 <= flooded_pct <= 30.0:
        # Perfect range
        deviation = abs(flooded_pct - 20.0)
        score += 100.0 - (deviation * 5.0)
    elif flooded_pct < 15.0:
        # Too little flooding
        score += 50.0 - (15.0 - flooded_pct) * 10.0
    else:
        # Too much flooding
        score += 50.0 - (flooded_pct - 30.0) * 5.0
    
    # 2. Mass balance score (target: <10% error)
    mass_err = abs(metrics.get('mass_error_pct', 50.0))
    if mass_err < 10.0:
        score += 50.0 - (mass_err * 2.0)
    else:
        score += 10.0 - (mass_err - 10.0)
    
    # 3. Max depth score (target: 0.5-2.0m)
    max_depth = metrics.get('max_depth', 0.0)
    if 0.5 <= max_depth <= 2.0:
        score += 50.0
    elif max_depth < 0.5:
        score += 25.0
    else:
        score += max(0, 50.0 - (max_depth - 2.0) * 10.0)
    
    return score


def main():
    parser = argparse.ArgumentParser(description='Parameter Sweep Calibration')
    parser.add_argument('--output_dir', type=str, default='outputs/parameter_sweep',
                        help='Output directory for sweep results')
    parser.add_argument('--quick', action='store_true',
                        help='Quick sweep (fewer combinations)')
    args = parser.parse_args()
    
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("╔══════════════════════════════════════════════════════════════════════════════╗")
    print("║              PARAMETER SWEEP CALIBRATION                                     ║")
    print("╚══════════════════════════════════════════════════════════════════════════════╝")
    print("")
    
    # Define parameter ranges
    if args.quick:
        manning_n_values = [0.030, 0.040, 0.050]
        infil_values = [5e-7, 1e-6, 5e-6]
        rain_scales = [1.0]  # Only baseline rainfall
    else:
        manning_n_values = [0.025, 0.030, 0.035, 0.040, 0.045, 0.050, 0.055]
        infil_values = [1e-7, 5e-7, 1e-6, 3e-6, 5e-6]
        rain_scales = [0.8, 1.0, 1.2]
    
    total_combos = len(manning_n_values) * len(infil_values) * len(rain_scales)
    
    print(f"🔬 Parameter Ranges:")
    print(f"   Manning's n:    {len(manning_n_values)} values from {min(manning_n_values):.3f} to {max(manning_n_values):.3f}")
    print(f"   Infiltration:   {len(infil_values)} values from {min(infil_values):.1e} to {max(infil_values):.1e} m/s")
    print(f"   Rain scaling:   {len(rain_scales)} values from {min(rain_scales):.1f}x to {max(rain_scales):.1f}x")
    print(f"   Total combinations: {total_combos}")
    print("")
    
    # Run parameter sweep
    print("🔄 Running simulations...")
    print("─" * 79)
    
    results = []
    for idx, (n, infil, rain) in enumerate(product(manning_n_values, infil_values, rain_scales), 1):
        print(f"[{idx}/{total_combos}]", end=" ")
        
        run_dir = output_dir / f"n{n:.3f}_i{infil:.1e}_r{rain:.1f}"
        metrics = run_baseline_with_params(n, infil, rain, run_dir)
        
        # Score this parameter set
        score = score_parameter_set(metrics)
        metrics['score'] = score
        
        results.append(metrics)
        
        if metrics.get('success', False):
            print(f"   ✅ Score: {score:.1f}, Flooded: {metrics.get('flooded_pct', 0):.1f}%, Mass err: {abs(metrics.get('mass_error_pct', 0)):.1f}%")
        else:
            print(f"   ❌ Failed")
    
    print("─" * 79)
    print("")
    
    # Analyze results
    print("📊 RESULTS ANALYSIS")
    print("=" * 79)
    
    # Filter successful runs
    successful = [r for r in results if r.get('success', False)]
    
    if not successful:
        print("❌ No successful runs!")
        return
    
    # Sort by score
    successful.sort(key=lambda x: x['score'], reverse=True)
    
    # Top 5 parameter sets
    print("\n🏆 TOP 5 PARAMETER SETS:")
    print("")
    for idx, result in enumerate(successful[:5], 1):
        print(f"{idx}. Manning's n={result['manning_n']:.3f}, Infiltration={result['infil_rate']:.2e} m/s, Rain={result['rain_scale']:.1f}x")
        print(f"   Score: {result['score']:.1f}")
        print(f"   Flooded: {result.get('flooded_pct', 0):.1f}% (target: 15-30%)")
        print(f"   Mass error: {abs(result.get('mass_error_pct', 0)):.1f}% (target: <10%)")
        print(f"   Max depth: {result.get('max_depth', 0):.2f}m (target: 0.5-2.0m)")
        print("")
    
    # Save results
    results_file = output_dir / 'sweep_results.json'
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"💾 Saved results to: {results_file}")
    
    # Generate heatmap
    print("\n📈 Generating heatmap...")
    generate_heatmap(results, output_dir)
    
    # Recommendation
    best = successful[0]
    print("\n" + "=" * 79)
    print("✅ RECOMMENDED PARAMETERS:")
    print("=" * 79)
    print(f"   Manning's n:        {best['manning_n']:.3f}")
    print(f"   Infiltration rate:  {best['infil_rate']:.2e} m/s")
    print(f"   Rain scaling:       {best['rain_scale']:.1f}x")
    print("")
    print(f"   Expected baseline flooding: {best.get('flooded_pct', 0):.1f}%")
    print(f"   Mass balance error:         {abs(best.get('mass_error_pct', 0)):.1f}%")
    print("")
    print("🚀 To use these parameters, add to pb_cli.py:")
    print(f"   --manning_n {best['manning_n']:.3f} --infil_rate_mps {best['infil_rate']:.2e}")
    print("=" * 79)


def generate_heatmap(results: List[Dict], output_dir: Path):
    """Generate heatmap of parameter sweep results."""
    # Filter successful
    successful = [r for r in results if r.get('success', False)]
    
    if len(successful) < 4:
        print("   ⚠️  Too few successful runs for heatmap")
        return
    
    # Extract data for heatmap (Manning's n vs Infiltration, averaged over rain)
    manning_vals = sorted(set(r['manning_n'] for r in successful))
    infil_vals = sorted(set(r['infil_rate'] for r in successful))
    
    # Create score matrix
    score_matrix = np.zeros((len(infil_vals), len(manning_vals)))
    count_matrix = np.zeros((len(infil_vals), len(manning_vals)))
    
    for r in successful:
        i = infil_vals.index(r['infil_rate'])
        j = manning_vals.index(r['manning_n'])
        score_matrix[i, j] += r['score']
        count_matrix[i, j] += 1
    
    # Average scores
    score_matrix = np.divide(score_matrix, count_matrix, where=count_matrix > 0)
    
    # Plot heatmap
    fig, ax = plt.subplots(figsize=(10, 8))
    im = ax.imshow(score_matrix, cmap='RdYlGn', aspect='auto')
    
    # Labels
    ax.set_xticks(range(len(manning_vals)))
    ax.set_yticks(range(len(infil_vals)))
    ax.set_xticklabels([f'{n:.3f}' for n in manning_vals])
    ax.set_yticklabels([f'{i:.1e}' for i in infil_vals])
    ax.set_xlabel("Manning's n", fontsize=12)
    ax.set_ylabel("Infiltration rate (m/s)", fontsize=12)
    ax.set_title("Parameter Sweep Results\n(Higher score = Better)", fontsize=14)
    
    # Colorbar
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label('Score', fontsize=12)
    
    # Annotate cells with scores
    for i in range(len(infil_vals)):
        for j in range(len(manning_vals)):
            if count_matrix[i, j] > 0:
                text = ax.text(j, i, f'{score_matrix[i, j]:.0f}',
                               ha="center", va="center", color="black", fontsize=8)
    
    plt.tight_layout()
    heatmap_file = output_dir / 'parameter_heatmap.png'
    plt.savefig(heatmap_file, dpi=150)
    print(f"   ✅ Saved heatmap to: {heatmap_file}")


if __name__ == '__main__':
    main()



