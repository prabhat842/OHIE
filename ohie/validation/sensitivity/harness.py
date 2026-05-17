from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ohie import DiffusiveWaveFV, DiffusiveWaveParams, Grid
from ohie.hydro.boundaries import RainfallBoundary
from ohie.interventions import DetentionBasin
from ohie.scenarios import run_intervention_scenario


@dataclass(frozen=True)
class SensitivityResult:
    parameter: str
    value: float
    max_depth_m: float
    flooded_cells: int
    volume_m3: float
    mass_error: float
    stable: bool


def _bed(grid: Grid) -> np.ndarray:
    x = np.linspace(0.0, 1.0, grid.nx)[:, None]
    y = np.linspace(0.0, 1.0, grid.ny)[None, :]
    return 0.03 * x + 0.02 * y - 0.18 * np.exp(-(((x - 0.55) ** 2 + (y - 0.45) ** 2) / 0.02))


def _run_case(parameter: str, value: float, *, grid: Grid | None = None, rain_mm_hr: float = 40.0, manning_n: float = 0.05, dt: float = 2.0) -> SensitivityResult:
    grid = grid or Grid(nx=35, ny=35, dx=30.0, dy=30.0)
    solver = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=dt, manning_n=manning_n))
    solver.initialize(_bed(grid), h0=0.0)
    solver.add_boundary(RainfallBoundary((rain_mm_hr / 1000.0) / 3600.0))
    try:
        solver.run(1200.0, dt=dt)
        finite = bool(np.isfinite(solver.h).all())
        mass_error = solver.mass_balance_error_fraction()
        stable = finite and mass_error < 0.05
        return SensitivityResult(parameter, value, float(np.max(solver.h)), int(np.sum(solver.h > 0.1)), solver.total_volume(), mass_error, stable)
    except Exception:
        return SensitivityResult(parameter, value, float("nan"), -1, float("nan"), float("inf"), False)


def manning_sensitivity(values=(0.025, 0.04, 0.06, 0.09)) -> list[SensitivityResult]:
    return [_run_case("manning_n", float(v), manning_n=float(v)) for v in values]


def resolution_sensitivity(values=(10.0, 30.0, 90.0)) -> list[SensitivityResult]:
    out = []
    for dx in values:
        extent = 1200.0
        n = max(8, int(extent / dx))
        out.append(_run_case("resolution_m", float(dx), grid=Grid(nx=n, ny=n, dx=float(dx), dy=float(dx))))
    return out


def timestep_sensitivity(values=(0.5, 1.0, 2.0, 5.0, 10.0)) -> list[SensitivityResult]:
    return [_run_case("dt_s", float(v), dt=float(v)) for v in values]


def rainfall_sensitivity(values=(10.0, 25.0, 50.0, 75.0)) -> list[SensitivityResult]:
    return [_run_case("rain_mm_hr", float(v), rain_mm_hr=float(v)) for v in values]


def intervention_sensitivity(values=(0.5, 1.0, 2.0)) -> list[dict[str, float]]:
    grid = Grid(nx=35, ny=35, dx=30.0, dy=30.0)
    out = []
    for depth in values:
        solver = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=2.0, manning_n=0.05))
        solver.initialize(_bed(grid), h0=0.0)
        solver.add_boundary(RainfallBoundary((40.0 / 1000.0) / 3600.0))
        result = run_intervention_scenario(solver, [DetentionBasin(19, 16, depth_m=float(depth), radius_cells=3)], t_end_s=1200.0, dt_s=2.0)
        out.append(
            {
                "parameter": "detention_depth_m",
                "value": float(depth),
                "flooded_area_reduction_m2": result.comparison.flooded_area_reduction_m2,
                "volume_reduction_m3": result.comparison.volume_reduction_m3,
                "mass_error": result.mass_balance_error_fraction,
            }
        )
    return out


def run_all_sensitivity() -> dict[str, list]:
    return {
        "manning": manning_sensitivity(),
        "resolution": resolution_sensitivity(),
        "timestep": timestep_sensitivity(),
        "rainfall": rainfall_sensitivity(),
        "intervention": intervention_sensitivity(),
    }

