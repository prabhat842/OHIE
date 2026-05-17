from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from ohie.interventions.couplers.base import HydraulicCoupler, exchange_q


@dataclass(frozen=True)
class DrainUpgradeCoupler:
    """Approximate culvert / drain conveyance upgrade between two cells."""

    upstream: tuple[int, int]
    downstream: tuple[int, int]
    area_m2: float
    discharge_coeff: float = 0.70
    bidirectional: bool = True
    name: str = "drain_upgrade_coupler"

    def apply(self, solver, t_s: float, dt_s: float) -> None:
        if solver.bed is None or solver.h is None or solver.source_rate is None:
            return
        ui, uj = self.upstream
        di, dj = self.downstream
        eta_u = solver.bed[ui, uj] + solver.h[ui, uj]
        eta_d = solver.bed[di, dj] + solver.h[di, dj]
        head = float(eta_u - eta_d)
        if head < 0.0 and not self.bidirectional:
            return
        sign = 1.0 if head >= 0.0 else -1.0
        q = sign * self.discharge_coeff * self.area_m2 * (2.0 * solver.params.g * abs(head)) ** 0.5
        exchange_q(solver, self.upstream, self.downstream, q, dt_s)


@dataclass(frozen=True)
class PumpCoupler:
    """Rate-limited exchange between an intake and an outfall cell."""

    intake: tuple[int, int]
    outfall: tuple[int, int]
    max_rate_m3s: float
    shutoff_head_m: float = 3.0
    name: str = "pump_coupler"

    def apply(self, solver, t_s: float, dt_s: float) -> None:
        if solver.bed is None or solver.h is None or solver.source_rate is None:
            return
        ii, ij = self.intake
        oi, oj = self.outfall
        eta_i = solver.bed[ii, ij] + solver.h[ii, ij]
        eta_o = solver.bed[oi, oj] + solver.h[oi, oj]
        static_head = max(0.0, float(eta_o - eta_i))
        factor = max(0.0, 1.0 - static_head / max(1.0e-9, self.shutoff_head_m))
        q = self.max_rate_m3s * factor
        exchange_q(solver, self.intake, self.outfall, q, dt_s)


@dataclass(frozen=True)
class RetentionCoupler:
    """Approximate storage-release exchange between a flooded cell and a basin cell."""

    upstream: tuple[int, int]
    storage: tuple[int, int]
    storage_capacity_m3: float
    storage_time_scale_s: float = 3600.0
    release_rate_m3s: float = 0.0
    discharge_coeff: float = 0.60
    name: str = "retention_coupler"

    def apply(self, solver, t_s: float, dt_s: float) -> None:
        if solver.bed is None or solver.h is None or solver.source_rate is None:
            return
        ui, uj = self.upstream
        si, sj = self.storage
        eta_u = solver.bed[ui, uj] + solver.h[ui, uj]
        eta_s = solver.bed[si, sj] + solver.h[si, sj]
        head = float(eta_u - eta_s)
        if head <= 0.0:
            # Controlled return flow from storage toward the upstream cell.
            q_release = min(self.release_rate_m3s, float(solver.h[si, sj] * solver.grid.cell_area / max(dt_s, 1.0e-9)))
            exchange_q(solver, self.storage, self.upstream, q_release, dt_s)
            return
        head_factor = min(1.0, max(0.0, head))
        q = self.discharge_coeff * (self.storage_capacity_m3 / max(self.storage_time_scale_s, 1.0e-9)) * head_factor
        q = min(q, float(solver.h[ui, uj] * solver.grid.cell_area / max(dt_s, 1.0e-9)))
        exchange_q(solver, self.upstream, self.storage, q, dt_s)


@dataclass(frozen=True)
class WeirCoupler:
    """Broad-crested weir exchange between two cells."""

    upstream: tuple[int, int]
    downstream: tuple[int, int]
    crest_elevation_m: float
    width_m: float
    discharge_coeff: float = 1.60
    name: str = "weir_coupler"

    def apply(self, solver, t_s: float, dt_s: float) -> None:
        if solver.bed is None or solver.h is None or solver.source_rate is None:
            return
        ui, uj = self.upstream
        di, dj = self.downstream
        eta_u = solver.bed[ui, uj] + solver.h[ui, uj]
        eta_d = solver.bed[di, dj] + solver.h[di, dj]
        if eta_u < eta_d:
            ui, uj, di, dj = di, dj, ui, uj
            eta_u, eta_d = eta_d, eta_u
        head = max(0.0, float(eta_u - self.crest_elevation_m))
        if head <= 0.0:
            return
        q = self.discharge_coeff * self.width_m * head**1.5
        exchange_q(solver, (ui, uj), (di, dj), q, dt_s)


@dataclass(frozen=True)
class GateCoupler:
    """Controlled gate wrapping a culvert-like opening."""

    upstream: tuple[int, int]
    downstream: tuple[int, int]
    max_area_m2: float
    opening_fraction: float | Callable[[float], float]
    discharge_coeff: float = 0.70
    name: str = "gate_coupler"

    def apply(self, solver, t_s: float, dt_s: float) -> None:
        opening = self.opening_fraction(t_s) if callable(self.opening_fraction) else self.opening_fraction
        opening = min(1.0, max(0.0, float(opening)))
        if opening <= 0.0:
            return
        DrainUpgradeCoupler(
            upstream=self.upstream,
            downstream=self.downstream,
            area_m2=self.max_area_m2 * opening,
            discharge_coeff=self.discharge_coeff,
            bidirectional=True,
            name=self.name,
        ).apply(solver, t_s, dt_s)
