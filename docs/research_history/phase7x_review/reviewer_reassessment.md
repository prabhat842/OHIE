# Reviewer Reassessment

## Skeptical Hydrologist

Would they say:

- local tuning artifact, if the external case still shows high mass error and narrow response
- bounded empirical approximation, only if the open-DEM case shows a clear but limited response

Current risk:

- the coefficient may still be terrain dependent enough to fail as a shared default

## Flood Modeler

Would they say:

- local tuning artifact, if the external case does not change the transfer story
- bounded empirical approximation, if the open-DEM case behaves qualitatively and reproducibly

Current risk:

- the boundary law may still be too simple to call transferable hydraulics

## Municipal Engineer

Would they say:

- local tuning artifact, if the result looks like a one-off benchmark trick
- bounded empirical approximation, if the response is interpretable and not overfit

Current risk:

- this is still not design-grade infrastructure modelling

## Reproducibility Reviewer

Would they say:

- local tuning artifact, if the external data and preprocessing are not documented tightly
- bounded empirical approximation, if the dataset and one-case workflow are reproducible and narrow

Current risk:

- only one external case is used, so the conclusion must stay limited to transferability, not general validity

## Current reading after the open-DEM case

The strongest reviewer position is now:

> bounded empirical approximation, not universal default

Why:

- the external case improved relative to the benchmark family
- the coefficient response is visible and reproducible
- the coefficient still remains terrain dependent

Residual concern:

- one case is not enough to argue general transferability across all Brahmaputra floodplain regimes
