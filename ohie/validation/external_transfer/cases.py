from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio

from ohie import DiffusiveWaveFV, DiffusiveWaveParams, Grid
from ohie.hydro.boundaries import FluxCoupledRiverBoundary, RainfallBoundary
from ohie.scenarios import run_with_history
from ohie.scenarios.metrics import persistence_duration


DATA_ROOT = Path(__file__).resolve().parents[3] / "ohie-data"
OPEN_DEM_PATH = DATA_ROOT / "external_transfer" / "brahmaputra_dhakuakhana_z12.tif"


@dataclass(frozen=True)
class ExternalTransferSensitivityRow:
    coefficient: float
    boundary_volume_m3: float
    mass_error: float
    near_edge_mean_depth_m: float
    near_edge_persistence_s: float
    flooded_area_cells: int


@dataclass(frozen=True)
class ExternalTransferResult:
    name: str
    site: str
    study_window: str
    dataset: str
    assumptions: str
    limitations: str
    confidence: str
    classification: str
    default_row: dict[str, float | str]
    baseline_row: dict[str, float | str]
    sensitivity_rows: list[ExternalTransferSensitivityRow]


def _load_dem(path: Path = OPEN_DEM_PATH) -> tuple[np.ndarray, Grid, dict[str, float], str]:
    with rasterio.open(path) as src:
        bed = src.read(1).astype(np.float64)
        nodata = src.nodata
        if nodata is not None:
            bed = np.where(bed == nodata, np.nan, bed)
        dx, dy = src.res
        grid = Grid(src.width, src.height, dx=float(dx), dy=float(dy))
        bounds = {
            "left": float(src.bounds.left),
            "bottom": float(src.bounds.bottom),
            "right": float(src.bounds.right),
            "top": float(src.bounds.top),
        }
        crs = src.crs.to_string() if src.crs else "unknown"
    return bed, grid, bounds, crs


def _edge_band(shape: tuple[int, int], edge: str, width: int = 3) -> np.ndarray:
    mask = np.zeros(shape, dtype=bool)
    if edge == "north":
        mask[:width, :] = True
    elif edge == "south":
        mask[-width:, :] = True
    elif edge == "west":
        mask[:, :width] = True
    elif edge == "east":
        mask[:, -width:] = True
    else:
        raise ValueError(edge)
    return mask


def _lowest_edge(bed: np.ndarray) -> tuple[str, np.ndarray]:
    edge_scores = {}
    for edge in ("north", "south", "west", "east"):
        band = _edge_band(bed.shape, edge)
        edge_scores[edge] = float(np.nanmedian(bed[band]))
    chosen = min(edge_scores, key=edge_scores.get)
    return chosen, _edge_band(bed.shape, chosen)


def _sanitize_bed(bed: np.ndarray) -> np.ndarray:
    if np.isnan(bed).any():
        filled = bed.copy()
        finite = np.isfinite(filled)
        fill_value = float(np.nanmedian(filled))
        filled[~finite] = fill_value
        return filled
    return bed


def _run_solver(
    bed: np.ndarray,
    grid: Grid,
    river_mask: np.ndarray,
    stage_m: float,
    rainfall_mm_hr: float,
    manning_n: float,
    coefficient: float | None,
) -> tuple[DiffusiveWaveFV, np.ndarray, np.ndarray]:
    solver = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=2.0, manning_n=manning_n, slope_cap=0.05))
    solver.initialize(bed, h0=0.0)
    solver.add_boundary(RainfallBoundary((rainfall_mm_hr / 1000.0) / 3600.0))
    if coefficient is not None:
        solver.add_boundary(FluxCoupledRiverBoundary(river_mask, stage_m=stage_m, exchange_coeff_m2_per_s=coefficient))
    depths, times = run_with_history(solver, t_end_s=3600.0, dt_s=2.0, sample_every_s=600.0)
    return solver, depths, times


def _summarize(solver: DiffusiveWaveFV, depths: np.ndarray, times: np.ndarray, edge_mask: np.ndarray) -> dict[str, float | str]:
    persist = persistence_duration(depths, times, threshold_m=0.02)
    mean_depth = float(np.mean(solver.h[edge_mask]))
    mean_persistence = float(np.mean(persist[edge_mask]))
    return {
        "near_edge_mean_depth_m": mean_depth,
        "near_edge_persistence_s": mean_persistence,
        "boundary_volume_m3": float(solver.mass.boundary),
        "mass_error": float(solver.mass_balance_error_fraction()),
        "flooded_area_cells": int(np.sum(solver.h > 0.02)),
        "max_depth_m": float(solver.max_depth()),
        "total_volume_m3": float(solver.total_volume()),
    }


def _classify(default_row: dict[str, float | str], sensitivity_rows: list[ExternalTransferSensitivityRow]) -> str:
    mass_error = float(default_row["mass_error"])
    mean_depth = float(default_row["near_edge_mean_depth_m"])
    flooded = int(default_row["flooded_area_cells"])
    boundary = float(default_row["boundary_volume_m3"])
    if mass_error > 0.05:
        return "Structural failure: the coefficient does not transfer cleanly to the external open-DEM floodplain under the current boundary law."
    if mass_error <= 0.02 and boundary > 0 and flooded > 0 and mean_depth > 0.0:
        if sensitivity_rows and max(row.mass_error for row in sensitivity_rows) - min(row.mass_error for row in sensitivity_rows) < 0.02:
            return "Partial transfer: the approximation is usable, but terrain regime still matters."
        return "Local failure: the external case improves relative to the benchmark family, but the coefficient remains terrain dependent."
    return "Partial transfer: the approximation responds, but the operating region remains narrow."


def run_external_transfer_case(data_root: Path = DATA_ROOT) -> ExternalTransferResult:
    path = data_root / "external_transfer" / "brahmaputra_dhakuakhana_z12.tif"
    bed, grid, bounds, crs = _load_dem(path)
    bed = _sanitize_bed(bed)

    edge_name, river_mask = _lowest_edge(bed)
    edge_band = bed[river_mask]
    stage = float(np.nanpercentile(edge_band, 90) + 0.35)

    baseline_solver, baseline_depths, baseline_times = _run_solver(
        bed=bed,
        grid=grid,
        river_mask=river_mask,
        stage_m=stage,
        rainfall_mm_hr=25.0,
        manning_n=0.055,
        coefficient=None,
    )
    default_solver, default_depths, default_times = _run_solver(
        bed=bed,
        grid=grid,
        river_mask=river_mask,
        stage_m=stage,
        rainfall_mm_hr=25.0,
        manning_n=0.055,
        coefficient=1e-6,
    )

    baseline_row = _summarize(baseline_solver, baseline_depths, baseline_times, river_mask)
    default_row = _summarize(default_solver, default_depths, default_times, river_mask)

    sensitivity_rows: list[ExternalTransferSensitivityRow] = []
    if float(default_row["mass_error"]) > 0.02 or float(default_row["flooded_area_cells"]) == 0:
        for coeff in [2e-7, 5e-7, 1e-6, 2e-6]:
            solver, depths, times = _run_solver(
                bed=bed,
                grid=grid,
                river_mask=river_mask,
                stage_m=stage,
                rainfall_mm_hr=25.0,
                manning_n=0.055,
                coefficient=coeff,
            )
            summary = _summarize(solver, depths, times, river_mask)
            sensitivity_rows.append(
                ExternalTransferSensitivityRow(
                    coefficient=coeff,
                    boundary_volume_m3=float(summary["boundary_volume_m3"]),
                    mass_error=float(summary["mass_error"]),
                    near_edge_mean_depth_m=float(summary["near_edge_mean_depth_m"]),
                    near_edge_persistence_s=float(summary["near_edge_persistence_s"]),
                    flooded_area_cells=int(summary["flooded_area_cells"]),
                )
            )

    classification = _classify(default_row, sensitivity_rows)
    confidence = "Low for calibration; Medium for transfer-failure diagnosis"
    if "Partial transfer" in classification:
        confidence = "Low for calibration; Medium for qualitative transfer behavior"

    return ExternalTransferResult(
        name="brahmaputra_dhakuakhana_open_dem_transfer",
        site="Dhakuakhana floodplain, Brahmaputra north-bank sector, Assam",
        study_window="AWS Terrain Tiles z12 tile 3122/1726 (~9.8 km square at the chosen location)",
        dataset=str(path),
        assumptions=(
            f"open DEM tile from AWS Terrain Tiles; river-adjacent edge chosen as the lowest-median border ({edge_name}); "
            "uniform rainfall forcing; no calibration; no engineered drainage network"
        ),
        limitations=(
            "open-DEM-only transfer test; river stage is a simplified edge forcing; no measured hydrograph; "
            "no SAR/NDWI/EMS validation; no embankment or channel morphology model"
        ),
        confidence=confidence,
        classification=classification,
        baseline_row=baseline_row,
        default_row=default_row,
        sensitivity_rows=sensitivity_rows,
    )
