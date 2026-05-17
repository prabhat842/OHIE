from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass
class RoutingNetwork:
    """Cell routing graph with optional flow partition weights.

    `receivers_i`, `receivers_j`, and `weights` have shape `(nx, ny, k)`.
    D8 uses `k=1`; D-Infinity uses `k=2` for the two bracketing downslope
    directions. Zero-weight receivers are ignored.
    """

    receivers_i: np.ndarray
    receivers_j: np.ndarray
    weights: np.ndarray
    flow_accumulation: np.ndarray
    outfall_i: np.ndarray
    outfall_j: np.ndarray
    method: str

    @property
    def downstream_i(self) -> np.ndarray:
        return self.receivers_i[:, :, 0]

    @property
    def downstream_j(self) -> np.ndarray:
        return self.receivers_j[:, :, 0]

    def downstream(self, i: int, j: int) -> tuple[int, int]:
        return int(self.downstream_i[i, j]), int(self.downstream_j[i, j])

    def outfall(self, i: int, j: int) -> tuple[int, int]:
        return int(self.outfall_i[i, j]), int(self.outfall_j[i, j])

    def path_to_outfall(self, i: int, j: int, max_steps: int | None = None) -> list[tuple[int, int]]:
        nx, ny = self.downstream_i.shape
        max_steps = max_steps or (nx + ny)
        path = [(int(i), int(j))]
        ci, cj = int(i), int(j)
        for _ in range(max_steps):
            candidates = [
                (float(self.weights[ci, cj, k]), int(self.receivers_i[ci, cj, k]), int(self.receivers_j[ci, cj, k]))
                for k in range(self.weights.shape[2])
            ]
            candidates.sort(reverse=True)
            weight, ni, nj = candidates[0]
            if weight <= 0.0 or (ni, nj) == (ci, cj):
                break
            path.append((ni, nj))
            ci, cj = ni, nj
            if ci == 0 or cj == 0 or ci == nx - 1 or cj == ny - 1:
                break
        return path


class RoutingStrategy(Protocol):
    """Interface for swappable terrain routing assumptions."""

    method: str

    def route(self, bed: np.ndarray, outfall_mask: np.ndarray | None = None) -> RoutingNetwork:
        """Return routing network for a terrain surface."""


def compute_outfalls(receivers_i: np.ndarray, receivers_j: np.ndarray, weights: np.ndarray, outfall_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    nx, ny, kmax = receivers_i.shape
    out_i = np.zeros((nx, ny), dtype=np.int32)
    out_j = np.zeros((nx, ny), dtype=np.int32)
    for i in range(nx):
        for j in range(ny):
            ci, cj = i, j
            for _ in range(nx + ny):
                if outfall_mask[ci, cj]:
                    break
                best_k = int(np.argmax(weights[ci, cj, :]))
                if weights[ci, cj, best_k] <= 0.0:
                    break
                ni = int(receivers_i[ci, cj, best_k])
                nj = int(receivers_j[ci, cj, best_k])
                if (ni, nj) == (ci, cj):
                    break
                ci, cj = ni, nj
                if ci == 0 or cj == 0 or ci == nx - 1 or cj == ny - 1:
                    break
            out_i[i, j] = ci
            out_j[i, j] = cj
    return out_i, out_j


def accumulate_by_elevation(bed: np.ndarray, receivers_i: np.ndarray, receivers_j: np.ndarray, weights: np.ndarray) -> np.ndarray:
    z = np.asarray(bed, dtype=np.float64)
    nx, ny = z.shape
    accum = np.ones((nx, ny), dtype=np.float64)
    for flat_idx in np.argsort(z, axis=None)[::-1]:
        i = int(flat_idx // ny)
        j = int(flat_idx % ny)
        for k in range(weights.shape[2]):
            w = float(weights[i, j, k])
            if w <= 0.0:
                continue
            ni = int(receivers_i[i, j, k])
            nj = int(receivers_j[i, j, k])
            if (ni, nj) != (i, j):
                accum[ni, nj] += accum[i, j] * w
    return accum

