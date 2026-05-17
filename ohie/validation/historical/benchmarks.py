from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ohie import DiffusiveWaveFV, DiffusiveWaveParams, Grid
from ohie.hydro.boundaries import RainfallBoundary, RiverStageBoundary
from ohie.interventions import ChannelCarve, DetentionBasin, Pump
from ohie.scenarios import run_intervention_scenario, run_with_history
from ohie.scenarios.metrics import persistence_duration, stagnation_index
from ohie.terrain import find_blue_spots
from ohie.terrain.routing import DInfinityRouting


@dataclass(frozen=True)
class HistoricalBenchmarkResult:
    name: str
    inputs: str
    assumptions: str
    limitations: str
    observed: str
    metrics: dict[str, float]


def rann_gadkabet_approximation() -> HistoricalBenchmarkResult:
    grid = Grid(nx=60, ny=60, dx=30.0, dy=30.0)
    x = np.linspace(0.0, 1.0, grid.nx)[:, None]
    y = np.linspace(0.0, 1.0, grid.ny)[None, :]
    bed = 0.0005 * x + 0.0003 * y
    bed -= 0.08 * np.exp(-(((x - 0.55) ** 2 + (y - 0.45) ** 2) / 0.015))
    bed[18, 18] -= 0.04
    bed[44, 38] -= 0.035
    bed[33:35, :] += 0.12
    routing = DInfinityRouting().route(bed)
    spots = find_blue_spots(bed, min_depth_m=0.01)
    solver = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=2.0, manning_n=0.025))
    solver.initialize(bed, h0=0.0)
    solver.add_boundary(RainfallBoundary((35.0 / 1000.0) / 3600.0))
    depths, times = run_with_history(solver, t_end_s=6 * 3600.0, dt_s=2.0, sample_every_s=900.0)
    persist = persistence_duration(depths, times, threshold_m=0.05)
    stagnation = stagnation_index(depths, times, threshold_m=0.05)
    north_depth = float(np.mean(solver.h[30:33, :]))
    south_depth = float(np.mean(solver.h[35:38, :]))
    return HistoricalBenchmarkResult(
        name="rann_gadkabet_approximation",
        inputs="synthetic <0.05% slope salt-flat surface, road-ridge barrier, 35 mm/hr 6-hour rainfall",
        assumptions="uses low Manning n=0.025 as salt-flat proxy; no salinity-viscosity physics; no real Gadkabet DEM",
        limitations="not calibrated; no tidal creek network; no SAR comparison; road 754K represented as idealized ridge",
        observed=f"blue_spots={len(spots)}, max_persistence={np.max(persist):.1f}s, north_depth={north_depth:.3f}, south_depth={south_depth:.3f}",
        metrics={
            "blue_spots": float(len(spots)),
            "max_flow_accumulation": float(np.max(routing.flow_accumulation)),
            "max_persistence_s": float(np.max(persist)),
            "mean_stagnation": float(np.mean(stagnation)),
            "ridge_north_depth": north_depth,
            "ridge_south_depth": south_depth,
            "mass_error": solver.mass_balance_error_fraction(),
        },
    )


def yamuna_boundary_approximation() -> HistoricalBenchmarkResult:
    grid = Grid(nx=50, ny=40, dx=30.0, dy=30.0)
    x = np.linspace(0.0, 1.0, grid.nx)[:, None]
    y = np.linspace(0.0, 1.0, grid.ny)[None, :]
    bed = 0.15 * x + 0.02 * y
    river = np.zeros(grid.shape, dtype=bool)
    river[:, 3:5] = True
    outfall_zone = np.zeros(grid.shape, dtype=bool)
    outfall_zone[20:30, 5:10] = True
    base = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=2.0, manning_n=0.05))
    base.initialize(bed, h0=0.0)
    base.add_boundary(RainfallBoundary((30.0 / 1000.0) / 3600.0))
    base.run(1800.0, dt=2.0)

    staged = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=2.0, manning_n=0.05))
    staged.initialize(bed, h0=0.0)
    staged.add_boundary(RainfallBoundary((30.0 / 1000.0) / 3600.0))
    staged.add_boundary(RiverStageBoundary(river, stage_m=0.35))
    depths, times = run_with_history(staged, t_end_s=1800.0, dt_s=2.0, sample_every_s=300.0)
    persist = persistence_duration(depths, times, threshold_m=0.05)
    return HistoricalBenchmarkResult(
        name="yamuna_boundary_approximation",
        inputs="synthetic sloping floodplain, river mask, rainfall, imposed river stage",
        assumptions="river stage is prescribed water-surface elevation; outfall suppression inferred from persistence near river",
        limitations="not calibrated to Yamuna; no SAR mask; no real hydrograph; no pipe outfall network",
        observed=f"base_volume={base.total_volume():.1f}m3, staged_volume={staged.total_volume():.1f}m3, outfall_persistence={np.mean(persist[outfall_zone]):.1f}s",
        metrics={
            "base_volume_m3": base.total_volume(),
            "staged_volume_m3": staged.total_volume(),
            "outfall_mean_persistence_s": float(np.mean(persist[outfall_zone])),
            "mass_error": staged.mass_balance_error_fraction(),
        },
    )


def gorakhpur_intervention_approximation() -> HistoricalBenchmarkResult:
    grid = Grid(nx=45, ny=45, dx=30.0, dy=30.0)
    x = np.linspace(0.0, 1.0, grid.nx)[:, None]
    y = np.linspace(0.0, 1.0, grid.ny)[None, :]
    bed = 0.03 * x + 0.02 * y - 0.16 * np.exp(-(((x - 0.45) ** 2 + (y - 0.55) ** 2) / 0.02))
    solver = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=2.0, manning_n=0.055))
    solver.initialize(bed, h0=0.0)
    solver.add_boundary(RainfallBoundary((45.0 / 1000.0) / 3600.0))
    result = run_intervention_scenario(
        solver,
        [DetentionBasin(20, 25, depth_m=1.2, radius_cells=4), ChannelCarve(22, 25, max_steps=60, carve_depth_m=0.25), Pump(20, 25, rate_m3s=0.5)],
        t_end_s=1800.0,
        dt_s=2.0,
    )
    return HistoricalBenchmarkResult(
        name="gorakhpur_intervention_approximation",
        inputs="synthetic low-gradient municipal terrain with ponding depression and rainfall",
        assumptions="interventions approximate retention pond, drain/channel, and pump from Gorakhpur-style workflow",
        limitations="not calibrated to Gorakhpur DEM; no population/asset exposure; no RFSM/GA reproduction",
        observed=f"flooded_area_reduction={result.comparison.flooded_area_reduction_m2:.1f}m2, volume_reduction={result.comparison.volume_reduction_m3:.1f}m3",
        metrics={
            "flooded_area_reduction_m2": result.comparison.flooded_area_reduction_m2,
            "volume_reduction_m3": result.comparison.volume_reduction_m3,
            "mass_error": result.mass_balance_error_fraction,
        },
    )
