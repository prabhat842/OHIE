# OHIE Lightweight Benchmark Data

This folder contains small benchmark arrays used by Phase 6 validation scripts.

These are not raw city-scale DEMs and are not calibrated operational datasets. They are lightweight, reproducible inputs for testing OHIE behavior on local historical-project-derived terrain chips and proxy flood masks.

## Contents

| File | Purpose | Source Status |
|------|---------|---------------|
| `real_terrain/flat_terrain_small.npz` | Low-gradient terrain experiment | Derived from local historical project DEM output |
| `real_terrain/river_adjacent_small.npz` | Terrain plus synthetic river-edge mask | Derived terrain with synthetic boundary mask |
| `remote_sensing/observed_water_mask_small.npz` | Proxy observation comparison mask | Derived from local historical flood output |

## Scientific Status

These files support reproducible software and behavior checks. They do not establish calibrated municipal flood accuracy.

The remote-sensing comparison is a **proxy comparison only** until raw Sentinel-1, NDWI, Copernicus EMS, or JRC-derived masks are wired in with documented preprocessing.

