from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

import numpy as np


Edge = Literal["west", "east", "south", "north"]


@dataclass(frozen=True)
class HydrographBoundary:
    """Time-varying inflow hydrograph applied to a mask."""

    mask: np.ndarray
    discharge_m3s: Callable[[float], float]
    name: str = "hydrograph"

    def apply(self, solver, t_s: float, dt_s: float) -> None:
        mask = np.asarray(self.mask, dtype=bool)
        cells = int(np.sum(mask))
        if cells == 0:
            return
        q = max(0.0, float(self.discharge_m3s(t_s)))
        source = np.zeros(solver.grid.shape, dtype=float)
        source[mask] = q / (cells * solver.grid.cell_area)
        if solver.source_rate is None:
            solver.source_rate = source
        else:
            solver.source_rate += source


@dataclass(frozen=True)
class FluxBoundary:
    """Specified discharge into an edge, distributed across edge cells."""

    edge: Edge
    discharge_m3s: float | Callable[[float], float]
    name: str = "flux"

    def apply(self, solver, t_s: float, dt_s: float) -> None:
        q = float(self.discharge_m3s(t_s) if callable(self.discharge_m3s) else self.discharge_m3s)
        slc, cells = _edge_slice_and_count(self.edge, solver.grid.nx, solver.grid.ny)
        source = np.zeros(solver.grid.shape, dtype=float)
        source[slc] = q / (cells * solver.grid.cell_area)
        if solver.source_rate is None:
            solver.source_rate = source
        else:
            solver.source_rate += source


def _edge_slice_and_count(edge: Edge, nx: int, ny: int):
    if edge == "west":
        return (0, slice(None)), ny
    if edge == "east":
        return (-1, slice(None)), ny
    if edge == "south":
        return (slice(None), 0), nx
    if edge == "north":
        return (slice(None), -1), nx
    raise ValueError(f"unknown edge: {edge}")

