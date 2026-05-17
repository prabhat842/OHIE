from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Depression:
    row: int
    col: int
    depth_m: float
    spill_elevation_m: float
    contributing_cells: int


def find_blue_spots(bed: np.ndarray, min_depth_m: float = 0.05) -> list[Depression]:
    """Detect local depressions suitable for ponding/storage screening.

    This is the first OHIE blue-spot primitive. It deliberately preserves
    depressions instead of filling them, because flat-terrain planning needs to
    distinguish routing surfaces from storage opportunities.
    """

    z = np.asarray(bed, dtype=np.float64)
    nx, ny = z.shape
    spots: list[Depression] = []
    for i in range(1, nx - 1):
        for j in range(1, ny - 1):
            neighbors = z[i - 1 : i + 2, j - 1 : j + 2].copy()
            center = z[i, j]
            neighbors[1, 1] = np.nan
            spill = float(np.nanmin(neighbors))
            depth = spill - float(center)
            if depth >= min_depth_m:
                contributing = int(np.sum(z[i - 1 : i + 2, j - 1 : j + 2] <= spill))
                spots.append(Depression(i, j, depth, spill, contributing))
    spots.sort(key=lambda spot: spot.depth_m, reverse=True)
    return spots

