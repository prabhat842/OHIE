# Flux Coefficient Generalization

The current flux-coupling coefficient is not universal. Phase 7T tested whether its behavior generalizes across terrain regimes and grid sizes.

## What can be explained

The coefficient is best understood as an effective exchange conductance per cell area. That means it should not be expected to stay identical across every terrain or grid resolution without some adjustment in interpretation.

### Cell size

If the grid is refined, each cell represents a smaller area. A coefficient that is too literal can therefore over- or under-express exchange unless the flux law is interpreted as an effective conductance at the benchmark scale.

### Boundary length

A longer river edge can distribute exchange across more cells. That does not make the coefficient invalid, but it does mean the total exchange response depends on how the boundary is discretized.

### Terrain resolution

Coarser terrain hides micro-relief and reduces small storage contrasts. That can make the same coefficient look more or less aggressive depending on how much local ponding the DEM preserves.

### Slope regime

On steeper terrain, the same boundary should generally exert less visible influence because gravitational routing away from the boundary dominates. On flatter terrain, the same coefficient can matter more because the receiving surface does not drain away as quickly.

## Generalization story

The transferability sweep does **not** support a shared operating region across the tested terrain classes.

Observed behavior:

- the coefficient response is strongly terrain dependent
- mass error rises far beyond the defensible threshold in every tested terrain family
- resolution variation does not recover a stable cross-terrain default

Current interpretation:

> the coefficient is a local benchmark-scale effective conductance on the original chip, not a transferable universal default

That is a defensible scientific story only if it is kept narrow. It is not a calibration claim, and it is not evidence of cross-terrain generalization.
