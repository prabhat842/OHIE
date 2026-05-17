# Compound Forcing Comparison

## overwrite_vs_flux_coupling

Assumptions: same terrain chip and same prescribed stage; flux-coupled boundary uses head-driven exchange instead of depth overwrite
Limitations: not a calibrated river model; the river mask is synthetic; exchange coefficient is a defensible approximation, not a field-calibrated conductance
Confidence: Medium for showing behavioral difference; Low for river-urban calibration

| Mode | Observed |
|---|---|
| overwrite-style boundary | max_depth=1.089m, flooded_cells=130, boundary_volume=23518.0m3, near_river_mean_depth=0.350m, near_river_persistence=3598.0s |
| flux-coupled boundary | max_depth=1.089m, flooded_cells=130, boundary_volume=89.1m3, near_river_mean_depth=0.035m, near_river_persistence=1800.0s |

| Comparison | Value |
|---|---:|
| max_depth_delta_m | 0 |
| flooded_cells_delta | 0 |
| boundary_volume_delta_m3 | 23429 |
| near_river_mean_depth_delta_m | 0.31528 |
| near_river_persistence_delta_s | 1798 |
| overwrite_mass_error | 6.35058e-13 |
| flux_mass_error | 0.00547189 |
