from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np

from ohie.hydro.grid import Grid


ArrayLike = float | np.ndarray


@dataclass
class DiffusiveWaveParams:
    """Numerical and hydraulic parameters for the fast DW-FV solver."""

    g: float = 9.81
    manning_n: float = 0.06
    h_min: float = 1.0e-4
    dt_max: float = 1.0
    slope_cap: float = 0.10
    max_depth_change_fraction: float = 0.40


@dataclass
class MassBalance:
    initial: float = 0.0
    rainfall: float = 0.0
    infiltration: float = 0.0
    source: float = 0.0
    boundary: float = 0.0

    def expected(self) -> float:
        return self.initial + self.rainfall - self.infiltration + self.source + self.boundary


@dataclass
class SolverLog:
    time_s: float
    max_depth_m: float
    total_volume_m3: float


@dataclass
class DiffusiveWaveFV:
    """Fast terrain-driven diffusive-wave finite-volume model.

    This is an OHIE extraction of the historical `HRFSolver.mode == "dw_fv"`
    idea. It intentionally starts smaller than the legacy solver: rainfall,
    infiltration, roughness, source/sink patches, and conservative terrain
    routing are first-class; advanced structures and calibrated boundaries are
    added through higher-level OHIE modules.
    """

    grid: Grid
    params: DiffusiveWaveParams = field(default_factory=DiffusiveWaveParams)
    bed: np.ndarray | None = None
    h: np.ndarray | None = None
    roughness_n: np.ndarray | None = None
    rain_rate: ArrayLike = 0.0
    infil_rate: ArrayLike = 0.0
    source_rate: np.ndarray | None = None
    boundaries: list = field(default_factory=list)
    structures: list = field(default_factory=list)
    time_s: float = 0.0
    mass: MassBalance = field(default_factory=MassBalance)

    def initialize(self, bed: np.ndarray, h0: ArrayLike = 0.0) -> None:
        bed_arr = np.asarray(bed, dtype=np.float64)
        if bed_arr.shape != self.grid.shape:
            raise ValueError(f"bed shape {bed_arr.shape} != grid shape {self.grid.shape}")
        self.bed = bed_arr.copy()
        self.h = self._as_field(h0).copy()
        self.h[self.h < 0.0] = 0.0
        self.roughness_n = np.full(self.grid.shape, self.params.manning_n, dtype=np.float64)
        self.source_rate = np.zeros(self.grid.shape, dtype=np.float64)
        self.time_s = 0.0
        self.mass = MassBalance(initial=self.total_volume())

    def clone(self) -> "DiffusiveWaveFV":
        other = DiffusiveWaveFV(self.grid, self.params)
        if self.bed is None or self.h is None:
            return other
        other.initialize(self.bed.copy(), self.h.copy())
        other.roughness_n = None if self.roughness_n is None else self.roughness_n.copy()
        other.rain_rate = self.rain_rate.copy() if isinstance(self.rain_rate, np.ndarray) else self.rain_rate
        other.infil_rate = self.infil_rate.copy() if isinstance(self.infil_rate, np.ndarray) else self.infil_rate
        other.source_rate = None if self.source_rate is None else self.source_rate.copy()
        other.boundaries = list(self.boundaries)
        other.structures = list(self.structures)
        other.time_s = self.time_s
        other.mass = MassBalance(
            initial=self.mass.initial,
            rainfall=self.mass.rainfall,
            infiltration=self.mass.infiltration,
            source=self.mass.source,
            boundary=self.mass.boundary,
        )
        return other

    def set_forcing(
        self,
        *,
        rain_rate: ArrayLike | None = None,
        infil_rate: ArrayLike | None = None,
        roughness_n: ArrayLike | None = None,
        source_rate: np.ndarray | None = None,
    ) -> None:
        self._require_state()
        if rain_rate is not None:
            self.rain_rate = self._as_field(rain_rate) if isinstance(rain_rate, np.ndarray) else float(rain_rate)
        if infil_rate is not None:
            self.infil_rate = self._as_field(infil_rate) if isinstance(infil_rate, np.ndarray) else float(infil_rate)
        if roughness_n is not None:
            self.roughness_n = self._as_field(roughness_n) if isinstance(roughness_n, np.ndarray) else np.full(
                self.grid.shape, float(roughness_n), dtype=np.float64
            )
        if source_rate is not None:
            self.source_rate = self._as_field(source_rate)

    def add_boundary(self, boundary) -> None:
        self.boundaries.append(boundary)

    def add_structure(self, structure) -> None:
        self.structures.append(structure)

    def add_source_patch(self, i: int, j: int, rate_mps: float, radius_cells: int = 0) -> None:
        self._require_state()
        assert self.source_rate is not None
        i0, i1, j0, j1 = self._window(i, j, radius_cells)
        self.source_rate[i0:i1, j0:j1] += float(rate_mps)

    def add_infiltration_patch(self, i: int, j: int, rate_mps: float, radius_cells: int = 0) -> None:
        self._require_state()
        field = self._as_field(self.infil_rate)
        i0, i1, j0, j1 = self._window(i, j, radius_cells)
        field[i0:i1, j0:j1] += float(rate_mps)
        self.infil_rate = field

    def carve_bed_patch(self, i: int, j: int, depth_m: float, radius_cells: int) -> float:
        self._require_state()
        assert self.bed is not None
        i0, i1, j0, j1 = self._window(i, j, radius_cells)
        removed = 0.0
        for ii in range(i0, i1):
            for jj in range(j0, j1):
                r = max(1e-9, ((ii - i) ** 2 + (jj - j) ** 2) ** 0.5 / max(1, radius_cells))
                if r <= 1.0:
                    dz = float(depth_m) * (1.0 - r * r)
                    self.bed[ii, jj] -= dz
                    removed += dz * self.grid.cell_area
        return removed

    def lower_roughness_path(self, path: Iterable[tuple[int, int]], manning_n: float, carve_depth_m: float = 0.0) -> int:
        self._require_state()
        assert self.bed is not None and self.roughness_n is not None
        changed = 0
        for i, j in path:
            if 0 <= i < self.grid.nx and 0 <= j < self.grid.ny:
                self.roughness_n[i, j] = min(self.roughness_n[i, j], float(manning_n))
                if carve_depth_m:
                    self.bed[i, j] -= float(carve_depth_m)
                changed += 1
        return changed

    def step(self, dt: float | None = None) -> None:
        self._require_state()
        assert self.bed is not None and self.h is not None and self.roughness_n is not None
        assert self.source_rate is not None
        dt = min(float(dt if dt is not None else self.params.dt_max), self.params.dt_max)
        dt = max(dt, 1.0e-6)
        if self.boundaries or self.structures:
            # Source boundaries are incremental, so reset them each step before
            # boundary/structure objects add current timestep contributions.
            self.source_rate = np.zeros_like(self.h, dtype=np.float64)
        if self.boundaries:
            for boundary in self.boundaries:
                boundary.apply(self, self.time_s, dt)
        if self.structures:
            if self.source_rate is None:
                self.source_rate = np.zeros_like(self.h, dtype=np.float64)
            for structure in self.structures:
                structure.apply(self, self.time_s, dt)

        h = self.h
        eta = self.bed + h
        qx = self._face_flux(eta[:-1, :], eta[1:, :], h[:-1, :], h[1:, :], self.roughness_n[:-1, :], self.roughness_n[1:, :], self.grid.dx, self.grid.dy, dt)
        qy = self._face_flux(eta[:, :-1], eta[:, 1:], h[:, :-1], h[:, 1:], self.roughness_n[:, :-1], self.roughness_n[:, 1:], self.grid.dy, self.grid.dx, dt)

        dvol = np.zeros_like(h)
        dvol[:-1, :] -= qx
        dvol[1:, :] += qx
        dvol[:, :-1] -= qy
        dvol[:, 1:] += qy

        rain = self._as_field(self.rain_rate)
        infil = np.minimum(self._as_field(self.infil_rate), h / dt + rain + self.source_rate)
        source = self.source_rate
        dvol += (rain - infil + source) * self.grid.cell_area

        h_new = h + (dt * dvol / self.grid.cell_area)
        h_new[h_new < 0.0] = 0.0
        self.h = h_new
        for boundary in self.boundaries:
            after_step = getattr(boundary, "after_step", None)
            if after_step is not None:
                after_step(self, self.time_s + dt, dt)

        area = self.grid.cell_area
        self.mass.rainfall += float(np.sum(rain) * area * dt)
        self.mass.infiltration += float(np.sum(infil) * area * dt)
        self.mass.source += float(np.sum(source) * area * dt)
        self.time_s += dt

    def run(self, t_end: float, dt: float | None = None, output_every: float | None = None) -> list[SolverLog]:
        logs: list[SolverLog] = []
        next_log = self.time_s
        while self.time_s < t_end - 1.0e-9:
            self.step(min(dt or self.params.dt_max, t_end - self.time_s))
            if output_every is not None and self.time_s >= next_log - 1.0e-9:
                logs.append(SolverLog(self.time_s, self.max_depth(), self.total_volume()))
                next_log += output_every
        return logs

    def max_depth(self) -> float:
        self._require_state()
        assert self.h is not None
        return float(np.max(self.h))

    def total_volume(self) -> float:
        self._require_state()
        assert self.h is not None
        return float(np.sum(self.h) * self.grid.cell_area)

    def mass_balance_error_fraction(self) -> float:
        final = self.total_volume()
        expected = self.mass.expected()
        return abs(final - expected) / max(1.0, abs(expected))

    def _face_flux(
        self,
        eta_l: np.ndarray,
        eta_r: np.ndarray,
        h_l: np.ndarray,
        h_r: np.ndarray,
        n_l: np.ndarray,
        n_r: np.ndarray,
        spacing: float,
        face_width: float,
        dt: float,
    ) -> np.ndarray:
        slope = np.clip((eta_l - eta_r) / max(1.0e-9, spacing), -self.params.slope_cap, self.params.slope_cap)
        h_up = np.where(slope >= 0.0, h_l, h_r)
        n = np.maximum(1.0e-4, 0.5 * (n_l + n_r))
        conveyance = (self.params.g ** 0.5 / n) * np.maximum(h_up, 0.0) ** (5.0 / 3.0)
        q_per_width = conveyance * np.sqrt(np.abs(slope)) * np.sign(slope)
        q = q_per_width * face_width
        # Local face draining guard. Interventions can create steep sub-grid
        # depressions; cap each face so one face cannot evacuate an upstream
        # cell faster than the timestep can support.
        cell_area = spacing * face_width
        q_cap = np.maximum(h_up, 0.0) * cell_area / max(dt, 1.0e-9) * 0.25
        return np.clip(q, -q_cap, q_cap)

    def _as_field(self, value: ArrayLike) -> np.ndarray:
        if isinstance(value, np.ndarray):
            arr = np.asarray(value, dtype=np.float64)
            if arr.shape != self.grid.shape:
                raise ValueError(f"field shape {arr.shape} != grid shape {self.grid.shape}")
            return arr
        return np.full(self.grid.shape, float(value), dtype=np.float64)

    def _window(self, i: int, j: int, radius: int) -> tuple[int, int, int, int]:
        r = max(0, int(radius))
        return max(0, i - r), min(self.grid.nx, i + r + 1), max(0, j - r), min(self.grid.ny, j + r + 1)

    def _require_state(self) -> None:
        if self.h is None:
            raise RuntimeError("solver is not initialized")
