#!/usr/bin/env python3
"""
Compute POI KPIs by sampling final_h.tif at POI locations.

Outputs:
- CSV with per-POI depth and flooded flag
- PNG overlay with POIs colored by depth

Dependencies: rasterio, fiona, shapely, pyproj, matplotlib
"""

from __future__ import annotations

import argparse
from pathlib import Path
import csv
import numpy as np
import rasterio as rio
from pyproj import Transformer
import fiona
from shapely.geometry import shape as shp_shape
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main() -> None:
    ap = argparse.ArgumentParser(description='POI KPI sampling')
    ap.add_argument('--run_dir', type=str, default='runs/gurdaspur_aoi12_manning_channels')
    ap.add_argument('--pois', type=str, default='Data/pois_aoi.geojson')
    ap.add_argument('--threshold_m', type=float, default=0.10)
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    tif = run_dir / 'final_h.tif'
    if not tif.exists():
        raise SystemExit(f'Missing {tif}')

    with rio.open(tif) as ds:
        h = ds.read(1).astype(float)
        transform = ds.transform
        crs = ds.crs
        height, width = h.shape

    rows = []
    xs = []
    ys = []
    vals = []

    with fiona.open(args.pois, 'r') as src:
        src_crs = src.crs_wkt or src.crs or 'EPSG:4326'
        to_raster = Transformer.from_crs(src_crs, crs, always_xy=True)
        for feat in src:
            geom = shp_shape(feat['geometry'])
            if geom.is_empty:
                continue
            xw, yw = geom.x, geom.y
            xr, yr = to_raster.transform(xw, yw)
            # map to row/col
            col, row = ~transform * (xr, yr)
            col = int(np.floor(col))
            row = int(np.floor(row))
            if 0 <= row < height and 0 <= col < width:
                depth = float(h[row, col])
            else:
                depth = float('nan')
            name = (feat.get('properties') or {}).get('name') or ''
            rows.append({'name': name, 'lon': xw, 'lat': yw, 'depth_m': depth, 'flooded': int(depth >= float(args.threshold_m)) if np.isfinite(depth) else 0})
            xs.append(col)
            ys.append(row)
            vals.append(depth if np.isfinite(depth) else 0.0)

    # CSV
    csv_path = run_dir / 'poi_kpis.csv'
    with open(csv_path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['name', 'lon', 'lat', 'depth_m', 'flooded'])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print('Wrote', csv_path)

    # PNG overlay
    vmax = max(0.2, float(np.nanpercentile(h, 99)))
    fig, ax = plt.subplots(figsize=(7,6))
    im = ax.imshow(h.T, origin='lower', cmap='viridis', vmin=0.0, vmax=vmax)
    # color POIs by depth relative to threshold
    xs_np = np.array(xs)
    ys_np = np.array(ys)
    vals_np = np.array(vals)
    flooded = vals_np >= float(args.threshold_m)
    ax.scatter(xs_np[~flooded], ys_np[~flooded], s=28, c='white', edgecolors='k', linewidths=0.3, alpha=0.9, label='POI dry')
    if np.any(flooded):
        ax.scatter(xs_np[flooded], ys_np[flooded], s=32, c='red', edgecolors='k', linewidths=0.3, alpha=0.9, label='POI flooded')
    ax.legend(loc='lower right')
    fig.colorbar(im, ax=ax, label='Depth (m)')
    ax.set_title(f'POIs (>= {args.threshold_m:.2f} m in red)')
    ax.set_xlabel('i (cells)')
    ax.set_ylabel('j (cells)')
    fig.tight_layout()
    png_path = run_dir / 'poi_overlay.png'
    fig.savefig(png_path, dpi=150)
    plt.close(fig)
    print('Saved', png_path)


if __name__ == '__main__':
    main()


