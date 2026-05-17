#!/usr/bin/env python3
"""
Export KMZ with ground overlays and vector layers for Google Earth.

Creates runs/gurdaspur_kmz_export/dashboard.kmz
"""

from __future__ import annotations

import argparse
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET
import rasterio as rio
from pyproj import Transformer


def ground_overlay_kml(png_path: Path, tif_ref: Path, name: str) -> str:
    with rio.open(tif_ref) as ds:
        transform = ds.transform
        crs = ds.crs
        width, height = ds.width, ds.height
        x0, y0 = transform * (0, 0)
        x1, y1 = transform * (width, height)
    # Transform bounds to WGS84
    try:
        tx = Transformer.from_crs(crs, 'EPSG:4326', always_xy=True)
        west, south = tx.transform(min(x0, x1), min(y0, y1))
        east, north = tx.transform(max(x0, x1), max(y0, y1))
    except Exception:
        # Fallback: assume already WGS84
        west, east = min(x0, x1), max(x0, x1)
        south, north = min(y0, y1), max(y0, y1)
    kml = f"""
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>{name}</name>
    <GroundOverlay>
      <name>{name}</name>
      <Icon>
        <href>{png_path.name}</href>
      </Icon>
      <LatLonBox>
        <north>{north}</north>
        <south>{south}</south>
        <east>{east}</east>
        <west>{west}</west>
      </LatLonBox>
    </GroundOverlay>
  </Document>
</kml>
""".strip()
    return kml


def main() -> None:
    ap = argparse.ArgumentParser(description='Export KMZ dashboard')
    ap.add_argument('--export_dir', type=str, default='runs/gurdaspur_kmz_export')
    ap.add_argument('--baseline_png', type=str, default='runs/gurdaspur_aoi12_tuned_couplers/overlay_roads.png')
    ap.add_argument('--baseline_tif', type=str, default='runs/gurdaspur_aoi12_tuned_couplers/final_h.tif')
    ap.add_argument('--selected_png', type=str, default='runs/gurdaspur_aoi12_selected/overlay_roads.png')
    ap.add_argument('--selected_tif', type=str, default='runs/gurdaspur_aoi12_selected/final_h.tif')
    ap.add_argument('--agent_png', type=str, default='', help='Optional third overlay PNG')
    ap.add_argument('--agent_tif', type=str, default='', help='Optional third overlay TIF reference')
    args = ap.parse_args()

    export_dir = Path(args.export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    kmz = export_dir / 'dashboard.kmz'

    # Prepare KML strings
    kml_baseline = ground_overlay_kml(Path(args.baseline_png), Path(args.baseline_tif), 'Baseline')
    kml_selected = ground_overlay_kml(Path(args.selected_png), Path(args.selected_tif), 'Selected')
    kml_agent = None
    if args.agent_png and args.agent_tif and Path(args.agent_png).exists() and Path(args.agent_tif).exists():
        kml_agent = ground_overlay_kml(Path(args.agent_png), Path(args.agent_tif), 'Agent Final')

    # Package into KMZ
    with zipfile.ZipFile(kmz, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('baseline.kml', kml_baseline)
        z.write(args.baseline_png, arcname=Path(args.baseline_png).name)
        z.writestr('selected.kml', kml_selected)
        z.write(args.selected_png, arcname=Path(args.selected_png).name)
        if kml_agent:
            z.writestr('agent.kml', kml_agent)
            z.write(args.agent_png, arcname=Path(args.agent_png).name)
    print('Saved', kmz)


if __name__ == '__main__':
    main()


