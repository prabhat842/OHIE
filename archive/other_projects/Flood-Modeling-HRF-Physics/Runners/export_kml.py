#!/usr/bin/env python3
"""
Export KMLs:
- Raster: given a GeoTIFF (final_h.tif) and a PNG overlay, produce a GroundOverlay KML.
- Vectors: convert GeoJSON (WGS84) to simple KML placemarks.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import json
import rasterio as rio
from pyproj import Transformer
from shutil import copy2


def raster_to_kml(png_path: Path, tif_ref: Path, kml_out: Path, name: str) -> None:
    with rio.open(tif_ref) as ds:
        transform = ds.transform
        crs = ds.crs
        width, height = ds.width, ds.height
        x0, y0 = transform * (0, 0)
        x1, y1 = transform * (width, height)
    try:
        tx = Transformer.from_crs(crs, 'EPSG:4326', always_xy=True)
        west, south = tx.transform(min(x0, x1), min(y0, y1))
        east, north = tx.transform(max(x0, x1), max(y0, y1))
    except Exception:
        west, east = min(x0, x1), max(x0, x1)
        south, north = min(y0, y1), max(y0, y1)
    # Ensure the PNG sits next to the KML so Google Earth can resolve the href
    target_png = kml_out.parent / png_path.name
    try:
        if not target_png.exists():
            copy2(png_path, target_png)
    except Exception:
        pass

    kml = f"""
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>{name}</name>
    <GroundOverlay>
      <name>{name}</name>
      <Icon><href>{target_png.name}</href></Icon>
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
    kml_out.write_text(kml)


def geojson_to_kml(gj_path: Path, kml_out: Path, style: str = '') -> None:
    if not gj_path.exists():
        kml_out.write_text('<kml xmlns="http://www.opengis.net/kml/2.2"><Document/></kml>')
        return
    gj = json.loads(gj_path.read_text())
    styles = {
        'roads': '<Style id="roads"><LineStyle><color>ffffffff</color><width>2</width></LineStyle></Style>',
        'rivers': '<Style id="rivers"><LineStyle><color>ff00ffff</color><width>2</width></LineStyle></Style>',
        'drains': '<Style id="drains"><LineStyle><color>ffffa500</color><width>2</width></LineStyle></Style>',
        'canals': '<Style id="canals"><LineStyle><color>ffff7f00</color><width>2</width></LineStyle></Style>',
        'culverts': '<Style id="culverts"><LineStyle><color>ff00ffff</color><width>3</width></LineStyle></Style>',
        'pois': '<Style id="pois"><IconStyle><color>ff0000ff</color><scale>1.1</scale><Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon></IconStyle></Style>'
    }
    style_tag = styles.get(style, '')
    placemarks = []
    for feat in gj.get('features', []):
        geom = feat.get('geometry', {})
        props = feat.get('properties') or {}
        name = props.get('name') or props.get('structure') or ''
        t = geom.get('type')
        coords = geom.get('coordinates')
        if t == 'LineString':
            pts = ' '.join([f"{x},{y},0" for x, y in coords])
            placemarks.append(f"<Placemark><name>{name}</name><styleUrl>#{style}</styleUrl><LineString><tessellate>1</tessellate><coordinates>{pts}</coordinates></LineString></Placemark>")
        elif t == 'MultiLineString':
            for ls in coords:
                pts = ' '.join([f"{x},{y},0" for x, y in ls])
                placemarks.append(f"<Placemark><name>{name}</name><styleUrl>#{style}</styleUrl><LineString><tessellate>1</tessellate><coordinates>{pts}</coordinates></LineString></Placemark>")
        elif t == 'Point':
            if isinstance(coords, (list, tuple)) and len(coords) >= 2:
                placemarks.append(f"<Placemark><name>{name}</name><styleUrl>#{style}</styleUrl><Point><coordinates>{coords[0]},{coords[1]},0</coordinates></Point></Placemark>")
    kml = f"""
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    {style_tag}
    {''.join(placemarks)}
  </Document>
</kml>
""".strip()
    kml_out.write_text(kml)


def main() -> None:
    ap = argparse.ArgumentParser(description='Export individual KMLs')
    ap.add_argument('--export_dir', type=str, default='runs/gurdaspur_kmz_export')
    ap.add_argument('--baseline_png', type=str, required=True)
    ap.add_argument('--baseline_tif', type=str, required=True)
    ap.add_argument('--selected_png', type=str, required=True)
    ap.add_argument('--selected_tif', type=str, required=True)
    ap.add_argument('--roads', type=str, required=True)
    ap.add_argument('--rivers', type=str, required=True)
    ap.add_argument('--drains', type=str, required=True)
    ap.add_argument('--canals', type=str, required=True)
    ap.add_argument('--pois', type=str, required=True)
    ap.add_argument('--structures', type=str, required=True)
    args = ap.parse_args()

    out = Path(args.export_dir); out.mkdir(parents=True, exist_ok=True)

    raster_to_kml(Path(args.baseline_png), Path(args.baseline_tif), out / 'baseline_overlay.kml', 'Baseline')
    raster_to_kml(Path(args.selected_png), Path(args.selected_tif), out / 'selected_overlay.kml', 'Selected (Budgeted)')

    geojson_to_kml(Path(args.roads), out / 'roads.kml', 'roads')
    geojson_to_kml(Path(args.rivers), out / 'rivers.kml', 'rivers')
    geojson_to_kml(Path(args.drains), out / 'drains.kml', 'drains')
    geojson_to_kml(Path(args.canals), out / 'canals.kml', 'canals')
    geojson_to_kml(Path(args.pois), out / 'pois.kml', 'pois')
    geojson_to_kml(Path(args.structures), out / 'structures.kml', 'culverts')
    print('KMLs saved to', out)


if __name__ == '__main__':
    main()


