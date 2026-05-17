import numpy as np

from ohie import DiffusiveWaveFV, DiffusiveWaveParams, Grid
from ohie.interventions import DetentionBasin, Pump
from ohie.scenarios import run_intervention_scenario


def test_intervention_scenario_reduces_flooded_area_and_volume():
    grid = Grid(nx=30, ny=30, dx=20.0, dy=20.0)
    x = np.linspace(0.0, 1.0, grid.nx)[:, None]
    y = np.linspace(0.0, 1.0, grid.ny)[None, :]
    bed = 0.02 * x + 0.02 * y
    bed -= 0.2 * np.exp(-(((x - 0.5) ** 2 + (y - 0.5) ** 2) / 0.02))
    solver = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=2.0, manning_n=0.05))
    solver.initialize(bed, h0=0.0)
    solver.set_forcing(rain_rate=(50.0 / 1000.0) / 3600.0, infil_rate=1.0e-9)

    result = run_intervention_scenario(
        solver,
        [DetentionBasin(15, 15, depth_m=1.0, radius_cells=3), Pump(15, 15, rate_m3s=0.5)],
        t_end_s=1800.0,
        dt_s=2.0,
    )

    assert result.effects
    assert result.comparison.flooded_area_reduction_m2 > 0.0
    assert result.comparison.volume_reduction_m3 > 0.0
    assert result.mass_balance_error_fraction < 0.01
