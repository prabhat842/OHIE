import numpy as np

from ohie import DiffusiveWaveFV, DiffusiveWaveParams, Grid
from ohie.hydro.boundaries import HydrographBoundary, RainfallBoundary, RiverStageBoundary
from ohie.interventions import CulvertCoupler
from ohie.scenarios import run_with_history
from ohie.scenarios.metrics import flood_exposure, persistence_duration, recovery_time, stagnation_index, time_to_peak
from ohie.terrain.routing import D8Routing, DInfinityRouting


def test_dinfinity_splits_flow_on_planar_diagonal_slope():
    bed = np.add.outer(np.linspace(1.0, 0.0, 8), np.linspace(1.0, 0.0, 8))
    network = DInfinityRouting().route(bed)
    assert network.weights.shape == (8, 8, 2)
    assert np.max(network.flow_accumulation) > 1.0
    assert D8Routing().route(bed).weights.shape == (8, 8, 1)


def test_rainfall_hydrograph_and_river_stage_boundaries_add_water():
    grid = Grid(nx=12, ny=12, dx=10.0, dy=10.0)
    solver = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=5.0))
    solver.initialize(np.zeros(grid.shape), h0=0.0)
    solver.add_boundary(RainfallBoundary(1.0e-6))
    mask = np.zeros(grid.shape, dtype=bool)
    mask[0, :] = True
    solver.add_boundary(HydrographBoundary(mask, discharge_m3s=lambda _t: 0.2))
    river = np.zeros(grid.shape, dtype=bool)
    river[:, -1] = True
    solver.add_boundary(RiverStageBoundary(river, stage_m=0.15))
    solver.run(20.0, dt=5.0)
    assert solver.total_volume() > 0.0
    assert np.allclose(solver.h[:, -1], 0.15)


def test_temporal_metrics_shapes_and_values():
    depths = np.array(
        [
            [[0.0, 0.2], [0.0, 0.0]],
            [[0.1, 0.3], [0.0, 0.2]],
            [[0.0, 0.0], [0.0, 0.2]],
        ]
    )
    times = np.array([0.0, 10.0, 20.0])
    assert persistence_duration(depths, times, threshold_m=0.1).shape == (2, 2)
    assert flood_exposure(depths, times).sum() > 0.0
    assert time_to_peak(depths, times)[0, 1] == 10.0
    assert recovery_time(depths, times, threshold_m=0.1)[1, 1] == 20.0
    assert stagnation_index(depths, times).shape == (2, 2)


def test_structure_coupler_moves_water_between_cells():
    grid = Grid(nx=5, ny=5, dx=10.0, dy=10.0)
    solver = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=1.0))
    solver.initialize(np.zeros(grid.shape), h0=0.0)
    solver.h[1, 1] = 1.0
    solver.mass.initial = solver.total_volume()
    solver.add_structure(CulvertCoupler((1, 1), (1, 2), area_m2=0.2))
    solver.step(1.0)
    assert solver.h[1, 2] > 0.0
    assert solver.mass_balance_error_fraction() < 0.05


def test_run_with_history_collects_depth_series():
    grid = Grid(nx=8, ny=8, dx=10.0, dy=10.0)
    solver = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=5.0))
    solver.initialize(np.zeros(grid.shape), h0=0.0)
    solver.add_boundary(RainfallBoundary(1.0e-6))
    depths, times = run_with_history(solver, t_end_s=20.0, dt_s=5.0, sample_every_s=10.0)
    assert depths.ndim == 3
    assert times.shape[0] == depths.shape[0]

