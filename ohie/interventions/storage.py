from __future__ import annotations

from dataclasses import dataclass

from ohie.interventions.base import InterventionEffect
from ohie.interventions.couplers.flow import RetentionCoupler


@dataclass(frozen=True)
class DetentionBasin:
    row: int
    col: int
    depth_m: float = 1.5
    radius_cells: int = 3
    infiltration_mps: float = 2.0e-6
    cost_per_m3: float = 2800.0
    name: str = "detention_basin"

    def apply(self, solver, routing=None) -> InterventionEffect:
        # Keep the terrain edit, but also initialize a coupler-backed storage
        # interpretation so the intervention is no longer just bed surgery.
        retention = RetentionCoupler(
            upstream=(self.row, self.col),
            storage=(self.row, min(self.col + self.radius_cells + 1, solver.grid.ny - 1)),
            storage_capacity_m3=max(1.0, (2 * self.radius_cells + 1) ** 2 * solver.grid.cell_area * self.depth_m),
            release_rate_m3s=0.0,
        )
        storage = solver.carve_bed_patch(self.row, self.col, self.depth_m, self.radius_cells)
        solver.add_infiltration_patch(self.row, self.col, self.infiltration_mps, self.radius_cells)
        retention.apply(solver, 0.0, 1.0)
        changed = (2 * self.radius_cells + 1) ** 2
        return InterventionEffect(
            intervention_type=self.name,
            location=(self.row, self.col),
            changed_cells=changed,
            storage_m3=storage,
            cost_proxy=storage * self.cost_per_m3,
            note="Creates local storage by lowering terrain and improving infiltration.",
        )
