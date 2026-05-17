from __future__ import annotations

from typing import Protocol

import numpy as np


class HydraulicCoupler(Protocol):
    """Protocol for first-class hydraulic couplers."""

    name: str

    def apply(self, solver, t_s: float, dt_s: float) -> None:
        """Exchange water or capacity between hydraulic elements in-place."""


def exchange_q(solver, source_cell: tuple[int, int], target_cell: tuple[int, int], q_m3s: float, dt_s: float) -> float:
    """Move volume between two cells while preserving non-negative depth."""

    if solver.h is None or solver.source_rate is None:
        return 0.0
    if q_m3s == 0.0:
        return 0.0
    si, sj = source_cell
    ti, tj = target_cell
    dt_s = max(float(dt_s), 1.0e-9)
    if q_m3s > 0.0:
        q_m3s = min(float(q_m3s), float(solver.h[si, sj] * solver.grid.cell_area / dt_s))
        rate = abs(q_m3s) / solver.grid.cell_area
        solver.source_rate[si, sj] -= rate
        solver.source_rate[ti, tj] += rate
    else:
        q_m3s = max(float(q_m3s), -float(solver.h[ti, tj] * solver.grid.cell_area / dt_s))
        rate = abs(q_m3s) / solver.grid.cell_area
        solver.source_rate[si, sj] += rate
        solver.source_rate[ti, tj] -= rate
    solver.mass.boundary += float(q_m3s) * dt_s
    return float(q_m3s)

