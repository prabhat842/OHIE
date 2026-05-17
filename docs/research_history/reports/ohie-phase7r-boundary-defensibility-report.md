# OHIE Phase 7R: Boundary Defensibility Revision Report

## Purpose

Phase 7R narrows the question from “does the boundary exist?” to:

> how defensible is the flux-coupling approximation?

## Flux Coefficient Story

The current default exchange coefficient is `1e-6 m^2/s`.

This is an empirical operating point, not a calibrated constant. It is defensible because it keeps the model in a conservative regime:

- `2e-7` to `5e-7` are safer for mass error but weaker in response.
- `1e-6` is still conservative and visibly responsive.
- `2e-6` begins to push mass error toward one percent.
- `5e-6` and `1e-5` become increasingly aggressive and eventually undermine the defensibility story.

The result is an explainable empirical coefficient, not an arbitrary one.

## Boundary Benchmark Upgrade

Added:

```text
validation/boundary_benchmarks/
```

This benchmark checks the expected direction of response under rising stage:

- higher stage should raise near-river depth
- higher stage should increase persistence
- flux coupling should remain gentler than overwrite forcing

The conclusion is still qualitative only.

## Under-Responsiveness Assessment

The flux boundary is now less likely to be dismissed as over-aggressive.

However, the benchmark shows that it is also less responsive than overwrite forcing, which is expected because it is intentionally conservative.

That means the unresolved question is not “is the coefficient too strong?”

It is:

> where is the defensible operating region for this approximation on the available benchmark terrain?

## Claim Freeze

Added:

```text
docs/public_language.md
```

The public language now forbids inflating the current state into calibrated or coupled claims.

## Reviewer Re-run

The revised reviewer attack shifts from:

- “this is not defensible”

to:

- “this is defensible, but still empirical and not transferable without calibration”

That is the right kind of criticism for this stage.

## Phase 8 Decision

Phase 8 should **not** start as a feature-heavy phase.

The right next move is:

> a short calibration-and-transferability revision sprint, if anything, or a pause for external review.

The model is now scientifically serious enough to defend as a scaffold, but not yet strong enough to justify capability expansion.

