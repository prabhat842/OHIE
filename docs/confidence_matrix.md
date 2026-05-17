# Confidence Matrix

Conservative confidence labels for the current OHIE state.

| Capability | Confidence | Why |
|---|---|---|
| Flat terrain routing | Medium | Works on small benchmark chips and shows D8/D-Infinity differences |
| Persistence estimation | Medium | Temporal metrics are implemented and behave consistently in synthetic tests |
| Flux-based boundary coupling | Low-Medium | Head-driven exchange is more defensible than overwrite forcing, but still simplified |
| River-urban coupling | Low | No calibrated coupled river solver or measured hydrograph integration |
| Intervention comparison | Medium-Low | Scenario comparison exists, but coupler realism is still limited |
| Hydraulic infrastructure realism | Low | Couplers are interpretable approximations, not pipe-network hydraulics |
| Real-world calibration | Low | No calibration workflow or observational fitting in Phase 7 |
| Failure-mode transparency | Medium | Explicit trust-boundary cases are now documented |

