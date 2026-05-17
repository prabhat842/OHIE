#!/usr/bin/env python3
"""
Create a differential overlay highlighting AI-chosen effects on flooded roads.

Green: roads flooded in baseline, dry in agent (improvement)
Orange: roads dry in baseline, flooded in agent (regression)
Red: flooded in both
White: all roads

Background: agent run depth raster
"""

from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
import rasterio as rio
from rasterio import features as rio_features
import fiona
from shapely.geometry import shape as shp_shape
from shapely.ops import transform as shp_transform
from pyproj import Transformer
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def rasterize_roads(path: Path, transform, shape, target_crs):
    with fiona.open(path, 'r') as src:
        src_crs = src.crs_wkt or src.crs or 'EPSG:4326'
        tx = Transformer.from_crs(src_crs, target_crs, always_xy=True)
        geoms = []
        for feat in src:
            geom = shp_shape(feat['geometry'])
            geom_t = shp_transform(lambda x, y, z=None: tx.transform(x, y), geom)
            geoms.append((geom_t, 1))
    return rio_features.rasterize(geoms, out_shape=shape, transform=transform, fill=0, all_touched=True, dtype=np.uint8)


def flooded_km(h: np.ndarray, road_mask: np.ndarray, threshold_m: float, dx: float, dy: float) -> float:
    flooded = (h >= threshold_m) & (road_mask > 0)
    pixel_len = 0.5 * (abs(dx) + abs(dy))
    return float(np.sum(flooded) * pixel_len) / 1000.0


def main():
    ap = argparse.ArgumentParser(description='Compare baseline vs agent runs on flooded roads')
    ap.add_argument('--base_dir', type=str, required=True)
    ap.add_argument('--agent_dir', type=str, required=True)
    ap.add_argument('--roads', type=str, default='Data/roads_aoi.geojson')
    ap.add_argument('--threshold_m', type=float, default=0.05)
    ap.add_argument('--structures', type=str, default='', help='Path to structures_debug.geojson to overlay')
    args = ap.parse_args()

    base_tif = Path(args.base_dir) / 'final_h.tif'
    agent_tif = Path(args.agent_dir) / 'final_h.tif'
    if not base_tif.exists() or not agent_tif.exists():
        raise SystemExit('Missing final_h.tif in one of the runs')

    with rio.open(agent_tif) as da:
        ha = da.read(1).astype(float)
        ta = da.transform
        cra = da.crs
        dx, dy = da.transform.a, da.transform.e
    with rio.open(base_tif) as db:
        hb = db.read(1).astype(float)
        tb = db.transform
        crb = db.crs

    if ha.shape != hb.shape or ta != tb:
        raise SystemExit('Runs are not aligned; please ensure same tile and resolution')

    roads = Path(args.roads)
    road_mask = rasterize_roads(roads, ta, ha.shape, cra)

    thr = float(args.threshold_m)
    fb = (hb >= thr) & (road_mask > 0)
    fa = (ha >= thr) & (road_mask > 0)

    km_base = flooded_km(hb, road_mask, thr, dx, dy)
    km_agent = flooded_km(ha, road_mask, thr, dx, dy)

    # Plot
    vmax = max(0.2, float(np.nanpercentile(ha, 99)))
    fig, ax = plt.subplots(figsize=(7.5, 6.5))
    im = ax.imshow(ha.T, origin='lower', cmap='viridis', vmin=0.0, vmax=vmax)
    # All roads
    ax.contour((road_mask>0).T, levels=[0.5], colors='white', linewidths=0.5, alpha=0.8)
    # Differences
    both = (fb & fa).T
    improved = (fb & ~fa).T
    worse = (~fb & fa).T
    if np.any(both):
        ax.contour(both, levels=[0.5], colors='red', linewidths=0.8, alpha=0.9)
    if np.any(improved):
        ax.contour(improved, levels=[0.5], colors='lime', linewidths=1.0, alpha=0.95)
    if np.any(worse):
        ax.contour(worse, levels=[0.5], colors='orange', linewidths=1.0, alpha=0.95)
    fig.colorbar(im, ax=ax, label='Depth (m) [agent]')
    # Overlay structures if provided
    if args.structures and Path(args.structures).exists():
        try:
            import json
            data = json.load(open(args.structures))
            for feat in data.get('features', []):
                geom = feat.get('geometry', {})
                coords = geom.get('coordinates', [])
                if geom.get('type') == 'LineString' and len(coords) >= 2:
                    # coords in lon/lat; transform to raster rows/cols
                    try:
                        tx = Transformer.from_crs('EPSG:4326', cra, always_xy=True)
                    except Exception:
                        tx = None
                    rows = []
                    cols = []
                    for lon, lat in coords:
                        if tx:
                            x, y = tx.transform(lon, lat)
                        else:
                            x, y = lon, lat
                        r, c = rowcol(ta, x, y)
                        if 0 <= r < ha.shape[0] and 0 <= c < ha.shape[1]:
                            rows.append(r)
                            cols.append(c)
                    if len(cols) > 1:
                        ax.plot(np.array(cols), np.array(rows), color='yellow', linewidth=1.2, alpha=0.9)
        except Exception:
            pass
    ax.set_title(f'AI impact on flooded roads (thr={thr:.02f} m)\nBase={km_base:.2f} km, Agent={km_agent:.2f} km, Δ={km_agent-km_base:+.2f} km\nGreen=improved, Red=still flooded, Orange=regression')
    ax.set_xlabel('i (cells)')
    ax.set_ylabel('j (cells)')
    fig.tight_layout()
    out_png = Path(args.agent_dir) / 'overlay_compare.png'
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print('Saved', out_png)


if __name__ == '__main__':
    main()




