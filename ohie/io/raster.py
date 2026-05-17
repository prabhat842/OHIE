from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class RasterData:
    array: np.ndarray
    transform: object | None = None
    crs: object | None = None
    profile: dict | None = None


def read_raster(path: str | Path, band: int = 1) -> RasterData:
    """Read a raster with optional rasterio dependency."""

    try:
        import rasterio
    except Exception as exc:
        raise RuntimeError("GeoTIFF IO requires optional dependency: pip install ohie[geo]") from exc
    with rasterio.open(path) as src:
        arr = src.read(band)
        return RasterData(arr, src.transform, src.crs, src.profile)


def write_raster(path: str | Path, array: np.ndarray, like: RasterData | None = None, **profile_overrides) -> None:
    """Write a single-band raster with optional rasterio dependency."""

    try:
        import rasterio
    except Exception as exc:
        raise RuntimeError("GeoTIFF IO requires optional dependency: pip install ohie[geo]") from exc
    arr = np.asarray(array)
    profile = dict(like.profile) if like and like.profile else {}
    profile.update(
        {
            "driver": profile.get("driver", "GTiff"),
            "height": arr.shape[0],
            "width": arr.shape[1],
            "count": 1,
            "dtype": str(arr.dtype),
        }
    )
    profile.update(profile_overrides)
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(arr, 1)

