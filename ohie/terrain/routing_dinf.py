from __future__ import annotations

import numpy as np

from ohie.terrain.routing import DInfinityRouting


def build_dinf_network(bed: np.ndarray, outfall_mask: np.ndarray | None = None):
    return DInfinityRouting().route(bed, outfall_mask)


def flow_direction_dinf_stub(bed: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return continuous downslope unit vectors for compatibility."""

    z = np.asarray(bed, dtype=np.float64)
    gy, gx = np.gradient(z)
    mag = np.sqrt(gx * gx + gy * gy)
    mag = np.where(mag > 1.0e-12, mag, 1.0)
    return -gx / mag, -gy / mag
