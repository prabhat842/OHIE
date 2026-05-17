# Next Scientific Bottleneck

Phase 7T established an important negative result:

- the flux-coupling coefficient does not transfer as a shared default across the tested terrain families
- mass error becomes unacceptably large across the current sweep
- the approximation remains local and benchmark-scale, not transferable in the general sense

## Recommended next step

Run a single external open-data transfer case before any new feature work.

### Why this is the right next move

- It tests whether the failure is local to the current benchmark family or more general.
- It is more scientifically valuable than adding new solver capability.
- It gives reviewers a cleaner basis for judging the boundary law.

## Secondary option

If an external transfer case is not available, the next step should be a terrain-aware coefficient study.

That would only be justified if it is framed as:

- an empirical generalization attempt
- not a calibration system
- not a universal law

## What not to do yet

- Phase 8 feature expansion
- new intervention types
- optimization
- AI or surrogate modeling
- claim inflation

## Decision rule

Proceed only if the next evidence step can answer one of these questions:

1. Does the failure persist on an external open-data terrain?
2. Can a terrain-aware coefficient law recover a shared operating region without disguising mass-error growth?

If neither can be answered cleanly, the correct outcome is to document the limitation rather than expand the architecture.
