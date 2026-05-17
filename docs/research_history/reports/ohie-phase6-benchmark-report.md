# OHIE Phase 6 Benchmark Report

## Executive Summary

Phase 6 adds reproducible real-data-informed benchmark scaffolds, literature behavior-class comparison, proxy observation-mask metrics, a reproducibility scorecard, a researcher quickstart, and a lightweight benchmark data package.

Gate posture:

> Phase 6 is credible as a reproducible research scaffold, not as calibrated operational validation.

## Real Terrain Benchmarks

| Case | Dataset | Purpose | Confidence |
|------|---------|---------|------------|
| Flat terrain small | `ohie-data/real_terrain/flat_terrain_small.npz` | Stagnation, persistence, D-Infinity routing behavior | Medium for reproducibility; Low for site-specific hydrology |
| River adjacent small | `ohie-data/real_terrain/river_adjacent_small.npz` | Prescribed river-stage boundary response | Medium for boundary plumbing; Low for real river hydraulics |

Required benchmark folders:

```text
validation/real_terrain/flat_terrain_case/
validation/real_terrain/river_adjacent_case/
```

Each folder includes:

- `README.md`
- `source_dataset.md`
- `config.yaml`
- `run.py`
- `expected_behavior.md`
- `observed_output.md`

## Literature Benchmark Report

Implemented in:

```text
ohie/validation/literature/benchmarks.py
validation/literature/
```

Required table:

| Benchmark | Literature Behavior | OHIE Behavior | Confidence |
|-----------|---------------------|---------------|------------|
| Closed basin conservation | Mass should be conserved except explicit losses | Computed from analytical validation | High |
| Bowl filling and spill threshold | Depressions fill and persist before spill/recovery | Computed from analytical validation | High |
| Flat terrain routing | Low slopes produce slow routing and stagnation pockets | Computed from Phase 6 terrain chip | Medium |
| River stage boundary influence | High receiving-water stage can increase adjacent inundation/persistence | Computed from Yamuna-style boundary approximation | Medium |
| Storage attenuation | Storage/conveyance interventions should reduce at least one meaningful metric without hiding tradeoffs | Gorakhpur-style approximation shows mixed response: volume can reduce while shallow extent may increase | Low |

No superiority claims are made.

## Remote Sensing Comparison

Implemented in:

```text
ohie/validation/remote_sensing/
validation/remote_sensing/
```

Current status:

> **proxy comparison only**

Metrics:

- IoU
- overlap percent
- flooded area agreement

The current mask is derived from local historical flood output, not raw Sentinel-1, NDWI, Copernicus EMS, or JRC water.

## Reproducibility

Implemented in:

```text
docs/reproducibility.md
docs/quickstart.md
ohie-data/
```

All Phase 6 benchmark scripts are intended to run from repository-local data.

## Scientific Honesty

OHIE currently cannot do:

- calibrated municipal flood forecasting
- groundwater coupling
- full pipe-network hydraulics
- calibrated river-urban drainage backwater coupling
- raw SAR/NDWI classification
- operational nowcasting
- full shallow-water-equation equivalence
- validated infrastructure design sizing

## Review Gate Recommendation

Phase 6 should be reviewed as:

> PASS WITH LIMITATIONS

Required reviewer caution:

- Do not treat proxy mask comparison as remote-sensing validation.
- Do not treat small terrain chips as city-scale real-data proof.
- Do not begin Phase 7 until the review package is inspected and accepted.
