from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np


@dataclass(frozen=True)
class RainfallBoundary:
    """Spatial and/or temporal rainfall forcing in m/s."""

    rate_mps: float | np.ndarray | Callable[[float], float | np.ndarray]
    name: str = "rainfall"

    def apply(self, solver, t_s: float, dt_s: float) -> None:
        value = self.rate_mps(t_s) if callable(self.rate_mps) else self.rate_mps
        solver.set_forcing(rain_rate=value)


@dataclass(frozen=True)
class SinkBoundary:
    """Controlled drainage or infiltration sink in m/s."""

    rate_mps: float | np.ndarray | Callable[[float], float | np.ndarray]
    name: str = "sink"

    def apply(self, solver, t_s: float, dt_s: float) -> None:
        value = self.rate_mps(t_s) if callable(self.rate_mps) else self.rate_mps
        solver.set_forcing(infil_rate=value)

