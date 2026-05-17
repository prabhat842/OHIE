# OHIE Phase 3 Implementation Review

## Summary

This implementation starts **Option 1** from the OHIE plan: a clean new open-source package named `ohie/`, created alongside the historical Aditya code without modifying the old project modules.

The first implementation is a **Flat Terrain Urban Flood Engine MVP** focused on the native OHIE loop:

> baseline simulation -> apply interventions -> recompute -> compare -> explain

It is not yet a full Yamuna, Gorakhpur, or Rann benchmark implementation. It is the first modular extraction of reusable primitives into a package shape suitable for open-source development.

## Files Added

### Package Metadata

| File | Purpose |
|---|---|
| `pyproject.toml` | Defines the `ohie` Python package, core dependency on `numpy`, optional GIS/test extras, and pytest config. |

### Core Package

| File | Purpose |
|---|---|
| `ohie/__init__.py` | Public package exports for `Grid`, `DiffusiveWaveFV`, and `DiffusiveWaveParams`. |
| `ohie/hydro/grid.py` | Uniform Cartesian grid model extracted from the historical HRF solver concept. |
| `ohie/hydro/solvers/diffusive_wave_fv.py` | First extracted hydrodynamic solver: fast diffusive-wave finite-volume engine. |

### Terrain Intelligence

| File | Purpose |
|---|---|
| `ohie/terrain/routing_d8.py` | D8 downstream routing, outfall detection, flow accumulation, and path-to-outfall logic. |
| `ohie/terrain/depressions.py` | Blue-spot / local depression detection for storage opportunity screening. |
| `ohie/terrain/routing_dinf.py` | Minimal D-Infinity scaffold using continuous downslope vectors. Full D-Infinity is not implemented yet. |

### Intervention Engine

| File | Purpose |
|---|---|
| `ohie/interventions/base.py` | Intervention protocol and `InterventionEffect` result object. |
| `ohie/interventions/storage.py` | `DetentionBasin`: modifies terrain and infiltration. |
| `ohie/interventions/drainage.py` | `ChannelCarve` and `CulvertResize`: modifies routing/roughness/drainage capacity. |
| `ohie/interventions/active.py` | `Pump`: active water removal approximation. |

### Scenario / Explainability

| File | Purpose |
|---|---|
| `ohie/scenarios/runner.py` | Runs baseline and intervention simulations from the same initial state. |
| `ohie/scenarios/compare.py` | Computes depth, flooded-area, and volume deltas. |
| `ohie/explain/summaries.py` | Converts intervention effects and scenario comparison into planner-readable text. |

### Example and Tests

| File | Purpose |
|---|---|
| `examples/flat_terrain_intervention_mvp.py` | Synthetic low-slope flood example with detention basin, channel carve, and pump. |
| `tests/test_solver.py` | Solver mass-balance and downslope movement smoke tests. |
| `tests/test_terrain.py` | D8 routing and blue-spot detection tests. |
| `tests/test_scenarios.py` | Intervention scenario test checking flooded-area and volume reduction. |

## Historical Code Reuse

This phase reused/refactored ideas from:

| Historical Source | OHIE Use |
|---|---|
| `Flood-Modeling-HRF-Physics/Physics/hrf.py` | Grid concept, DW-FV solver idea, forcing/mass-balance pattern. |
| `Flood-Modeling-HRF-Physics/Runners/build_hydro_network.py` | D8 routing, outfall detection, flow accumulation pattern. |
| `Flood-Modeling-HRF-Physics/AI/intervention_applier.py` | Physics-modifying intervention design: storage, pumps, channel carve, culverts. |
| `Flood-Modeling-HRF-Physics/AI/domain_knowledge/hydraulic_rules.py` | Flat-terrain intervention logic: storage/pumps for low-gradient and backwater conditions. |
| Rann/Kutch case-study PDF | MVP focus on flat terrain, ponding, storage, drainage corridors, and mass balance. |

## Current Capabilities

### Solver

Implemented:

- Uniform grid.
- Diffusive-wave finite-volume style terrain routing.
- Rainfall forcing.
- Infiltration forcing.
- Source/sink fields.
- Manning roughness field.
- Face-level draining guard.
- Mass-balance ledger.
- Scenario cloning.

Not yet implemented:

- Full shallow-water mode in the new OHIE package.
- Weir/bridge/culvert structural face couplers as first-class OHIE objects.
- Time-varying river-stage boundaries in OHIE package form.
- Outfall submergence/backwater controls.

### Terrain

Implemented:

- D8 routing.
- Flow accumulation.
- Terrain-derived outfall detection.
- Path to outfall.
- Blue-spot/local depression detection.
- D-Infinity scaffold.

Not yet implemented:

- Full D-Infinity flow partitioning.
- Sink filling / breaching API.
- Depression spill-elevation persistence model.
- Sub-basin segmentation.
- Drainage spine extraction.

### Interventions

Implemented:

- `DetentionBasin`: lowers terrain and increases infiltration.
- `ChannelCarve`: lowers roughness/carves a D8 path toward outfall.
- `CulvertResize`: approximates local added drainage capacity.
- `Pump`: active local water removal approximation.

Not yet implemented:

- Retention pond as distinct wet-storage object.
- Underground tank with outlet/routing logic.
- Gates, outfall redesign, flood walls, levees, wetlands.
- Detailed cost catalogs.
- Asset IDs and GIS geometry footprints.

### Scenario Comparison

Implemented metrics:

- Baseline max depth.
- Intervention max depth.
- Max-depth change.
- Flooded-area reduction above threshold.
- Volume reduction.
- Mean depth reduction.
- Mass-balance error.
- Plain-language summary.

Important behavior:

- Storage interventions may **increase local peak depth** because water is intentionally concentrated in a basin while reducing broader flooded area. The summary now explains that case explicitly.

## How To Run

From repo root:

```bash
python3 -m pytest -q
```

Expected:

```text
5 passed
```

Run the MVP example:

```bash
python3 examples/flat_terrain_intervention_mvp.py
```

Observed output during implementation:

```text
detention_basin near cell (25, 28) adds about 27000 m3 of storage.
channel_carve near cell (31, 28): Creates a preferential drainage corridor to the terrain-derived outfall.
pump near cell (25, 28) adds about 0.8 m3/s of drainage capacity.
Intervention scenario increases local peak depth by 0.37 m, which can happen when storage intentionally concentrates water and reduces flooded area by 47700 m2 above 0.10 m.
Mass balance error fraction: 0.0039
```

## Review Notes

### What Is Strong

- The package boundary is clean and separate from historical scripts.
- The first solver and scenario APIs are small enough to test.
- Interventions modify model physics, not just annotations.
- The baseline/intervention comparison is native to the engine.
- Tests cover mass balance, routing, blue spots, and intervention outcome.

### What Needs Review

- `DiffusiveWaveFV` is a simplified extraction, not a line-for-line port of the historical HRF solver.
- The current face-flux limiter is intentionally conservative for stability; it needs benchmark calibration.
- `CulvertResize` is currently a local drainage approximation, not a structural hydraulic coupler.
- `D-Infinity` is explicitly a scaffold.
- `ChannelCarve` currently follows D8, which is insufficient for Rann-like flat terrain until D-Infinity and depression routing are completed.

## Recommended Next Implementation Steps

1. Implement full D-Infinity routing and flow partitioning.
2. Add sink filling / breaching with a flag to preserve real blue spots.
3. Port structural culvert/weir/bridge couplers from historical `hrf.py`.
4. Add river-stage and outfall boundary-condition objects.
5. Add YAML scenario configs.
6. Add benchmark folders:
   - `benchmarks/rann_gadkabet`
   - `benchmarks/yamuna_2025`
   - `benchmarks/gorakhpur`
7. Add GeoTIFF/vector IO behind optional `geo` dependencies.
8. Add cost/catalog files for intervention objects.

## Status

Phase 3 MVP skeleton: **implemented and smoke-tested**.

Scientific/benchmark validation: **not yet complete**.

