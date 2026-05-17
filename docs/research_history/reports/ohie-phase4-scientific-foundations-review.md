# OHIE Phase 4 Scientific Foundations Review

## Summary

Phase 4 strengthens OHIE from a working intervention MVP into a more research-extensible hydrodynamic framework.

Implemented focus areas:

- boundary condition framework
- routing strategy architecture
- D-Infinity routing implementation
- temporal flood metrics
- first-class hydraulic structure couplers
- YAML experiment config layer
- synthetic benchmark framework
- optional Geo IO layer
- researcher-facing docs skeleton

## 1. Architecture Refactor Summary

### Boundary Abstraction

New package:

```text
ohie/hydro/boundaries/
```

Implemented:

- `BoundaryCondition` protocol
- `RainfallBoundary`
- `RiverStageBoundary`
- `HydrographBoundary`
- `FixedHeadBoundary`
- `FluxBoundary`
- `SinkBoundary`

Solver integration:

- `DiffusiveWaveFV.add_boundary(boundary)`
- boundaries apply before each timestep
- stage/head boundaries can also enforce after the timestep through `after_step`

Review files:

- `ohie/hydro/boundaries/base.py`
- `ohie/hydro/boundaries/forcing.py`
- `ohie/hydro/boundaries/stage.py`
- `ohie/hydro/boundaries/flux.py`
- `ohie/hydro/solvers/diffusive_wave_fv.py`

### Routing Strategy Abstraction

New package:

```text
ohie/terrain/routing/
```

Implemented:

- `RoutingStrategy` protocol
- `RoutingNetwork`
- `D8Routing`
- `DInfinityRouting`
- `MultiFlowRouting` scaffold

Compatibility:

- Existing `ohie.terrain.routing_d8.build_d8_network` still works.

Review files:

- `ohie/terrain/routing/base.py`
- `ohie/terrain/routing/d8.py`
- `ohie/terrain/routing/dinf.py`
- `ohie/terrain/routing/multiflow.py`

### Structural Coupler Framework

Implemented:

- `HydraulicStructure` protocol
- `CulvertCoupler`
- `WeirCoupler`
- `GateCoupler`
- `PumpStructure`

Solver integration:

- `DiffusiveWaveFV.add_structure(structure)`
- structures modify source/sink terms per timestep
- exchange is capped by available source-cell water for stability

Review file:

- `ohie/interventions/structures.py`

## 2. D-Infinity Completion

Implemented:

- continuous downslope gradient angle
- flow partition to two adjacent downslope receivers
- weighted accumulation
- outfall tracing through dominant receiver

Important scientific caveat:

This is **Tarboton-inspired D-Infinity**, not a full reproduction of every triangular-facet edge case from the original method. The implementation is suitable for OHIE research extensibility and flat-terrain experimentation, but should be benchmarked before being treated as a certified hydrology method.

Benchmark comparison command:

```bash
python3 examples/benchmark_demo.py
```

Observed comparison:

```text
{'d8_max_accumulation': 911.0,
 'dinfinity_max_accumulation': 917.3352169243572,
 'd8_outfall_unique': 78.0,
 'dinfinity_outfall_unique': 78.0}
```

## 3. Boundary Demonstration

Implemented tests demonstrate:

- rainfall forcing
- hydrograph inflow
- river-stage enforcement

Review test:

- `tests/test_phase4_boundaries_routing_metrics.py`

Relevant test:

```python
test_rainfall_hydrograph_and_river_stage_boundaries_add_water
```

This confirms the solver can use multiple boundary types without modifying solver internals.

## 4. YAML Experiment Demo

New config layer:

```text
ohie/config/
```

Example config:

```text
examples/configs/flat_terrain.yaml
```

Demo command:

```bash
python3 examples/yaml_experiment_demo.py
```

Observed output:

```text
Intervention scenario increases local peak depth by 0.41 m, which can happen when storage intentionally concentrates water and reduces flooded area by 68400 m2 above 0.10 m.
mass_balance_error_fraction=0.0020
```

Scientific note:

YAML support uses optional `pyyaml`. Install via:

```bash
pip install -e ".[config]"
```

## 5. Benchmark Suite

New package:

```text
ohie/benchmarks/
```

Implemented:

- synthetic flat-bowl terrain benchmark
- D8 vs D-Infinity routing comparison
- mass balance
- runtime
- max depth
- flooded cell count
- persistence
- flood exposure

Demo command:

```bash
python3 examples/benchmark_demo.py
```

Observed benchmark:

```text
BenchmarkResult(
  name='synthetic_flat_bowl',
  runtime_s≈0.17,
  mass_balance_error_fraction=0.0,
  max_depth_m=0.12124988559369969,
  flooded_cell_count=12,
  persistence_cell_seconds=3600.0,
  exposure_meter_seconds=33589.33333333333
)
```

## 6. Persistence & Temporal Metrics

New package:

```text
ohie/scenarios/metrics/
```

Implemented:

- `persistence_duration`
- `flood_exposure`
- `stagnation_index`
- `time_to_peak`
- `recovery_time`

Also added:

- `run_with_history` in `ohie/scenarios/runner.py`

These metrics shift OHIE beyond instantaneous depth maps toward dynamic flood behavior.

## 7. Geo IO Layer

New package:

```text
ohie/io/
```

Implemented:

- `read_raster`
- `write_raster`
- `read_vector_geometries`

Scientific/engineering constraint:

Geo IO is optional. Core OHIE remains `numpy`-only. GeoTIFF/vector support requires:

```bash
pip install -e ".[geo]"
```

## 8. Documentation Skeleton

New docs:

- `docs/architecture.md`
- `docs/physics-assumptions.md`
- `docs/extension-guide.md`
- `docs/boundary-api.md`
- `docs/routing-api.md`
- `docs/intervention-api.md`
- `docs/solver-limitations.md`
- `docs/notebooks.md`

The docs explicitly state approximations, missing physics, and stability tradeoffs.

## 9. Verification

Test command:

```bash
python3 -m pytest -q
```

Observed:

```text
10 passed
```

Demo commands verified:

```bash
python3 examples/flat_terrain_intervention_mvp.py
python3 examples/yaml_experiment_demo.py
python3 examples/benchmark_demo.py
```

## 10. Remaining Gaps

Important unresolved scientific work:

- Full Tarboton D-Infinity triangular-facet implementation.
- Full shallow-water solver port into the new OHIE package.
- Robust outfall submergence/backwater model.
- Pipe/drain graph network model.
- Real GeoTIFF benchmark datasets.
- Calibration workflows for SAR/gauge data.
- Sensitivity analysis harness.
- Real Rann/Yamuna/Gorakhpur benchmark configs.

## Status

Phase 4 framework sprint: **implemented and smoke-tested**.

Scientific validation: **synthetic only so far**.

