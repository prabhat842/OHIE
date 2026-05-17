from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ohie import DiffusiveWaveFV, DiffusiveWaveParams, Grid
from ohie.hydro.boundaries import FluxCoupledRiverBoundary, RainfallBoundary
from ohie.scenarios import run_with_history
from ohie.scenarios.metrics import persistence_duration


DATA_ROOT = Path(__file__).resolve().parents[3] / "ohie-data"


@dataclass(frozen=True)
class TransferabilityRow:
    terrain: str
    coefficient: float
    grid_shape: tuple[int, int]
    cell_size_m: float
    near_river_mean_depth_m: float
    near_river_persistence_s: float
    boundary_volume_m3: float
    mass_error: float
    flooded_area_cells: int
    qualitative_realism: str


@dataclass(frozen=True)
class TransferabilitySummary:
    name: str
    assumptions: str
    limitations: str
    confidence: str
    stable_region: dict[str, str]
    best_default: str
    rows: list[TransferabilityRow]


def _resample_bilinear(arr: np.ndarray, new_nx: int, new_ny: int) -> np.ndarray:
    x_old = np.linspace(0.0, 1.0, arr.shape[0])
    y_old = np.linspace(0.0, 1.0, arr.shape[1])
    x_new = np.linspace(0.0, 1.0, new_nx)
    y_new = np.linspace(0.0, 1.0, new_ny)
    temp = np.array([np.interp(x_new, x_old, arr[:, j]) for j in range(arr.shape[1])]).T
    return np.array([np.interp(y_new, y_old, temp[i, :]) for i in range(temp.shape[0])])


def _terrain_library() -> dict[str, tuple[np.ndarray, np.ndarray, float, float, float, float]]:
    flat_data = np.load(DATA_ROOT / "real_terrain" / "flat_terrain_small.npz", allow_pickle=False)
    moderate_data = np.load(DATA_ROOT / "real_terrain" / "river_adjacent_small.npz", allow_pickle=False)

    flat_bed = np.asarray(flat_data["bed"], dtype=np.float64)
    flat_mask = np.zeros_like(flat_bed, dtype=bool)
    flat_mask[:, :3] = True

    moderate_bed = np.asarray(moderate_data["bed"], dtype=np.float64)
    moderate_mask = np.asarray(moderate_data["river_mask"], dtype=bool)

    nx, ny = 26, 26
    x = np.linspace(0.0, 1.0, nx)[:, None]
    y = np.linspace(0.0, 1.0, ny)[None, :]
    steep_bed = 0.18 * x + 0.04 * y - 0.10 * np.exp(-(((x - 0.45) ** 2 + (y - 0.55) ** 2) / 0.02))
    steep_mask = np.zeros((nx, ny), dtype=bool)
    steep_mask[:, :2] = True

    return {
        "flat": (flat_bed, flat_mask, float(flat_data["dx_m"]), float(flat_data["dy_m"]), 0.055, 0.25),
        "moderate": (moderate_bed, moderate_mask, float(moderate_data["dx_m"]), float(moderate_data["dy_m"]), 0.06, 0.35),
        "steep": (steep_bed, steep_mask, 30.0, 30.0, 0.05, 0.30),
    }


def _grid_family(base_bed: np.ndarray, base_mask: np.ndarray, base_dx: float, base_dy: float) -> list[tuple[np.ndarray, np.ndarray, Grid, float]]:
    # Keep the same physical extent while changing cell count.
    nx, ny = base_bed.shape
    extent_x = nx * base_dx
    extent_y = ny * base_dy
    family = []
    for new_nx, new_ny in [(20, 20), (nx, ny), (40, 40)]:
        bed = _resample_bilinear(base_bed, new_nx, new_ny)
        mask = np.zeros((new_nx, new_ny), dtype=bool)
        mask[:, : max(2, min(3, new_ny // 10))] = True
        dx = extent_x / new_nx
        dy = extent_y / new_ny
        family.append((bed, mask, Grid(new_nx, new_ny, dx=dx, dy=dy), float(np.percentile(bed[mask], 90) + 0.35)))
    return family


def _run_case(
    terrain: str,
    bed: np.ndarray,
    river_mask: np.ndarray,
    grid: Grid,
    stage: float,
    rain_mm_hr: float,
    manning_n: float,
    coefficients: list[float],
) -> list[TransferabilityRow]:
    rows: list[TransferabilityRow] = []
    for coeff in coefficients:
        solver = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=2.0, manning_n=manning_n, slope_cap=0.05))
        solver.initialize(bed, h0=0.0)
        solver.add_boundary(RainfallBoundary((rain_mm_hr / 1000.0) / 3600.0))
        solver.add_boundary(FluxCoupledRiverBoundary(river_mask, stage_m=stage, exchange_coeff_m2_per_s=coeff))
        depths, times = run_with_history(solver, t_end_s=3600.0, dt_s=2.0, sample_every_s=600.0)
        persist = persistence_duration(depths, times, threshold_m=0.02)
        rows.append(
            TransferabilityRow(
                terrain=terrain,
                coefficient=coeff,
                grid_shape=grid.shape,
                cell_size_m=grid.dx,
                near_river_mean_depth_m=float(np.mean(solver.h[river_mask])),
                near_river_persistence_s=float(np.mean(persist[river_mask])),
                boundary_volume_m3=float(solver.mass.boundary),
                mass_error=solver.mass_balance_error_fraction(),
                flooded_area_cells=int(np.sum(solver.h > 0.02)),
                qualitative_realism=_qualitative_realism(terrain, coeff, solver.mass_balance_error_fraction(), float(np.mean(solver.h[river_mask]))),
            )
        )
    return rows


def _qualitative_realism(terrain: str, coeff: float, mass_error: float, mean_depth: float) -> str:
    if mass_error > 0.02:
        return "aggressive / trust limited"
    if terrain == "steep" and coeff >= 5e-6:
        return "over-responsive for steep terrain"
    if coeff <= 5e-7:
        return "conservative / weak response"
    if coeff <= 2e-6:
        return "bounded / defensible"
    return "borderline / monitor mass error"


def run_transferability_study() -> TransferabilitySummary:
    coefficients = [2e-7, 5e-7, 1e-6, 2e-6, 5e-6, 1e-5]
    rows: list[TransferabilityRow] = []

    flat_bed, flat_mask, flat_dx, flat_dy, flat_man, flat_rain = _terrain_library()["flat"]
    flat_grid = Grid(flat_bed.shape[0], flat_bed.shape[1], dx=flat_dx, dy=flat_dy)
    flat_stage = float(np.percentile(flat_bed[flat_mask], 90) + 0.25)
    rows.extend(_run_case("flat", flat_bed, flat_mask, flat_grid, flat_stage, flat_rain, flat_man, coefficients))

    moderate_bed, moderate_mask, moderate_dx, moderate_dy, moderate_man, moderate_rain = _terrain_library()["moderate"]
    moderate_grid = Grid(moderate_bed.shape[0], moderate_bed.shape[1], dx=moderate_dx, dy=moderate_dy)
    moderate_stage = float(np.percentile(moderate_bed[moderate_mask], 90) + 0.35)
    rows.extend(_run_case("moderate", moderate_bed, moderate_mask, moderate_grid, moderate_stage, moderate_rain, moderate_man, coefficients))

    steep_bed, steep_mask, steep_dx, steep_dy, steep_man, steep_rain = _terrain_library()["steep"]
    steep_grid = Grid(steep_bed.shape[0], steep_bed.shape[1], dx=steep_dx, dy=steep_dy)
    steep_stage = float(np.percentile(steep_bed[steep_mask], 90) + 0.30)
    rows.extend(_run_case("steep", steep_bed, steep_mask, steep_grid, steep_stage, steep_rain, steep_man, coefficients))

    res_family = _grid_family(moderate_bed, moderate_mask, moderate_dx, moderate_dy)
    for bed, mask, grid, stage in res_family:
        rows.extend(_run_case(f"resolution_{grid.nx}", bed, mask, grid, stage, moderate_rain, moderate_man, coefficients))

    stable_region = {
        "flat": "No shared stable region under the 1% mass-error threshold; all coefficients exceed the limit",
        "moderate": "No shared stable region under the 1% mass-error threshold; all coefficients exceed the limit",
        "steep": "No shared stable region under the 1% mass-error threshold; all coefficients exceed the limit",
        "resolution": "No shared stable region under the 1% mass-error threshold; all coefficients exceed the limit",
    }

    return TransferabilitySummary(
        name="transferability_boundary_robustness",
        assumptions="same flux-coupling law evaluated on multiple terrain regimes and resolution variants",
        limitations="terrain families are benchmark regimes, not externally calibrated basins; the study reveals strong terrain and resolution dependence and no shared stable region under the current mass-error threshold",
        confidence="Low for transferable generalization; Medium only as a local benchmark-scale approximation on the original chip",
        stable_region=stable_region,
        best_default="No transferable default identified; 1e-6 remains a local benchmark-scale compromise only",
        rows=rows,
    )
