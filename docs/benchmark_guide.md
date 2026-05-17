# Benchmark Guide

OHIE keeps its evidence visible through the `validation/` tree.

## Core benchmark groups

- `validation/analytical/`: controlled hydrodynamic sanity tests
- `validation/boundary_benchmarks/`: stage-response boundary checks
- `validation/boundary_sensitivity/`: coefficient sensitivity and operating region checks
- `validation/compound_forcing/`: overwrite forcing versus flux-coupled approximation
- `validation/external_transfer/`: one external Brahmaputra open-DEM transfer case
- `validation/failure_cases/`: explicit failure modes
- `validation/terrain_regimes/`: terrain-regime transfer characterization
- `validation/transferability/`: internal benchmark-family transfer test

## How to use the benchmarks

1. Start with `validation/analytical/run.py`.
2. Read `validation/README.md` and `docs/scientific_position.md`.
3. Run the boundary and transfer cases.
4. Inspect the observed outputs and compare them to the stated limitations.

## What the benchmarks are for

- benchmark reproduction
- transfer characterization
- failure visibility
- reviewer critique

## What they are not for

- calibration
- operational forecasting
- design-grade drainage sizing
- universal transfer claims

The public rule is simple:

> benchmarks support critique first, claims second.
