from __future__ import annotations

import numpy as np


def _as_mask(mask: np.ndarray) -> np.ndarray:
    return np.asarray(mask, dtype=bool)


def intersection_over_union(simulated: np.ndarray, observed: np.ndarray) -> float:
    sim = _as_mask(simulated)
    obs = _as_mask(observed)
    union = int(np.logical_or(sim, obs).sum())
    if union == 0:
        return 1.0
    return float(np.logical_and(sim, obs).sum() / union)


def observed_overlap(simulated: np.ndarray, observed: np.ndarray) -> float:
    sim = _as_mask(simulated)
    obs = _as_mask(observed)
    observed_count = int(obs.sum())
    if observed_count == 0:
        return 1.0 if int(sim.sum()) == 0 else 0.0
    return float(np.logical_and(sim, obs).sum() / observed_count)


def flooded_area_agreement(simulated: np.ndarray, observed: np.ndarray) -> float:
    sim_area = float(_as_mask(simulated).sum())
    obs_area = float(_as_mask(observed).sum())
    if obs_area == 0.0:
        return 1.0 if sim_area == 0.0 else 0.0
    return float(max(0.0, 1.0 - abs(sim_area - obs_area) / obs_area))
