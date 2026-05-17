from __future__ import annotations

import numpy as np


def _validate(depth_series: np.ndarray, times_s: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    depths = np.asarray(depth_series, dtype=np.float64)
    times = np.asarray(times_s, dtype=np.float64)
    if depths.ndim != 3:
        raise ValueError("depth_series must have shape (time, nx, ny)")
    if times.ndim != 1 or times.shape[0] != depths.shape[0]:
        raise ValueError("times_s must be 1D and match depth_series time dimension")
    if np.any(np.diff(times) < 0):
        raise ValueError("times_s must be non-decreasing")
    return depths, times


def persistence_duration(depth_series: np.ndarray, times_s: np.ndarray, threshold_m: float = 0.10) -> np.ndarray:
    """Seconds each cell remains above a flood threshold."""

    depths, times = _validate(depth_series, times_s)
    if len(times) < 2:
        return np.zeros(depths.shape[1:], dtype=np.float64)
    dt = np.diff(times, prepend=times[0])
    return np.sum((depths > threshold_m) * dt[:, None, None], axis=0)


def flood_exposure(depth_series: np.ndarray, times_s: np.ndarray) -> np.ndarray:
    """Depth-duration exposure integral, in meter-seconds."""

    depths, times = _validate(depth_series, times_s)
    if len(times) < 2:
        return np.zeros(depths.shape[1:], dtype=np.float64)
    dt = np.diff(times, prepend=times[0])
    return np.sum(depths * dt[:, None, None], axis=0)


def time_to_peak(depth_series: np.ndarray, times_s: np.ndarray) -> np.ndarray:
    """Time in seconds when each cell reaches maximum depth."""

    depths, times = _validate(depth_series, times_s)
    idx = np.argmax(depths, axis=0)
    return times[idx]


def recovery_time(depth_series: np.ndarray, times_s: np.ndarray, threshold_m: float = 0.10) -> np.ndarray:
    """Last time each cell is above threshold, or 0 if never flooded."""

    depths, times = _validate(depth_series, times_s)
    flooded = depths > threshold_m
    out = np.zeros(depths.shape[1:], dtype=np.float64)
    for k, t in enumerate(times):
        out[flooded[k]] = t
    return out


def stagnation_index(depth_series: np.ndarray, times_s: np.ndarray, velocity_series: np.ndarray | None = None, threshold_m: float = 0.10) -> np.ndarray:
    """Proxy for stagnant flooding.

    If velocities are unavailable, stagnation is approximated as persistence
    weighted by low temporal depth variability. If velocities are supplied, the
    index is flooded duration where velocity is below 0.05 m/s.
    """

    depths, times = _validate(depth_series, times_s)
    persist = persistence_duration(depths, times, threshold_m)
    if velocity_series is not None:
        vel = np.asarray(velocity_series, dtype=np.float64)
        if vel.shape != depths.shape:
            raise ValueError("velocity_series must match depth_series shape")
        dt = np.diff(times, prepend=times[0])
        return np.sum(((depths > threshold_m) & (vel < 0.05)) * dt[:, None, None], axis=0)
    variability = np.std(depths, axis=0)
    return persist / (1.0 + variability)

