from __future__ import annotations

from typing import Protocol


class BoundaryCondition(Protocol):
    """Protocol for external forcing or hydraulic boundary models."""

    name: str

    def apply(self, solver, t_s: float, dt_s: float) -> None:
        """Modify solver fields in-place before a timestep."""

