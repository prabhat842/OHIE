# Intervention API

Interventions modify model physics.

Implemented interventions:

- `DetentionBasin`
- `ChannelCarve`
- `CulvertResize`
- `Pump`

Hydraulic structures:

- `CulvertCoupler`
- `WeirCoupler`
- `GateCoupler`
- `PumpStructure`

Every intervention should return an `InterventionEffect` so scenario comparisons can explain what changed.

