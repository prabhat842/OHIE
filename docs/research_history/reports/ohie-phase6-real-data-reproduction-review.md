# OHIE Phase 6: Real Data Reproduction & Scientific Benchmark Sprint

## Purpose

Phase 6 moves OHIE from mostly synthetic validation toward reproducible, real-data-informed scientific benchmarking.

The goal is not operational flood forecasting and not a claim that OHIE is superior to established tools. The goal is to demonstrate that OHIE can produce scientifically reasonable behavior on small, reproducible terrain and observation cases while remaining transparent about assumptions, calibration gaps, and missing physics.

## Mission Statement

OHIE Phase 6 should prove that the framework is serious enough for researchers to inspect, rerun, critique, and extend.

The sprint focuses on:

- real terrain behavior
- literature-inspired benchmark reproduction
- remote-sensing alignment
- reproducibility scoring
- researcher onboarding
- lightweight benchmark dataset packaging

The sprint explicitly avoids:

- dashboards
- AI or surrogate models
- GPU acceleration
- major new architecture
- operational flood forecast claims
- perfect shallow-water fidelity claims

## Implementation Scope

### 1. Real Terrain Experiments

Create:

```text
validation/real_terrain/
```

Required benchmark cases:

| Case | Purpose | Required Output |
|------|---------|-----------------|
| Flat terrain case | Test stagnation, persistence, routing realism, and D-Infinity behavior on low-gradient terrain | README, source dataset notes, config, runnable script, expected behavior, observed output |
| River-adjacent terrain case | Test whether river-stage forcing visibly alters flood behavior | README, source dataset notes, config, runnable script, expected behavior, observed output |

Dataset policy:

- Use small reproducible extents only.
- Prefer open datasets such as FABDEM, Copernicus DEM, SRTM, or HydroSHEDS.
- If the repository only contains derived local data, label it honestly as local open-data-derived or historical-project-derived, not as freshly downloaded real data.
- Do not include large raw DEMs.

Scientific honesty required for each case:

- terrain source
- preprocessing assumptions
- spatial resolution
- boundary assumptions
- missing calibration
- confidence level

### 2. Literature Reproduction Benchmarks

Create:

```text
validation/literature/
```

The objective is behavior-class reproduction, not exact parity.

Candidate benchmark classes:

| Benchmark Class | OHIE Behavior To Check |
|-----------------|------------------------|
| Floodplain inundation | Water spreads preferentially through lower terrain and conserves mass reasonably |
| Bowl filling | Ponding occurs before spillover |
| Flat-terrain routing | Routing remains stable despite weak slopes |
| Simplified river forcing | External stage changes affect nearby inundation or drainage |
| Storage attenuation | Detention/retention reduces peak depth, flooded area, or duration |

Required comparison table:

| Benchmark | Literature Behavior | OHIE Behavior | Confidence |
|-----------|---------------------|---------------|------------|

Confidence should be conservative:

- High only for simple, well-constrained behavior.
- Medium for qualitative agreement.
- Low where calibration, missing physics, or incomplete inputs dominate.

### 3. Remote Sensing Comparison

Create:

```text
validation/remote_sensing/
```

Goal:

Compare OHIE inundation outputs against observed or observation-derived water masks.

Preferred observation sources:

- Sentinel-1 SAR water masks
- NDWI-derived optical water masks
- Copernicus EMS flood extent products
- JRC Global Surface Water

Minimum acceptable metrics:

| Metric | Meaning |
|--------|---------|
| IoU | Intersection-over-union between simulated and observed flood masks |
| overlap percent | Fraction of observed flooded cells captured by simulation |
| flooded area agreement | Ratio or percent difference in simulated vs observed flooded area |
| persistence similarity | Similarity of observed/simulated duration where temporal observations exist |

Important limitation:

If only proxy or historical-derived observation masks are available, label the comparison as a remote-sensing scaffold or proxy comparison. Do not present it as real SAR validation.

### 4. Reproducibility Scorecard

Create:

```text
docs/reproducibility.md
```

For each validation case, classify:

| Status | Meaning |
|--------|---------|
| Reproducible | Inputs are included or openly obtainable, script runs, expected behavior documented |
| Partially reproducible | Script/config exist but external data access or preprocessing is incomplete |
| Synthetic only | Scientifically useful, but not a real-data benchmark |

The scorecard should answer:

- Can another researcher rerun this?
- Are inputs obtainable?
- Are preprocessing assumptions documented?
- Are outputs recreated by script?
- Is the confidence level explicit?

### 5. Researcher Quickstart

Create:

```text
docs/quickstart.md
```

Target:

Less than 15 minutes to first experiment.

The quickstart should cover:

1. install dependencies
2. run a synthetic validation case
3. run a real-terrain benchmark
4. inspect outputs
5. modify rainfall or boundary conditions
6. add or alter an intervention
7. understand where assumptions are documented

### 6. Benchmark Dataset Package

Create:

```text
ohie-data/
```

Purpose:

Provide lightweight, shared baseline datasets so researchers are not all testing against different terrain or masks.

Recommended structure:

```text
ohie-data/
├── README.md
├── metadata.yaml
├── real_terrain/
│   ├── flat_terrain_small.npz
│   └── river_adjacent_small.npz
└── remote_sensing/
    └── observed_water_mask_small.npz
```

Dataset package rules:

- Keep files small.
- Prefer arrays, masks, and metadata over large raw rasters.
- Document the upstream source.
- Document any preprocessing.
- Include license/source notes when known.
- If source licensing is unclear, do not redistribute raw data; include scripts or instructions instead.

## Expected Repository Changes

### New Validation Modules

```text
ohie/validation/real_terrain/
ohie/validation/literature/
ohie/validation/remote_sensing/
```

Suggested responsibilities:

| Module | Responsibility |
|--------|----------------|
| `real_terrain` | Run small real-terrain DEM experiments |
| `literature` | Reproduce published behavior classes conservatively |
| `remote_sensing` | Compute agreement metrics between simulated and observed water |

### New Reproducibility Folders

```text
validation/real_terrain/
validation/literature/
validation/remote_sensing/
```

Each runnable benchmark should include:

```text
README.md
source_dataset.md
config.yaml
run.py
expected_behavior.md
observed_output.md
```

### New Documentation

```text
docs/reproducibility.md
docs/quickstart.md
```

### New Dataset Package

```text
ohie-data/
```

## Acceptance Criteria

Phase 6 is complete when the repository contains:

| Deliverable | Acceptance Check |
|-------------|------------------|
| Real terrain report | At least one flat terrain and one river-adjacent case are documented and runnable |
| Literature benchmark report | Behavior comparison table exists with conservative confidence labels |
| Remote sensing comparison | Basic agreement metrics are implemented and demonstrated |
| Reproducibility scorecard | Every benchmark is classified by reproducibility status |
| Researcher quickstart | A new researcher can run a first experiment in under 15 minutes |
| Dataset package | Lightweight benchmark datasets or source instructions exist |
| Scientific honesty section | Assumptions, missing physics, calibration limits, and confidence are explicit |

## Scientific Honesty Requirements

Every Phase 6 benchmark must clearly state:

- whether it is calibrated
- whether terrain is raw, conditioned, or derived
- whether observations are true remote sensing or proxy masks
- whether boundary conditions are measured or synthetic
- whether results are qualitative or quantitative
- what physics are missing
- where OHIE should not yet be trusted

Current expected limitations:

- no groundwater coupling
- no full pipe-network hydraulics
- simplified or approximate backwater behavior
- no operational nowcasting pipeline
- no SAR-specific classification workflow unless explicitly added
- no claim of calibrated municipal accuracy
- no claim of full shallow-water equivalence unless separately validated

## Review Questions

Before implementation, reviewers should decide:

1. Which local historical datasets can be redistributed inside `ohie-data/`?
2. Which datasets should be referenced but not copied because of licensing or size?
3. Should Phase 6 use only existing repository data first, then add external open DEM download scripts later?
4. What minimum remote-sensing comparison is acceptable for the first pass?
5. Should Rann/Kutch-derived flat terrain remain the headline real-terrain benchmark?
6. Should Yamuna-style stage forcing remain the headline river-adjacent benchmark?

## Recommended First Pass

A practical first implementation should avoid external download complexity and produce a reviewable baseline:

1. Package two small local terrain arrays into `ohie-data/`.
2. Add real-terrain scripts that run OHIE on those arrays.
3. Add one observation/proxy mask and compute IoU-style metrics.
4. Add literature-inspired comparison tables.
5. Add reproducibility and quickstart docs.
6. Clearly label anything not yet based on raw external open data.

This gives OHIE a credible Phase 6 foundation without overclaiming.

