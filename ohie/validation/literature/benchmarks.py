from __future__ import annotations

from dataclasses import dataclass

from ohie.validation.analytical import run_all_analytical_validations
from ohie.validation.historical.benchmarks import gorakhpur_intervention_approximation, yamuna_boundary_approximation
from ohie.validation.real_terrain import flat_terrain_case


@dataclass(frozen=True)
class LiteratureBenchmark:
    benchmark: str
    literature_behavior: str
    ohie_behavior: str
    confidence: str
    limitation: str


def literature_behavior_table() -> list[LiteratureBenchmark]:
    analytical = {item.test: item for item in run_all_analytical_validations()}
    flat = flat_terrain_case()
    yamuna = yamuna_boundary_approximation()
    gorakhpur = gorakhpur_intervention_approximation()
    return [
        LiteratureBenchmark(
            benchmark="Closed basin conservation",
            literature_behavior="Closed-basin rainfall storage should conserve mass apart from explicitly represented losses.",
            ohie_behavior=(
                f"mass_error={analytical['closed_basin_mass_conservation'].metrics['mass_error']:.3e}; "
                f"pass={analytical['closed_basin_mass_conservation'].passed}"
            ),
            confidence="High",
            limitation="Constrained synthetic case; does not validate real-world roughness, infiltration, or drainage.",
        ),
        LiteratureBenchmark(
            benchmark="Bowl filling and spill threshold",
            literature_behavior="Depressions should fill and persist before overflow or recovery.",
            ohie_behavior=f"observed={analytical['bowl_depression_filling'].observed}",
            confidence="High",
            limitation="Idealized bowl; no sub-grid sewer or soil storage behavior.",
        ),
        LiteratureBenchmark(
            benchmark="Flat terrain routing",
            literature_behavior="Low-gradient terrain should show slow routing, sensitivity to flow-direction assumptions, and stagnation pockets.",
            ohie_behavior=(
                f"max_persistence={flat.metrics['max_persistence_s']:.1f}s; "
                f"DInfinity_split_fraction={flat.metrics['dinfinity_split_fraction']:.3f}"
            ),
            confidence="Medium",
            limitation="Uses small local derived terrain chip; not a calibrated Rann/NCR benchmark.",
        ),
        LiteratureBenchmark(
            benchmark="River stage boundary influence",
            literature_behavior="A high receiving-water stage can increase adjacent inundation and persistence where drainage is suppressed.",
            ohie_behavior=f"observed={yamuna.observed}",
            confidence="Medium",
            limitation="Boundary is prescribed stage on a mask; no measured hydrograph or 1D/2D river coupling.",
        ),
        LiteratureBenchmark(
            benchmark="Storage attenuation",
            literature_behavior="Added storage and conveyance interventions should reduce at least one meaningful flooding metric without hiding tradeoffs.",
            ohie_behavior=f"mixed response observed: {gorakhpur.observed}",
            confidence="Low",
            limitation="Interventions are simplified physics objects and the current approximation can trade lower volume for larger shallow extent; no cost calibration or engineered drainage network.",
        ),
    ]
