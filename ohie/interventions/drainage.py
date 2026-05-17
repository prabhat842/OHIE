from __future__ import annotations

from dataclasses import dataclass

from ohie.interventions.base import InterventionEffect
from ohie.interventions.couplers.flow import DrainUpgradeCoupler


@dataclass(frozen=True)
class ChannelCarve:
    row: int
    col: int
    max_steps: int = 100
    carve_depth_m: float = 0.4
    manning_n: float = 0.03
    cost_per_cell: float = 50_000.0
    name: str = "channel_carve"

    def apply(self, solver, routing=None) -> InterventionEffect:
        if routing is None:
            raise ValueError("ChannelCarve requires a routing network")
        path = routing.path_to_outfall(self.row, self.col, max_steps=self.max_steps)
        changed = solver.lower_roughness_path(path, self.manning_n, self.carve_depth_m)
        return InterventionEffect(
            intervention_type=self.name,
            location=(self.row, self.col),
            changed_cells=changed,
            cost_proxy=changed * self.cost_per_cell,
            note="Creates a preferential drainage corridor to the terrain-derived outfall.",
        )


@dataclass(frozen=True)
class CulvertResize:
    row: int
    col: int
    area_m2: float = 4.0
    discharge_coeff: float = 0.70
    local_sink_mps: float = 2.0e-6
    radius_cells: int = 1
    cost_proxy: float = 2_000_000.0
    name: str = "culvert_resize"

    def apply(self, solver, routing=None) -> InterventionEffect:
        if routing is None:
            path = [(self.row, self.col), (self.row, min(self.col + 1, solver.grid.ny - 1))]
        else:
            path = routing.path_to_outfall(self.row, self.col, max_steps=max(2, self.radius_cells + 1))
        upstream = path[0]
        downstream = path[1] if len(path) > 1 else upstream
        coupler = DrainUpgradeCoupler(
            upstream=upstream,
            downstream=downstream,
            area_m2=self.area_m2,
            discharge_coeff=self.discharge_coeff,
            bidirectional=True,
        )
        coupler.apply(solver, 0.0, 1.0)
        capacity = self.discharge_coeff * self.area_m2 * (2.0 * solver.params.g * 0.75) ** 0.5
        return InterventionEffect(
            intervention_type=self.name,
            location=(self.row, self.col),
            changed_cells=(2 * self.radius_cells + 1) ** 2,
            flow_capacity_m3s=capacity,
            cost_proxy=self.cost_proxy,
            note="Approximates added conveyance at a bottleneck as a hydraulic exchange coupler.",
        )
