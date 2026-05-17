"""Terrain intelligence utilities."""

from ohie.terrain.depressions import Depression, find_blue_spots
from ohie.terrain.routing import D8Routing, DInfinityRouting, MultiFlowRouting, RoutingNetwork, RoutingStrategy
from ohie.terrain.routing_d8 import D8Network, build_d8_network

__all__ = [
    "D8Network",
    "D8Routing",
    "DInfinityRouting",
    "Depression",
    "MultiFlowRouting",
    "RoutingNetwork",
    "RoutingStrategy",
    "build_d8_network",
    "find_blue_spots",
]
