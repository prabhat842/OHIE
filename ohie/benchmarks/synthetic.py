from __future__ import annotations

from dataclasses import dataclass
import time

import numpy as np

from ohie import DiffusiveWaveFV, DiffusiveWaveParams, Grid
from ohie.hydro.boundaries import RainfallBoundary
from ohie.scenarios import run_with_history
from ohie.scenarios.metrics import flood_exposure, persistence_duration
from ohie.terrain.routing import D8Routing, DInfinityRouting


@dataclass(frozen=True)
class BenchmarkResult:
    name: str
    runtime_s: float
    mass_balance_error_fraction: float
    max_depth_m: float
    flooded_cell_count: int
    persistence_cell_seconds: float
    exposure_meter_seconds: float


def synthetic_flat_bowl(grid: Grid) -> np.ndarray:
    x = np.linspace(0.0, 1.0, grid.nx)[:, None]
    y = np.linspace(0.0, 1.0, grid.ny)[None, :]
    bed = 0.02 * x + 0.02 * y
    bed -= 0.25 * np.exp(-(((x - 0.5) ** 2 + (y - 0.5) ** 2) / 0.02))
    return bed


def run_flat_bowl_benchmark() -> BenchmarkResult:
    grid = Grid(nx=40, ny=40, dx=30.0, dy=30.0)
    solver = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=2.0, manning_n=0.045))
    solver.initialize(synthetic_flat_bowl(grid), h0=0.0)
    solver.add_boundary(RainfallBoundary((40.0 / 1000.0) / 3600.0))
    t0 = time.perf_counter()
    depth_series, times = run_with_history(solver, t_end_s=1800.0, dt_s=2.0, sample_every_s=300.0)
    runtime = time.perf_counter() - t0
    final = solver.h
    persist = persistence_duration(depth_series, times)
    exposure = flood_exposure(depth_series, times)
    return BenchmarkResult(
        name="synthetic_flat_bowl",
        runtime_s=runtime,
        mass_balance_error_fraction=solver.mass_balance_error_fraction(),
        max_depth_m=float(np.max(final)),
        flooded_cell_count=int(np.sum(final > 0.10)),
        persistence_cell_seconds=float(np.sum(persist)),
        exposure_meter_seconds=float(np.sum(exposure)),
    )


def compare_d8_dinfinity() -> dict[str, float]:
    grid = Grid(nx=40, ny=40, dx=30.0, dy=30.0)
    bed = synthetic_flat_bowl(grid)
    d8 = D8Routing().route(bed)
    dinf = DInfinityRouting().route(bed)
    return {
        "d8_max_accumulation": float(np.max(d8.flow_accumulation)),
        "dinfinity_max_accumulation": float(np.max(dinf.flow_accumulation)),
        "d8_outfall_unique": float(len(set(zip(d8.outfall_i.ravel().tolist(), d8.outfall_j.ravel().tolist())))),
        "dinfinity_outfall_unique": float(len(set(zip(dinf.outfall_i.ravel().tolist(), dinf.outfall_j.ravel().tolist())))),
    }

