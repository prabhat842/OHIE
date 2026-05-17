# Routing API

Routing lives in `ohie.terrain.routing`.

Implemented:

- `D8Routing`: single steepest downslope receiver.
- `DInfinityRouting`: continuous-angle, two-receiver flow partition.
- `MultiFlowRouting`: scaffold delegating to D-Infinity until full MFD is implemented.

Routing strategies return `RoutingNetwork`, which stores receivers, weights, flow accumulation, outfalls, and path-to-outfall helpers.

Scientific honesty:

- `DInfinityRouting` is Tarboton-inspired, but not yet a complete reproduction of every triangular-facet edge case.

