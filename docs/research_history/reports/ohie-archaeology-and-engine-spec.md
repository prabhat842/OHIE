# Open Hydrodynamic Intervention Engine (OHIE)

## Phase 1: Archaeology

This document maps the reusable historical work and proposes an OHIE architecture. No implementation has been started in this phase.

Inputs inspected:

- Current code workspace: `/home/prabhat/Desktop/Infraloom(urbanist)-All-Code-Files/Urbanist-Prototypes`
- Draft case-study archive: `/home/prabhat/Desktop/Infraloom-Draft`
- Key PDFs:
  - `/home/prabhat/Desktop/Infraloom-Draft/Case-Studies/Academic/CUL-IITD-001-Yamuna.pdf`
  - `/home/prabhat/Desktop/Infraloom-Draft/Case-Studies/B2B-Exploratory/CUL-TCS-004-Arup-Rann-Kutch.pdf`
  - `/home/prabhat/Desktop/Infraloom-Draft/Case-Studies/Open-Data/CUL-TCS-003-GKP-Water-Resilience.pdf`
  - `/home/prabhat/Desktop/Infraloom-Draft/Case-Studies/Open-Data/CUL-TCS-001-GKP-Linear-Alignment.pdf`

## Executive Decision

OHIE should be built by extracting and modernizing existing primitives, not by creating a fresh simulator.

The strongest reusable base is:

- `Flood-Modeling-HRF-Physics/Physics/hrf.py` for the hydrodynamic core.
- `Flood-Modeling-HRF-Physics/Runners/pb_cli.py` and `pb_cli_spu.py` for geospatial runner patterns, dynamic stage forcing, channel masks, river masks, and outputs.
- `Flood-Modeling-HRF-Physics/AI/intervention_applier.py` for intervention-to-physics translation.
- `Flood-Modeling-HRF-Physics/AI/intervention_library.py` for intervention schemas and cost proxies.
- `Flood-Resilience/urban_diagnostics.py` and `Water-Management/water_resource_diagnostics.py` for terrain/hydrology suitability analysis.
- `Flood-Resilience/intervention_rules.py` for rapid RFSM-style scenario scoring.
- Rann/Yamuna/Gorakhpur PDFs for benchmark requirements and target behavior.

The MVP should be a **Flat Terrain Urban Flood Engine** because that is the most differentiated use case and is directly supported by the Rann, Gorakhpur, and NCR problem framing.

## Reusable Primitives Table

| Existing Module / Artifact | Reusable | Needs Rewrite | Notes |
|---|---:|---:|---|
| `Flood-Modeling-HRF-Physics/Physics/hrf.py` | High | Medium | Core solver includes shallow-water, diffusive-wave, DW-FV, rainfall, infiltration, sources, roughness, structures, sponge/tide boundary, mass ledgers. Should be refactored into `ohie.hydro` with clean typed APIs and tests. |
| `HRFSolver.mode == "dw_fv"` | High | Low-Medium | Best first solver mode for low-slope urban/flat terrain. Needs validation harness and cleaner boundary handling. |
| `HRFSolver` shallow-water / pseudo-spectral mode | Medium | Medium | Useful for detailed studies and benchmark comparison; not MVP default. FFT periodic boundary assumptions need careful API separation. |
| `HRFSolver.apply_tide_bc` / sponge boundary | High | Medium | Critical for Yamuna stage, Rann surge, coastal backwater, and outfall suppression. Needs general boundary-condition objects. |
| `Weir`, `Culvert`, `Bridge` structures in `hrf.py` | High | Medium | Structure primitives exist. Need generalized `HydraulicStructure` interfaces, rating curves, invert levels, and asset metadata. |
| `Runners/pb_cli.py` | Medium | High | Good IO/runner archaeology: DEM, LULC, rivers, drains, ponds, stage points, QCIA design, outputs. Should not be copied as a monolithic CLI. |
| `Runners/pb_cli_spu.py` | Medium-High | High | Adds rain CSV, stage CSV, channel type masks, `tidal_channel` parsing, frame outputs, and SPU hooks. Important for operational forcing patterns. |
| `Runners/build_hydro_network.py` | High | Medium | D8, outfalls, flow accumulation artifacts. Needs conversion to `ohie.terrain` plus D-Infinity and flat-terrain improvements. |
| `AI/intervention_applier.py` | High | Medium | Key differentiator. Applies detention basins, pumps, culverts, drains/channels, barriers, green infrastructure, trenches, smart valves, tanks. Needs typed intervention objects, unit tests, and removal of coarse-grid boost heuristics from core logic. |
| `AI/intervention_library.py` | Medium-High | Medium | Useful intervention catalog and cost proxies. Needs schema cleanup and external YAML/JSON catalogs. |
| `AI/domain_knowledge/hydraulic_rules.py` | High | Medium | Encodes intervention feasibility logic: gradients, Froude, flow accumulation, backwater, storage vs conveyance decisions. Should become `ohie.interventions.rules`. |
| `run_qcia_flood_optimization.py` | Medium | High | Valuable workflow concept: baseline simulation, causal features, intervention selection, optimized rerun, comparison. Current code has heuristics and hard-coded choices; should inform `ohie.scenarios` and `ohie.optimization`, not be imported as-is. |
| `AI/qcia_core/*` | Medium | High | Useful for future optimization/explainability. Not MVP-critical. Keep behind optional extra. |
| `Flood-Resilience/urban_diagnostics.py` | High | Medium | Implements pit filling, D8, accumulation, slope, TWI, suitability maps. Needs extraction from hard-coded Singapore/Gorakhpur paths. |
| `Flood-Resilience/intervention_rules.py` | Medium | Medium-High | Rapid RFSM critic useful for fast scenario search. It simulates ponds/levees but only implicitly handles bioswales/culverts. Use as optional surrogate, not as hydrodynamic truth. |
| `Flood-Resilience/intervention_planner.py` | Medium | High | Shows GA planning and KML export. Extract ideas for scenario portfolios; rewrite for clean API. |
| `Water-Management/water_resource_diagnostics.py` | Medium-High | Medium | Useful runoff availability, recharge, harvesting, water resilience suitability. Important for "store water where" questions. |
| `Water-Management/intervention_rules.py` | Medium | Medium | Useful water-balance adaptation. Needs unification with flood intervention schema. |
| `Aero-GIS/bioswale_designer.py` | Medium | Medium | Useful infrastructure-risk and site-scale optimization pattern for airports/industrial parks. Not core MVP. |
| `Linear-Alignment-MTHL/alignment_validator.py` | Medium | Medium | Includes standing surge/tide risk validation and alignment scoring. Useful for infrastructure risk Tier 3. |
| `Infraloom-Draft/...Yamuna.pdf` | High as benchmark spec | N/A | Provides validated target: Yamuna 2025 hindcast, SAR comparison, IoU 0.774 in river corridor, river-stage hydrograph, NASA HGT, OSM river/land-use data, AI-proposed drainage intervention. |
| `Infraloom-Draft/...Rann-Kutch.pdf` | High as benchmark spec | N/A | Defines flat terrain requirements: <0.05% slope, sheet flow, D-Infinity thalwegs, blue spots, salinity/viscosity correction, road damming, rain + tidal surge, mass balance <1%. |
| `Infraloom-Draft/...GKP-Water-Resilience.pdf` | High as product/workflow spec | N/A | Confirms Gorakhpur integrated flood + water-resilience pipeline, suitability atlases, GA, RFSM critic, HRF/Bayesian engineering refinement, KML/GLB outputs. |

## Case Study Archaeology

### Yamuna

Evidence from `CUL-IITD-001-Yamuna.pdf`:

- Hindcast target: September 3, 2025 Yamuna river flood.
- Data: SAR observation from IIT Delhi HydroSense Lab, NASA HGT terrain, OSM river channels and land use, digitized river-stage hydrograph.
- Reported validation: river-corridor IoU 0.774, precision 0.790, recall 0.975.
- Runtime target: about 195 seconds per tile on CPU-only Apple M4 Pro.
- Intervention demonstration: AI identified ponding and simulated a new drainage channel; output included baseline, intervention, delta, Google Earth overlay, and GeoJSON drain alignment.

OHIE implication:

- Yamuna becomes a benchmark for **river-stage boundary + SAR validation + drain intervention impact**.
- Required OHIE modules: `io.dem`, `io.osm`, `hydro.boundaries.StageHydrograph`, `scenarios.compare`, `metrics.iou`, `interventions.ChannelDiversion`.

### Rann of Kutch

Evidence from `CUL-TCS-004-Arup-Rann-Kutch.pdf`:

- Problem: flat terrain below 0.05% slope, sheet flow, salinity effects, road embankment damming, tidal/cyclonic forcing.
- Solver claim: DW-FV solver, mass balance below 1%.
- Terrain intelligence: D-Infinity thalweg extraction, blue-spot analysis, flow accumulation, drainage corridors, culvert flux gates.
- Scenario examples: 1-hour sheet flow, 4-hour channelization, 6-hour cyclone with rain plus tidal surge, backwater behind Road 754K.
- Intervention concepts: Fortress protection, Sponge strategy, levees, culverts, ponds, fuse channels, stage-storage curves.
- Calibration assumptions: SRTM 30 m, salinity density, salt-crust low infiltration, culvert dimensions inferred from OSM and flow accumulation.

OHIE implication:

- Rann is the best benchmark for **flat-terrain hydrology**.
- OHIE must not rely only on D8. It needs D-Infinity, depression/blue-spot persistence, sheet-flow routing, stage/surge boundaries, and road-embankment barrier logic.
- The existing code does not contain a visible salinity-viscosity kernel, D-Infinity implementation, or Rann-specific config. These should be built from the Rann spec, while reusing DW-FV and tidal/stage primitives.

### Gorakhpur

Evidence from code and `CUL-TCS-003-GKP-Water-Resilience.pdf`:

- Code: `Flood-Resilience/run_gorakhpur_analysis.py`, `urban_diagnostics.py`, `intervention_rules.py`, `intervention_planner.py`.
- Outputs: `Flood-Resilience/Outputs/Gorakhpur_Run_*/intervention_plan.json`, KML, suitability rasters, cropped AOI rasters.
- Planning methods: strategic atlas, priority zones, GA, RFSM critic, retention ponds, levees, bioswales, culverts.
- Water-management extension: `Water-Management/*` for harvesting, recharge, NbS, pumps.

OHIE implication:

- Gorakhpur becomes the benchmark for **municipal intervention planning** and open-data workflow.
- It should validate scenario outputs, not just depth maps.

### Jabalpur

Evidence from code:

- `Flood-Modeling-HRF-Physics/extra_tools/run_qcia_workflow_real.py`
- `Flood-Modeling-HRF-Physics/extra_tools/run_qcia_enhanced.py`
- `Flood-Modeling-HRF-Physics/reports/jabalpur_qcia_demo/*`
- `Flood-Modeling-HRF-Physics/extra_tools/outputs/qcia_full_demo/*`

OHIE implication:

- Jabalpur is the benchmark for QCIA-style intervention selection and baseline-vs-optimized comparison.

### Airport / Infrastructure Risk

Evidence:

- `Aero-GIS/bioswale_designer.py`
- `Aero-GIS/airport_selector.py`
- `Linear-Alignment-MTHL/alignment_validator.py`

OHIE implication:

- These should become Tier 3 examples after core OHIE stabilizes.

## What Should Not Be Reused Directly

- Monolithic runners with hard-coded paths and city labels.
- Ad hoc CLI scripts as public API.
- Hard-coded intervention priorities in `run_qcia_flood_optimization.py`.
- Coarse-grid "physics boost" as a hidden default.
- RFSM outputs as proof of hydrodynamic truth.
- Case-study PDF claims as implementation evidence unless corresponding code/config/output exists.

## Phase 2: Engine Specification

## Proposed Repository Structure

```text
ohie/
  terrain/
    dem.py
    conditioning.py
    depressions.py
    routing_d8.py
    routing_dinf.py
    blue_spots.py
    basins.py
    drainage_spines.py
    outfalls.py
  hydro/
    grid.py
    state.py
    solvers/
      diffusive_wave_fv.py
      shallow_water.py
      rfsm.py
    boundaries.py
    forcing.py
    structures.py
    mass_balance.py
  interventions/
    base.py
    storage.py
    drainage.py
    nature_based.py
    active.py
    catalog.py
    rules.py
    applier.py
  scenarios/
    scenario.py
    runner.py
    compare.py
    metrics.py
  routing/
    graph.py
    drains.py
    outfall_controls.py
  calibration/
    sar.py
    gauges.py
    roughness.py
    validation.py
  optimization/
    candidate_generation.py
    scoring.py
    search.py
  io/
    raster.py
    vector.py
    osm.py
    config.py
    outputs.py
  explain/
    summaries.py
    diagnostics.py
  benchmarks/
    yamuna_2025/
    rann_gadkabet/
    gorakhpur/
    jabalpur/
  examples/
  notebooks/
  tests/
  docs/
```

## Core Data Model

### TerrainModel

Responsibilities:

- DEM/DSM ingestion.
- Conditioning.
- Depression/blue-spot detection.
- D8 and D-Infinity routing.
- Flow accumulation.
- Drainage spine extraction.
- Basin/sub-basin segmentation.
- Outfall detection.

Flat terrain requirements:

- Preserve real depressions when requested.
- Separate "fill for routing" from "retain for storage".
- D-Infinity or multiple-flow-direction routing must be first-class.
- Store depression persistence and spill elevation.

### HydroModel

Responsibilities:

- Maintain grid, state, bed, water depth, velocity, forcing, structures, boundary conditions.
- Provide solver modes:
  - `DiffusiveWaveFV`: MVP default.
  - `ShallowWater`: detailed mode.
  - `RFSM`: optional fast surrogate for search.

Boundary objects:

- `RainfallUniform`
- `RainfallRaster`
- `RainfallTimeSeries`
- `StageHydrograph`
- `OpenBoundary`
- `RiverMaskStage`
- `OutfallControl`
- `PumpSchedule`

### Intervention

Every intervention must implement:

```python
class Intervention:
    def footprint(self, terrain) -> Geometry: ...
    def cost(self, context) -> CostEstimate: ...
    def apply(self, hydro_model, terrain_model) -> InterventionEffect: ...
    def explain(self, before, after) -> str: ...
```

Intervention categories:

- Storage: detention basin, retention pond, underground tank, blue-spot formalization.
- Drainage: drain widening, channel carve, culvert resize, outfall redesign, diversion corridor.
- Nature-based: recharge zone, sponge park, wetland, bioswale, infiltration trench.
- Active: pump, gate, smart valve, operational routing.
- Protection: levee, wall, road-embankment notch, fuse channel.

### Scenario

Scenario must be a reproducible config:

```yaml
name: sponge_strategy
terrain:
  dem: data/dem.tif
forcing:
  rainfall: 35_mm_hr_6h
  stage: rann_surge.csv
solver:
  mode: diffusive_wave_fv
interventions:
  - type: detention_basin
    location: [x, y]
    volume_m3: 50000
  - type: culvert_resize
    asset_id: CULV_17
    area_m2: 9.0
```

Scenario outputs:

- depth rasters over time.
- max depth.
- duration above thresholds.
- inundation extent.
- velocity / flux where available.
- mass balance report.
- before/after delta.
- intervention effects.
- cost proxy.
- planner explanation.

## MVP: Flat Terrain Urban Flood Engine

The MVP should implement:

1. `TerrainModel.from_dem()`
2. DEM conditioning with fill/breach modes.
3. Depression and blue-spot analysis.
4. D8 routing reused from `build_hydro_network.py`.
5. D-Infinity routing new implementation.
6. `DiffusiveWaveFV` extracted from `HRFSolver`.
7. Rainfall uniform/raster/time-series forcing.
8. Stage boundary and river-mask stage forcing.
9. Storage interventions:
   - detention basin
   - retention pond
   - underground tank
10. Drainage interventions:
   - channel carve / widening
   - culvert resize
   - outfall control placeholder
11. Active interventions:
   - pump with head-dependent capacity
12. Scenario comparison:
   - depth reduction
   - extent reduction
   - duration reduction
   - storage captured
   - cost proxy
13. Explainability:
   - one-sentence findings per intervention.
   - bottleneck diagnostics.

## Key Tradeoffs

### DW-FV First, SWE Second

DW-FV should be the MVP default because it is stable and fast for pluvial, urban, and flat-terrain sheet flow. SWE remains important for detailed flood dynamics and should be preserved, but it is not the fastest path to an intervention-aware engine.

### Terrain Routing Must Improve Beyond D8

D8 exists and is reusable, but the Rann brief makes D-Infinity mandatory. In flat terrain, single-direction routing can fabricate artificial flow paths. OHIE should support:

- D8 for fast/simple city runs.
- D-Infinity for flat basins.
- depression spill routing for blue spots.
- drainage graph overrides where surveyed drains exist.

### Interventions Must Modify Physics

Annotations are not enough. The existing `InterventionApplier` already proves this direction:

- basins modify bed and infiltration.
- pumps modify sink/source fields.
- culverts modify structural connectivity.
- drains carve channels and modify Manning roughness.
- levees/walls raise terrain and set overflow crests.

OHIE should formalize this pattern.

### RFSM Is Useful, But Not the Core Solver

RFSM is useful for rapid search and municipal screening. It should be a surrogate mode with explicit labeling. Final scenario comparison should use DW-FV or SWE.

## Benchmark Plan

### Benchmark 1: Yamuna 2025

Goal:

- Reproduce river-corridor SAR validation workflow.

Required metrics:

- IoU, precision, recall.
- runtime per tile.
- mass balance.
- baseline/intervention depth delta for AI-proposed drain.

Inputs:

- NASA HGT or DEM.
- OSM river/land-use.
- river-stage hydrograph.
- SAR flood mask.

### Benchmark 2: Rann / Gadkabet

Goal:

- Validate flat-terrain sheet flow and road-damming behavior.

Required metrics:

- mass balance below 1% target.
- blue-spot detection.
- D-Infinity thalweg extraction.
- road embankment backwater depth.
- scenario comparison: Fortress vs Sponge vs Hybrid.

Required new work:

- D-Infinity.
- salinity/salt-crust parameter hooks.
- road barrier/fuse-channel intervention.
- stage-storage curves.

### Benchmark 3: Gorakhpur

Goal:

- Reproduce municipal intervention planning workflow with open data.

Required metrics:

- suitability atlas generation.
- top priority zones.
- scenario portfolio.
- intervention JSON/KML outputs.
- before/after flood reduction.

### Benchmark 4: Jabalpur

Goal:

- Reproduce QCIA baseline vs optimized workflow.

Required metrics:

- causal feature extraction.
- intervention selection.
- optimized rerun.
- road flooding / exposed asset reduction.

## Development Phases

### Phase 1: Archaeology

Status: complete enough to begin design. Remaining optional work:

- extract more detailed PDF tables/figures if source data is available.
- locate any hidden Rann code outside current workspace, because the PDF references functionality not visible as code.

### Phase 2: Engine Specification

Status: this document.

### Phase 3: Minimal Viable Solver

Build the flat-terrain MVP only after agreement on API boundaries.

Recommended first implementation sequence:

1. create package skeleton.
2. extract `Grid`, `SWEParams`, `HRFSolver` concepts into clean modules.
3. port DW-FV into `ohie.hydro.solvers.diffusive_wave_fv`.
4. port raster/vector IO.
5. port D8/outfall.
6. implement D-Infinity and blue spots.
7. port intervention objects and applier.
8. implement scenario compare.
9. add small synthetic tests.
10. add first benchmark configs.

### Phase 4: Benchmarking

Do not claim OHIE is validated until benchmarks are runnable and versioned.

## Open Source Defaults

Recommended license: **Apache 2.0**.

Reason:

- permissive like MIT.
- clearer patent grant.
- better for infrastructure/engineering adoption.

Testing requirements:

- unit tests for terrain routing.
- mass balance tests for solvers.
- intervention effect tests.
- scenario compare tests.
- benchmark smoke tests.

Documentation requirements:

- plain-language examples.
- reproducible YAML configs.
- "what changed and why" intervention explanations.
- no dashboard dependency.

## Strategic Positioning

OHIE should not compete with HEC-RAS or MIKE as a certified final-design replacement.

It should compete on workflow:

> Simulate baseline, apply interventions, recompute, compare, explain, and iterate.

The strategic differentiator is not just hydrodynamics. It is **intervention-aware hydrodynamic decision intelligence**.

