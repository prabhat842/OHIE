# Boundary Benchmark Results

## stage_response_benchmark

Assumptions: same local terrain chip, same rainfall, staged river boundary applied to the same mask
Limitations: qualitative behavior-class benchmark only; not a calibrated river-plain experiment
Confidence: Medium for behavior-class defensibility; Low for river-urban calibration

Expected behavior: increasing stage should increase near-river depth and persistence; flux-coupled response should remain more gradual than overwrite forcing
Observed behavior: overwrite forcing pins near-river depth to stage; flux-coupled forcing responds gradually and keeps mass error lower than high-coefficient exchange

| Stage (m) | Boundary | Near-river mean depth (m) | Near-river persistence (s) | Mass error |
|---:|---|---:|---:|---:|
| 10.150 | overwrite | 0.150 | 3598.0 | 0.000000 |
| 10.150 | flux_coupled | 0.034 | 1800.0 | 0.002206 |
| 10.300 | overwrite | 0.300 | 3598.0 | 0.000000 |
| 10.300 | flux_coupled | 0.035 | 1800.0 | 0.004659 |
| 10.450 | overwrite | 0.450 | 3598.0 | 0.000000 |
| 10.450 | flux_coupled | 0.035 | 1800.0 | 0.007089 |
