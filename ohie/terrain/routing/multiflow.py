from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ohie.terrain.routing.base import RoutingNetwork
from ohie.terrain.routing.dinf import DInfinityRouting


@dataclass(frozen=True)
class MultiFlowRouting:
    """Future multiple-flow-direction strategy scaffold.

    Current behavior delegates to D-Infinity so experiments can select the
    strategy without breaking. A later implementation should distribute flow to
    all downslope neighbors using slope-weighted exponents.
    """

    method: str = "multiflow"

    def route(self, bed: np.ndarray, outfall_mask: np.ndarray | None = None) -> RoutingNetwork:
        network = DInfinityRouting().route(bed, outfall_mask)
        network.method = self.method
        return network

