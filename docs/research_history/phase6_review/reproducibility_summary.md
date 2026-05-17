# Phase 6 Reproducibility Summary

## Rerunnable Artifacts

| Artifact | Rerunnable | Notes |
|----------|------------|-------|
| `validation/real_terrain/flat_terrain_case/run.py` | Yes | Uses packaged NPZ terrain |
| `validation/real_terrain/river_adjacent_case/run.py` | Yes | Uses packaged NPZ terrain and mask |
| `validation/literature/run.py` | Yes | Generates behavior-class table |
| `validation/remote_sensing/run.py` | Yes | Uses packaged proxy mask |
| `validation/analytical/run.py` | Yes | Existing synthetic validation |
| `validation/sensitivity/run.py` | Yes | Existing sensitivity harness |

## Dataset Accessibility

All Phase 6 scripts run against repository-local data in:

```text
ohie-data/
```

The data package is lightweight and documented, but the source status is limited:

- local historical-project-derived artifacts
- not fresh external open-data downloads
- not publication-grade remote sensing

## Setup

The expected first-run path is documented in:

```text
docs/quickstart.md
```

## Reproducibility Gate

Recommendation:

> PASS WITH LIMITATIONS

Reason:

The code can be rerun from local inputs, but external real-data acquisition and preprocessing are not yet fully automated.

