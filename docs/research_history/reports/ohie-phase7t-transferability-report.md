# OHIE Phase 7T: Transferability and Boundary Robustness Report

## Summary

Phase 7T checks whether the flux-coupled boundary approximation generalizes beyond the original benchmark chip.

## Result

The coefficient story does **not** survive transferability testing as a shared operating default.

### What survived

- the same coefficient ordering remains visible across terrain classes
- the approximation remains interpretable as a local exchange law
- the sweep identifies a failure boundary instead of hiding it

### What tightened

- mass error becomes unacceptably large across all tested terrain classes under the current sweep
- the coefficient is now best described as a local benchmark-scale effective conductance only
- no shared stable region survives the 1% mass-error threshold

## Operating Region

Best current reading:

- no transferable cross-terrain region survives the current mass-error threshold
- `1e-6` remains only a local benchmark-scale compromise on the original chip
- `2e-6`, `5e-6`, and `1e-5` all become progressively less defensible as aggressiveness rises

## Transferability Conclusion

The approximation does not generalize modestly enough to support a transferable default.

That is still scientifically useful, because the failure mode is now explicit rather than hidden behind optimistic wording.

## Next Bottleneck

The next scientific bottleneck is not more capability.

It is:

> whether a revised boundary law can recover a shared operating region without disguising mass-error growth

That would require a new evidence step, not a feature step.
