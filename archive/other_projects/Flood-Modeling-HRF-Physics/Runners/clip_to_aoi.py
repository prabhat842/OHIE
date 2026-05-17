#!/usr/bin/env python3
"""
Clip input GeoJSON layers to the AOI defined by a georeferenced raster footprint (final_h.tif).

Inputs:
- --raster runs/.../final_h.tif (defines AOI extent and CRS)
- --layers Data/osm_rivers.geojson ... (any number of GeoJSONs)

Outputs:
- For each input, writes <basename>_aoi.geojson next to the input unless --out-dir is given.

Dependencies: fiona, shapely, pyproj, rasterio
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

import rasterio as rio
from shapely.geometry import box as shp_box, shape as shp_shape, mapping as shp_mapping
from shapely.ops import transform as shp_transform
from pyproj import Transformer
import fiona


def main() -> None:
    ap = argparse.ArgumentParser(description="Clip GeoJSON layers to raster AOI")
    ap.add_argument('--raster', type=str, required=True)
    ap.add_argument('--layers', type=str, nargs='+', required=True)
    ap.add_argument('--out-dir', type=str, default='')
    args = ap.parse_args()

    raster_path = Path(args.raster)
    if not raster_path.exists():
        raise SystemExit(f"Raster not found: {raster_path}")

    with rio.open(raster_path) as ds:
        transform = ds.transform
        crs = ds.crs
        width, height = ds.width, ds.height
        x0, y0 = transform * (0, 0)
        x1, y1 = transform * (width, height)
        xmin, xmax = sorted([x0, x1])
        ymin, ymax = sorted([y0, y1])
        aoi_poly = shp_box(xmin, ymin, xmax, ymax)
        to_wgs84 = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)

    out_dir = Path(args.out_dir) if args.out_dir else None

    for layer in args.layers:
        in_path = Path(layer)
        if not in_path.exists():
            print(f"Skip missing: {in_path}")
            continue
        with fiona.open(in_path, 'r') as src:
            src_crs = src.crs_wkt or src.crs
            if not src_crs:
                src_crs = "EPSG:4326"
            transformer = Transformer.from_crs(src_crs, crs, always_xy=True)
            feats_out = []
            for feat in src:
                try:
                    geom = shp_shape(feat['geometry'])
                    geom_t = shp_transform(lambda x, y, z=None: transformer.transform(x, y), geom)
                    inter = geom_t.intersection(aoi_poly)
                    if inter.is_empty:
                        continue
                    props = dict(feat.get('properties') or {})
                    # Write in WGS84 so it renders everywhere (geojson.io/QGIS)
                    inter_wgs = shp_transform(lambda x, y, z=None: to_wgs84.transform(x, y), inter)
                    feats_out.append({"type":"Feature","geometry":shp_mapping(inter_wgs),"properties":props})
                except Exception:
                    continue
        if not feats_out:
            print(f"No features after clip: {in_path}")
        base = in_path.stem
        out_name = f"{base}_aoi.geojson"
        out_path = (out_dir / out_name) if out_dir else (in_path.parent / out_name)
        out = {"type":"FeatureCollection","features":feats_out}
        out_path.write_text(__import__('json').dumps(out))
        print(f"Wrote {out_path} ({len(feats_out)} features)")


if __name__ == '__main__':
    main()
