# Reviewer Attacks

## Skeptical Hydrologist

Strongest criticism:

- The river boundary is still an exchange approximation, not a coupled river-plain model.

Remaining weakness:

- No measured hydrograph, no backwater calibration, no discharge validation.

Future fix path:

- Replace exchange coefficients with calibrated stage-discharge or boundary flux relations for specific test basins.

## Flood Modeler

Strongest criticism:

- The solver still relies on a diffusive-wave approximation with hard caps and limited structure realism.

Remaining weakness:

- No pipe-network hydraulics, no full SWE solver, and no explicit energy validation.

Future fix path:

- Add a verified boundary-flux study and a documented structural coupler benchmark set.

## Municipal Engineer

Strongest criticism:

- The tool can compare interventions, but it cannot yet rank them under budget, operations, or failure constraints.

Remaining weakness:

- Infrastructure objects are still simplified and not design-grade.

Future fix path:

- Add optimization only after hydraulic couplers and boundary exchange are defensible.

## Reproducibility Reviewer

Strongest criticism:

- The benchmark data are reproducible, but still partly derived or proxy-based rather than fully open-data-native.

Remaining weakness:

- No automatic open-data ingestion and no calibrated remote-sensing pipeline.

Future fix path:

- Add explicit download/preprocessing scripts for open DEM and observation products, with licensing notes.

