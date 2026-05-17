# Sensitivity Results

## manning

| Parameter | Value | Max Depth | Flooded Cells / Area Reduction | Volume | Mass Error | Stable |
|---|---:|---:|---:|---:|---:|---|
| manning_n | 0.025 | 0.0833 | 0 | 14700.000 | 1.237e-16 | PASS |
| manning_n | 0.04 | 0.0664 | 0 | 14700.000 | 1.237e-16 | PASS |
| manning_n | 0.06 | 0.0541 | 0 | 14700.000 | 1.237e-16 | PASS |
| manning_n | 0.09 | 0.0424 | 0 | 14700.000 | 1.237e-16 | PASS |

## resolution

| Parameter | Value | Max Depth | Flooded Cells / Area Reduction | Volume | Mass Error | Stable |
|---|---:|---:|---:|---:|---:|---|
| resolution_m | 10.0 | 0.0561 | 0 | 19200.000 | 1.895e-16 | PASS |
| resolution_m | 30.0 | 0.0530 | 0 | 19200.000 | 0 | PASS |
| resolution_m | 90.0 | 0.0376 | 0 | 18252.000 | 4.186e-15 | PASS |

## timestep

| Parameter | Value | Max Depth | Flooded Cells / Area Reduction | Volume | Mass Error | Stable |
|---|---:|---:|---:|---:|---:|---|
| dt_s | 0.5 | 0.0600 | 0 | 14700.000 | 1.237e-16 | PASS |
| dt_s | 1.0 | 0.0600 | 0 | 14700.000 | 1.237e-16 | PASS |
| dt_s | 2.0 | 0.0598 | 0 | 14700.000 | 1.237e-16 | PASS |
| dt_s | 5.0 | 0.0603 | 0 | 14700.000 | 1.237e-16 | PASS |
| dt_s | 10.0 | 0.0596 | 0 | 14700.000 | 1.237e-16 | PASS |

## rainfall

| Parameter | Value | Max Depth | Flooded Cells / Area Reduction | Volume | Mass Error | Stable |
|---|---:|---:|---:|---:|---:|---|
| rain_mm_hr | 10.0 | 0.0110 | 0 | 3675.000 | 1.237e-16 | PASS |
| rain_mm_hr | 25.0 | 0.0362 | 0 | 9187.500 | 3.96e-16 | PASS |
| rain_mm_hr | 50.0 | 0.0747 | 0 | 18375.000 | 1.98e-16 | PASS |
| rain_mm_hr | 75.0 | 0.1071 | 3 | 27562.500 | 1.32e-16 | PASS |

## intervention

| Parameter | Value | Max Depth | Flooded Cells / Area Reduction | Volume | Mass Error | Stable |
|---|---:|---:|---:|---:|---:|---|
| detention_depth_m | 0.5 | 0.0000 | -2700.0 | 105.840 | 0 | PASS |
| detention_depth_m | 1.0 | 0.0000 | -4500.0 | 105.840 | 0 | PASS |
| detention_depth_m | 2.0 | 0.0000 | -4500.0 | 105.840 | 0 | PASS |

