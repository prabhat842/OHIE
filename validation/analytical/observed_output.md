# Analytical Validation Results

| Test | Expected | Observed | Pass/Fail |
|---|---|---|---|
| flat_plane_rainfall | water moves downslope, remains stable, and conserves mass | lower_sum=1.436, upper_sum=1.064, mass_error=3.486e-15 | PASS |
| bowl_depression_filling | water accumulates in the depression and flood persistence is captured | center_depth=0.032, edge_depth=0.006, max_persistence=600.0s | PASS |
| dam_break_approximation | initial water pulse propagates outward with approximate mass conservation | front_cell=29, upstream_mean=0.628, mass_error=0 | PASS |
| steep_vs_flat_routing | routing responds differently to steep and flat terrain; D8 and D-Infinity differ on flat terrain | d8_peak_delta=614.000, d8_dinf_flat_diff=2726.275 | PASS |
| closed_basin_mass_conservation | closed basin without forcing conserves water volume | mass_error=4.366e-16, final_volume=6250.000 | PASS |
