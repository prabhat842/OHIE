# Physics Assumptions

The current OHIE solver is a fast diffusive-wave finite-volume approximation.

Approximated:

- Momentum is not fully prognostic as in full shallow-water equations.
- Flow is terrain-gradient driven through Manning-style conveyance.
- Local face fluxes use stability caps to avoid draining cells unrealistically in one timestep.
- Current culvert/weir/gate structures are simplified rating-curve couplers.

Missing:

- Full shallow-water solver in the new OHIE package.
- Calibrated turbulence, sediment, salinity, and pipe surcharge physics.
- Full dynamic outfall submergence and backwater closure logic.

Numerical tradeoff:

- The MVP prioritizes robust scenario iteration over high-order hydraulic fidelity.

