#!/usr/bin/env python3
"""
Select a square AOI around the DEM center for a target area (km^2),
derive its WGS84 bbox, and fetch AOI roads/POIs via Overpass.

Outputs:
- Prints recommended pb_cli.py arguments for a CPU DW-FV run on this AOI
- Writes Data/roads_aoi.geojson and Data/pois_aoi.geojson

Dependencies: rasterio, pyproj, requests (requests used by fetch_osm_layers)
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Tuple

import rasterio as rio
from pyproj import Transformer


def compute_aoi_window(
    dem_path: Path, target_area_km2: float, upsample: int
) -> tuple[int, int, int, int, float, float, any, any]:
    """
    Returns (col0, row0, nx_win, ny_win, dx_m, dy_m, transform_window, crs)
    nx_win, ny_win are DEM pixels BEFORE upsampling.
    """
    with rio.open(dem_path) as ds:
        width, height = ds.width, ds.height
        dx_m, dy_m = ds.res
        dx_m = float(abs(dx_m))
        dy_m = float(abs(dy_m))

        # target side length (m) of square AOI
        side_m = (target_area_km2 * 1_000_000.0) ** 0.5
        # window size in DEM pixels (before upsample)
        nx_win = max(10, int(round(side_m / dx_m)))
        ny_win = max(10, int(round(side_m / dy_m)))

        # center on DEM center
        col0 = max(0, width // 2 - nx_win // 2)
        row0 = max(0, height // 2 - ny_win // 2)
        col0 = int(max(0, min(col0, width - nx_win)))
        row0 = int(max(0, min(row0, height - ny_win)))

        window = rio.windows.Window(col_off=col0, row_off=row0, width=nx_win, height=ny_win)
        transform_window = ds.window_transform(window)
        crs = ds.crs
    return col0, row0, nx_win, ny_win, dx_m / max(1, upsample), dy_m / max(1, upsample), transform_window, crs


def window_bounds_lonlat(transform, crs, nx_win: int, ny_win: int) -> Tuple[float, float, float, float]:
    # get UTM bounds
    x0, y0 = transform * (0, 0)
    x1, y1 = transform * (nx_win, ny_win)
    xmin, xmax = sorted([x0, x1])
    ymin, ymax = sorted([y0, y1])

    # to WGS84
    transformer = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    w0, s0 = transformer.transform(xmin, ymin)
    w1, n1 = transformer.transform(xmax, ymax)
    south = min(s0, n1)
    north = max(s0, n1)
    west = min(w0, w1)
    east = max(w0, w1)
    return south, west, north, east


def main() -> None:
    ap = argparse.ArgumentParser(description="AOI selection and OSM clip for Gurdaspur demo")
    ap.add_argument("--dem", type=str, default="Data/GDSP_DEM_utm43n_100m.tif")
    ap.add_argument("--area_km2", type=float, default=5.0, help="Target square AOI area in km^2")
    ap.add_argument("--upsample", type=int, default=2, help="DEM upsample factor for the simulation")
    ap.add_argument("--out-roads", type=str, default="Data/roads_aoi.geojson")
    ap.add_argument("--out-pois", type=str, default="Data/pois_aoi.geojson")
    args = ap.parse_args()

    dem_path = Path(args.dem)
    if not dem_path.exists():
        raise SystemExit(f"DEM not found: {dem_path}")

    col0, row0, nx_win, ny_win, dx_sim, dy_sim, win_transform, win_crs = compute_aoi_window(
        dem_path, target_area_km2=float(args.area_km2), upsample=int(args.upsample)
    )
    south, west, north, east = window_bounds_lonlat(win_transform, win_crs, nx_win, ny_win)

    print("AOI (DEM window):")
    print(f"  col0={col0}, row0={row0}, nx_win={nx_win}, ny_win={ny_win}, upsample={int(args.upsample)}")
    print("AOI (meters per cell at sim grid):")
    print(f"  dx_sim={dx_sim:.1f} m, dy_sim={dy_sim:.1f} m")
    print("AOI (WGS84 bbox):")
    print(f"  south,west,north,east = {south:.6f},{west:.6f},{north:.6f},{east:.6f}")

    # Fetch clipped OSM layers using existing utility
    bbox = f"{south},{west},{north},{east}"
    print("Fetching AOI roads/POIs via Overpass ...")
    import subprocess, sys
    cmd = [
        sys.executable,
        str(Path(__file__).resolve().parent / "fetch_osm_layers.py"),
        "--bbox",
        bbox,
        "--out-roads",
        str(args.out_roads),
        "--out-pois",
        str(args.out_pois),
    ]
    subprocess.check_call(cmd)

    # Recommend pb_cli arguments for a quick CPU DW-FV run
    print("\nRecommended pb_cli.py command:")
    # nx/ny here are the DEM window pixels BEFORE upsample
    rec = (
        f"python Runners/pb_cli.py "
        f"--dem {dem_path} "
        f"--out runs/gurdaspur_aoi_demo "
        f"--nx {nx_win} --ny {ny_win} --upsample {int(args.upsample)} "
        f"--tile_col0 {col0} --tile_row0 {row0} "
        f"--rivers Data/osm_rivers.geojson "
        f"--lulc Data/LULC2_utm43n_100m.tif "
        f"--rain_mm_per_hour 20 --t_hours 1.5 --h_init_m 0.0 --plot_vmax 0.0"
    )
    print(rec)


if __name__ == "__main__":
    main()




