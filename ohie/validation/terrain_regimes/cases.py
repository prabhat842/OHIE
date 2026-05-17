from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlretrieve

import numpy as np
import rasterio

from ohie import DiffusiveWaveFV, DiffusiveWaveParams, Grid
from ohie.hydro.boundaries import FluxCoupledRiverBoundary, RainfallBoundary
from ohie.scenarios import run_with_history
from ohie.scenarios.metrics import persistence_duration


DATA_ROOT = Path(__file__).resolve().parents[3] / "ohie-data"
REGIME_ROOT = DATA_ROOT / "terrain_regimes"
WINDOW_CELLS = 288


@dataclass(frozen=True)
class TerrainRegimeTerrain:
    key: str
    label: str
    lat: float
    lon: float
    z: int
    source_url: str
    local_path: Path


@dataclass(frozen=True)
class TerrainRegimeDescriptor:
    key: str
    label: str
    mean_slope: float
    slope_variance: float
    relief_range_m: float
    floodplain_width_proxy_m: float
    terrain_roughness: float
    elevation_variance: float
    storage_proxy_m3: float


@dataclass(frozen=True)
class TerrainRegimeResult:
    terrain: TerrainRegimeTerrain
    descriptors: TerrainRegimeDescriptor
    boundary_volume_m3: float
    mass_error: float
    near_edge_response_m: float
    persistence_s: float
    flooded_area_delta_cells: int
    classification: str
    summary: str


def _tile_indices(lat: float, lon: float, z: int) -> tuple[int, int]:
    import math

    n = 2**z
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def _terrain_catalog() -> list[TerrainRegimeTerrain]:
    terrain_specs = [
        ("flat_floodplain", "Flat floodplain", 27.2011, 94.4571),
        ("moderate_river_valley", "Moderate river valley", 26.6330, 92.8000),
        ("basin_storage", "Basin storage terrain", 23.7000, 70.3000),
        ("steep_edge", "Steep terrain edge", 30.3165, 78.0322),
        ("mixed_relief", "Mixed relief terrain", 25.5788, 91.8933),
    ]
    out: list[TerrainRegimeTerrain] = []
    for key, label, lat, lon in terrain_specs:
        z = 12
        x, y = _tile_indices(lat, lon, z)
        local_path = REGIME_ROOT / f"{key}_z{z}_{x}_{y}.tif"
        source_url = f"https://s3.amazonaws.com/elevation-tiles-prod/geotiff/{z}/{x}/{y}.tif"
        out.append(TerrainRegimeTerrain(key=key, label=label, lat=lat, lon=lon, z=z, source_url=source_url, local_path=local_path))
    return out


def _ensure_tile(terrain: TerrainRegimeTerrain) -> Path:
    terrain.local_path.parent.mkdir(parents=True, exist_ok=True)
    if not terrain.local_path.exists():
        urlretrieve(terrain.source_url, terrain.local_path)
    return terrain.local_path


def _longest_true_run(values: np.ndarray) -> int:
    longest = current = 0
    for item in values:
        if item:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _descriptor_from_bed(bed: np.ndarray, dx: float, dy: float) -> TerrainRegimeDescriptor:
    slopes_x = np.gradient(bed, dx, axis=0)
    slopes_y = np.gradient(bed, dy, axis=1)
    slope_mag = np.sqrt(slopes_x**2 + slopes_y**2)
    mean_slope = float(np.mean(slope_mag))
    slope_variance = float(np.var(slope_mag))
    relief_range = float(np.nanmax(bed) - np.nanmin(bed))
    elevation_variance = float(np.var(bed))

    low_relief_threshold = float(np.nanpercentile(bed, 35))
    low_slope_threshold = float(np.nanpercentile(slope_mag, 45))
    low_relief_mask = (bed <= low_relief_threshold) & (slope_mag <= low_slope_threshold)
    floodplain_width_proxy_m = float(np.sqrt(max(1.0, np.sum(low_relief_mask) * dx * dy)))

    terrain_roughness = float(np.std(slope_mag))
    storage_proxy_m3 = float(np.sum(np.maximum(low_relief_threshold - bed, 0.0)) * dx * dy)

    return TerrainRegimeDescriptor(
        key="",
        label="",
        mean_slope=mean_slope,
        slope_variance=slope_variance,
        relief_range_m=relief_range,
        floodplain_width_proxy_m=floodplain_width_proxy_m,
        terrain_roughness=terrain_roughness,
        elevation_variance=elevation_variance,
        storage_proxy_m3=storage_proxy_m3,
    )


def _load_terrain(terrain: TerrainRegimeTerrain) -> tuple[np.ndarray, Grid]:
    path = _ensure_tile(terrain)
    with rasterio.open(path) as src:
        bed = src.read(1).astype(np.float64)
        nodata = src.nodata
        if nodata is not None:
            bed = np.where(bed == nodata, np.nan, bed)
        dx, dy = src.res
        if src.width > WINDOW_CELLS and src.height > WINDOW_CELLS:
            x0 = (src.width - WINDOW_CELLS) // 2
            y0 = (src.height - WINDOW_CELLS) // 2
            bed = bed[y0 : y0 + WINDOW_CELLS, x0 : x0 + WINDOW_CELLS]
            width = WINDOW_CELLS
            height = WINDOW_CELLS
        else:
            width = src.width
            height = src.height
        grid = Grid(width, height, dx=float(dx), dy=float(dy))
    if np.isnan(bed).any():
        fill = float(np.nanmedian(bed))
        bed = np.where(np.isfinite(bed), bed, fill)
    return bed, grid


def _lowest_edge_mask(bed: np.ndarray) -> tuple[str, np.ndarray]:
    edges = {
        "north": np.nanmedian(bed[:3, :]),
        "south": np.nanmedian(bed[-3:, :]),
        "west": np.nanmedian(bed[:, :3]),
        "east": np.nanmedian(bed[:, -3:]),
    }
    edge = min(edges, key=edges.get)
    mask = np.zeros_like(bed, dtype=bool)
    if edge == "north":
        mask[:3, :] = True
    elif edge == "south":
        mask[-3:, :] = True
    elif edge == "west":
        mask[:, :3] = True
    else:
        mask[:, -3:] = True
    return edge, mask


def _run_case(terrain: TerrainRegimeTerrain) -> TerrainRegimeResult:
    bed, grid = _load_terrain(terrain)
    descriptor = _descriptor_from_bed(bed, grid.dx, grid.dy)
    descriptor = TerrainRegimeDescriptor(
        key=terrain.key,
        label=terrain.label,
        mean_slope=descriptor.mean_slope,
        slope_variance=descriptor.slope_variance,
        relief_range_m=descriptor.relief_range_m,
        floodplain_width_proxy_m=descriptor.floodplain_width_proxy_m,
        terrain_roughness=descriptor.terrain_roughness,
        elevation_variance=descriptor.elevation_variance,
        storage_proxy_m3=descriptor.storage_proxy_m3,
    )

    edge_name, river_mask = _lowest_edge_mask(bed)
    stage = float(np.percentile(bed[river_mask], 90) + 0.35)

    baseline = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=5.0, manning_n=0.055, slope_cap=0.05))
    baseline.initialize(bed, h0=0.0)
    baseline.add_boundary(RainfallBoundary((25.0 / 1000.0) / 3600.0))
    baseline.run(1800.0, dt=5.0)
    baseline_depth = baseline.h.copy()

    solver = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=5.0, manning_n=0.055, slope_cap=0.05))
    solver.initialize(bed, h0=0.0)
    solver.add_boundary(RainfallBoundary((25.0 / 1000.0) / 3600.0))
    solver.add_boundary(FluxCoupledRiverBoundary(river_mask, stage_m=stage, exchange_coeff_m2_per_s=1e-6))
    depths, times = run_with_history(solver, t_end_s=1800.0, dt_s=5.0, sample_every_s=300.0)
    persist = persistence_duration(depths, times, threshold_m=0.02)

    edge_response = float(np.mean(solver.h[river_mask]) - np.mean(baseline_depth[river_mask]))
    flooded_delta = int(np.sum(solver.h > 0.02) - np.sum(baseline_depth > 0.02))
    mass_error = float(solver.mass_balance_error_fraction())

    if mass_error <= 0.01 and edge_response > 0.01 and flooded_delta >= 0:
        classification = "Strong Transfer"
    elif mass_error <= 0.05 and edge_response > 0.0:
        classification = "Moderate Transfer"
    else:
        classification = "Weak Transfer"

    summary = (
        f"edge={edge_name}; baseline_mean_edge={float(np.mean(baseline_depth[river_mask])):.3f}m; "
        f"default_mean_edge={float(np.mean(solver.h[river_mask])):.3f}m; "
        f"mass_error={mass_error:.6f}; boundary_volume={float(solver.mass.boundary):.1f}m3"
    )

    return TerrainRegimeResult(
        terrain=terrain,
        descriptors=descriptor,
        boundary_volume_m3=float(solver.mass.boundary),
        mass_error=mass_error,
        near_edge_response_m=edge_response,
        persistence_s=float(np.mean(persist[river_mask])),
        flooded_area_delta_cells=flooded_delta,
        classification=classification,
        summary=summary,
    )


def run_terrain_regime_study() -> list[TerrainRegimeResult]:
    return [_run_case(terrain) for terrain in _terrain_catalog()]
