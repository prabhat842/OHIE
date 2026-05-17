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

from hrf import Grid, SWEParams, ExponentialFilter, HRFSolver, _xp, _device, to_numpy
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
            arr = ds.read(1, window=window, out_shape=(out_h, out_w), resampling=Resampling.bilinear).astype(np.float32)
            base_transform = ds.window_transform(window)
            transform = base_transform * Affine.scale(1.0 / upsample, 1.0 / upsample)
        else:
            arr = ds.read(1, window=window).astype(np.float32)
            transform = ds.window_transform(window)
        crs = ds.crs
        dx_m, dy_m = ds.res
        dx_m = float(abs(dx_m)) / max(1, upsample)
        dy_m = float(abs(dy_m)) / max(1, upsample)
        return arr, dx_m, dy_m, transform, crs


def resample_raster_to_grid(src_path: Path, dst_transform, dst_crs, width: int, height: int,
                            resampling: Resampling = Resampling.bilinear) -> np.ndarray:
    with rio.open(src_path) as src:
        src_arr = src.read(1).astype(np.float32)
        dst_arr = np.zeros((height, width), dtype=np.float32)
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
                rio.open(src_path).read(1, out_shape=(height, width), resampling=resampling),
                dtype=np.float32,
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
        carved = bed - carve_depth_m * (mask.astype(np.float32))
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
        carved = bed - carve_depth_m * (mask.astype(np.float32))
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
    ap.add_argument('--rain_csv', type=str, default='', help='CSV with columns time_s,rain_mmph (domain-wide)')
    ap.add_argument('--infil_mps', type=float, default=1.0e-8)
    ap.add_argument('--lulc', type=str, default=str(root / 'Data_PB/lulc_gurdaspur_bhuvan_utm_100m.tif'))
    ap.add_argument('--rivers', type=str, default=str(root / 'Data_PB/osm_waterways.geojson'))
    ap.add_argument('--burn_buffer_m', type=float, default=40.0)
    ap.add_argument('--canal_bankfull_m', type=float, default=2.0, help='Bankfull depth for canals')
    ap.add_argument('--drain_bankfull_m', type=float, default=1.0, help='Bankfull depth for drains/ditches')
    ap.add_argument('--canal_n', type=float, default=0.025, help='Manning n for canals')
    ap.add_argument('--drain_n', type=float, default=0.040, help='Manning n for drains')
    ap.add_argument('--river_n', type=float, default=0.040, help='Manning n for rivers (overrides --manning_n in channel cells)')
    ap.add_argument('--burn_depth_m', type=float, default=1.0)
    ap.add_argument('--t_hours', type=float, default=3.0)
    ap.add_argument('--manning_n', type=float, default=0.06, help='Manning roughness for DW-FV')
    ap.add_argument('--river_stage_m', type=float, default=0.0)
    ap.add_argument('--river_line_rain_mmph', type=float, default=0.0)
    ap.add_argument('--stage_step_m', type=float, default=0.0)
    ap.add_argument('--stage_step_at_h', type=float, default=0.0)
    ap.add_argument('--stage_points', type=str, default='')
    ap.add_argument('--stage_csv', type=str, default='', help='CSV with columns time_s,stage_m (incremental dz or absolute?)')
    ap.add_argument('--drains', type=str, default='')
    ap.add_argument('--drain_sink_mps', type=float, default=0.0)
    ap.add_argument('--h_init_m', type=float, default=0.0)
    ap.add_argument('--plot_vmax', type=float, default=0.0)
    ap.add_argument('--save_interval_min', type=float, default=0.0, help='Save PNG every N minutes (0=off)')
    ap.add_argument('--save_kmz_frames', action='store_true', help='Also save KMZ frames when saving PNGs')
    ap.add_argument('--tile_col0', type=int, default=-1)
    ap.add_argument('--tile_row0', type=int, default=-1)
    # Numerical controls
    ap.add_argument('--h_min', type=float, default=2.0e-2, help='Minimum water depth clamp (m)')
    ap.add_argument('--sponge_width', type=int, default=0, help='Sponge layer width (cells)')
    ap.add_argument('--sponge_tau', type=float, default=180.0, help='Sponge relaxation timescale (s)')
    ap.add_argument('--cfl', type=float, default=0.15, help='CFL number for timestep selection')
    ap.add_argument('--dt_max', type=float, default=0.1, help='Maximum timestep (s)')
    # SPU controls
    ap.add_argument('--spu_adaptive', action='store_true', help='Enable SPU adaptive truncation')
    ap.add_argument('--spu_tail_target', type=float, default=1e-3, help='SPU tail energy target')
    ap.add_argument('--spu_filter_type', type=str, default='exp', help='SPU filter type (hard|exp)')
    ap.add_argument('--spu_mfrac', type=float, default=0.3, help='SPU retained spectral fraction (0-1)')
    args = ap.parse_args()

    dem_clip = Path(args.dem)
    lulc_raster = Path(args.lulc) if args.lulc else None
    drains_raster = Path(args.drains) if args.drains else None
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
    grid = Grid(nx=nx, ny=ny, Lx=Lx, Ly=Ly, xp=_xp, device=_device)
    prm = SWEParams(g=9.81, manning_n=float(args.manning_n), h_min=float(args.h_min), cfl=float(args.cfl), vmax_guard_coef=0.7, dt_max=float(args.dt_max),
                    sponge_width=int(args.sponge_width), sponge_tau=float(args.sponge_tau),
                    adaptive_truncation=args.spu_adaptive, tail_target=args.spu_tail_target, filter_type=args.spu_filter_type,
                    mfrac_min=0.2, mfrac_max=float(max(0.2, min(1.0, args.spu_mfrac))))
    filt = ExponentialFilter(alpha=96.0, p=8)
    solver = HRFSolver(grid, prm, filt)
    solver.mode = "dw_fv"

    # Initial conditions
    h0 = np.full((nx, ny), float(args.h_init_m), dtype=np.float32)
    if float(args.river_stage_m) > 0.0 and np.any(river_mask):
        h0 = h0 + (river_mask.astype(np.float32) * float(args.river_stage_m))
    u0 = np.zeros_like(h0)
    v0 = np.zeros_like(h0)
    solver.initialize(h0, u0, v0)

    # Rain forcing
    rain_field = None
    rain_rate_mps = 0.0 if args.rain_off else (float(args.rain_mm_per_hour) / 1000.0) / 3600.0
    # CSV domain-mean rain time series (piecewise constant)
    rain_series = None
    if args.rain_csv and not args.rain_off:
        try:
            import csv
            rain_series = []
            with open(args.rain_csv, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # time
                    if 'time_s' in row:
                        t_s = float(row['time_s'])
                    elif 'time_hours' in row:
                        t_s = float(row['time_hours']) * 3600.0
                    else:
                        continue
                    # rain
                    if 'rain_mmph' in row:
                        mmph = float(row['rain_mmph'])
                    elif 'rain_mm_per_hr' in row:
                        mmph = float(row['rain_mm_per_hr'])
                    else:
                        continue
                    rain_series.append((t_s, mmph))
            rain_series.sort(key=lambda x: x[0])
        except Exception:
            rain_series = None
    if args.rain_raster and not args.rain_off and rain_series is None:
        try:
            rain_mm_h = resample_raster_to_grid(Path(args.rain_raster), win_transform, win_crs, width=ny, height=nx,
                                                resampling=Resampling.bilinear)
            rain_field = (rain_mm_h / 1000.0) / 3600.0
        except Exception:
            rain_field = None
    # Line rain along river
    if float(args.river_line_rain_mmph) > 0.0 and np.any(to_numpy(river_mask)) and not args.rain_off:
        add_mps = (float(args.river_line_rain_mmph) / 1000.0) / 3600.0
        if rain_field is None:
            rain_field = np.full((nx, ny), rain_rate_mps, dtype=np.float32)
        if not hasattr(rain_field, 'shape'):
            rain_field = np.full((nx, ny), float(rain_field), dtype=np.float32)
        rain_field = rain_field + add_mps * river_mask.astype(np.float32)

    # Infiltration
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

        with rio.open(lulc_raster) as src:
            # Read band 1 only
            lulc_indices = src.read(1, out_shape=(bed.shape[0], bed.shape[1]), resampling=Resampling.nearest)
        
        for class_id, rate in lulc_map.items():
            mask = (lulc_indices == class_id)
            if np.any(mask):
                infil_rate[mask] = rate
                print(f'Applied rate {rate:.1e} to {np.sum(mask)} pixels for class ID {class_id}')
    else:
        print('LULC not found or specified, using uniform infiltration.')
        infil_rate = float(args.infil_mps)

    # Build type masks from OSM waterway tag or raster masks
    canal_mask = np.zeros_like(bed, dtype=np.uint8)
    drain_mask = np.zeros_like(bed, dtype=np.uint8)
    river_cells_mask = np.zeros_like(bed, dtype=np.uint8)
    crest = np.zeros_like(bed, dtype=np.float32)
    if rivers_path and rivers_path.exists():
        suffix = rivers_path.suffix.lower()
        if suffix in ('.tif', '.tiff'):
            try:
                # Treat nonzero raster as river mask
                arr = resample_raster_to_grid(rivers_path, win_transform, win_crs, width=bed.shape[1], height=bed.shape[0], resampling=Resampling.nearest)
                river_cells_mask = (np.nan_to_num(arr, nan=0.0) > 0).astype(np.uint8)
                print('Built river mask from raster', rivers_path, 'pixels=', int(np.sum(river_cells_mask)))
            except Exception:
                pass
        elif _HAS_VECTOR:
            try:
                with fiona.open(rivers_path, 'r') as src:
                    src_crs = src.crs_wkt or src.crs
                    transformer = Transformer.from_crs(src_crs, win_crs, always_xy=True)
                    geoms_canal = []
                    geoms_drain = []
                    geoms_river = []
                    for feat in src:
                        props = feat.get('properties', {})
                        w = str(props.get('waterway','')).lower()
                        geom = shp_shape(feat['geometry'])
                        geom_t = shp_transform(lambda x,y,z=None: transformer.transform(x,y), geom)
                        if w == 'canal':
                            geoms_canal.append(geom_t.buffer(max(args.burn_buffer_m, max(dx_m, dy_m)*1.5)))
                        elif w in ('drain','ditch'):
                            geoms_drain.append(geom_t.buffer(max(args.burn_buffer_m*0.5, max(dx_m, dy_m))))
                        elif w in ('river','stream','brook','tidal_channel'):
                            geoms_river.append(geom_t.buffer(max(args.burn_buffer_m, max(dx_m, dy_m)*2.0)))
                    if geoms_canal:
                        canal_mask = rio_features.rasterize(((g,1) for g in geoms_canal), out_shape=bed.shape, transform=win_transform, fill=0, all_touched=True, dtype=np.uint8)
                    if geoms_drain:
                        drain_mask = rio_features.rasterize(((g,1) for g in geoms_drain), out_shape=bed.shape, transform=win_transform, fill=0, all_touched=True, dtype=np.uint8)
                    if geoms_river:
                        river_cells_mask = rio_features.rasterize(((g,1) for g in geoms_river), out_shape=bed.shape, transform=win_transform, fill=0, all_touched=True, dtype=np.uint8)
            except Exception:
                pass

    # Roughness field from LULC (base) then override along channels
    rough_n = np.full(bed.shape, float(args.manning_n), dtype=np.float32)
    # Simple LULC->n mapping (optional refinement)
    try:
        if lulc_raster and lulc_raster.exists():
            with rio.open(lulc_raster) as src:
                lulc_idx = src.read(1, out_shape=(bed.shape[0], bed.shape[1]), resampling=Resampling.nearest)
            lut_n = {
                11: 0.020, # built-up
                21: 0.040, 22:0.040, 23:0.040, 24:0.040, # crops
                31: 0.050, # plantation
                41: 0.080, 42:0.080, # forest
                51: 0.030, # water bodies (channelized)
            }
            for cls, nval in lut_n.items():
                rough_n[lulc_idx==cls] = nval
    except Exception:
        pass
    # Override in channels
    if np.any(river_cells_mask):
        rough_n[river_cells_mask==1] = float(args.river_n)
    if np.any(canal_mask):
        rough_n[canal_mask==1] = float(args.canal_n)
    if np.any(drain_mask):
        rough_n[drain_mask==1] = float(args.drain_n)

    # Crest elevations for canal/drain overflow weirs: bed + bankfull
    crest[:] = bed + 0.0
    if np.any(canal_mask):
        crest[canal_mask==1] = bed[canal_mask==1] + float(args.canal_bankfull_m)
    if np.any(drain_mask):
        crest[drain_mask==1] = bed[drain_mask==1] + float(args.drain_bankfull_m)

    # Combined overflow mask (canal or drain)
    overflow_mask = ((canal_mask==1) | (drain_mask==1)).astype(np.uint8)

    # Apply forcing
    # Ensure all forcing fields are on the correct device if they are arrays
    if isinstance(bed, np.ndarray):
        bed = _xp.asarray(bed, device=_device)
    if isinstance(river_mask, np.ndarray):
        river_mask = _xp.asarray(river_mask, device=_device, dtype=_xp.float32)
    if isinstance(infil_rate, np.ndarray):
        infil_rate = _xp.asarray(infil_rate, device=_device)
    if isinstance(rain_field, np.ndarray):
        rain_field = _xp.asarray(rain_field, device=_device, dtype=_xp.float32)

    solver.set_forcing(bed=bed, rain_rate=(rain_field if rain_field is not None else rain_rate_mps),
                       infil_rate=infil_rate, roughness_n=rough_n,
                       overflow_mask=overflow_mask, crest_elev=crest, overflow_Cd=1.6)

    # Simulation
    sim_seconds = float(args.t_hours) * 3600.0
    stage_step_seconds = float(args.stage_step_at_h) * 3600.0

    # Optional stage time series (absolute stage increments dz) from CSV
    stage_schedule = None
    if args.stage_csv:
        try:
            import csv
            stage_schedule = []
            with open(args.stage_csv, 'r') as f:
                reader = csv.DictReader(f)
                # support either time_s or time_hours columns
                for row in reader:
                    if 'time_s' in row:
                        t_s = float(row['time_s'])
                    elif 'time_hours' in row:
                        t_s = float(row['time_hours']) * 3600.0
                    else:
                        continue
                    stage_schedule.append((t_s, float(row['stage_m'])))
            stage_schedule.sort(key=lambda x: x[0])
        except Exception:
            stage_schedule = None

    # Build frame writer if requested
    interval = max(0.0, float(args.save_interval_min)) * 60.0
    frame_writer = None
    if interval > 0.0:
        frames_dir = out_dir / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        def write_frame(t_cur: float, solver: HRFSolver) -> None:  # type: ignore[name-defined]
            try:
                import numpy as np
                import matplotlib.pyplot as plt
                h_cpu = to_numpy(solver.h)
                vmax_plot = float(args.plot_vmax) if float(args.plot_vmax) > 0.0 else float(np.nanmax(h_cpu))
                vmax_plot = max(0.1, vmax_plot)
                fig, ax = plt.subplots(figsize=(6, 5))
                im = ax.imshow(h_cpu.T, origin="lower", cmap="viridis", aspect="auto",
                               vmin=0.0, vmax=vmax_plot)
                fig.colorbar(im, ax=ax, label="h (m)")
                ax.set_title(f"Depth h at t~{int(t_cur/60)} min")
                fig.tight_layout()
                png_path = frames_dir / f"frame_{int(round(t_cur/60)):04d}.png"
                fig.savefig(png_path, dpi=130)
                plt.close(fig)
                if args.save_kmz_frames:
                    # Export KMZ for this frame
                    try:
                        from make_kmz import build_kmz
                        tif_tmp = frames_dir / f"frame_{int(round(t_cur/60)):04d}.tif"
                        profile = {"driver": "GTiff", "height": ny, "width": nx, "count": 1,
                                   "dtype": "float32", "crs": win_crs, "transform": win_transform, "nodata": 0.0}
                        with rio.open(tif_tmp, "w", **profile) as dst:
                            dst.write(h_cpu.astype("float32"), 1)
                        kmz_path = frames_dir / f"frame_{int(round(t_cur/60)):04d}.kmz"
                        build_kmz(tif_tmp, kmz_path, vmax=vmax_plot)
                        try:
                            tif_tmp.unlink()
                        except Exception:
                            pass
                    except Exception:
                        pass
            except Exception:
                pass
        frame_writer = write_frame

    # If we have stage schedule and want an open downstream boundary, set sponge toward stage on east edge
    if stage_schedule:
        def eta_func(t: float) -> float:
            current = [v for tt,v in stage_schedule if tt <= t]
            return current[-1] if current else 0.0
        solver.tide_bc = {"edge": "east", "eta_func": eta_func}

    # Helper to run a segment with correct output_every and writer
    def run_to(t_break: float):
        oe = interval if interval > 0.0 else 300.0
        solver.run(t_end=t_break, output_every=oe, verbose=True, frame_writer=frame_writer)

    # Drive simulation across schedules
    if args.stage_points and _xp.any(river_mask):
        schedule = [(t, dz) for (t, dz) in parse_stage_points(args.stage_points) if 0.0 <= t <= sim_seconds]
        t_prev = 0.0
        dz_prev = 0.0
        for t_cur, dz_cur in schedule:
            if t_cur > t_prev:
                run_to(t_cur)
            inc = dz_cur - dz_prev
            if abs(inc) > 0.0:
                solver.h += river_mask * inc
            t_prev = t_cur
            dz_prev = dz_cur
        # Continue to end with CSV drivers
        next_t = t_prev
        if stage_schedule or rain_series:
            times = set([sim_seconds])
            if stage_schedule:
                times.update([t for t,_ in stage_schedule if t > next_t and t <= sim_seconds])
            if rain_series:
                times.update([t for t,_ in rain_series if t > next_t and t <= sim_seconds])
            for t_break in sorted(times):
                if rain_series:
                    current = [v for t,v in rain_series if t <= next_t]
                    if current:
                        rr_mps = (current[-1]/1000.0)/3600.0
                        solver.set_forcing(bed=bed, rain_rate=rr_mps, infil_rate=infil_rate)
                if stage_schedule:
                    current_stage = [v for t,v in stage_schedule if t <= next_t]
                    if current_stage and _xp.any(river_mask>0):
                        target = current_stage[-1]
                        h_mask_mean = float(_xp.mean(solver.h[river_mask>0]))
                        inc = target - h_mask_mean
                        solver.h += river_mask * inc
                run_to(t_break)
                next_t = t_break
        else:
            run_to(sim_seconds)
    elif float(args.stage_step_m) > 0.0 and 0.0 < stage_step_seconds < sim_seconds and _xp.any(river_mask):
        run_to(stage_step_seconds)
        solver.h += river_mask * float(args.stage_step_m)
        run_to(sim_seconds)
    else:
        if stage_schedule or rain_series:
            next_t = 0.0
            times = set([sim_seconds])
            if stage_schedule:
                times.update([t for t,_ in stage_schedule if 0.0 < t <= sim_seconds])
            if rain_series:
                times.update([t for t,_ in rain_series if 0.0 < t <= sim_seconds])
            for t_break in sorted(times):
                if rain_series:
                    current = [v for t,v in rain_series if t <= next_t]
                    if current:
                        rr_mps = (current[-1]/1000.0)/3600.0
                        solver.set_forcing(bed=bed, rain_rate=rr_mps, infil_rate=infil_rate)
                if stage_schedule and _xp.any(river_mask>0):
                    current_stage = [v for t,v in stage_schedule if t <= next_t]
                    if current_stage:
                        target = current_stage[-1]
                        h_mask_mean = float(_xp.mean(solver.h[river_mask>0]))
                        inc = target - h_mask_mean
                        solver.h += river_mask * inc
                run_to(t_break)
                next_t = t_break
        else:
            run_to(sim_seconds)

    # Save outputs
    np.savez(out_dir / "final_snapshot.npz", h=to_numpy(solver.h), u=to_numpy(solver.u), v=to_numpy(solver.v), bed=to_numpy(bed),
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
            dst.write(to_numpy(solver.h).astype("float32"), 1)
        # Save river mask for diagnostics
        if np.any(to_numpy(river_mask)):
            mask_profile = dict(profile)
            mask_profile.update({"dtype": "uint8"})
            with rio.open(out_dir / "river_mask.tif", "w", **mask_profile) as mds:
                mds.write(to_numpy(river_mask).astype("uint8"), 1)
    except Exception:
        pass

    try:
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(6, 5))
        h_cpu = to_numpy(solver.h)
        vmax_plot = float(args.plot_vmax) if float(args.plot_vmax) > 0.0 else float(np.nanmax(h_cpu))
        vmax_plot = max(0.2, vmax_plot)
        im = ax.imshow(h_cpu.T, origin="lower", cmap="viridis", aspect="auto",
                       vmin=0.0, vmax=vmax_plot)
        fig.colorbar(im, ax=ax, label="h (m)")
        ax.set_title("Gurdaspur: Final depth h")
        fig.tight_layout()
        fig.savefig(out_dir / "final_h.png", dpi=150)
        plt.close(fig)
    except Exception:
        pass

    # (In-run frames already written if requested)

    # Simple mass budget
    rain_used = float(np.nanmean(to_numpy(rain_field))) if (rain_field is not None and hasattr(rain_field, 'shape')) else float(rain_rate_mps)
    infil_used = float(np.nanmean(to_numpy(infil_rate))) if hasattr(infil_rate, 'shape') else float(infil_rate)
    rain_vol = rain_used * (grid.Lx * grid.Ly) * sim_seconds
    infil_vol = infil_used * (grid.Lx * grid.Ly) * sim_seconds
    delta_storage = solver.total_mass() - solver.mass0
    print(f"Mass budget: rain_in={rain_vol:.3f} m^3, infil={infil_vol:.3f} m^3, dStorage={delta_storage:.3f} m^3")


if __name__ == "__main__":
    main()



