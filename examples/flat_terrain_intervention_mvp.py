from __future__ import annotations

import numpy as np
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ohie import DiffusiveWaveFV, DiffusiveWaveParams, Grid
from ohie.explain import summarize_effects
from ohie.interventions import ChannelCarve, DetentionBasin, Pump
from ohie.scenarios import run_intervention_scenario


def main() -> None:
    grid = Grid(nx=60, ny=60, dx=30.0, dy=30.0)
    x = np.linspace(0.0, 1.0, grid.nx)[:, None]
    y = np.linspace(0.0, 1.0, grid.ny)[None, :]

    # Very low slope, with a central blue spot and an embankment-like ridge.
    bed = 0.05 * x + 0.02 * y
    bed -= 0.25 * np.exp(-(((x - 0.42) ** 2 + (y - 0.48) ** 2) / 0.01))
    bed[32:34, :] += 0.20

    solver = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=2.0, manning_n=0.045))
    solver.initialize(bed, h0=0.0)
    solver.set_forcing(rain_rate=(45.0 / 1000.0) / 3600.0, infil_rate=1.0e-9)

    result = run_intervention_scenario(
        solver,
        interventions=[
            DetentionBasin(row=25, col=28, depth_m=1.2, radius_cells=4),
            ChannelCarve(row=31, col=28, max_steps=40, carve_depth_m=0.25),
            Pump(row=25, col=28, rate_m3s=0.8),
        ],
        t_end_s=90 * 60,
        dt_s=2.0,
    )

    for line in summarize_effects(result.effects, result.comparison):
        print(line)
    print(f"Mass balance error fraction: {result.mass_balance_error_fraction:.4f}")


if __name__ == "__main__":
    main()
