#!/usr/bin/env python3
"""
Compute flooded road length (h > threshold) and render an overlay PNG for AOI.

Inputs:
- final_h.tif (georeferenced)
- Data/roads_aoi.geojson (clipped roads)

Outputs:
- runs/gurdaspur_aoi_demo/overlay_roads.png
- prints flooded km stats

Dependencies: rasterio, shapely, fiona, matplotlib
"""

from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
import rasterio as rio
from rasterio import features as rio_features
from shapely.geometry import shape as shp_shape, mapping as shp_mapping
from shapely.ops import transform as shp_transform
from pyproj import Transformer
import fiona
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def rasterize_roads(roads_path: Path, transform, shape, target_crs):
    with fiona.open(roads_path, 'r') as src:
        src_crs = src.crs_wkt or src.crs
        # Default to EPSG:4326 if missing
        if not src_crs:
            src_crs = "EPSG:4326"
        transformer = Transformer.from_crs(src_crs, target_crs, always_xy=True)
        geoms = []
        for feat in src:
            geom = shp_shape(feat['geometry'])
            geom_t = shp_transform(lambda x, y, z=None: transformer.transform(x, y), geom)
            geoms.append((geom_t, 1))
    mask = rio_features.rasterize(
        geoms, out_shape=shape, transform=transform, fill=0, all_touched=True, dtype=np.uint8
    )
    return mask


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run_dir', type=str, default='runs/gurdaspur_aoi_demo')
    ap.add_argument('--roads', type=str, default='Data/roads_aoi.geojson')
    ap.add_argument('--rivers', type=str, default='Data/osm_rivers_aoi.geojson')
    ap.add_argument('--drains', type=str, default='Data/osm_drains_aoi.geojson')
    ap.add_argument('--canals', type=str, default='Data/osm_canals_aoi.geojson')
    ap.add_argument('--structures', type=str, default='Data/osm_structures_aoi.geojson')
    ap.add_argument('--depth_threshold_m', type=float, default=0.2)
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    final_tif = run_dir / 'final_h.tif'
    if not final_tif.exists():
        raise SystemExit(f"Missing {final_tif}")
    roads_path = Path(args.roads)
    if not roads_path.exists():
        raise SystemExit(f"Missing {roads_path}")

    with rio.open(final_tif) as ds:
        h = ds.read(1).astype(float)
        transform = ds.transform
        crs = ds.crs
        dx = abs(ds.transform.a)
        dy = abs(ds.transform.e)
        # rasterize roads
        road_mask = rasterize_roads(roads_path, transform, h.shape, crs)

    flooded = (h >= float(args.depth_threshold_m)) & (road_mask > 0)
    # Approx flooded length: count of road pixels intersecting flooded × pixel length scale proxy
    # Use average of dx, dy as a rough per-pixel length proxy for linework
    pixel_len = 0.5 * (dx + dy)
    flooded_len_m = float(np.sum(flooded) * pixel_len)
    flooded_len_km = flooded_len_m / 1000.0
    total_road_len_m = float(np.sum(road_mask > 0) * pixel_len)
    total_road_len_km = total_road_len_m / 1000.0

    log_lines = [
        f"Road flooded length (h>={args.depth_threshold_m:.2f} m): {flooded_len_km:.3f} km / {total_road_len_km:.3f} km",
        f"Pixel length proxy used per road cell: {pixel_len:.3f} m",
    ]
    print(log_lines[0])

    # Overlay figure
    vmax = max(0.2, float(np.nanpercentile(h, 99)))
    fig, ax = plt.subplots(figsize=(7,6))
    im = ax.imshow(h.T, origin='lower', cmap='viridis', vmin=0.0, vmax=vmax)
    # draw roads as mask contours
    ax.contour((road_mask>0).T, levels=[0.5], colors='white', linewidths=0.6, alpha=0.8)
    ax.contour(flooded.T, levels=[0.5], colors='red', linewidths=0.8, alpha=0.9)
    # optional hydro layers
    for path, color, lw in [
        (Path(args.rivers), 'cyan', 1.5),
        (Path(args.drains), 'deepskyblue', 1.5),
        (Path(args.canals), 'dodgerblue', 1.5),
        (Path(args.structures), 'yellow', 1.8),
    ]:
        if path.exists():
            try:
                with fiona.open(path, 'r') as src:
                    src_crs = src.crs_wkt or src.crs or 'EPSG:4326'
                    transformer = Transformer.from_crs(src_crs, crs, always_xy=True)
                    for feat in src:
                        geom = shp_shape(feat['geometry'])
                        geom_t = shp_transform(lambda x, y, z=None: transformer.transform(x, y), geom)
                        gtype = geom_t.geom_type
                        if gtype in ("Point", "MultiPoint"):
                            # draw points explicitly so they are visible at coarse grids
                            if gtype == "Point":
                                xs = [geom_t.x]; ys = [geom_t.y]
                            else:
                                xs = [p.x for p in geom_t.geoms]; ys = [p.y for p in geom_t.geoms]
                            # map world coords to pixel indices
                            with rio.open(final_tif) as _ds:
                                ij = [_ds.index(x, y) for x, y in zip(xs, ys)]
                            # ij -> (row, col); plot in (col, row) as image axes
                            cols = [c for r, c in ij]; rows = [r for r, c in ij]
                            ax.scatter(cols, rows, s=40, c=color, edgecolors='black', linewidths=0.6, marker='o', alpha=0.95, zorder=5)
                        else:
                            # rasterize and contour lines/polygons
                            mask = rio_features.rasterize([(geom_t, 1)], out_shape=h.shape, transform=transform, fill=0, all_touched=True)
                            ax.contour((mask>0).T, levels=[0.5], colors=color, linewidths=lw, alpha=0.95, zorder=4)
            except Exception:
                pass
    cbar = fig.colorbar(im, ax=ax, label='Depth (m)')
    ax.set_title('AOI: Depth; roads white, flooded red; rivers/drains/canals cyan/blue; structures yellow')
    ax.set_xlabel('i (cells)')
    ax.set_ylabel('j (cells)')
    fig.tight_layout()
    out_png = run_dir / 'overlay_roads.png'
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"Saved {out_png}")

    log_path = run_dir / 'overlay_roads.log'
    try:
        with log_path.open('w', encoding='utf-8') as f:
            for line in log_lines:
                f.write(line + "\n")
            f.write(f"Saved overlay: {out_png}\n")
    except Exception:
        pass


if __name__ == '__main__':
    main()


