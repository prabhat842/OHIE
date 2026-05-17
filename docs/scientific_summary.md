# OHIE Scientific Summary

## What problem OHIE explores

OHIE explores whether a flood model can move beyond static flood extent prediction and support reproducible intervention comparison with a defensible flux-coupled boundary approximation.

## What was tested

- overwrite forcing versus flux-coupled boundaries
- coefficient sensitivity for the boundary approximation
- failure modes under steep, flat, and mixed-relief terrain
- one external open-DEM transfer case on a Brahmaputra floodplain micro-extent
- a small terrain-regime sweep across multiple open DEM chips

## What worked

- the flux-coupled boundary is more defensible than overwrite-stage forcing
- the coefficient has an explainable conservative operating point
- low-gradient and basin-like terrains preserve the clearest response
- the external open-DEM case showed partial transfer rather than a hard failure

## What failed

- a shared universal coefficient did not survive the internal terrain-family sweep
- mixed-relief terrain weakened transfer clearly
- the approximation is still simplified and not calibrated

## What remains uncertain

- whether the current coefficient can be generalized into a terrain-aware empirical law
- whether additional external cases would preserve the same bounded response
- how far the approximation can go before terrain dependence dominates

## Why the framework matters

OHIE is useful because it makes boundary behavior, failure modes, and transfer limits explicit.

That is scientifically valuable even when the result is negative or partial.

The framework is coherent enough to critique honestly, which is the point of the current phase.
