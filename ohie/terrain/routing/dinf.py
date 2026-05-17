from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ohie.terrain.routing.base import RoutingNetwork, accumulate_by_elevation, compute_outfalls


_DIRS = [
    (-1, 0, -np.pi / 2),
    (-1, 1, -np.pi / 4),
    (0, 1, 0.0),
    (1, 1, np.pi / 4),
    (1, 0, np.pi / 2),
    (1, -1, 3 * np.pi / 4),
    (0, -1, np.pi),
    (-1, -1, -3 * np.pi / 4),
]


@dataclass(frozen=True)
class DInfinityRouting:
    """Tarboton-inspired continuous-angle routing.

    This implementation computes a local downslope gradient angle and partitions
    flow to the two adjacent D8 receivers bracketing that angle. It is designed
    for experimentation in flat terrain, but does not yet include all triangular
    facet edge cases from the original D-Infinity paper.
    """

    method: str = "dinfinity"

    def route(self, bed: np.ndarray, outfall_mask: np.ndarray | None = None) -> RoutingNetwork:
        z = np.asarray(bed, dtype=np.float64)
        nx, ny = z.shape
        outfall_mask = np.zeros_like(z, dtype=bool) if outfall_mask is None else np.asarray(outfall_mask, dtype=bool)
        ri = np.zeros((nx, ny, 2), dtype=np.int32)
        rj = np.zeros((nx, ny, 2), dtype=np.int32)
        weights = np.zeros((nx, ny, 2), dtype=np.float64)

        grad_i, grad_j = np.gradient(z)
        for i in range(nx):
            for j in range(ny):
                # Downslope vector in row/col coordinates.
                vi = -float(grad_i[i, j])
                vj = -float(grad_j[i, j])
                if (vi * vi + vj * vj) <= 1.0e-18:
                    ri[i, j, :] = i
                    rj[i, j, :] = j
                    continue

                angle = np.arctan2(vi, vj)
                candidates = []
                for oi, oj, theta in _DIRS:
                    ii, jj = i + oi, j + oj
                    if not (0 <= ii < nx and 0 <= jj < ny):
                        continue
                    drop = z[i, j] - z[ii, jj]
                    if drop <= 0.0:
                        continue
                    diff = abs(_angle_diff(angle, theta))
                    candidates.append((diff, drop, ii, jj, theta))
                if not candidates:
                    ri[i, j, :] = i
                    rj[i, j, :] = j
                    continue

                candidates.sort(key=lambda item: item[0])
                selected = candidates[:2]
                if len(selected) == 1:
                    _, _, ii, jj, _ = selected[0]
                    ri[i, j, 0] = ii
                    rj[i, j, 0] = jj
                    weights[i, j, 0] = 1.0
                    ri[i, j, 1] = i
                    rj[i, j, 1] = j
                    continue

                # Weight by angular closeness and local drop.
                scores = []
                for diff, drop, ii, jj, _ in selected:
                    scores.append(max(1.0e-9, (np.pi / 4 - min(diff, np.pi / 4))) * drop)
                total = float(sum(scores))
                for k, item in enumerate(selected):
                    _, _, ii, jj, _ = item
                    ri[i, j, k] = ii
                    rj[i, j, k] = jj
                    weights[i, j, k] = scores[k] / total if total > 0.0 else 0.5

        accum = accumulate_by_elevation(z, ri, rj, weights)
        out_i, out_j = compute_outfalls(ri, rj, weights, outfall_mask)
        return RoutingNetwork(ri, rj, weights, accum, out_i, out_j, self.method)


def _angle_diff(a: float, b: float) -> float:
    return float((a - b + np.pi) % (2 * np.pi) - np.pi)

