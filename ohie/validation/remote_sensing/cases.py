from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ohie import DiffusiveWaveFV, DiffusiveWaveParams, Grid
from ohie.hydro.boundaries import RainfallBoundary
from ohie.validation.remote_sensing.metrics import flooded_area_agreement, intersection_over_union, observed_overlap


DATA_ROOT = Path(__file__).resolve().parents[3] / "ohie-data"


@dataclass(frozen=True)
class RemoteSensingResult:
    name: str
    dataset: str
    assumptions: str
    limitations: str
    confidence: str
    observed: str
    metrics: dict[str, float]


def proxy_observation_comparison(data_root: Path = DATA_ROOT) -> RemoteSensingResult:
    terrain = np.load(data_root / "real_terrain" / "flat_terrain_small.npz", allow_pickle=False)
    obs = np.load(data_root / "remote_sensing" / "observed_water_mask_small.npz", allow_pickle=False)
    bed = np.asarray(terrain["bed"], dtype=np.float64)
    observed_mask = np.asarray(obs["observed_mask"], dtype=bool)
    grid = Grid(nx=bed.shape[0], ny=bed.shape[1], dx=float(terrain["dx_m"]), dy=float(terrain["dy_m"]))

    solver = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=2.0, manning_n=0.055, slope_cap=0.05))
    solver.initialize(bed, h0=0.0)
    solver.add_boundary(RainfallBoundary((35.0 / 1000.0) / 3600.0))
    solver.run(2 * 3600.0, dt=2.0)
    simulated_mask = solver.h > 0.02

    iou = intersection_over_union(simulated_mask, observed_mask)
    overlap = observed_overlap(simulated_mask, observed_mask)
    area_agreement = flooded_area_agreement(simulated_mask, observed_mask)
    return RemoteSensingResult(
        name="proxy_observed_water_mask_small",
        dataset=str(data_root / "remote_sensing" / "observed_water_mask_small.npz"),
        assumptions="proxy comparison only; observed mask is a local historical flood-output mask, not raw SAR/NDWI classification",
        limitations="not calibrated; no event rainfall match; no sensor uncertainty; no geolocation error model",
        confidence="Low",
        observed=f"IoU={iou:.3f}, observed_overlap={overlap:.3f}, area_agreement={area_agreement:.3f}",
        metrics={
            "iou": iou,
            "overlap_percent": overlap * 100.0,
            "flooded_area_agreement": area_agreement,
            "simulated_flooded_cells": float(np.sum(simulated_mask)),
            "observed_flooded_cells": float(np.sum(observed_mask)),
        },
    )
