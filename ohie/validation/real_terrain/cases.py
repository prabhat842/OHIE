from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ohie import DiffusiveWaveFV, DiffusiveWaveParams, Grid
from ohie.hydro.boundaries import RainfallBoundary, RiverStageBoundary
from ohie.scenarios import run_with_history
from ohie.scenarios.metrics import persistence_duration, stagnation_index
from ohie.terrain.routing import D8Routing, DInfinityRouting


DATA_ROOT = Path(__file__).resolve().parents[3] / "ohie-data"


@dataclass(frozen=True)
class RealTerrainResult:
    name: str
    dataset: str
    assumptions: str
    limitations: str
    confidence: str
    observed: str
    metrics: dict[str, float]


def flat_terrain_case(data_root: Path = DATA_ROOT) -> RealTerrainResult:
    data = np.load(data_root / "real_terrain" / "flat_terrain_small.npz", allow_pickle=False)
    bed = np.asarray(data["bed"], dtype=np.float64)
    dx = float(data["dx_m"])
    dy = float(data["dy_m"])
    grid = Grid(nx=bed.shape[0], ny=bed.shape[1], dx=dx, dy=dy)

    solver = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=2.0, manning_n=0.055, slope_cap=0.05))
    solver.initialize(bed, h0=0.0)
    solver.add_boundary(RainfallBoundary((35.0 / 1000.0) / 3600.0))
    depths, times = run_with_history(solver, t_end_s=2 * 3600.0, dt_s=2.0, sample_every_s=600.0)

    persist = persistence_duration(depths, times, threshold_m=0.02)
    stagnation = stagnation_index(depths, times, threshold_m=0.02)
    d8 = D8Routing().route(bed)
    dinf = DInfinityRouting().route(bed)
    split_fraction = float(np.mean(np.count_nonzero(dinf.weights > 0.05, axis=2) > 1))

    return RealTerrainResult(
        name="flat_terrain_small",
        dataset=str(data_root / "real_terrain" / "flat_terrain_small.npz"),
        assumptions="local historical-project-derived terrain chip; uniform rainfall; no calibration; no measured drainage network",
        limitations="not calibrated; not a raw DEM benchmark; no observed hydrograph; no pipe hydraulics; no remote-sensing calibration",
        confidence="Medium for software reproducibility; Low for site-specific hydrologic accuracy",
        observed=(
            f"max_depth={solver.max_depth():.3f}m, max_persistence={float(np.max(persist)):.1f}s, "
            f"DInfinity_split_fraction={split_fraction:.3f}"
        ),
        metrics={
            "max_depth_m": solver.max_depth(),
            "total_volume_m3": solver.total_volume(),
            "mass_error": solver.mass_balance_error_fraction(),
            "max_persistence_s": float(np.max(persist)),
            "mean_stagnation": float(np.mean(stagnation)),
            "d8_max_accumulation": float(np.max(d8.flow_accumulation)),
            "dinfinity_max_accumulation": float(np.max(dinf.flow_accumulation)),
            "dinfinity_split_fraction": split_fraction,
        },
    )


def river_adjacent_case(data_root: Path = DATA_ROOT) -> RealTerrainResult:
    data = np.load(data_root / "real_terrain" / "river_adjacent_small.npz", allow_pickle=False)
    bed = np.asarray(data["bed"], dtype=np.float64)
    river_mask = np.asarray(data["river_mask"], dtype=bool)
    dx = float(data["dx_m"])
    dy = float(data["dy_m"])
    grid = Grid(nx=bed.shape[0], ny=bed.shape[1], dx=dx, dy=dy)

    base = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=2.0, manning_n=0.06, slope_cap=0.05))
    base.initialize(bed, h0=0.0)
    base.add_boundary(RainfallBoundary((25.0 / 1000.0) / 3600.0))
    base.run(3600.0, dt=2.0)

    staged = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=2.0, manning_n=0.06, slope_cap=0.05))
    staged.initialize(bed, h0=0.0)
    staged.add_boundary(RainfallBoundary((25.0 / 1000.0) / 3600.0))
    stage = float(np.percentile(bed[river_mask], 90) + 0.35)
    staged.add_boundary(RiverStageBoundary(river_mask, stage_m=stage))
    depths, times = run_with_history(staged, t_end_s=3600.0, dt_s=2.0, sample_every_s=600.0)

    near_river = np.zeros_like(river_mask, dtype=bool)
    near_river[:, : min(7, river_mask.shape[1])] = True
    persist = persistence_duration(depths, times, threshold_m=0.02)
    volume_delta = staged.total_volume() - base.total_volume()

    return RealTerrainResult(
        name="river_adjacent_small",
        dataset=str(data_root / "real_terrain" / "river_adjacent_small.npz"),
        assumptions="local terrain chip with synthetic river-edge mask; prescribed static river stage; uniform rainfall",
        limitations="synthetic river mask is not measured; no real stage hydrograph; no outfall network; backwater is approximate fixed-stage forcing",
        confidence="Medium for boundary-framework demonstration; Low for site-specific river hydraulics",
        observed=(
            f"base_volume={base.total_volume():.1f}m3, staged_volume={staged.total_volume():.1f}m3, "
            f"near_river_persistence={float(np.mean(persist[near_river])):.1f}s"
        ),
        metrics={
            "base_volume_m3": base.total_volume(),
            "staged_volume_m3": staged.total_volume(),
            "stage_added_volume_m3": volume_delta,
            "near_river_mean_persistence_s": float(np.mean(persist[near_river])),
            "mass_error": staged.mass_balance_error_fraction(),
        },
    )


def run_all_real_terrain(data_root: Path = DATA_ROOT) -> list[RealTerrainResult]:
    return [flat_terrain_case(data_root), river_adjacent_case(data_root)]
