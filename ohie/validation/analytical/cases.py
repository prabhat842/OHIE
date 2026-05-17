from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ohie import DiffusiveWaveFV, DiffusiveWaveParams, Grid
from ohie.hydro.boundaries import RainfallBoundary
from ohie.scenarios import run_with_history
from ohie.scenarios.metrics import persistence_duration
from ohie.terrain import find_blue_spots
from ohie.terrain.routing import D8Routing, DInfinityRouting


@dataclass(frozen=True)
class ValidationResult:
    test: str
    expected: str
    observed: str
    passed: bool
    metrics: dict[str, float]


def flat_plane_rainfall() -> ValidationResult:
    grid = Grid(nx=30, ny=20, dx=20.0, dy=20.0)
    bed = np.linspace(1.0, 0.0, grid.nx)[:, None] * np.ones(grid.shape)
    solver = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=2.0, manning_n=0.05))
    solver.initialize(bed, h0=0.0)
    solver.add_boundary(RainfallBoundary((25.0 / 1000.0) / 3600.0))
    solver.run(900.0, dt=2.0)
    upper = float(np.sum(solver.h[:10, :]))
    lower = float(np.sum(solver.h[-10:, :]))
    mass_error = solver.mass_balance_error_fraction()
    passed = lower > upper and mass_error < 0.01 and np.isfinite(solver.h).all()
    return ValidationResult(
        "flat_plane_rainfall",
        "water moves downslope, remains stable, and conserves mass",
        f"lower_sum={lower:.3f}, upper_sum={upper:.3f}, mass_error={mass_error:.4g}",
        passed,
        {"lower_depth_sum": lower, "upper_depth_sum": upper, "mass_error": mass_error},
    )


def bowl_depression_filling() -> ValidationResult:
    grid = Grid(nx=40, ny=40, dx=20.0, dy=20.0)
    x = np.linspace(-1.0, 1.0, grid.nx)[:, None]
    y = np.linspace(-1.0, 1.0, grid.ny)[None, :]
    bed = 0.08 * (x * x + y * y)
    spots = find_blue_spots(bed, min_depth_m=0.001)
    solver = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=2.0, manning_n=0.06))
    solver.initialize(bed, h0=0.0)
    solver.add_boundary(RainfallBoundary((35.0 / 1000.0) / 3600.0))
    depths, times = run_with_history(solver, t_end_s=1800.0, dt_s=2.0, sample_every_s=300.0)
    center_depth = float(solver.h[grid.nx // 2, grid.ny // 2])
    edge_depth = float(np.mean([solver.h[0, :].mean(), solver.h[-1, :].mean(), solver.h[:, 0].mean(), solver.h[:, -1].mean()]))
    persistence = float(np.max(persistence_duration(depths, times, threshold_m=0.02)))
    passed = center_depth > edge_depth and persistence > 0.0 and solver.mass_balance_error_fraction() < 0.01
    return ValidationResult(
        "bowl_depression_filling",
        "water accumulates in the depression and flood persistence is captured",
        f"center_depth={center_depth:.3f}, edge_depth={edge_depth:.3f}, max_persistence={persistence:.1f}s",
        passed,
        {"center_depth": center_depth, "edge_depth": edge_depth, "max_persistence_s": persistence, "blue_spots": float(len(spots))},
    )


def dam_break_approximation() -> ValidationResult:
    grid = Grid(nx=60, ny=10, dx=10.0, dy=10.0)
    bed = np.zeros(grid.shape)
    solver = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=0.5, manning_n=0.035))
    solver.initialize(bed, h0=0.0)
    solver.h[:10, :] = 1.0
    solver.mass.initial = solver.total_volume()
    solver.run(120.0, dt=0.5)
    front_cells = np.where(np.max(solver.h, axis=1) > 0.02)[0]
    front = int(front_cells.max()) if len(front_cells) else 0
    mass_error = solver.mass_balance_error_fraction()
    passed = front > 10 and solver.h[:10, :].mean() < 1.0 and mass_error < 0.02 and np.isfinite(solver.h).all()
    return ValidationResult(
        "dam_break_approximation",
        "initial water pulse propagates outward with approximate mass conservation",
        f"front_cell={front}, upstream_mean={solver.h[:10, :].mean():.3f}, mass_error={mass_error:.4g}",
        passed,
        {"front_cell": float(front), "upstream_mean_depth": float(solver.h[:10, :].mean()), "mass_error": mass_error},
    )


def steep_vs_flat_routing() -> ValidationResult:
    grid = Grid(nx=35, ny=35, dx=30.0, dy=30.0)
    steep = np.linspace(5.0, 0.0, grid.nx)[:, None] * np.ones(grid.shape)
    x = np.linspace(-1.0, 1.0, grid.nx)[:, None]
    y = np.linspace(-1.0, 1.0, grid.ny)[None, :]
    flat = 0.02 * x + 0.02 * y - 0.05 * np.exp(-(x * x + y * y) / 0.1)
    d8_steep = D8Routing().route(steep)
    d8_flat = D8Routing().route(flat)
    dinf_flat = DInfinityRouting().route(flat)
    d8_peak_delta = float(abs(np.max(d8_steep.flow_accumulation) - np.max(d8_flat.flow_accumulation)))
    routing_difference = float(np.sum(np.abs(d8_flat.flow_accumulation - dinf_flat.flow_accumulation)))
    passed = d8_peak_delta > 0.0 and routing_difference > 0.0
    return ValidationResult(
        "steep_vs_flat_routing",
        "routing responds differently to steep and flat terrain; D8 and D-Infinity differ on flat terrain",
        f"d8_peak_delta={d8_peak_delta:.3f}, d8_dinf_flat_diff={routing_difference:.3f}",
        passed,
        {"d8_peak_delta": d8_peak_delta, "d8_dinf_flat_diff": routing_difference},
    )


def closed_basin_mass_conservation() -> ValidationResult:
    grid = Grid(nx=25, ny=25, dx=10.0, dy=10.0)
    x = np.linspace(-1.0, 1.0, grid.nx)[:, None]
    y = np.linspace(-1.0, 1.0, grid.ny)[None, :]
    bed = 0.1 * (x * x + y * y)
    solver = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=1.0, manning_n=0.05))
    solver.initialize(bed, h0=0.1)
    solver.run(600.0, dt=1.0)
    mass_error = solver.mass_balance_error_fraction()
    passed = mass_error < 1.0e-10 and np.isfinite(solver.h).all()
    return ValidationResult(
        "closed_basin_mass_conservation",
        "closed basin without forcing conserves water volume",
        f"mass_error={mass_error:.4g}, final_volume={solver.total_volume():.3f}",
        passed,
        {"mass_error": mass_error, "final_volume": solver.total_volume()},
    )


def run_all_analytical_validations() -> list[ValidationResult]:
    return [
        flat_plane_rainfall(),
        bowl_depression_filling(),
        dam_break_approximation(),
        steep_vs_flat_routing(),
        closed_basin_mass_conservation(),
    ]
