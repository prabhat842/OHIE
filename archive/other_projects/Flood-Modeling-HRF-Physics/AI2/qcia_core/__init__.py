"""
QCIA Core - Quantum-Inspired Causal Intelligence Architecture

A library for causal discovery, causal reasoning, quantum-inspired optimization,
and risk-aware decision making.
"""

from .causal_graph import CausalGraph, Edge
from .causal_discovery import CausalDiscoveryEngine
from .causal_reasoning import (
    StructuralEquation,
    StructuralCausalModel,
    CausalReasoningEngine
)
from .quantum_optimizer import (
    QuantumInspiredOptimizer,
    AnnealingSchedule
)

__version__ = "0.1.0"

__all__ = [
    "CausalGraph",
    "Edge",
    "CausalDiscoveryEngine",
    "StructuralEquation",
    "StructuralCausalModel",
    "CausalReasoningEngine",
    "QuantumInspiredOptimizer",
    "AnnealingSchedule",
]

