from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Grid:
    """Uniform Cartesian model grid.

    Historical source: `Flood-Modeling-HRF-Physics/Physics/hrf.py::Grid`.
    This stripped version keeps OHIE's first solver independent of FFT-specific
    state used by the old pseudo-spectral SWE mode.
    """

    nx: int
    ny: int
    dx: float
    dy: float

    def __post_init__(self) -> None:
        if self.nx < 2 or self.ny < 2:
            raise ValueError("Grid must have at least 2 cells in each direction")
        if self.dx <= 0 or self.dy <= 0:
            raise ValueError("Grid spacing must be positive")

    @property
    def shape(self) -> tuple[int, int]:
        return (self.nx, self.ny)

    @property
    def cell_area(self) -> float:
        return self.dx * self.dy

    @property
    def area(self) -> float:
        return self.nx * self.ny * self.cell_area

