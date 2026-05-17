#!/usr/bin/env python3
"""
Fetch OSM roads and POIs for an AOI and write GeoJSON layers.

Defaults:
- AOI derived from Data/osm_waterways.geojson (assumed WGS84 lon/lat). If missing, --bbox is required.
- Outputs: Data/roads.geojson and Data/pois.geojson

Dependencies: requests (install: pip install requests)
This script intentionally avoids heavy geospatial deps.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any, Dict, Iterable, List, Tuple

try:
    import requests  # type: ignore
except Exception as exc:  # pragma: no cover
    print("ERROR: The 'requests' package is required. Install with: pip install requests", file=sys.stderr)
    raise


OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def read_bbox_from_waterways_geojson(geojson_path: str) -> Tuple[float, float, float, float]:
    with open(geojson_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if data.get("type") != "FeatureCollection":
        raise ValueError("Expected a GeoJSON FeatureCollection")

    min_lon = float("inf")
    min_lat = float("inf")
    max_lon = float("-inf")
    max_lat = float("-inf")

    def update_bounds(coords: Iterable):
        nonlocal min_lon, min_lat, max_lon, max_lat
        for coord in coords:
            # coord could be nested
            if isinstance(coord, (list, tuple)) and len(coord) == 2 and all(isinstance(v, (int, float)) for v in coord):
                lon, lat = float(coord[0]), float(coord[1])
                min_lon = min(min_lon, lon)
                min_lat = min(min_lat, lat)
                max_lon = max(max_lon, lon)
                max_lat = max(max_lat, lat)
            else:
                update_bounds(coord)  # recurse

    for feature in data.get("features", []):
        geom = feature.get("geometry") or {}
        gtype = geom.get("type")
        coords = geom.get("coordinates")
        if not coords:
            continue
        if gtype in {"Point"}:
            update_bounds([coords])
        elif gtype in {"MultiPoint", "LineString"}:
            update_bounds(coords)
        elif gtype in {"MultiLineString", "Polygon"}:
            update_bounds(coords)
        elif gtype in {"MultiPolygon"}:
            update_bounds(coords)

    if any(v in (float("inf"), float("-inf")) for v in (min_lon, min_lat, max_lon, max_lat)):
        raise ValueError("Could not compute bounds from waterways GeoJSON")

    # Sanity: assume WGS84 lon/lat; if extreme values, warn
    if max(abs(min_lon), abs(max_lon), abs(min_lat), abs(max_lat)) > 180:
        raise ValueError(
            "Waterways GeoJSON does not look like WGS84 lon/lat. Provide --bbox south,west,north,east."
        )

    return (min_lat, min_lon, max_lat, max_lon)  # south, west, north, east


def fetch_overpass(query: str, max_tries: int = 5, sleep_s: float = 2.0) -> Dict[str, Any]:
    last_err: Exception | None = None
    for attempt in range(1, max_tries + 1):
        try:
            resp = requests.post(OVERPASS_URL, data={"data": query}, timeout=300)
            if resp.status_code == 429 or resp.status_code == 504:
                # Too many requests / gateway timeout
                time.sleep(sleep_s * attempt)
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # pragma: no cover
            last_err = exc
            time.sleep(sleep_s * attempt)
    if last_err is not None:
        raise last_err
    raise RuntimeError("Overpass fetch failed for unknown reasons")


def build_roads_query(south: float, west: float, north: float, east: float) -> str:
    highway_filter = "|".join(
        [
            "motorway",
            "trunk",
            "primary",
            "secondary",
            "tertiary",
            "residential",
            "unclassified",
            "service",
            "living_street",
            "track",
            "path",
            "footway",
            "cycleway",
        ]
    )
    return f"""
[out:json][timeout:180];
(
  way["highway"~"^{highway_filter}$"]({south},{west},{north},{east});
);
out tags geom;
""".strip()


def build_pois_query(south: float, west: float, north: float, east: float) -> str:
    return f"""
[out:json][timeout:240];
(
  nwr["amenity"]({south},{west},{north},{east});
  nwr["shop"]({south},{west},{north},{east});
  nwr["healthcare"]({south},{west},{north},{east});
  nwr["emergency"]({south},{west},{north},{east});
  nwr["public_transport"]({south},{west},{north},{east});
  nwr["tourism"]({south},{west},{north},{east});
  nwr["office"]({south},{west},{north},{east});
  nwr["government"]({south},{west},{north},{east});
  nwr["police"]({south},{west},{north},{east});
  nwr["fire_station"]({south},{west},{north},{east});
  nwr["fuel"]({south},{west},{north},{east});
  nwr["power"="substation"]({south},{west},{north},{east});
  nwr["building"~"school|hospital|college|university"]({south},{west},{north},{east});
);
out tags geom;
""".strip()


def elements_to_roads_geojson(elements: List[Dict[str, Any]]) -> Dict[str, Any]:
    features: List[Dict[str, Any]] = []
    for el in elements:
        if el.get("type") != "way":
            continue
        tags = el.get("tags", {})
        if "highway" not in tags:
            continue
        geom = el.get("geometry")
        if not geom:
            continue
        coords = [[pt["lon"], pt["lat"]] for pt in geom if "lon" in pt and "lat" in pt]
        if len(coords) < 2:
            continue
        feature = {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {
                "id": el.get("id"),
                **tags,
            },
        }
        features.append(feature)
    return {"type": "FeatureCollection", "features": features}


def _centroid_lonlat(coords: List[List[float]]) -> Tuple[float, float]:
    # Simple mean centroid sufficient for small AOIs
    if not coords:
        return (0.0, 0.0)
    sum_lon = 0.0
    sum_lat = 0.0
    n = 0
    for lon, lat in coords:
        sum_lon += float(lon)
        sum_lat += float(lat)
        n += 1
    return (sum_lon / n, sum_lat / n)


def elements_to_pois_geojson(elements: List[Dict[str, Any]]) -> Dict[str, Any]:
    features: List[Dict[str, Any]] = []

    def is_poi(tags: Dict[str, Any]) -> bool:
        return any(
            key in tags
            for key in (
                "amenity",
                "shop",
                "healthcare",
                "emergency",
                "public_transport",
                "tourism",
                "office",
                "government",
                "police",
                "fire_station",
                "fuel",
                "building",
                "power",
            )
        )

    for el in elements:
        tags = el.get("tags", {})
        if not tags or not is_poi(tags):
            continue

        if el.get("type") == "node":
            lat = el.get("lat")
            lon = el.get("lon")
            if lat is None or lon is None:
                continue
            geometry = {"type": "Point", "coordinates": [float(lon), float(lat)]}
        else:
            geom = el.get("geometry")
            if not geom:
                # Fallback to center if available
                center = el.get("center")
                if center and "lon" in center and "lat" in center:
                    geometry = {"type": "Point", "coordinates": [center["lon"], center["lat"]]}
                else:
                    continue
            else:
                coords = [[pt["lon"], pt["lat"]] for pt in geom if "lon" in pt and "lat" in pt]
                lon, lat = _centroid_lonlat(coords)
                geometry = {"type": "Point", "coordinates": [lon, lat]}

        feature = {
            "type": "Feature",
            "geometry": geometry,
            "properties": {
                "id": el.get("id"),
                **tags,
            },
        }
        features.append(feature)

    return {"type": "FeatureCollection", "features": features}


def write_geojson(path: str, data: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch OSM roads and POIs as GeoJSON")
    parser.add_argument("--bbox", type=str, default=None, help="south,west,north,east in WGS84")
    parser.add_argument("--waterways", type=str, default="Data/osm_waterways.geojson", help="Path to waterways GeoJSON for AOI bounds (WGS84)")
    parser.add_argument("--out-roads", type=str, default="Data/roads.geojson")
    parser.add_argument("--out-pois", type=str, default="Data/pois.geojson")
    args = parser.parse_args()

    if args.bbox:
        try:
            south, west, north, east = [float(v.strip()) for v in args.bbox.split(",")]
        except Exception as exc:  # pragma: no cover
            raise SystemExit(f"Invalid --bbox. Expected 'south,west,north,east'. Error: {exc}")
    else:
        try:
            south, west, north, east = read_bbox_from_waterways_geojson(args.waterways)
        except FileNotFoundError:
            raise SystemExit("AOI not provided. Either supply --bbox or provide Data/osm_waterways.geojson")

    # Expand bbox slightly (1%) to catch edges
    lat_pad = (north - south) * 0.01
    lon_pad = (east - west) * 0.01
    south -= lat_pad
    north += lat_pad
    west -= lon_pad
    east += lon_pad

    print(f"Using bbox (south,west,north,east) = ({south:.6f},{west:.6f},{north:.6f},{east:.6f})")

    # Roads
    roads_query = build_roads_query(south, west, north, east)
    roads_data = fetch_overpass(roads_query)
    roads_geojson = elements_to_roads_geojson(roads_data.get("elements", []))
    write_geojson(args.out_roads, roads_geojson)
    print(f"Wrote {len(roads_geojson['features'])} roads to {args.out_roads}")

    # POIs
    pois_query = build_pois_query(south, west, north, east)
    pois_data = fetch_overpass(pois_query)
    pois_geojson = elements_to_pois_geojson(pois_data.get("elements", []))
    write_geojson(args.out_pois, pois_geojson)
    print(f"Wrote {len(pois_geojson['features'])} POIs to {args.out_pois}")


if __name__ == "__main__":
    main()




