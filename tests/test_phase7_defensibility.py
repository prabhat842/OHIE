import numpy as np

from ohie import DiffusiveWaveFV, DiffusiveWaveParams, Grid
from ohie.interventions import CulvertResize, Pump
from ohie.validation.compound_forcing import compare_overwrite_vs_flux_coupling
from ohie.validation.failure_cases import run_all_failure_cases


def test_phase7_compound_forcing_comparison_runs():
    result = compare_overwrite_vs_flux_coupling()
    assert result.confidence in {"Medium for showing behavioral difference; Low for river-urban calibration", "Medium for behavioral difference; Low for river-urban calibration"}
    assert result.comparison["overwrite_mass_error"] >= 0.0
    assert result.comparison["flux_mass_error"] >= 0.0
    assert result.comparison["boundary_volume_delta_m3"] != 0.0


def test_phase7_failure_suite_runs():
    results = run_all_failure_cases()
    assert len(results) == 4
    assert all(item.confidence_limit for item in results)


def test_coupler_backed_interventions_keep_compatibility_without_routing():
    grid = Grid(nx=10, ny=10, dx=20.0, dy=20.0)
    bed = np.ones(grid.shape) * (0.01 * grid.dx)
    solver = DiffusiveWaveFV(grid, DiffusiveWaveParams(dt_max=1.0, manning_n=0.05))
    solver.initialize(bed, h0=0.1)
    pump = Pump(3, 3, rate_m3s=0.1)
    culvert = CulvertResize(3, 3, area_m2=1.0)
    pump.apply(solver, routing=None)
    culvert.apply(solver, routing=None)
    assert solver.mass.boundary != 0.0
