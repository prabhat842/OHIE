from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ohie import DiffusiveWaveFV, DiffusiveWaveParams, Grid
from ohie.hydro.boundaries import FluxCoupledRiverBoundary, RainfallBoundary, RiverStageBoundary
from ohie.scenarios import run_with_history
from ohie.scenarios.metrics import persistence_duration


DATA_ROOT = Path(__file__).resolve().parents[3] / "ohie-data"


@dataclass(frozen=True)
class CompoundForcingResult:
    name: str
    assumptions: str
    limitations: str
    confidence: str
    overwrite_observed: str
    flux_observed: str
    comparison: dict[str, float]


def compare_overwrite_vs_flux_coupling(data_root: Path = DATA_ROOT) -> CompoundForcingResult:
    data = np.load(data_root / "real_terrain" / "river_adjacent_small.npz", allow_pickle=False)
    bed = np.asarray(data["bed"], dtype=np.float64)
    river_mask = np.asarray(data["river_mask"], dtype=bool)
    grid = Grid(nx=bed.shape[0], ny=bed.shape[1], dx=float(data["dx_m"]), dy=float(data["dy_m"]))

    stage = float(np.percentile(bed[river_mask], 90) + 0.35)

    overwrite = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=2.0, manning_n=0.06, slope_cap=0.05))
    overwrite.initialize(bed, h0=0.0)
    overwrite.add_boundary(RainfallBoundary((25.0 / 1000.0) / 3600.0))
    overwrite.add_boundary(RiverStageBoundary(river_mask, stage_m=stage))
    overwrite_depths, overwrite_times = run_with_history(overwrite, t_end_s=3600.0, dt_s=2.0, sample_every_s=600.0)

    flux = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=2.0, manning_n=0.06, slope_cap=0.05))
    flux.initialize(bed, h0=0.0)
    flux.add_boundary(RainfallBoundary((25.0 / 1000.0) / 3600.0))
    flux.add_boundary(FluxCoupledRiverBoundary(river_mask, stage_m=stage, exchange_coeff_m2_per_s=1.0e-6))
    flux_depths, flux_times = run_with_history(flux, t_end_s=3600.0, dt_s=2.0, sample_every_s=600.0)

    overwrite_persist = persistence_duration(overwrite_depths, overwrite_times, threshold_m=0.02)
    flux_persist = persistence_duration(flux_depths, flux_times, threshold_m=0.02)
    overwrite_flooded = int(np.sum(overwrite.h > 0.02))
    flux_flooded = int(np.sum(flux.h > 0.02))
    overwrite_mask_mean = float(np.mean(overwrite.h[river_mask]))
    flux_mask_mean = float(np.mean(flux.h[river_mask]))
    return CompoundForcingResult(
        name="overwrite_vs_flux_coupling",
        assumptions="same terrain chip and same prescribed stage; flux-coupled boundary uses head-driven exchange instead of depth overwrite",
        limitations="not a calibrated river model; the river mask is synthetic; exchange coefficient is a defensible approximation, not a field-calibrated conductance",
        confidence="Medium for showing behavioral difference; Low for river-urban calibration",
        overwrite_observed=(
            f"max_depth={overwrite.max_depth():.3f}m, flooded_cells={overwrite_flooded}, "
            f"boundary_volume={overwrite.mass.boundary:.1f}m3, near_river_mean_depth={overwrite_mask_mean:.3f}m, "
            f"near_river_persistence={float(np.mean(overwrite_persist[river_mask])):.1f}s"
        ),
        flux_observed=(
            f"max_depth={flux.max_depth():.3f}m, flooded_cells={flux_flooded}, "
            f"boundary_volume={flux.mass.boundary:.1f}m3, near_river_mean_depth={flux_mask_mean:.3f}m, "
            f"near_river_persistence={float(np.mean(flux_persist[river_mask])):.1f}s"
        ),
        comparison={
            "max_depth_delta_m": overwrite.max_depth() - flux.max_depth(),
            "flooded_cells_delta": float(overwrite_flooded - flux_flooded),
            "boundary_volume_delta_m3": overwrite.mass.boundary - flux.mass.boundary,
            "near_river_mean_depth_delta_m": overwrite_mask_mean - flux_mask_mean,
            "near_river_persistence_delta_s": float(np.mean(overwrite_persist[river_mask]) - np.mean(flux_persist[river_mask])),
            "overwrite_mass_error": overwrite.mass_balance_error_fraction(),
            "flux_mass_error": flux.mass_balance_error_fraction(),
        },
    )
