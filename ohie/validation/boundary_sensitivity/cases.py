from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ohie import DiffusiveWaveFV, DiffusiveWaveParams, Grid
from ohie.hydro.boundaries import FluxCoupledRiverBoundary, RainfallBoundary, RiverStageBoundary


DATA_ROOT = Path(__file__).resolve().parents[3] / "ohie-data"


@dataclass(frozen=True)
class BoundarySensitivityRow:
    coefficient: float
    near_river_mean_depth_m: float
    near_river_persistence_s: float
    boundary_volume_m3: float
    mass_error: float


def boundary_coefficient_sweep(data_root: Path = DATA_ROOT) -> list[BoundarySensitivityRow]:
    data = np.load(data_root / "real_terrain" / "river_adjacent_small.npz", allow_pickle=False)
    bed = np.asarray(data["bed"], dtype=np.float64)
    river_mask = np.asarray(data["river_mask"], dtype=bool)
    grid = Grid(nx=bed.shape[0], ny=bed.shape[1], dx=float(data["dx_m"]), dy=float(data["dy_m"]))
    stage = float(np.percentile(bed[river_mask], 90) + 0.35)
    rows: list[BoundarySensitivityRow] = []
    for coeff in [2e-7, 5e-7, 1e-6, 2e-6, 5e-6, 1e-5]:
        solver = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=2.0, manning_n=0.06, slope_cap=0.05))
        solver.initialize(bed, h0=0.0)
        solver.add_boundary(RainfallBoundary((25.0 / 1000.0) / 3600.0))
        solver.add_boundary(FluxCoupledRiverBoundary(river_mask, stage_m=stage, exchange_coeff_m2_per_s=coeff))
        times = []
        depths = []
        next_sample = 0.0
        while solver.time_s < 3600.0 - 1.0e-9:
            solver.step(min(2.0, 3600.0 - solver.time_s))
            if solver.time_s >= next_sample - 1.0e-9:
                depths.append(solver.h.copy())
                times.append(solver.time_s)
                next_sample += 600.0
        depths = np.asarray(depths)
        times = np.asarray(times)
        persist = np.sum((depths > 0.02) * np.diff(times, prepend=times[0])[:, None, None], axis=0)
        rows.append(
            BoundarySensitivityRow(
                coefficient=coeff,
                near_river_mean_depth_m=float(np.mean(solver.h[river_mask])),
                near_river_persistence_s=float(np.mean(persist[river_mask])),
                boundary_volume_m3=float(solver.mass.boundary),
                mass_error=solver.mass_balance_error_fraction(),
            )
        )
    return rows

