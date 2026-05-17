# OHIE Phase 7: Scientific Defensibility Report

## What Changed

Phase 7 focuses on narrowing the gap between the claims OHIE can make and the physics it actually implements.

### Flux Coupling

- Added `ohie/hydro/boundaries/flux_coupling.py`
- Added `FluxCoupledRiverBoundary`
- Kept overwrite-stage forcing available for comparison only

### Hydraulic Couplers

- Added `ohie/interventions/couplers/`
- Added `HydraulicCoupler`
- Upgraded `CulvertResize` to a coupler-backed exchange model
- Upgraded `Pump` to a coupler-backed transfer model

### Trust-Boundary Documentation

- Added `docs/claim_discipline.md`
- Added `docs/confidence_matrix.md`
- Added `phase7_review/reviewer_attacks.md`

### Failure Transparency

- Added `validation/failure_cases/`
- Documented timestep, terrain discontinuity, boundary, and parameter-regime failures

## Defensibility Comparison

### Overwrite Boundary

Strength:

- simple
- easy to interpret

Weakness:

- imposes stage directly on depth
- can look like coupling without actually being coupling

### Flux-Coupled Boundary

Strength:

- exchange is head-driven
- outflow is capped by available water
- more defensible for a compound-forcing scaffold

Weakness:

- still simplified
- still not a calibrated river-plain interaction model

## Current Claim Discipline

The right claim now is:

> OHIE provides benchmark reproduction scaffolds, flux-coupled boundary approximations, and coupler-based intervention comparisons.

The wrong claim would be:

> OHIE is now a calibrated compound-flood decision engine.

