# Transferability Failure Modes

## Steep terrain overreaction

Expected failure:

- boundary exchange can become less meaningful as terrain slope dominates routing

Why:

- the flux law is still a local exchange approximation, so steep terrain should reduce its visible influence

Confidence implication:

- if the boundary drives too much change on steep terrain, the approximation is too aggressive

## Flat terrain under-response

Expected failure:

- very low coefficients may barely alter inundation or persistence

Why:

- flat terrain can require some exchange signal before the boundary becomes hydrologically visible

Confidence implication:

- too little response makes the boundary hard to justify as more than bookkeeping

## Resolution instability

Expected failure:

- the same coefficient may look stronger or weaker as cell size changes

Why:

- exchange is interpreted at the cell scale, so discretization matters

Confidence implication:

- a strong resolution dependence would weaken the claim of bounded transferability

## Excessive exchange coefficient

Expected failure:

- mass error and boundary aggressiveness rise together

Why:

- the flux law becomes too strong and stops behaving like a cautious exchange approximation

Confidence implication:

- the model should not use that coefficient region for defensible claims

## Weak sensitivity

Expected failure:

- coefficient changes do not produce meaningfully different behavior

Why:

- the boundary is too weak to matter and becomes difficult to interpret scientifically

Confidence implication:

- a physically interpretable approximation should still respond to coefficient changes

## Transferability collapse across terrain families

Expected failure:

- the same coefficient region does not survive flat, moderate, steep, and resolution-variant terrain classes

Why:

- the approximation is benchmark-local and may depend on the original terrain chip, grid size, and local boundary geometry

Confidence implication:

- if no shared operating region survives the sweep, the coefficient is not transferable as a universal default
