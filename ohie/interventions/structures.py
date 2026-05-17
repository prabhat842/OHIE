from __future__ import annotations

from ohie.interventions.couplers.base import HydraulicCoupler
from ohie.interventions.couplers.flow import DrainUpgradeCoupler, GateCoupler, PumpCoupler, RetentionCoupler, WeirCoupler

HydraulicStructure = HydraulicCoupler
CulvertCoupler = DrainUpgradeCoupler
PumpStructure = PumpCoupler

__all__ = [
    "CulvertCoupler",
    "GateCoupler",
    "HydraulicStructure",
    "PumpStructure",
    "RetentionCoupler",
    "WeirCoupler",
]

