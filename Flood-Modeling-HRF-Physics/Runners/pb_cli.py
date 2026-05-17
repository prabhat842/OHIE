#!/usr/bin/env python3
"""
Delhi runner (DW-FV) with CLI flags for DEM/LULC/rivers/drains and river stage schedule.

This restores the earlier Delhi interface so existing scenario scripts keep working.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Tuple, Optional, List

import numpy as np
import rasterio as rio
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.warp import reproject as rio_reproject
from rasterio import features as rio_features

try:
    import fiona  # type: ignore
    from shapely.geometry import shape as shp_shape  # type: ignore
    from shapely.ops import transform as shp_transform  # type: ignore
    from pyproj import Transformer  # type: ignore
    _HAS_VECTOR = True
except Exception:
    _HAS_VECTOR = False

import sys
from pathlib import Path

# Ensure project root on sys.path for module imports like Physics.hrf
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from Physics.hrf import Grid, SWEParams, ExponentialFilter, HRFSolver, FaceIndex, Culvert, Bridge, Weir
import json


def load_dem_tile_utm(dem_path: Path, nx: int, ny: int, upsample: int,
                      col0: Optional[int] = None, row0: Optional[int] = None) -> Tuple[np.ndarray, float, float, any, any]:
    with rio.open(dem_path) as ds:
        width, height = ds.width, ds.height
        if col0 is None or row0 is None:
            col0 = max(0, width // 2 - nx // 2)
            row0 = max(0, height // 2 - ny // 2)
        col0 = int(max(0, min(col0, width - nx)))
        row0 = int(max(0, min(row0, height - ny)))
        window = rio.windows.Window(col_off=col0, row_off=row0, width=nx, height=ny)
        if upsample > 1:
            out_h = int(window.height * upsample)
            out_w = int(window.width * upsample)
            arr = ds.read(1, window=window, out_shape=(out_h, out_w), resampling=Resampling.bilinear).astype(np.float64)
            base_transform = ds.window_transform(window)
            transform = base_transform * Affine.scale(1.0 / upsample, 1.0 / upsample)
        else:
            arr = ds.read(1, window=window).astype(np.float64)
            transform = ds.window_transform(window)
        crs = ds.crs
        dx_m, dy_m = ds.res
        dx_m = float(abs(dx_m)) / max(1, upsample)
        dy_m = float(abs(dy_m)) / max(1, upsample)
        return arr, dx_m, dy_m, transform, crs


def resample_raster_to_grid(src_path: Path, dst_transform, dst_crs, width: int, height: int,
                            resampling: Resampling = Resampling.bilinear,
                            band: int = 1) -> np.ndarray:
    """Reproject/resample a single band from src_path to the destination grid.

    Parameters
    - src_path: input raster path
    - dst_transform/dst_crs/width/height: target grid definition
    - resampling: rasterio.enums.Resampling
    - band: 1-based band index to read
    """
    with rio.open(src_path) as src:
        band = int(max(1, min(band, src.count or 1)))
        src_arr = src.read(band).astype(np.float64)
        dst_arr = np.zeros((height, width), dtype=np.float64)
        try:
            rio_reproject(
                source=src_arr,
                destination=dst_arr,
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=dst_transform,
                dst_crs=dst_crs,
                resampling=resampling,
            )
        except Exception:
            dst_arr = np.array(
                rio.open(src_path).read(band, out_shape=(height, width), resampling=resampling),
                dtype=np.float64,
            )
        return dst_arr


def _load_vector_buffers_geojson(path: Path, target_crs, buffer_m: float):
    """Fallback reader that supports standard FeatureCollection and line-delimited GeoJSON.

    Assumes input CRS is EPSG:4326 if not specified in the file.
    """
    try:
        text = path.read_text()
    except Exception:
        return []

    feats = []
    # Try full JSON first
    try:
        gj = json.loads(text)
        if isinstance(gj, dict) and 'features' in gj and isinstance(gj['features'], list) and len(gj['features']) > 0:
            feats = gj['features']
    except Exception:
        gj = None

    # If no features, try newline-delimited GeoJSON (one Feature per line)
    if not feats:
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    if obj.get('type') == 'Feature' and 'geometry' in obj:
                        feats.append(obj)
                    elif 'type' in obj and 'coordinates' in obj:
                        feats.append({'type': 'Feature', 'geometry': obj, 'properties': {}})
            except Exception:
                continue

    if not feats:
        return []

    transformer = Transformer.from_crs("EPSG:4326", target_crs, always_xy=True)
    geoms = []
    for feat in feats:
        try:
            geom = shp_shape(feat.get('geometry'))
            geom_t = shp_transform(lambda x, y, z=None: transformer.transform(x, y), geom)
            geoms.append(geom_t.buffer(buffer_m))
        except Exception:
            continue
    return geoms


def burn_rivers_into_bed(bed: np.ndarray, transform, crs, rivers_path: Path,
                         buffer_m: float = 30.0, carve_depth_m: float = 1.0) -> np.ndarray:
    if not _HAS_VECTOR or not rivers_path or not rivers_path.exists():
        return bed
    try:
        with fiona.open(rivers_path, 'r') as src:
            src_crs = src.crs_wkt or src.crs
            transformer = Transformer.from_crs(src_crs, crs, always_xy=True)
            geoms = []
            for feat in src:
                geom = shp_shape(feat["geometry"])  # LineString/MultiLineString
                geom_t = shp_transform(lambda x, y, z=None: transformer.transform(x, y), geom)
                geoms.append(geom_t.buffer(buffer_m))
        mask = rio_features.rasterize(
            ((g, 1) for g in geoms), out_shape=bed.shape, transform=transform,
            fill=0, all_touched=True, dtype=np.uint8
        )
        carved = bed - carve_depth_m * (mask.astype(np.float64))
        carved = carved - np.nanmin(carved)
        return carved
    except Exception:
        # Fallback: parse GeoJSON directly (assume EPSG:4326)
        geoms = _load_vector_buffers_geojson(rivers_path, crs, buffer_m)
        if not geoms:
            return bed
        mask = rio_features.rasterize(
            ((g, 1) for g in geoms), out_shape=bed.shape, transform=transform,
            fill=0, all_touched=True, dtype=np.uint8
        )
        carved = bed - carve_depth_m * (mask.astype(np.float64))
        carved = carved - np.nanmin(carved)
        return carved


def build_river_mask(shape: Tuple[int, int], transform, crs, rivers_path: Optional[Path],
                     buffer_m: float = 30.0) -> np.ndarray:
    if not _HAS_VECTOR or not rivers_path or not rivers_path.exists():
        return np.zeros(shape, dtype=np.uint8)
    try:
        with fiona.open(rivers_path, 'r') as src:
            src_crs = src.crs_wkt or src.crs
            transformer = Transformer.from_crs(src_crs, crs, always_xy=True)
            geoms = []
            for feat in src:
                geom = shp_shape(feat["geometry"])  # LineString/MultiLineString
                geom_t = shp_transform(lambda x, y, z=None: transformer.transform(x, y), geom)
                geoms.append(geom_t.buffer(buffer_m))
        mask = rio_features.rasterize(
            ((g, 1) for g in geoms), out_shape=shape, transform=transform,
            fill=0, all_touched=True, dtype=np.uint8
        )
        return mask
    except Exception:
        # Fallback: parse GeoJSON directly
        geoms = _load_vector_buffers_geojson(rivers_path, crs, buffer_m)
        if not geoms:
            return np.zeros(shape, dtype=np.uint8)
        mask = rio_features.rasterize(
            ((g, 1) for g in geoms), out_shape=shape, transform=transform,
            fill=0, all_touched=True, dtype=np.uint8
        )
        return mask


def build_infiltration_from_lulc(lulc_path: Optional[Path], dst_transform, dst_crs, width: int, height: int,
                                 infil_min: float = 5.0e-10, infil_max: float = 2.0e-8) -> Optional[np.ndarray]:
    if not lulc_path or not lulc_path.exists():
        return None
    try:
        arr = resample_raster_to_grid(lulc_path, dst_transform, dst_crs, width=width, height=height,
                                      resampling=Resampling.nearest)
        arr = np.nan_to_num(arr, nan=0.0)
        vmin = float(np.min(arr))
        vmax = float(np.max(arr))
        if vmax - vmin < 1e-6:
            return None
        norm = (arr - vmin) / (vmax - vmin)
        infil = infil_min + norm * (infil_max - infil_min)
        infil[arr == 0.0] = 1.0e-8
        return infil
    except Exception:
        return None


def parse_stage_points(spec: str) -> List[tuple]:
    parts = [p.strip() for p in str(spec).split(',') if p.strip()]
    out = []
    for p in parts:
        t_s, dz_s = p.split(':')
        out.append((float(t_s) * 3600.0, float(dz_s)))
    return sorted(out, key=lambda x: x[0])


def main():
    root = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description="Punjab DW-FV runner")
    ap.add_argument('--dem', type=str, default=str(root / 'Data_PB/dem_gurdaspur_utm43n_100m.tif'))
    ap.add_argument('--out', type=str, default=str(root / 'runs_final/gurdaspur_run_1'))
    ap.add_argument('--nx', type=int, default=300)
    ap.add_argument('--ny', type=int, default=300)
    ap.add_argument('--upsample', type=int, default=1)
    ap.add_argument('--rain_mm_per_hour', type=float, default=20.0)
    ap.add_argument('--rain_off', action='store_true')
    ap.add_argument('--rain_raster', type=str, default='')
    ap.add_argument('--infil_mps', type=float, default=1.0e-8)
    ap.add_argument('--lulc', type=str, default=str(root / 'Data_PB/lulc_gurdaspur_bhuvan_utm_100m.tif'))
    ap.add_argument('--rivers', type=str, default=str(root / 'Data_PB/osm_waterways.geojson'))
    ap.add_argument('--burn_buffer_m', type=float, default=40.0)
    ap.add_argument('--burn_depth_m', type=float, default=1.0)
    ap.add_argument('--t_hours', type=float, default=3.0)
    ap.add_argument('--river_stage_m', type=float, default=0.0)
    ap.add_argument('--river_line_rain_mmph', type=float, default=0.0)
    ap.add_argument('--stage_step_m', type=float, default=0.0)
    ap.add_argument('--stage_step_at_h', type=float, default=0.0)
    ap.add_argument('--stage_points', type=str, default='')
    ap.add_argument('--drains', type=str, default='')
    ap.add_argument('--drain_sink_mps', type=float, default=0.0)
    ap.add_argument('--canals', type=str, default='')
    ap.add_argument('--culverts', type=str, default='')
    ap.add_argument('--culverts_selected', type=str, default='')
    ap.add_argument('--roads', type=str, default='Data/roads_aoi.geojson')
    ap.add_argument('--culvert_area_m2', type=float, default=0.5)
    ap.add_argument('--bridge_free_area_m2', type=float, default=2.0)
    ap.add_argument('--bridge_press_area_m2', type=float, default=1.0)
    ap.add_argument('--channel_buffer_m', type=float, default=20.0)
    ap.add_argument('--channel_crest_h_m', type=float, default=0.15)
    ap.add_argument('--channel_n', type=float, default=0.030)
    ap.add_argument('--culverts_crossings_only', action='store_true')
    # Optional detention ponds (polygons in WGS84)
    ap.add_argument('--ponds', type=str, default='', help='GeoJSON polygons to depress as detention ponds (WGS84)')
    ap.add_argument('--pond_depth_m', type=float, default=0.5, help='Bed depression depth inside pond polygons')
    # QCIA design integration
    ap.add_argument('--qcia_design', type=str, default='', help='Path to QCIA design JSON (applies AI-selected interventions)')
    ap.add_argument('--h_init_m', type=float, default=0.0)
    ap.add_argument('--plot_vmax', type=float, default=0.0)
    ap.add_argument('--tile_col0', type=int, default=-1)
    ap.add_argument('--tile_row0', type=int, default=-1)
    # Numerical controls
    ap.add_argument('--h_min', type=float, default=1.0e-3, help='Minimum water depth clamp (m)')
    ap.add_argument('--sponge_width', type=int, default=0, help='Sponge layer width (cells)')
    ap.add_argument('--sponge_tau', type=float, default=180.0, help='Sponge relaxation timescale (s)')
    ap.add_argument('--cfl', type=float, default=0.15, help='CFL number for timestep selection')
    ap.add_argument('--dt_max', type=float, default=0.1, help='Maximum timestep (s)')
    args = ap.parse_args()

    dem_clip = Path(args.dem)
    lulc_raster = Path(args.lulc) if args.lulc else None
    drains_raster = Path(args.drains) if args.drains else None
    canals_raster = Path(args.canals) if args.canals else None
    culverts_raster = Path(args.culverts) if args.culverts else None
    culverts_selected = Path(args.culverts_selected) if args.culverts_selected else None
    roads_vector = Path(args.roads) if args.roads else None
    rivers_path = Path(args.rivers) if args.rivers else None
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    col0 = None if int(args.tile_col0) < 0 else int(args.tile_col0)
    row0 = None if int(args.tile_row0) < 0 else int(args.tile_row0)
    bed, dx_m, dy_m, win_transform, win_crs = load_dem_tile_utm(dem_clip, nx=int(args.nx), ny=int(args.ny), upsample=int(args.upsample), col0=col0, row0=row0)
    nx, ny = bed.shape
    bed = bed - np.nanmin(bed)
    bed = np.nan_to_num(bed, nan=np.nanmin(bed))

    # Burn rivers and build a mask
    river_mask = np.zeros_like(bed, dtype=np.uint8)
    if rivers_path and rivers_path.exists():
        bed = burn_rivers_into_bed(bed, win_transform, win_crs, rivers_path,
                                   buffer_m=max(args.burn_buffer_m, max(dx_m, dy_m) * 2.0),
                                   carve_depth_m=float(args.burn_depth_m))
        river_mask = build_river_mask(bed.shape, win_transform, win_crs, rivers_path,
                                      buffer_m=max(args.burn_buffer_m, max(dx_m, dy_m) * 2.0))

    # Grid and solver
    Lx = dx_m * nx
    Ly = dy_m * ny
    grid = Grid(nx=nx, ny=ny, Lx=Lx, Ly=Ly)
    prm = SWEParams(g=9.81, manning_n=0.06, h_min=float(args.h_min), cfl=float(args.cfl), vmax_guard_coef=0.7, dt_max=float(args.dt_max),
                    sponge_width=int(args.sponge_width), sponge_tau=float(args.sponge_tau))
    filt = ExponentialFilter(alpha=96.0, p=8)
    solver = HRFSolver(grid, prm, filt)
    solver.mode = "dw_fv"
    # Attach river mask for conservative routing of infrastructure outfalls
    try:
        solver.river_mask = river_mask.astype(np.uint8)
    except Exception:
        solver.river_mask = np.zeros((nx, ny), dtype=np.uint8)

    # Initial conditions
    h0 = np.full((nx, ny), float(args.h_init_m), dtype=np.float64)
    if float(args.river_stage_m) > 0.0 and np.any(river_mask):
        h0 = h0 + (river_mask.astype(np.float64) * float(args.river_stage_m))
    u0 = np.zeros_like(h0)
    v0 = np.zeros_like(h0)
    solver.initialize(h0, u0, v0)

    # Rain forcing
    rain_field = None
    rain_rate_mps = 0.0 if args.rain_off else (float(args.rain_mm_per_hour) / 1000.0) / 3600.0
    if args.rain_raster and not args.rain_off:
        try:
            rain_mm_h = resample_raster_to_grid(Path(args.rain_raster), win_transform, win_crs, width=ny, height=nx,
                                                resampling=Resampling.bilinear)
            rain_field = (rain_mm_h / 1000.0) / 3600.0
        except Exception:
            rain_field = None
    # Line rain along river
    if float(args.river_line_rain_mmph) > 0.0 and np.any(river_mask) and not args.rain_off:
        add_mps = (float(args.river_line_rain_mmph) / 1000.0) / 3600.0
        if rain_field is None:
            rain_field = np.full((nx, ny), rain_rate_mps, dtype=np.float64)
        if not hasattr(rain_field, 'shape'):
            rain_field = np.full((nx, ny), float(rain_field), dtype=np.float64)
        rain_field = rain_field + add_mps * river_mask.astype(np.float64)

    # Infiltration
    roughness_map = None
    if lulc_raster and lulc_raster.exists():
        print('Using LULC for infiltration map:', lulc_raster)
        # Bhuvan LULC paletted raster: values are class IDs, not colors.
        # See https://bhuvan-app1.nrsc.gov.in/disaster/disaster.php -> LULC Map -> Legend
        lulc_map = {
            11: 2e-9,  # Built-up (Urban)
            12: 2e-9,  # Built-up (Rural)
            21: 3e-7,  # Agriculture (Kharif)
            22: 3e-7,  # Agriculture (Rabi)
            23: 3e-7,  # Agriculture (Zaid)
            24: 3e-7,  # Double/Triple crop
            31: 4e-7,  # Plantation
            41: 8e-7,  # Evergreen Forest
            42: 8e-7,  # Deciduous Forest
            51: 0.0,   # Water bodies
        }
        # Fallback for unmapped classes (e.g. Grassland, Wasteland)
        default_rate = float(args.infil_mps)
        infil_rate = np.full(bed.shape, default_rate, dtype=np.float32)

        # Try RGB paletted mapping first (many SISDP rasters are 3-band color)
        try:
            with rio.open(lulc_raster) as _src_chk:
                band_count = int(_src_chk.count or 1)
        except Exception:
            band_count = 1

        default_n = 0.060
        roughness_map = np.full(bed.shape, default_n, dtype=np.float32)

        if band_count >= 3:
            R = resample_raster_to_grid(lulc_raster, win_transform, win_crs,
                                        width=bed.shape[1], height=bed.shape[0],
                                        resampling=Resampling.nearest, band=1)
            G = resample_raster_to_grid(lulc_raster, win_transform, win_crs,
                                        width=bed.shape[1], height=bed.shape[0],
                                        resampling=Resampling.nearest, band=2)
            B = resample_raster_to_grid(lulc_raster, win_transform, win_crs,
                                        width=bed.shape[1], height=bed.shape[0],
                                        resampling=Resampling.nearest, band=3)
            R = np.clip(np.rint(R), 0, 255).astype(np.uint8)
            G = np.clip(np.rint(G), 0, 255).astype(np.uint8)
            B = np.clip(np.rint(B), 0, 255).astype(np.uint8)

            # Color triplets from QGIS Identify (provided by user)
            colors = {
                'built_up_pink':  (204, 51, 204),   # Rural built-up
                'built_up_red':   (230, 0, 0),      # Urban built-up
                'water_blue':     (0, 51, 204),     # Rivers/streams
                'forest_green':   (80, 187, 62),    # Forest
                'agri_yellow':    (255, 255, 115),  # Agriculture/cropland
            }

            infil_by_cat = {
                'built_up_pink': 2e-9,
                'built_up_red':  2e-9,
                'water_blue':    0.0,
                'forest_green':  8e-7,
                'agri_yellow':   3e-7,
            }
            n_by_cat = {
                'built_up_pink': 0.020,
                'built_up_red':  0.018,
                'water_blue':    0.012,
                'forest_green':  0.100,
                'agri_yellow':   0.050,
            }

            for name, (r, g, b) in colors.items():
                m = (R == r) & (G == g) & (B == b)
                if np.any(m):
                    infil_rate[m] = float(infil_by_cat[name])
                    roughness_map[m] = float(n_by_cat[name])
                    print(f"Applied {name}: infil={infil_by_cat[name]:.1e}, n={n_by_cat[name]:.3f} to {int(np.sum(m))} pixels for RGB=({r},{g},{b})")

            # Heuristic color ranges to catch near shades
            already = (infil_rate != default_rate) | (np.abs(roughness_map - default_n) > 1e-9)

            # Built-up: strong red or magenta (R high & G,B low OR R,B high & G low)
            built_mask = (((R > 180) & (G < 120) & (B < 120)) |
                          ((R > 160) & (B > 160) & (G < 120) & (np.abs(R.astype(int) - B.astype(int)) < 60))) & (~already)
            if np.any(built_mask):
                infil_rate[built_mask] = 2e-9
                roughness_map[built_mask] = 0.019
                print(f"Applied built_up_heuristic to {int(np.sum(built_mask))} pixels")

            # Water: strong blue (B high, G moderate, R low)
            water_mask = ((B > 150) & (G > 40) & (R < 100)) & (~already)
            if np.any(water_mask):
                infil_rate[water_mask] = 0.0
                roughness_map[water_mask] = 0.012
                print(f"Applied water_heuristic to {int(np.sum(water_mask))} pixels")

            # Forest: strong green (G high, R,B low)
            forest_mask = ((G > 160) & (R < 120) & (B < 140)) & (~already)
            if np.any(forest_mask):
                infil_rate[forest_mask] = 8e-7
                roughness_map[forest_mask] = 0.10
                print(f"Applied forest_heuristic to {int(np.sum(forest_mask))} pixels")

            # Agriculture: yellow (R & G high, B low/moderate)
            agri_mask = ((R > 200) & (G > 200) & (B < 160)) & (~already)
            if np.any(agri_mask):
                infil_rate[agri_mask] = 3e-7
                roughness_map[agri_mask] = 0.05
                print(f"Applied agri_heuristic to {int(np.sum(agri_mask))} pixels")

            # Done with RGB path; still allow class-ID fallback below for any remaining matches
        
        # Class-ID fallback using band 1 (useful if LULC is single-band categories)
        lulc_arr = resample_raster_to_grid(
            lulc_raster,
            dst_transform=win_transform,
            dst_crs=win_crs,
            width=bed.shape[1],
            height=bed.shape[0],
            resampling=Resampling.nearest,
            band=1,
        )
        lulc_indices = np.array(np.rint(lulc_arr), dtype=np.int32)

        # Typical values: urban ~0.015-0.020; crops ~0.04-0.06; plantation ~0.04-0.05; forests ~0.08-0.12; water ~0.010-0.015
        lulc_to_n = {
            11: 0.018,  # Built-up Urban
            12: 0.020,  # Built-up Rural/settlement
            21: 0.050,  # Agriculture
            22: 0.050,
            23: 0.050,
            24: 0.055,  # Double/triple crop slightly higher
            31: 0.045,  # Plantation
            41: 0.100,  # Evergreen Forest
            42: 0.090,  # Deciduous Forest
            51: 0.012,  # Water bodies
        }
        for class_id, nval in lulc_to_n.items():
            m = (lulc_indices == class_id)
            if np.any(m):
                roughness_map[m] = nval
                print(f'Applied Manning n {nval:.3f} to {np.sum(m)} pixels for LULC {class_id}')

        for class_id, rate in lulc_map.items():
            mask = (lulc_indices == class_id)
            if np.any(mask):
                infil_rate[mask] = rate
                print(f'Applied rate {rate:.1e} to {np.sum(mask)} pixels for class ID {class_id}')
    else:
        print('LULC not found or specified, using uniform infiltration.')
        infil_rate = float(args.infil_mps)

    # Channel/drain/canal masks and simple hydraulics
    channel_mask = np.zeros_like(bed, dtype=np.uint8)
    for p in [drains_raster, canals_raster, culverts_raster]:
        if p and p.exists():
            # Support both vector (GeoJSON) and raster (TIFF) inputs as masks
            suffix = p.suffix.lower()
            if suffix in ('.tif', '.tiff'):
                try:
                    # Resample raster mask to grid; treat nonzero as channel
                    mask_arr = resample_raster_to_grid(p, win_transform, win_crs, width=bed.shape[1], height=bed.shape[0], resampling=Resampling.nearest)
                    m = (np.nan_to_num(mask_arr, nan=0.0) > 0).astype(np.uint8)
                    if np.any(m):
                        channel_mask = np.maximum(channel_mask, m)
                        print('Added channel mask from raster', p, 'pixels=', int(np.sum(m)))
                except Exception:
                    pass
            else:
                try:
                    m = build_river_mask(bed.shape, win_transform, win_crs, p, buffer_m=max(float(args.channel_buffer_m), max(dx_m, dy_m) * 1.5))
                    if m is not None and np.any(m):
                        channel_mask = np.maximum(channel_mask, m.astype(np.uint8))
                        print('Added channel mask from', p, 'pixels=', int(np.sum(m)))
                except Exception:
                    pass
    # Increase local sink along channels if requested
    if float(args.drain_sink_mps) > 0.0 and np.any(channel_mask):
        if not hasattr(infil_rate, 'shape'):
            infil_rate = np.full(bed.shape, float(infil_rate), dtype=np.float64)
        infil_rate = infil_rate + float(args.drain_sink_mps) * channel_mask.astype(np.float64)
        print('Applied extra sink along channels:', float(args.drain_sink_mps))
    # Lower roughness along channels
    if roughness_map is None:
        roughness_map = np.full(bed.shape, float(args.infil_mps) * 0.0 + 0.06, dtype=np.float32)  # default baseline 0.06
    if np.any(channel_mask):
        roughness_map = roughness_map.astype(np.float32)
        roughness_map[channel_mask > 0] = float(args.channel_n)
        print('Applied channel Manning n =', float(args.channel_n))
    # Overflow mask: allow broad-crested overflow within channel cells
    overflow_mask = None
    crest_elev = None
    if np.any(channel_mask):
        overflow_mask = channel_mask.astype(np.uint8)
        crest_elev = np.where(channel_mask > 0,
                              bed + float(args.channel_crest_h_m),
                              bed + 1.0e6).astype(np.float64)
        print('Configured overflow crest height m =', float(args.channel_crest_h_m))

    # Optional ponds: depress bed inside polygons
    if args.ponds:
        try:
            ppath = Path(args.ponds)
            if _HAS_VECTOR and ppath.exists():
                with fiona.open(ppath, 'r') as src:
                    src_crs = src.crs_wkt or src.crs or 'EPSG:4326'
                    transformer = Transformer.from_crs(src_crs, win_crs, always_xy=True)
                    geoms = []
                    for feat in src:
                        geom = shp_shape(feat['geometry'])
                        geom_t = shp_transform(lambda x, y, z=None: transformer.transform(x, y), geom)
                        geoms.append(geom_t)
                if geoms:
                    mask = rio_features.rasterize(
                        ((g, 1) for g in geoms), out_shape=bed.shape, transform=win_transform, fill=0, all_touched=True, dtype=np.uint8
                    )
                    bed = bed - float(args.pond_depth_m) * (mask.astype(np.float64))
                    bed = bed - np.nanmin(bed)
                    print('Applied detention ponds from', ppath, 'depth_m=', float(args.pond_depth_m))
        except Exception:
            pass

    # Apply forcing (include spatial roughness and optional overflow)
    solver.set_forcing(bed=bed,
                       rain_rate=(rain_field if rain_field is not None else rain_rate_mps),
                       infil_rate=infil_rate,
                       roughness_n=roughness_map,
                       overflow_mask=overflow_mask,
                       crest_elev=crest_elev,
                       overflow_Cd=1.6)

    # Provide design-storm metadata for intervention applier (for demand-based sizing)
    try:
        sim_seconds_meta = float(args.t_hours) * 3600.0
        if rain_field is not None and hasattr(rain_field, 'shape'):
            rain_mean_mps = float(np.nanmean(rain_field))
        else:
            rain_mean_mps = float(rain_rate_mps)
        solver.rain_depth_m = float(rain_mean_mps * sim_seconds_meta)
        solver.design_storm_seconds = sim_seconds_meta
    except Exception:
        pass

    # Build simple culvert/bridge couplers from AOI lines by linking neighboring cells along the line
    def add_line_culverts(path: Optional[Path], area_m2: float = 0.5):
        if not path or not path.exists():
            return
        try:
            with fiona.open(path, 'r') as src:
                src_crs = src.crs_wkt or src.crs or 'EPSG:4326'
                transformer = Transformer.from_crs(src_crs, win_crs, always_xy=True)
                for feat in src:
                    geom = shp_shape(feat['geometry'])
                    # transform to raster CRS
                    geom_t = shp_transform(lambda x, y, z=None: transformer.transform(x, y), geom)
                    # rasterize thin mask to derive cell pairs
                    m = rio_features.rasterize([(geom_t, 1)], out_shape=bed.shape, transform=win_transform, fill=0, all_touched=True)
                    # connect neighbors where mask crosses a face
                    nx, ny = bed.shape
                    faces = []
                    # horizontal faces
                    horz = (m[0:nx-1, :] > 0) & (m[1:nx, :] > 0)
                    ii, jj = np.where(horz)
                    for i, j in zip(ii.tolist(), jj.tolist()):
                        faces.append(FaceIndex(i=i, j=j, dir='x'))
                    # vertical faces
                    vert = (m[:, 0:ny-1] > 0) & (m[:, 1:ny] > 0)
                    ii, jj = np.where(vert)
                    for i, j in zip(ii.tolist(), jj.tolist()):
                        faces.append(FaceIndex(i=i, j=j, dir='y'))
                    if faces:
                        solver.structures['culverts'].append(Culvert(faces=faces, area=float(area_m2)))
        except Exception:
            pass

    # Culvert placement
    if culverts_selected and culverts_selected.exists():
        # Use pre-selected culvert faces (WGS84 line segments)
        try:
            with fiona.open(culverts_selected, 'r') as src:
                src_crs = src.crs_wkt or src.crs or 'EPSG:4326'
                transformer = Transformer.from_crs(src_crs, win_crs, always_xy=True)
                segs = []
                for feat in src:
                    geom = shp_shape(feat['geometry'])
                    geom_t = shp_transform(lambda x, y, z=None: transformer.transform(x, y), geom)
                    m = rio_features.rasterize([(geom_t, 1)], out_shape=bed.shape, transform=win_transform, fill=0, all_touched=True)
                    nx, ny = bed.shape
                    horz = (m[0:nx-1, :] > 0) & (m[1:nx, :] > 0)
                    ii, jj = np.where(horz)
                    for i, j in zip(ii.tolist(), jj.tolist()):
                        segs.append(FaceIndex(i=i, j=j, dir='x'))
                    vert = (m[:, 0:ny-1] > 0) & (m[:, 1:ny] > 0)
                    ii, jj = np.where(vert)
                    for i, j in zip(ii.tolist(), jj.tolist()):
                        segs.append(FaceIndex(i=i, j=j, dir='y'))
                if segs:
                    solver.structures['culverts'].append(Culvert(faces=segs, area=float(args.culvert_area_m2)))
                    print('Added selected culverts:', len(segs))
        except Exception:
            pass
    elif bool(args.culverts_crossings_only) and roads_vector and roads_vector.exists() and np.any(channel_mask):
        try:
            # Rasterize roads in grid CRS
            if _HAS_VECTOR:
                with fiona.open(roads_vector, 'r') as src:
                    src_crs = src.crs_wkt or src.crs or 'EPSG:4326'
                    transformer = Transformer.from_crs(src_crs, win_crs, always_xy=True)
                    geoms = []
                    for feat in src:
                        geom = shp_shape(feat['geometry'])
                        geom_t = shp_transform(lambda x, y, z=None: transformer.transform(x, y), geom)
                        geoms.append((geom_t, 1))
                road_mask = rio_features.rasterize(
                    geoms, out_shape=bed.shape, transform=win_transform, fill=0, all_touched=True, dtype=np.uint8
                )
            else:
                road_mask = np.zeros_like(bed, dtype=np.uint8)
            # Crossings where road and channel coincide
            cross = (road_mask > 0) & (channel_mask > 0)
            ii, jj = np.where(cross)
            faces = []
            for i, j in zip(ii.tolist(), jj.tolist()):
                # choose the neighbor face aligned with steepest bed gradient
                sx = 0.0; sy = 0.0
                if 0 < i < bed.shape[0]-1:
                    sx = abs((bed[i+1, j] - bed[i-1, j]) / max(1e-9, 2*dx_m))
                if 0 < j < bed.shape[1]-1:
                    sy = abs((bed[i, j+1] - bed[i, j-1]) / max(1e-9, 2*dy_m))
                if sx >= sy and i < bed.shape[0]-1:
                    faces.append(FaceIndex(i=i, j=j, dir='x'))
                elif j < bed.shape[1]-1:
                    faces.append(FaceIndex(i=i, j=j, dir='y'))
            if faces:
                solver.structures['culverts'].append(Culvert(faces=faces, area=float(args.culvert_area_m2)))
                print('Added crossings-only culverts:', len(faces))
        except Exception:
            pass
    else:
        # Legacy: culverts along entire lines
        add_line_culverts(drains_raster, area_m2=float(args.culvert_area_m2))
        add_line_culverts(canals_raster, area_m2=float(args.culvert_area_m2))
        add_line_culverts(culverts_raster, area_m2=float(args.culvert_area_m2))

    # Parse bridges/weirs from structures GeoJSON if present
    def add_line_structures(path: Optional[Path]):
        if not path or not path.exists():
            return
        try:
            with fiona.open(path, 'r') as src:
                src_crs = src.crs_wkt or src.crs or 'EPSG:4326'
                transformer = Transformer.from_crs(src_crs, win_crs, always_xy=True)
                for feat in src:
                    props = feat.get('properties') or {}
                    tag_bridge = str(props.get('bridge') or props.get('man_made') or '').lower()
                    tag_weir = str(props.get('weir') or props.get('waterway') or '').lower()
                    is_bridge = 'bridge' in tag_bridge
                    is_weir = ('weir' in tag_weir) or (props.get('waterway') == 'weir')
                    geom = shp_shape(feat['geometry'])
                    geom_t = shp_transform(lambda x, y, z=None: transformer.transform(x, y), geom)
                    m = rio_features.rasterize([(geom_t, 1)], out_shape=bed.shape, transform=win_transform, fill=0, all_touched=True)
                    nx, ny = bed.shape
                    faces = []
                    horz = (m[0:nx-1, :] > 0) & (m[1:nx, :] > 0)
                    ii, jj = np.where(horz)
                    for i, j in zip(ii.tolist(), jj.tolist()):
                        faces.append(FaceIndex(i=i, j=j, dir='x'))
                    vert = (m[:, 0:ny-1] > 0) & (m[:, 1:ny] > 0)
                    ii, jj = np.where(vert)
                    for i, j in zip(ii.tolist(), jj.tolist()):
                        faces.append(FaceIndex(i=i, j=j, dir='y'))
                    if not faces:
                        continue
                    if is_bridge:
                        solver.structures['bridges'].append(Bridge(faces=faces, area_free= float(args.bridge_free_area_m2), area_press=float(args.bridge_press_area_m2)))
                    elif is_weir:
                        # Put a weir at line with crest slightly above local bed; width_per_face = grid spacing approx
                        solver.structures['weirs'].append(Weir(faces=faces, Cd=1.6, crest_elev=float(np.nanmean(bed)) + 0.1, width_per_face=dy_m))
        except Exception:
            pass

    add_line_structures(Path(args.culverts) if args.culverts else None)
    add_line_structures(Path(args.rivers) if args.rivers else None)
    # If a dedicated structures file exists in Data/osm_structures_aoi.geojson, add it as well
    try:
        struct_path = Path('Data/osm_structures_aoi.geojson')
        if struct_path.exists():
            add_line_structures(struct_path)
    except Exception:
        pass

    # --- Export structures debug as WGS84 GeoJSON for visualization ---
    try:
        to_wgs84 = Transformer.from_crs(win_crs, "EPSG:4326", always_xy=True)
        feats_dbg = []
        def cell_center_lonlat(i: int, j: int):
            # rasterio transform maps (col, row) -> map coords of upper-left corner; add 0.5 for center
            x, y = win_transform * (j + 0.5, i + 0.5)
            lon, lat = to_wgs84.transform(x, y)
            return lon, lat
        # Bridges
        for b in solver.structures.get('bridges', []):
            for fc in b.faces:
                lon0, lat0 = cell_center_lonlat(fc.i, fc.j)
                if fc.dir == 'x':
                    lon1, lat1 = cell_center_lonlat(fc.i + 1, fc.j)
                else:
                    lon1, lat1 = cell_center_lonlat(fc.i, fc.j + 1)
                feats_dbg.append({
                    'type': 'Feature',
                    'geometry': {'type': 'LineString', 'coordinates': [[lon0, lat0], [lon1, lat1]]},
                    'properties': {'structure': 'bridge', 'area_free': getattr(b, 'area_free', None), 'area_press': getattr(b, 'area_press', None)}
                })
        # Culverts
        for c in solver.structures.get('culverts', []):
            for fc in c.faces:
                lon0, lat0 = cell_center_lonlat(fc.i, fc.j)
                if fc.dir == 'x':
                    lon1, lat1 = cell_center_lonlat(fc.i + 1, fc.j)
                else:
                    lon1, lat1 = cell_center_lonlat(fc.i, fc.j + 1)
                feats_dbg.append({
                    'type': 'Feature',
                    'geometry': {'type': 'LineString', 'coordinates': [[lon0, lat0], [lon1, lat1]]},
                    'properties': {'structure': 'culvert', 'area': getattr(c, 'area', None)}
                })
        # Weirs
        for w in solver.structures.get('weirs', []):
            for fc in w.faces:
                lon0, lat0 = cell_center_lonlat(fc.i, fc.j)
                if fc.dir == 'x':
                    lon1, lat1 = cell_center_lonlat(fc.i + 1, fc.j)
                else:
                    lon1, lat1 = cell_center_lonlat(fc.i, fc.j + 1)
                feats_dbg.append({
                    'type': 'Feature',
                    'geometry': {'type': 'LineString', 'coordinates': [[lon0, lat0], [lon1, lat1]]},
                    'properties': {'structure': 'weir', 'crest_elev': getattr(w, 'crest_elev', None)}
                })
        dbg = {'type': 'FeatureCollection', 'features': feats_dbg}
        (out_dir / 'structures_debug.geojson').write_text(json.dumps(dbg))
        print('Wrote structures debug:', out_dir / 'structures_debug.geojson', 'features=', len(feats_dbg))
    except Exception:
        pass

    # Apply QCIA design (if provided)
    if args.qcia_design and Path(args.qcia_design).exists():
        try:
            sys.path.insert(0, str(_ROOT / 'AI'))
            from intervention_applier import apply_qcia_design_to_solver
            applied = apply_qcia_design_to_solver(solver, grid, Path(args.qcia_design), verbose=True)
            print(f"   Applied {len(applied)} QCIA interventions")
        except Exception as e:
            print(f"   ⚠️  Failed to apply QCIA design: {e}")
            import traceback
            traceback.print_exc()
    
    # Simulation
    sim_seconds = float(args.t_hours) * 3600.0
    stage_step_seconds = float(args.stage_step_at_h) * 3600.0

    if args.stage_points and np.any(river_mask):
        schedule = [(t, dz) for (t, dz) in parse_stage_points(args.stage_points) if 0.0 <= t <= sim_seconds]
        t_prev = 0.0
        dz_prev = 0.0
        for t_cur, dz_cur in schedule:
            if t_cur > t_prev:
                solver.run(t_end=t_cur, output_every=300.0, verbose=True)
            inc = dz_cur - dz_prev
            if abs(inc) > 0.0:
                solver.h[...] = solver.h + river_mask.astype(np.float64) * inc
            t_prev = t_cur
            dz_prev = dz_cur
        logs = solver.run(t_end=sim_seconds, output_every=300.0, verbose=True)
    elif float(args.stage_step_m) > 0.0 and 0.0 < stage_step_seconds < sim_seconds and np.any(river_mask):
        solver.run(t_end=stage_step_seconds, output_every=300.0, verbose=True)
        solver.h[...] = solver.h + river_mask.astype(np.float64) * float(args.stage_step_m)
        logs = solver.run(t_end=sim_seconds, output_every=300.0, verbose=True)
    else:
        logs = solver.run(t_end=sim_seconds, output_every=300.0, verbose=True)

    # Save outputs
    np.savez(out_dir / "final_snapshot.npz", h=solver.h, u=solver.u, v=solver.v, bed=bed,
             dx_m=dx_m, dy_m=dy_m, Lx=Lx, Ly=Ly)
    try:
        profile = {
            "driver": "GTiff",
            "height": ny,
            "width": nx,
            "count": 1,
            "dtype": "float32",
            "crs": win_crs,
            "transform": win_transform,
            "nodata": 0.0,
        }
        with rio.open(out_dir / "final_h.tif", "w", **profile) as dst:
            dst.write(solver.h.astype("float32"), 1)
        # Save river mask for diagnostics
        if np.any(river_mask):
            mask_profile = dict(profile)
            mask_profile.update({"dtype": "uint8"})
            with rio.open(out_dir / "river_mask.tif", "w", **mask_profile) as mds:
                mds.write(river_mask.astype("uint8"), 1)

        # Save applied infiltration and roughness maps for QA
        try:
            infil_out = infil_rate if hasattr(infil_rate, 'shape') else np.full((nx, ny), float(infil_rate), dtype=np.float32)
            with rio.open(out_dir / "infiltration_mps.tif", "w", **profile) as ids:
                ids.write(infil_out.astype("float32"), 1)
        except Exception:
            pass
        try:
            rough_out = roughness_map if roughness_map is not None else np.full((nx, ny), 0.06, dtype=np.float32)
            with rio.open(out_dir / "roughness_n.tif", "w", **profile) as rds:
                rds.write(rough_out.astype("float32"), 1)
        except Exception:
            pass
    except Exception:
        pass

    try:
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(6, 5))
        vmax_plot = float(args.plot_vmax) if float(args.plot_vmax) > 0.0 else float(np.nanmax(solver.h))
        vmax_plot = max(0.2, vmax_plot)
        im = ax.imshow(solver.h.T, origin="lower", cmap="viridis", aspect="auto",
                       vmin=0.0, vmax=vmax_plot)
        fig.colorbar(im, ax=ax, label="h (m)")
        ax.set_title("Dehradun: Final depth h")
        fig.tight_layout()
        fig.savefig(out_dir / "final_h.png", dpi=150)
        plt.close(fig)
    except Exception:
        pass

    # Detailed mass budget
    rain_used = float(np.nanmean(rain_field)) if (rain_field is not None and hasattr(rain_field, 'shape')) else float(rain_rate_mps)
    infil_used = float(np.nanmean(infil_rate)) if hasattr(infil_rate, 'shape') else float(infil_rate)
    rain_vol = rain_used * (grid.Lx * grid.Ly) * sim_seconds
    infil_vol = infil_used * (grid.Lx * grid.Ly) * sim_seconds
    delta_storage = solver.total_mass() - solver.mass0
    
    print(f"\n{'='*70}")
    print(f"MASS BUDGET SUMMARY")
    print(f"{'='*70}")
    print(f"Initial mass:        {solver.mass0:12.3f} m³")
    print(f"Rainfall input:      {rain_vol:12.3f} m³  (tracked: {getattr(solver,'rain_total',0.0):.3f})")
    print(f"Infiltration loss:  -{infil_vol:12.3f} m³  (tracked: {getattr(solver,'infil_total',0.0):.3f})")
    # Include generic source (e.g., pump outfalls) and boundary flux via sponge
    source_vol = float(getattr(solver, 'source_total', 0.0))
    bflux_vol = float(getattr(solver, 'boundary_flux_total', 0.0))
    print(f"Pump/Source input:   {source_vol:12.3f} m³")
    pond_storage = float(getattr(solver, 'pond_storage_total', 0.0))
    if pond_storage > 0.0:
        print(f"Pond storage (ledger): {pond_storage:12.3f} m³")
    print(f"Boundary flux:       {bflux_vol:12.3f} m³  (positive=inflow)")
    net_input_report = (rain_vol - infil_vol + source_vol + bflux_vol)
    print(f"Net input:           {net_input_report:12.3f} m³")
    print(f"Storage change:      {delta_storage:12.3f} m³")
    print(f"Final mass:          {solver.total_mass():12.3f} m³  (excludes h_min film)")
    
    expected_final = solver.mass0 + (rain_vol - infil_vol) + source_vol + bflux_vol + pond_storage
    discrepancy = solver.total_mass() - expected_final
    discrepancy_pct_rain = 100.0 * abs(discrepancy) / max(1.0, rain_vol)
    discrepancy_pct_total = 100.0 * abs(discrepancy) / max(1.0, solver.total_mass())
    
    print(f"\nExpected final:      {expected_final:12.3f} m³")
    print(f"Discrepancy:         {discrepancy:12.3f} m³")
    print(f"                     ({discrepancy_pct_rain:.1f}% of rainfall, {discrepancy_pct_total:.1f}% of final mass)")
    
    # For realistic flood modeling, some discrepancy is expected due to:
    # 1. Boundary inflows (upstream watersheds contributing water)
    # 2. Numerical dispersion in shallow water equations
    # 3. Terrain-induced convergence/divergence
    if discrepancy_pct_total < 10.0:
        print(f"✅ Mass balance acceptable (< 10% of total mass)")
    elif discrepancy_pct_total < 20.0:
        print(f"⚠️  Mass balance moderate (10-20% of total mass)")
        print(f"   Likely cause: boundary inflows from upstream catchments")
    else:
        print(f"❌ Mass balance poor (> 20% of total mass)")
        print(f"   Check: boundary conditions, numerical stability, or physics bugs")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()



