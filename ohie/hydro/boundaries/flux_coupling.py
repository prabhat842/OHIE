from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np


@dataclass(frozen=True)
class FluxCoupledRiverBoundary:
    """Approximate river-to-floodplain exchange using a flux coupling law.

    This is intentionally weaker than a full coupled river-urban solver, but it
    is more defensible than directly overwriting cell depths because exchange is
    driven by head difference and capped by available volume.
    """

    mask: np.ndarray
    stage_m: float | Callable[[float], float]
    exchange_coeff_m2_per_s: float = 2.5e-6
    max_exchange_m3s: float | None = None
    name: str = "flux_coupled_river"

    def apply(self, solver, t_s: float, dt_s: float) -> None:
        if solver.bed is None or solver.h is None:
            return
        mask = np.asarray(self.mask, dtype=bool)
        if not np.any(mask):
            return
        stage = float(self.stage_m(t_s) if callable(self.stage_m) else self.stage_m)
        dt_s = max(float(dt_s), 1.0e-9)
        domain_head = solver.bed[mask] + solver.h[mask]
        head_diff = stage - domain_head
        q = self.exchange_coeff_m2_per_s * head_diff * solver.grid.cell_area
        if self.max_exchange_m3s is not None:
            q = np.clip(q, -float(self.max_exchange_m3s), float(self.max_exchange_m3s))

        # Do not remove more water than is present in the masked cells.
        available_outflow = solver.h[mask] * solver.grid.cell_area / dt_s
        q = np.where(q < 0.0, np.maximum(q, -available_outflow), q)
        source = np.zeros_like(solver.h, dtype=np.float64)
        source[mask] = q / solver.grid.cell_area
        if solver.source_rate is None:
            solver.source_rate = source
        else:
            solver.source_rate += source
        solver.mass.boundary += float(np.sum(q) * dt_s)

