# Phase 6 Real Terrain Benchmarks

These benchmarks move OHIE beyond purely synthetic terrain while keeping the inputs small enough to rerun quickly.

They are scientifically limited. The current terrain chips are local historical-project-derived arrays from earlier flood-resilience outputs. They are not calibrated real-world validation cases and should not be presented as operational accuracy evidence.

## Cases

| Case | Script | Purpose |
|------|--------|---------|
| Flat terrain | `flat_terrain_case/run.py` | Stagnation, persistence, routing realism, D-Infinity behavior |
| River-adjacent terrain | `river_adjacent_case/run.py` | Stage boundary response and inundation change |

