# Transferability Results

## transferability_boundary_robustness

Assumptions: same flux-coupling law evaluated on multiple terrain regimes and resolution variants
Limitations: terrain families are benchmark regimes, not externally calibrated basins; the study reveals strong terrain and resolution dependence and no shared stable region under the current mass-error threshold
Confidence: Low for transferable generalization; Medium only as a local benchmark-scale approximation on the original chip

Best default: No transferable default identified; 1e-6 remains a local benchmark-scale compromise only

| Terrain | Coefficient | Grid | Cell size (m) | Mean depth (m) | Persistence (s) | Boundary volume (m3) | Mass error | Flooded cells | Qualitative realism |
|---|---:|---|---:|---:|---:|---:|---:|---:|---|
| flat | 2.0e-07 | 26x26 | 30.9 | 0.002 | 69.2 | 312.5 | 0.397586 | 7 | aggressive / trust limited |
| flat | 5.0e-07 | 26x26 | 30.9 | 0.005 | 200.0 | 784.0 | 0.453437 | 10 | aggressive / trust limited |
| flat | 1.0e-06 | 26x26 | 30.9 | 0.010 | 261.4 | 1569.2 | 0.475600 | 10 | aggressive / trust limited |
| flat | 2.0e-06 | 26x26 | 30.9 | 0.019 | 307.6 | 3137.6 | 0.487492 | 15 | aggressive / trust limited |
| flat | 5.0e-06 | 26x26 | 30.9 | 0.046 | 322.9 | 7828.5 | 0.494911 | 25 | aggressive / trust limited |
| flat | 1.0e-05 | 26x26 | 30.9 | 0.098 | 530.5 | 15594.4 | 0.497432 | 36 | aggressive / trust limited |
| moderate | 2.0e-07 | 26x26 | 30.9 | 0.001 | 0.0 | 18.7 | 0.071183 | 0 | aggressive / trust limited |
| moderate | 5.0e-07 | 26x26 | 30.9 | 0.001 | 0.0 | 46.7 | 0.146586 | 0 | aggressive / trust limited |
| moderate | 1.0e-06 | 26x26 | 30.9 | 0.002 | 0.0 | 93.4 | 0.226596 | 0 | aggressive / trust limited |
| moderate | 2.0e-06 | 26x26 | 30.9 | 0.003 | 0.0 | 186.5 | 0.311649 | 0 | aggressive / trust limited |
| moderate | 5.0e-06 | 26x26 | 30.9 | 0.007 | 0.0 | 463.7 | 0.402235 | 0 | aggressive / trust limited |
| moderate | 1.0e-05 | 26x26 | 30.9 | 0.013 | 0.0 | 919.1 | 0.445387 | 0 | aggressive / trust limited |
| steep | 2.0e-07 | 26x26 | 30.0 | 0.001 | 0.0 | 12.6 | 0.060661 | 0 | aggressive / trust limited |
| steep | 5.0e-07 | 26x26 | 30.0 | 0.001 | 0.0 | 31.5 | 0.128253 | 0 | aggressive / trust limited |
| steep | 1.0e-06 | 26x26 | 30.0 | 0.002 | 0.0 | 62.9 | 0.204034 | 0 | aggressive / trust limited |
| steep | 2.0e-06 | 26x26 | 30.0 | 0.003 | 0.0 | 125.6 | 0.289592 | 0 | aggressive / trust limited |
| steep | 5.0e-06 | 26x26 | 30.0 | 0.006 | 0.0 | 312.6 | 0.387010 | 0 | aggressive / trust limited |
| steep | 1.0e-05 | 26x26 | 30.0 | 0.009 | 11.5 | 621.3 | 0.435959 | 1 | aggressive / trust limited |
| resolution_20 | 2.0e-07 | 20x20 | 40.1 | 0.001 | 0.0 | 16.2 | 0.062881 | 0 | aggressive / trust limited |
| resolution_20 | 5.0e-07 | 20x20 | 40.1 | 0.001 | 0.0 | 40.5 | 0.132201 | 0 | aggressive / trust limited |
| resolution_20 | 1.0e-06 | 20x20 | 40.1 | 0.002 | 0.0 | 80.9 | 0.209003 | 0 | aggressive / trust limited |
| resolution_20 | 2.0e-06 | 20x20 | 40.1 | 0.003 | 0.0 | 161.6 | 0.294567 | 0 | aggressive / trust limited |
| resolution_20 | 5.0e-06 | 20x20 | 40.1 | 0.007 | 0.0 | 401.8 | 0.390482 | 0 | aggressive / trust limited |
| resolution_20 | 1.0e-05 | 20x20 | 40.1 | 0.013 | 0.0 | 796.5 | 0.438022 | 0 | aggressive / trust limited |
| resolution_26 | 2.0e-07 | 26x26 | 30.9 | 0.001 | 0.0 | 12.5 | 0.049823 | 0 | aggressive / trust limited |
| resolution_26 | 5.0e-07 | 26x26 | 30.9 | 0.001 | 0.0 | 31.2 | 0.108317 | 0 | aggressive / trust limited |
| resolution_26 | 1.0e-06 | 26x26 | 30.9 | 0.002 | 0.0 | 62.3 | 0.177963 | 0 | aggressive / trust limited |
| resolution_26 | 2.0e-06 | 26x26 | 30.9 | 0.003 | 0.0 | 124.4 | 0.262295 | 0 | aggressive / trust limited |
| resolution_26 | 5.0e-06 | 26x26 | 30.9 | 0.005 | 0.0 | 309.6 | 0.366545 | 0 | aggressive / trust limited |
| resolution_26 | 1.0e-05 | 26x26 | 30.9 | 0.009 | 0.0 | 615.1 | 0.422576 | 0 | aggressive / trust limited |
| resolution_40 | 2.0e-07 | 40x40 | 20.1 | 0.001 | 0.0 | 12.2 | 0.048698 | 0 | aggressive / trust limited |
| resolution_40 | 5.0e-07 | 40x40 | 20.1 | 0.001 | 0.0 | 30.4 | 0.106183 | 0 | aggressive / trust limited |
| resolution_40 | 1.0e-06 | 40x40 | 20.1 | 0.002 | 0.0 | 60.7 | 0.175072 | 0 | aggressive / trust limited |
| resolution_40 | 2.0e-06 | 40x40 | 20.1 | 0.003 | 0.0 | 121.3 | 0.259137 | 0 | aggressive / trust limited |
| resolution_40 | 5.0e-06 | 40x40 | 20.1 | 0.005 | 0.0 | 301.8 | 0.364050 | 0 | aggressive / trust limited |
| resolution_40 | 1.0e-05 | 40x40 | 20.1 | 0.010 | 0.0 | 599.5 | 0.420875 | 0 | aggressive / trust limited |
