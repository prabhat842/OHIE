from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ohie import DiffusiveWaveFV, DiffusiveWaveParams, Grid
from ohie.hydro.boundaries import FluxCoupledRiverBoundary, RainfallBoundary, RiverStageBoundary
from ohie.scenarios import run_with_history
from ohie.scenarios.metrics import persistence_duration


@dataclass(frozen=True)
class FailureCaseResult:
    case: str
    failure_mode: str
    why_not_trust: str
    observed: str
    confidence_limit: str
    metrics: dict[str, float]


def timestep_instability_proxy() -> FailureCaseResult:
    grid = Grid(nx=30, ny=30, dx=30.0, dy=30.0)
    x = np.linspace(0.0, 1.0, grid.nx)[:, None]
    y = np.linspace(0.0, 1.0, grid.ny)[None, :]
    bed = 0.08 * x + 0.02 * y - 0.22 * np.exp(-(((x - 0.55) ** 2 + (y - 0.45) ** 2) / 0.018))

    fine = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=1.0, manning_n=0.05))
    fine.initialize(bed, h0=0.0)
    fine.add_boundary(RainfallBoundary((45.0 / 1000.0) / 3600.0))
    fine.run(1800.0, dt=1.0)

    coarse = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=20.0, manning_n=0.05))
    coarse.initialize(bed, h0=0.0)
    coarse.add_boundary(RainfallBoundary((45.0 / 1000.0) / 3600.0))
    coarse.run(1800.0, dt=20.0)

    return FailureCaseResult(
        case="timestep_instability_proxy",
        failure_mode="coarse timestep sensitivity",
        why_not_trust="The same terrain and rainfall produce materially different peak depth and flooded-cell counts when the timestep is loosened too far.",
        observed=f"fine_max_depth={fine.max_depth():.3f}m, coarse_max_depth={coarse.max_depth():.3f}m, fine_mass_error={fine.mass_balance_error_fraction():.4g}, coarse_mass_error={coarse.mass_balance_error_fraction():.4g}",
        confidence_limit="Do not trust coarse timesteps in steep or highly ponded terrain without a tighter stability study.",
        metrics={
            "fine_max_depth_m": fine.max_depth(),
            "coarse_max_depth_m": coarse.max_depth(),
            "depth_delta_m": coarse.max_depth() - fine.max_depth(),
            "fine_mass_error": fine.mass_balance_error_fraction(),
            "coarse_mass_error": coarse.mass_balance_error_fraction(),
        },
    )


def terrain_discontinuity_failure() -> FailureCaseResult:
    grid = Grid(nx=35, ny=35, dx=20.0, dy=20.0)
    bed = np.zeros(grid.shape)
    bed[:, 18:] += 1.2
    bed[15:20, 16:19] -= 0.35
    solver = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=2.0, manning_n=0.05))
    solver.initialize(bed, h0=0.0)
    solver.add_boundary(RainfallBoundary((35.0 / 1000.0) / 3600.0))
    depths, times = run_with_history(solver, t_end_s=1800.0, dt_s=2.0, sample_every_s=300.0)
    upstream = float(np.mean(solver.h[:, :15]))
    downstream = float(np.mean(solver.h[:, 20:]))
    step_ratio = upstream / max(1.0e-9, downstream)
    return FailureCaseResult(
        case="terrain_discontinuity_failure",
        failure_mode="abrupt terrain step / discontinuity",
        why_not_trust="A hard elevation break can create a visually convincing but numerically artificial ponding pattern upstream of the discontinuity.",
        observed=f"upstream_mean_depth={upstream:.3f}m, downstream_mean_depth={downstream:.3f}m, step_ratio={step_ratio:.2f}",
        confidence_limit="Do not trust results across unresolved cliffs, cutlines, or DEM stitching artifacts.",
        metrics={
            "upstream_mean_depth_m": upstream,
            "downstream_mean_depth_m": downstream,
            "step_ratio": step_ratio,
            "max_persistence_s": float(np.max(persistence_duration(depths, times, threshold_m=0.02))),
        },
    )


def boundary_breakdown_failure() -> FailureCaseResult:
    grid = Grid(nx=26, ny=26, dx=30.0, dy=30.0)
    x = np.linspace(0.0, 1.0, grid.nx)[:, None]
    y = np.linspace(0.0, 1.0, grid.ny)[None, :]
    bed = 0.02 * x + 0.01 * y
    mask = np.zeros(grid.shape, dtype=bool)
    mask[:, :3] = True
    stage = 0.45

    overwrite = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=2.0, manning_n=0.06))
    overwrite.initialize(bed, h0=0.0)
    overwrite.add_boundary(RainfallBoundary((25.0 / 1000.0) / 3600.0))
    overwrite.add_boundary(RiverStageBoundary(mask, stage_m=stage))
    overwrite.run(1800.0, dt=2.0)

    flux = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=2.0, manning_n=0.06))
    flux.initialize(bed, h0=0.0)
    flux.add_boundary(RainfallBoundary((25.0 / 1000.0) / 3600.0))
    flux.add_boundary(FluxCoupledRiverBoundary(mask, stage_m=stage, exchange_coeff_m2_per_s=1.0e-6))
    flux.run(1800.0, dt=2.0)

    return FailureCaseResult(
        case="boundary_breakdown_failure",
        failure_mode="overwrite-style river boundary",
        why_not_trust="Depth overwrite can produce a large, instantaneous storage change that looks like coupling but is really a boundary imposition.",
        observed=f"overwrite_boundary_m3={overwrite.mass.boundary:.1f}, flux_boundary_m3={flux.mass.boundary:.1f}, overwrite_max_depth={overwrite.max_depth():.3f}m, flux_max_depth={flux.max_depth():.3f}m",
        confidence_limit="Do not use overwrite-stage boundaries for compound forcing claims once flux coupling is available.",
        metrics={
            "overwrite_boundary_m3": overwrite.mass.boundary,
            "flux_boundary_m3": flux.mass.boundary,
            "overwrite_max_depth_m": overwrite.max_depth(),
            "flux_max_depth_m": flux.max_depth(),
            "boundary_volume_delta_m3": overwrite.mass.boundary - flux.mass.boundary,
        },
    )


def poor_parameter_regime_failure() -> FailureCaseResult:
    grid = Grid(nx=35, ny=35, dx=30.0, dy=30.0)
    x = np.linspace(0.0, 1.0, grid.nx)[:, None]
    y = np.linspace(0.0, 1.0, grid.ny)[None, :]
    bed = 0.01 * x + 0.01 * y - 0.18 * np.exp(-(((x - 0.4) ** 2 + (y - 0.55) ** 2) / 0.02))
    solver = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=10.0, manning_n=0.012, slope_cap=0.30))
    solver.initialize(bed, h0=0.0)
    solver.add_boundary(RainfallBoundary((80.0 / 1000.0) / 3600.0))
    solver.run(2400.0, dt=10.0)
    flooded_cells = int(np.sum(solver.h > 0.02))
    return FailureCaseResult(
        case="poor_parameter_regime_failure",
        failure_mode="extreme low-roughness / coarse-limiter regime",
        why_not_trust="The solver becomes too energetic and under-damped when roughness is unrealistically low and slope limiting is relaxed.",
        observed=f"max_depth={solver.max_depth():.3f}m, flooded_cells={flooded_cells}, mass_error={solver.mass_balance_error_fraction():.4g}",
        confidence_limit="Do not interpret results in this parameter regime as design-relevant hydraulics.",
        metrics={
            "max_depth_m": solver.max_depth(),
            "flooded_cells": float(flooded_cells),
            "mass_error": solver.mass_balance_error_fraction(),
        },
    )


def run_all_failure_cases() -> list[FailureCaseResult]:
    return [
        timestep_instability_proxy(),
        terrain_discontinuity_failure(),
        boundary_breakdown_failure(),
        poor_parameter_regime_failure(),
    ]
