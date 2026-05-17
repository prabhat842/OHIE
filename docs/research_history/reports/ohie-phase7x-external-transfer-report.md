# OHIE Phase 7X: External Open-Data Transfer Report

## Summary

Phase 7X tested one open-DEM Brahmaputra floodplain case near Dhakuakhana using AWS Terrain Tiles.

## Result

The current flux-coupling coefficient does **not** look structurally broken outside the benchmark family.

It behaves better on the external open-DEM case than it did on the internal terrain family, which suggests the Phase 7T failure was at least partly benchmark-local.

### Evidence

- Baseline mass error: `0.000000`
- Default `1e-6` mass error: `0.004086`
- Boundary volume: `9858.094 m3`
- Near-edge mean depth increased from `0.028 m` to `0.040 m`
- Near-edge persistence increased from `459.7 s` to `568.2 s`

## Interpretation

This is best classified as:

> local failure on the benchmark family, with partial transfer to the external open-DEM floodplain

That means:

- the coefficient is still terrain dependent
- the approximation is not a universal default
- the transfer problem is not purely structural

## Reviewer-facing conclusion

A skeptical reviewer would likely move from:

- "this is just benchmark-local tuning"

to:

- "this is a bounded empirical approximation with a narrow but real transfer signal"

That is a better scientific position than Phase 7T, but it is still not calibration or validation.

## Next bottleneck

The next question is no longer whether the approximation can transfer at all.

It is:

> what terrain features control whether transfer is narrow, moderate, or lost

That is a terrain-law question, not a feature-expansion question.
