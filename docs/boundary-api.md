# Boundary API

Boundary conditions live in `ohie.hydro.boundaries`.

Implemented:

- `RainfallBoundary`
- `RiverStageBoundary`
- `HydrographBoundary`
- `FixedHeadBoundary`
- `FluxBoundary`
- `SinkBoundary`

Each boundary implements:

```python
def apply(self, solver, t_s: float, dt_s: float) -> None:
    ...
```

Boundary objects modify solver fields before each timestep. This makes temporal forcing explicit and replaceable.

