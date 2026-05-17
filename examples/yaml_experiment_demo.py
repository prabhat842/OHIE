from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ohie.config import load_experiment_config
from ohie.scenarios import run_intervention_scenario


def main() -> None:
    cfg = load_experiment_config(Path(__file__).parent / "configs" / "flat_terrain.yaml")
    solver = cfg.build_solver()
    result = run_intervention_scenario(
        solver,
        cfg.build_interventions(),
        t_end_s=60 * 60,
        dt_s=solver.params.dt_max,
    )
    print(result.comparison.planner_summary())
    print(f"mass_balance_error_fraction={result.mass_balance_error_fraction:.4f}")


if __name__ == "__main__":
    main()

