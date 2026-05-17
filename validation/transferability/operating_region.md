# Operating Region Analysis

## Summary

The flux-coupling approximation does not exhibit a shared transferable operating region across the tested terrain classes under the current mass-error threshold.

## Stable Region Table

| Terrain | Stable Region | Best Default | Confidence |
|----------|----------------|--------------|------------|
| Flat terrain | No shared stable region under the 1% mass-error threshold | `1e-6` only as a local benchmark-scale compromise | Low |
| Moderate gradient | No shared stable region under the 1% mass-error threshold | `1e-6` only as a local benchmark-scale compromise | Low |
| Steep edge case | No shared stable region under the 1% mass-error threshold | `1e-6` only as a local benchmark-scale compromise | Low |
| Resolution variation | No shared stable region under the 1% mass-error threshold | `1e-6` only as a local benchmark-scale compromise | Low |

## Interpretation

- The coefficient story does **not** transfer cleanly outside the original benchmark chip.
- The same ordering remains visible, but it is not enough to establish a shared stable region.
- Mass error dominates the sweep across all tested terrain classes.
- `1e-6` is only the least-bad local compromise on the original benchmark chip, not a universal default.

## Reviewer-facing conclusion

The approximation is benchmark-local and empirically tuned. It is not yet transferable in the scientific sense required for a general boundary default.
