from __future__ import annotations

import numpy as np

from ohie.terrain.routing import D8Routing, RoutingNetwork

D8Network = RoutingNetwork


def build_d8_network(bed: np.ndarray, outfall_mask: np.ndarray | None = None) -> D8Network:
    """Build D8 flow directions, outfalls, and flow accumulation.

    Historical source: `Runners/build_hydro_network.py` and
    `AI/intervention_applier.py::_build_flow_routing`.
    """
    return D8Routing().route(np.asarray(bed, dtype=np.float64), outfall_mask)
