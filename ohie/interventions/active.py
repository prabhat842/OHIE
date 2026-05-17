from __future__ import annotations

from dataclasses import dataclass

from ohie.interventions.base import InterventionEffect
from ohie.interventions.couplers.flow import PumpCoupler


@dataclass(frozen=True)
class Pump:
    row: int
    col: int
    rate_m3s: float = 1.5
    radius_cells: int = 1
    cost_proxy: float = 15_000_000.0
    name: str = "pump"

    def apply(self, solver, routing=None) -> InterventionEffect:
        patch_cells = (2 * self.radius_cells + 1) ** 2
        if routing is None:
            outfall = (self.row, min(self.col + self.radius_cells + 1, solver.grid.ny - 1))
        else:
            outfall = routing.outfall(self.row, self.col)
        coupler = PumpCoupler(intake=(self.row, self.col), outfall=outfall, max_rate_m3s=self.rate_m3s)
        coupler.apply(solver, 0.0, 1.0)
        return InterventionEffect(
            intervention_type=self.name,
            location=(self.row, self.col),
            changed_cells=patch_cells,
            flow_capacity_m3s=self.rate_m3s,
            cost_proxy=self.cost_proxy,
            note="Actively moves water through a hydraulic coupler to a routed outfall.",
        )
