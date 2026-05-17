# Extension Guide

Researchers can extend OHIE through protocols:

- Add routing: implement `RoutingStrategy.route()`.
- Add boundary: implement `BoundaryCondition.apply()`.
- Add structure: implement `HydraulicStructure.apply()`.
- Add intervention: implement an object with `apply(solver, routing)`.
- Add metrics: create functions over depth time series.

Extensions should document:

- physics represented,
- assumptions,
- required inputs,
- stability limits,
- benchmark behavior.

