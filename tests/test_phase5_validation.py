from ohie.validation.analytical import run_all_analytical_validations
from ohie.validation.historical.benchmarks import (
    gorakhpur_intervention_approximation,
    rann_gadkabet_approximation,
    yamuna_boundary_approximation,
)
from ohie.validation.sensitivity import run_all_sensitivity


def test_all_analytical_validations_pass():
    results = run_all_analytical_validations()
    assert all(item.passed for item in results)


def test_sensitivity_harness_runs_and_reports_stability():
    results = run_all_sensitivity()
    assert set(results) == {"manning", "resolution", "timestep", "rainfall", "intervention"}
    assert all(item.stable for group in ["manning", "resolution", "timestep", "rainfall"] for item in results[group])


def test_historical_approximations_run_and_disclose_limitations():
    for fn in [rann_gadkabet_approximation, yamuna_boundary_approximation, gorakhpur_intervention_approximation]:
        result = fn()
        assert "not calibrated" in result.limitations.lower()
        assert result.metrics

