#!/usr/bin/env python3
"""
Generate delta visuals from baseline and optimized simulation outputs.

Outputs:
- delta_grid.png: baseline - optimized flood depth heatmap
- site_zoom_<k>.png: zoomed insets around pond/pump sites
- Prints KPIs: flooded area above thresholds and depth percentiles
"""

import json
import argparse
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt


def load_depth(npz_dir: Path) -> np.ndarray:
    npz_path = npz_dir / 'final_snapshot.npz'
    data = np.load(npz_path)
    return data['h']


def save_delta_grid(h_base: np.ndarray, h_opt: np.ndarray, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    delta = h_base - h_opt
    fig = plt.figure(figsize=(10, 8))
    ax = plt.subplot(111)
    im = ax.imshow(delta, cmap='RdYlGn', vmin=-0.5, vmax=0.5)
    ax.set_title('Depth Reduction (baseline - optimized)\nGreen = improvement', fontsize=14, weight='bold')
    ax.axis('off')
    cbar = plt.colorbar(im, ax=ax, fraction=0.046)
    cbar.set_label('ΔDepth (m)')
    mean_delta = float(np.mean(delta))
    pos_frac = float(np.mean(delta > 0.05))
    ax.text(0.02, 0.98, f"Mean Δ: {mean_delta:.3f} m\nCells improved (>5cm): {pos_frac*100:.1f}%",
            transform=ax.transAxes, va='top', fontsize=10,
            bbox=dict(boxstyle='round', facecolor='white', alpha=0.9))
    fig.tight_layout()
    fig.savefig(out_dir / 'delta_grid.png', dpi=300, bbox_inches='tight')
    plt.close(fig)


def save_site_zooms(h_base: np.ndarray, h_opt: np.ndarray, design_path: Path, out_dir: Path, max_sites: int = 3):
    with open(design_path, 'r') as f:
        design = json.load(f)
    # Prefer ponds/pumps first
    sites = []
    for it in ['pond', 'pump', 'culvert']:
        for k, iv in enumerate(design['interventions']):
            if it in iv['type'].lower():
                sites.append((it, iv))
    sites = sites[:max_sites]
    for idx, (it, iv) in enumerate(sites, 1):
        i, j = iv['location']
        r = 10
        i0, i1 = max(0, i - r), min(h_base.shape[0], i + r + 1)
        j0, j1 = max(0, j - r), min(h_base.shape[1], j + r + 1)
        hb = h_base[i0:i1, j0:j1]
        ho = h_opt[i0:i1, j0:j1]
        d = hb - ho
        fig = plt.figure(figsize=(15, 5))
        ax1 = plt.subplot(1, 3, 1)
        im1 = ax1.imshow(hb, cmap='Blues', vmin=0, vmax=2)
        ax1.set_title('Baseline', fontsize=12, weight='bold')
        ax1.axis('off')
        plt.colorbar(im1, ax=ax1, fraction=0.046)
        ax2 = plt.subplot(1, 3, 2)
        im2 = ax2.imshow(ho, cmap='Blues', vmin=0, vmax=2)
        ax2.set_title('Optimized', fontsize=12, weight='bold')
        ax2.axis('off')
        plt.colorbar(im2, ax=ax2, fraction=0.046)
        ax3 = plt.subplot(1, 3, 3)
        im3 = ax3.imshow(d, cmap='RdYlGn', vmin=-0.5, vmax=0.5)
        ax3.set_title('ΔDepth (m)  Green=improvement', fontsize=12, weight='bold')
        ax3.axis('off')
        plt.colorbar(im3, ax=ax3, fraction=0.046)
        text = f"Site: {iv['type']} at ({i},{j})\nMean Δ: {np.mean(d):.3f} m  (>5cm improved: {np.mean(d>0.05)*100:.1f}%)"
        ax3.text(0.02, 0.98, text, transform=ax3.transAxes, va='top', fontsize=9,
                 bbox=dict(boxstyle='round', facecolor='white', alpha=0.9))
        fig.suptitle(f'Zoom #{idx}: {iv['type']}', fontsize=14, weight='bold')
        fig.tight_layout(rect=[0, 0, 1, 0.95])
        fig.savefig(out_dir / f'site_zoom_{idx:02d}.png', dpi=300, bbox_inches='tight')
        plt.close(fig)


def compute_kpis(h: np.ndarray, thresholds=(0.1, 0.2, 0.3)):
    total_cells = h.size
    area_fracs = {thr: float(np.sum(h >= thr)) / total_cells for thr in thresholds}
    nonzero = h[h > 1e-3]
    p50 = float(np.percentile(nonzero, 50)) if nonzero.size else 0.0
    p90 = float(np.percentile(nonzero, 90)) if nonzero.size else 0.0
    return area_fracs, p50, p90


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base_dir', required=True)
    ap.add_argument('--opt_dir', required=True)
    ap.add_argument('--design', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    base_dir = Path(args.base_dir)
    opt_dir = Path(args.opt_dir)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    h_base = load_depth(base_dir)
    h_opt = load_depth(opt_dir)

    # Delta grid
    save_delta_grid(h_base, h_opt, out_dir)

    # Site zooms
    save_site_zooms(h_base, h_opt, Path(args.design), out_dir, max_sites=3)

    # KPIs
    thr = (0.1, 0.2, 0.3)
    area_b, p50_b, p90_b = compute_kpis(h_base, thr)
    area_o, p50_o, p90_o = compute_kpis(h_opt, thr)
    print('\nKPI SUMMARY (from depth grids):')
    for t in thr:
        print(f"  Flooded area >= {t:.1f} m: baseline={area_b[t]*100:.1f}%  optimized={area_o[t]*100:.1f}%  Δ={(area_b[t]-area_o[t])*100:.1f} pp")
    print(f"  Depth percentiles (P50): baseline={p50_b:.2f} m  optimized={p50_o:.2f} m  Δ={p50_b-p50_o:.2f} m")
    print(f"  Depth percentiles (P90): baseline={p90_b:.2f} m  optimized={p90_o:.2f} m  Δ={p90_b-p90_o:.2f} m")


if __name__ == '__main__':
    main()




