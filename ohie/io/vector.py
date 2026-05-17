from __future__ import annotations

from pathlib import Path


def read_vector_geometries(path: str | Path):
    """Read vector geometries with optional fiona/shapely dependency."""

    try:
        import fiona
        from shapely.geometry import shape
    except Exception as exc:
        raise RuntimeError("Vector IO requires optional dependency: pip install ohie[geo]") from exc
    geoms = []
    with fiona.open(path) as src:
        for feat in src:
            geoms.append(shape(feat["geometry"]))
    return geoms

