from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

import numpy as np


Edge = Literal["west", "east", "south", "north"]


@dataclass(frozen=True)
class RiverStageBoundary:
    """Dynamic stage forcing over a river/channel mask.

    Stage is interpreted as water-surface elevation, not water depth.
    """

    mask: np.ndarray
    stage_m: float | Callable[[float], float]
    name: str = "river_stage"

    def apply(self, solver, t_s: float, dt_s: float) -> None:
        if solver.bed is None or solver.h is None:
            return
        stage = float(self.stage_m(t_s) if callable(self.stage_m) else self.stage_m)
        mask = np.asarray(self.mask, dtype=bool)
        before = float(np.sum(solver.h[mask]) * solver.grid.cell_area)
        target_h = np.maximum(0.0, stage - solver.bed[mask])
        solver.h[mask] = target_h
        after = float(np.sum(solver.h[mask]) * solver.grid.cell_area)
        solver.mass.boundary += after - before

    def after_step(self, solver, t_s: float, dt_s: float) -> None:
        self.apply(solver, t_s, dt_s)


@dataclass(frozen=True)
class FixedHeadBoundary:
    """Static water-surface elevation along a model edge."""

    edge: Edge
    stage_m: float
    relaxation: float = 1.0
    name: str = "fixed_head"

    def apply(self, solver, t_s: float, dt_s: float) -> None:
        if solver.bed is None or solver.h is None:
            return
        slc = _edge_slice(self.edge)
        before = float(np.sum(solver.h[slc]) * solver.grid.cell_area)
        target = np.maximum(0.0, float(self.stage_m) - solver.bed[slc])
        relax = min(1.0, max(0.0, float(self.relaxation)))
        solver.h[slc] = (1.0 - relax) * solver.h[slc] + relax * target
        after = float(np.sum(solver.h[slc]) * solver.grid.cell_area)
        solver.mass.boundary += after - before

    def after_step(self, solver, t_s: float, dt_s: float) -> None:
        self.apply(solver, t_s, dt_s)


def _edge_slice(edge: Edge):
    if edge == "west":
        return (0, slice(None))
    if edge == "east":
        return (-1, slice(None))
    if edge == "south":
        return (slice(None), 0)
    if edge == "north":
        return (slice(None), -1)
    raise ValueError(f"unknown edge: {edge}")
