from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ScenarioComparison:
    baseline_max_depth_m: float
    intervention_max_depth_m: float
    max_depth_reduction_m: float
    flooded_area_reduction_m2: float
    volume_reduction_m3: float
    mean_depth_reduction_m: float
    threshold_m: float

    def planner_summary(self) -> str:
        if self.max_depth_reduction_m >= 0.0:
            peak_text = f"reduces peak depth by {self.max_depth_reduction_m:.2f} m"
        else:
            peak_text = (
                f"increases local peak depth by {abs(self.max_depth_reduction_m):.2f} m, "
                "which can happen when storage intentionally concentrates water"
            )
        area_text = "reduces" if self.flooded_area_reduction_m2 >= 0 else "increases"
        return (
            f"Intervention scenario {peak_text} and {area_text} flooded area by "
            f"{abs(self.flooded_area_reduction_m2):.0f} m2 above {self.threshold_m:.2f} m."
        )


def compare_depths(
    baseline_h: np.ndarray,
    intervention_h: np.ndarray,
    *,
    cell_area_m2: float,
    threshold_m: float = 0.10,
) -> ScenarioComparison:
    base = np.asarray(baseline_h, dtype=np.float64)
    alt = np.asarray(intervention_h, dtype=np.float64)
    if base.shape != alt.shape:
        raise ValueError("baseline and intervention depth rasters must have the same shape")
    delta = base - alt
    return ScenarioComparison(
        baseline_max_depth_m=float(np.max(base)),
        intervention_max_depth_m=float(np.max(alt)),
        max_depth_reduction_m=float(np.max(base) - np.max(alt)),
        flooded_area_reduction_m2=float((np.sum(base > threshold_m) - np.sum(alt > threshold_m)) * cell_area_m2),
        volume_reduction_m3=float(np.sum(delta) * cell_area_m2),
        mean_depth_reduction_m=float(np.mean(delta)),
        threshold_m=threshold_m,
    )
