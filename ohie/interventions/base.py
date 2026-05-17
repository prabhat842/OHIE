from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class InterventionEffect:
    intervention_type: str
    location: tuple[int, int]
    changed_cells: int
    storage_m3: float = 0.0
    flow_capacity_m3s: float = 0.0
    cost_proxy: float = 0.0
    note: str = ""


class Intervention(Protocol):
    name: str

    def apply(self, solver, routing=None) -> InterventionEffect:
        """Modify solver physics in-place."""

