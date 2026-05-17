#!/usr/bin/env python3
"""
Build Hydrologic Network Artifacts (D8, Outfalls, Flow Accumulation)
===================================================================
Inputs: baseline_dir with final_snapshot.npz and final_h.tif (for transform/CRS)
Outputs (in baseline_dir):
  - flow_dir_d8.tif         : encoded D8 direction (0..7 for 8 neighbors; 255 for pit/edge)
  - outfall_i.tif           : raster of outfall i-index for each cell
  - outfall_j.tif           : raster of outfall j-index for each cell
  - flow_accum.tif          : upstream contributing cell count (including self)

Notes:
 - D8 uses steepest descent on bed elevation; ties broken by lowest neighbor.
 - Outfall is nearest river_mask cell along the path; if none, first boundary cell reached.
 - If river_mask.tif is absent, outfall becomes nearest boundary along D8 path.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Tuple

import numpy as np
import rasterio as rio


def load_baseline_arrays(baseline_dir: Path) -> Tuple[np.ndarray, float, float, any, any]:
    npz = np.load(baseline_dir / 'final_snapshot.npz')
    bed = np.asarray(npz.get('bed'))
    dx = float(npz.get('dx_m', 100.0))
    dy = float(npz.get('dy_m', 100.0))
    # Read transform/CRS from final_h.tif if available
    with rio.open(baseline_dir / 'final_h.tif') as ds:
        transform = ds.transform
        crs = ds.crs
    return bed, dx, dy, transform, crs


def load_river_mask(baseline_dir: Path, shape: Tuple[int, int]) -> np.ndarray:
    path = baseline_dir / 'river_mask.tif'
    if path.exists():
        try:
            with rio.open(path) as ds:
                arr = ds.read(1)
            return (np.nan_to_num(arr, nan=0.0) > 0).astype(np.uint8)
        except Exception:
            pass
    return np.zeros(shape, dtype=np.uint8)


def build_d8(bed: np.ndarray) -> np.ndarray:
    nx, ny = bed.shape
    d8 = np.zeros((nx, ny, 2), dtype=np.int32)
    # neighbor offsets in order: NW, N, NE, W, E, SW, S, SE
    nbrs = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    for i in range(nx):
        for j in range(ny):
            best_di, best_dj = 0, 0
            best_drop = 0.0
            z0 = float(bed[i, j])
            for di, dj in nbrs:
                ii = i + di
                jj = j + dj
                if 0 <= ii < nx and 0 <= jj < ny:
                    dz = z0 - float(bed[ii, jj])
                    if dz > (best_drop + 1e-12) or (abs(dz - best_drop) <= 1e-12 and bed[ii, jj] < (z0 - best_drop)):
                        best_drop = dz
                        best_di, best_dj = di, dj
            d8[i, j, 0] = i + best_di
            d8[i, j, 1] = j + best_dj
    return d8


def d8_dir_code(i: int, j: int, ni: int, nj: int) -> int:
    # Map neighbor offset to code 0..7; 255 if same cell
    di = ni - i
    dj = nj - j
    mapping = {
        (-1, -1): 0, (-1, 0): 1, (-1, 1): 2,
        (0, -1): 3,  (0, 1): 4,
        (1, -1): 5,  (1, 0): 6,  (1, 1): 7,
    }
    return mapping.get((di, dj), 255)


def compute_outfalls(d8: np.ndarray, river_mask: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    nx, ny, _ = d8.shape
    out_i = np.zeros((nx, ny), dtype=np.int32)
    out_j = np.zeros((nx, ny), dtype=np.int32)
    for i in range(nx):
        for j in range(ny):
            vi, vj = int(i), int(j)
            visited = 0
            while visited < (nx + ny):
                if river_mask[vi, vj] > 0:
                    break
                ni = int(d8[vi, vj, 0])
                nj = int(d8[vi, vj, 1])
                if ni == vi and nj == vj:
                    break
                vi, vj = ni, nj
                visited += 1
                if vi == 0 or vj == 0 or vi == nx - 1 or vj == ny - 1:
                    break
            out_i[i, j] = vi
            out_j[i, j] = vj
    return out_i, out_j


def compute_flow_accum(bed: np.ndarray, d8: np.ndarray) -> np.ndarray:
    nx, ny = bed.shape
    accum = np.ones((nx, ny), dtype=np.float64)
    order = np.argsort(bed, axis=None)
    for flat_idx in order:
        i = int(flat_idx // ny)
        j = int(flat_idx % ny)
        ni = int(d8[i, j, 0])
        nj = int(d8[i, j, 1])
        if (ni != i or nj != j) and 0 <= ni < nx and 0 <= nj < ny:
            accum[ni, nj] += accum[i, j]
    return accum


def write_tif(path: Path, arr: np.ndarray, transform, crs, dtype='float32'):
    h, w = arr.shape
    profile = {
        'driver': 'GTiff',
        'height': h,
        'width': w,
        'count': 1,
        'dtype': dtype,
        'crs': crs,
        'transform': transform,
        'nodata': 0,
    }
    with rio.open(path, 'w', **profile) as ds:
        ds.write(arr.astype(dtype), 1)


def main():
    ap = argparse.ArgumentParser(description='Build hydrologic network artifacts (D8, outfalls, accumulation)')
    ap.add_argument('--baseline_dir', type=str, required=True)
    args = ap.parse_args()
    base = Path(args.baseline_dir)
    if not (base / 'final_snapshot.npz').exists():
        print(f"❌ {base/'final_snapshot.npz'} not found. Run baseline first.")
        return 1
    bed, dx, dy, transform, crs = load_baseline_arrays(base)
    nx, ny = bed.shape
    print(f"Building network for grid {nx}×{ny}, dx={dx}, dy={dy}")
    river_mask = load_river_mask(base, bed.shape)
    d8 = build_d8(bed)
    out_i, out_j = compute_outfalls(d8, river_mask)
    accum = compute_flow_accum(bed, d8)
    # Encode direction codes
    dir_codes = np.full((nx, ny), 255, dtype=np.uint8)
    for i in range(nx):
        for j in range(ny):
            dir_codes[i, j] = d8_dir_code(i, j, int(d8[i, j, 0]), int(d8[i, j, 1]))
    # Write artifacts
    write_tif(base / 'flow_dir_d8.tif', dir_codes, transform, crs, dtype='uint8')
    write_tif(base / 'outfall_i.tif', out_i, transform, crs, dtype='int32')
    write_tif(base / 'outfall_j.tif', out_j, transform, crs, dtype='int32')
    write_tif(base / 'flow_accum.tif', accum, transform, crs, dtype='float32')
    print('✅ Wrote hydrologic network artifacts: flow_dir_d8.tif, outfall_i.tif, outfall_j.tif, flow_accum.tif')
    return 0


if __name__ == '__main__':
    main()




