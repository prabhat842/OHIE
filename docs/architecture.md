# OHIE Architecture Overview

OHIE is organized around replaceable scientific components:

- `ohie.hydro`: grid, solver, boundary, and structure primitives.
- `ohie.terrain`: terrain conditioning, routing, depressions, and basin intelligence.
- `ohie.interventions`: physics-modifying interventions and hydraulic structures.
- `ohie.scenarios`: baseline/intervention runs, comparison, and temporal metrics.
- `ohie.config`: reproducible experiment configs.
- `ohie.benchmarks`: synthetic method comparisons.
- `ohie.io`: optional geospatial IO.

The engine is designed so researchers can swap routing, boundaries, interventions, and metrics without editing solver internals.

