from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ohie.terrain.routing.base import RoutingNetwork, accumulate_by_elevation, compute_outfalls


_NEIGHBORS = [
    (-1, -1),
    (-1, 0),
    (-1, 1),
    (0, -1),
    (0, 1),
    (1, -1),
    (1, 0),
    (1, 1),
]


@dataclass(frozen=True)
class D8Routing:
    """Single-flow-direction routing using steepest downslope neighbor."""

    method: str = "d8"

    def route(self, bed: np.ndarray, outfall_mask: np.ndarray | None = None) -> RoutingNetwork:
        z = np.asarray(bed, dtype=np.float64)
        nx, ny = z.shape
        outfall_mask = np.zeros_like(z, dtype=bool) if outfall_mask is None else np.asarray(outfall_mask, dtype=bool)

        ri = np.zeros((nx, ny, 1), dtype=np.int32)
        rj = np.zeros((nx, ny, 1), dtype=np.int32)
        w = np.zeros((nx, ny, 1), dtype=np.float64)
        for i in range(nx):
            for j in range(ny):
                best_i, best_j = i, j
                best_slope = 0.0
                for oi, oj in _NEIGHBORS:
                    ii, jj = i + oi, j + oj
                    if 0 <= ii < nx and 0 <= jj < ny:
                        distance = (oi * oi + oj * oj) ** 0.5
                        slope = (z[i, j] - z[ii, jj]) / max(distance, 1.0)
                        if slope > best_slope + 1.0e-12:
                            best_slope = slope
                            best_i, best_j = ii, jj
                ri[i, j, 0] = best_i
                rj[i, j, 0] = best_j
                w[i, j, 0] = 1.0 if (best_i, best_j) != (i, j) else 0.0

        accum = accumulate_by_elevation(z, ri, rj, w)
        out_i, out_j = compute_outfalls(ri, rj, w, outfall_mask)
        return RoutingNetwork(ri, rj, w, accum, out_i, out_j, self.method)

