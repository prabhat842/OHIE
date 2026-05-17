# Flux Coupling Rationale

OHIE Phase 7 introduced `FluxCoupledRiverBoundary` as a more defensible approximation than depth overwrite.

## Why the default coefficient exists

The current default exchange coefficient is `1e-6 m^2/s`.

That value is not a calibrated field estimate. It is an empirical operating point chosen because it sits in a conservative part of the observed sensitivity curve:

| Coefficient | Boundary Volume | Mass Error |
|-------------|----------------|-------------|
| `2e-7` | `17.8 m3` | `0.0011` |
| `5e-7` | `44.6 m3` | `0.0028` |
| `1e-6` | `89.1 m3` | `0.0055` |
| `2e-6` | `177.8 m3` | `0.0108` |
| `5e-6` | `442.1 m3` | `0.0260` |
| `1e-5` | `876.3 m3` | `0.0491` |

## Why not `1e-7`?

It is too weak to be operationally useful as a boundary approximation. The exchange remains so small that the boundary risks becoming numerically present but hydrologically negligible.

## Why not `1e-5`?

It starts to behave aggressively and pushes mass error close to five percent on the current benchmark. That is too high for a defensibility sprint.

## Why `1e-6`?

It is a compromise point:

- response is visible
- mass error stays low
- boundary forcing is still much weaker than overwrite-style depth imposition
- the result is interpretable as an approximation rather than a calibrated coupling law

## Tradeoff narrative

The coefficient moves the boundary along a simple three-way tradeoff:

1. responsiveness
2. stability / mass error
3. boundary aggressiveness

Lower values preserve mass better but risk under-response. Higher values increase river influence but quickly make the coupling look like an aggressive sink/source rather than a cautious exchange law.

The current default is therefore best understood as:

> conservative empirical exchange for benchmark scaffolding

not:

> a field-calibrated conductance

## Scaling thought experiment

The coefficient could eventually depend on:

- cell size, because exchange should not change dramatically just because the grid is refined
- boundary length, because a longer river edge should distribute exchange differently than a short one
- terrain resolution, because coarse DEMs hide local storage and micro-relief

One physically reasonable way to think about the coefficient is as an effective conductance per cell area. That suggests the exchange law should be interpreted cautiously when grid resolution changes.

Current takeaway:

- the coefficient is explainable
- the current value is conservative
- it is still empirical
- it should not be presented as a universal hydraulic constant

