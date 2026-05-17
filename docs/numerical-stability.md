# Numerical Stability Characterization

OHIE currently uses a fast diffusive-wave finite-volume solver. It is intended for transparent, intervention-aware experimentation, not certified final-design hydraulics.

## Stable Regions Observed So Far

Synthetic tests are stable for:

- grid sizes from roughly 10 m to 90 m in the current validation harness,
- timesteps from 0.5 s to 10 s on the synthetic flat-bowl case,
- Manning n from 0.025 to 0.09,
- rainfall from 10 to 75 mm/hr,
- low-gradient ponding cases with mass error below the current 5% screening threshold.

## Stability Mechanisms

Implemented safeguards:

- face-level flux limiting,
- non-negative water-depth clamp,
- source/sink accounting,
- mass-balance ledger,
- post-step stage enforcement for fixed-head/river-stage boundaries.

## Known Instability Risks

OHIE may behave poorly when:

- interventions create very steep unresolved terrain discontinuities,
- timestep is too large for grid spacing and local depth,
- boundary stages impose abrupt jumps without relaxation,
- structural couplers move too much water through tiny cells,
- D8 routing is used in nearly flat terrain where flow direction is ambiguous,
- cells contain very large depth gradients compared with terrain resolution.

## Practical Guidance

Researchers should:

- start with small timesteps and increase gradually,
- monitor `mass_balance_error_fraction`,
- run timestep sensitivity before interpreting intervention effects,
- compare D8 and D-Infinity in flat terrain,
- avoid treating local peak depth alone as success/failure for storage interventions,
- use persistence and exposure metrics alongside maximum depth.

## Scientific Honesty

The current solver does not prove hydraulic correctness on real sites. It demonstrates transparent, reproducible behavior on synthetic cases. Real-world use requires calibration against gauges, SAR, field observations, or established model outputs.

