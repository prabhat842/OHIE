#!/usr/bin/env python3
"""
Select top road×channel crossings under a budget using a simple benefit proxy
and write selected culvert face segments as WGS84 GeoJSON.

Benefit proxy per crossing c:
  score(c) = mean_depth_in_window × road_pixels_in_window

Spacing: enforce a minimum spacing in meters between selected sites.

Inputs:
- depth_tif: baseline final_h.tif (defines grid, transform, CRS)
- roads: roads_aoi.geojson (WGS84)
- channels: list of channel vectors (drains/canals/culverts) (WGS84)

Outputs:
- out_geojson: line segments across selected faces (WGS84)
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

import numpy as np
import rasterio as rio
from rasterio import features as rio_features
import fiona
from shapely.geometry import shape as shp_shape, mapping as shp_mapping
from shapely.ops import transform as shp_transform
from shapely.strtree import STRtree
from shapely.geometry import Point as ShpPoint, LineString as ShpLine
from pyproj import Transformer
import json


def rasterize_lines(path: Path, transform, crs, shape) -> np.ndarray:
    with fiona.open(path, 'r') as src:
        src_crs = src.crs_wkt or src.crs or 'EPSG:4326'
        tx = Transformer.from_crs(src_crs, crs, always_xy=True)
        geoms = []
        # Estimate pixel size (meters) to buffer thin lines so crossings overlap on-grid
        try:
            import math
            px = abs(transform.a)
            py = abs(transform.e)
            buf = 0.8 * max(px, py)
            if not math.isfinite(buf) or buf <= 0:
                buf = 1.0
        except Exception:
            buf = 1.0
        for feat in src:
            geom = shp_shape(feat['geometry'])
            geom_t = shp_transform(lambda x, y, z=None: tx.transform(x, y), geom)
            # Buffer to ensure at least one shared pixel where lines cross
            try:
                geom_b = geom_t.buffer(buf)
            except Exception:
                geom_b = geom_t
            geoms.append((geom_b, 1))
    return rio_features.rasterize(geoms, out_shape=shape, transform=transform, fill=0, all_touched=True, dtype=np.uint8)


def main() -> None:
    ap = argparse.ArgumentParser(description='Select top crossings for culverts under budget')
    ap.add_argument('--depth_tif', type=str, required=True)
    ap.add_argument('--roads', type=str, required=True)
    ap.add_argument('--channels', type=str, nargs='+', required=True)
    ap.add_argument('--budget', type=float, default=500000.0)
    ap.add_argument('--unit_cost', type=float, default=25000.0)
    ap.add_argument('--min_spacing_m', type=float, default=300.0)
    ap.add_argument('--win_cells', type=int, default=3, help='Radius (cells) for local window')
    ap.add_argument('--out_geojson', type=str, default='Data/selected_culverts.geojson')
    args = ap.parse_args()

    with rio.open(args.depth_tif) as ds:
        h = ds.read(1).astype(float)
        transform = ds.transform
        crs = ds.crs
        dx = abs(ds.transform.a)
        dy = abs(ds.transform.e)
        height, width = h.shape

    # Masks
    road_mask = rasterize_lines(Path(args.roads), transform, crs, h.shape)
    chan_mask = np.zeros_like(road_mask, dtype=np.uint8)
    for cpath in args.channels:
        p = Path(cpath)
        if p.exists():
            chan_mask = np.maximum(chan_mask, rasterize_lines(p, transform, crs, h.shape))

    cross = (road_mask > 0) & (chan_mask > 0)
    ii, jj = np.where(cross)

    # Score crossings
    R = int(max(1, args.win_cells))
    scores = []
    for i, j in zip(ii.tolist(), jj.tolist()):
        i0 = max(0, i - R); i1 = min(height, i + R + 1)
        j0 = max(0, j - R); j1 = min(width, j + R + 1)
        win_h = h[i0:i1, j0:j1]
        win_r = road_mask[i0:i1, j0:j1]
        score = float(np.nanmean(win_h) * np.sum(win_r > 0))
        scores.append((score, i, j))
    scores.sort(reverse=True)

    # Spacing constraint using planar distances in grid meters
    selected: List[tuple[int,int]] = []
    min_d2 = (args.min_spacing_m ** 2) / max(1e-9, (dx*dx))  # in (i-units)^2 approx; assume dx≈dy
    for score, i, j in scores:
        if args.budget < args.unit_cost:
            break
        ok = True
        for (si, sj) in selected:
            di = (i - si); dj = (j - sj)
            if (di*di + dj*dj) * (dx*dx) < (args.min_spacing_m ** 2):
                ok = False; break
        if ok:
            selected.append((i, j))
            args.budget -= args.unit_cost

    # Build tiny face segments across steepest gradient
    feats = []
    to_wgs84 = Transformer.from_crs(crs, 'EPSG:4326', always_xy=True)
    for i, j in selected:
        sx = 0.0; sy = 0.0
        if 0 < i < height-1:
            sx = abs((h[i+1, j] - h[i-1, j]) / max(1e-9, 2*dx))
        if 0 < j < width-1:
            sy = abs((h[i, j+1] - h[i, j-1]) / max(1e-9, 2*dy))
        # pixel center coords
        x0, y0 = transform * (j + 0.5, i + 0.5)
        if sx >= sy and i < height-1:
            x1, y1 = transform * (j + 0.5, i + 1 + 0.5)
        else:
            x1, y1 = transform * (j + 1 + 0.5, i + 0.5)
        lon0, lat0 = to_wgs84.transform(x0, y0)
        lon1, lat1 = to_wgs84.transform(x1, y1)
        feats.append({'type':'Feature','geometry':{'type':'LineString','coordinates':[[lon0,lat0],[lon1,lat1]]},'properties':{'structure':'culvert'}})

    out = {'type':'FeatureCollection','features':feats}
    Path(args.out_geojson).write_text(json.dumps(out))
    print('Wrote', args.out_geojson, 'selected=', len(feats))


if __name__ == '__main__':
    main()




