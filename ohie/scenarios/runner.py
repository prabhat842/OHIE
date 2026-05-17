from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from ohie.interventions.base import Intervention, InterventionEffect
from ohie.scenarios.compare import ScenarioComparison, compare_depths
from ohie.terrain.routing_d8 import build_d8_network


@dataclass
class ScenarioResult:
    baseline_depth: np.ndarray
    intervention_depth: np.ndarray
    effects: list[InterventionEffect]
    comparison: ScenarioComparison
    mass_balance_error_fraction: float


def run_with_history(solver, *, t_end_s: float, dt_s: float, sample_every_s: float) -> tuple[np.ndarray, np.ndarray]:
    """Run a solver and collect depth snapshots for temporal metrics."""

    depths = []
    times = []
    next_sample = solver.time_s
    while solver.time_s < t_end_s - 1.0e-9:
        solver.step(min(dt_s, t_end_s - solver.time_s))
        if solver.time_s >= next_sample - 1.0e-9:
            depths.append(solver.h.copy())
            times.append(solver.time_s)
            next_sample += sample_every_s
    return np.asarray(depths), np.asarray(times)


def run_intervention_scenario(
    solver,
    interventions: Iterable[Intervention],
    *,
    t_end_s: float,
    dt_s: float | None = None,
    threshold_m: float = 0.10,
) -> ScenarioResult:
    """Run baseline and intervention simulations from the same initial state."""

    if solver.bed is None:
        raise RuntimeError("solver must be initialized before running a scenario")

    baseline = solver.clone()
    baseline.run(t_end_s, dt=dt_s)
    baseline_h = baseline.h.copy()

    intervention_solver = solver.clone()
    routing = build_d8_network(intervention_solver.bed)
    effects = [item.apply(intervention_solver, routing=routing) for item in interventions]
    intervention_solver.run(t_end_s, dt=dt_s)
    intervention_h = intervention_solver.h.copy()

    comparison = compare_depths(
        baseline_h,
        intervention_h,
        cell_area_m2=solver.grid.cell_area,
        threshold_m=threshold_m,
    )
    return ScenarioResult(
        baseline_depth=baseline_h,
        intervention_depth=intervention_h,
        effects=effects,
        comparison=comparison,
        mass_balance_error_fraction=intervention_solver.mass_balance_error_fraction(),
    )
