from __future__ import annotations

from ohie.interventions.base import InterventionEffect
from ohie.scenarios.compare import ScenarioComparison


def summarize_effects(effects: list[InterventionEffect], comparison: ScenarioComparison) -> list[str]:
    lines = []
    for effect in effects:
        if effect.storage_m3 > 0:
            lines.append(
                f"{effect.intervention_type} near cell {effect.location} adds about "
                f"{effect.storage_m3:.0f} m3 of storage."
            )
        elif effect.flow_capacity_m3s > 0:
            lines.append(
                f"{effect.intervention_type} near cell {effect.location} adds about "
                f"{effect.flow_capacity_m3s:.1f} m3/s of drainage capacity."
            )
        else:
            lines.append(f"{effect.intervention_type} near cell {effect.location}: {effect.note}")
    lines.append(comparison.planner_summary())
    return lines

