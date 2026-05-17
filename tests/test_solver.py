import numpy as np

from ohie import DiffusiveWaveFV, DiffusiveWaveParams, Grid


def test_diffusive_wave_adds_rainfall_volume_on_flat_closed_domain():
    grid = Grid(nx=10, ny=10, dx=10.0, dy=10.0)
    solver = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=5.0))
    solver.initialize(np.zeros(grid.shape), h0=0.0)
    solver.set_forcing(rain_rate=1.0e-5, infil_rate=0.0)
    solver.run(100.0, dt=5.0)
    expected = 1.0e-5 * grid.area * 100.0
    assert abs(solver.total_volume() - expected) / expected < 1.0e-9
    assert solver.mass_balance_error_fraction() < 1.0e-9


def test_water_moves_down_slope():
    grid = Grid(nx=20, ny=10, dx=10.0, dy=10.0)
    bed = np.linspace(1.0, 0.0, grid.nx)[:, None] * np.ones(grid.shape)
    solver = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=1.0))
    solver.initialize(bed, h0=0.0)
    initial = np.zeros(grid.shape)
    initial[2:5, :] = 0.3
    solver.h = initial
    solver.mass.initial = solver.total_volume()
    solver.run(20.0, dt=1.0)
    assert solver.h[8:, :].sum() > 0.0

