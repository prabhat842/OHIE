#!/usr/bin/env python3
"""
Hydraulic Feasibility Checker
==============================
Physics-based rules for intervention placement and sizing.

Implements civil engineering domain knowledge:
- Manning's equation for culvert sizing
- Froude number checks for flow regime
- Gradient requirements for gravity drainage
- Flow accumulation thresholds
"""

import numpy as np
from typing import Dict, Tuple, Optional


class HydraulicFeasibilityChecker:
    """
    Checks if interventions are hydraulically feasible and recommends types.
    
    Based on standard civil engineering practice and hydraulic theory.
    """
    
    def __init__(self, dem: np.ndarray, h: np.ndarray, u: np.ndarray, v: np.ndarray,
                 flow_accum: Optional[np.ndarray] = None, dx: float = 100.0):
        """
        Args:
            dem: Digital elevation model (bed elevation)
            h: Water depth grid
            u: x-velocity
            v: y-velocity
            flow_accum: Flow accumulation grid (number of upstream cells)
            dx: Grid cell size (m)
        """
        self.dem = dem
        self.h = h
        self.u = u
        self.v = v
        self.flow_accum = flow_accum if flow_accum is not None else np.ones_like(dem)
        self.dx = dx
        
        # Pre-compute derived fields
        self.velocity = np.sqrt(u**2 + v**2)
        self.froude = self._compute_froude()
        self.gradient_x, self.gradient_y = self._compute_gradients()
        
    def _compute_froude(self) -> np.ndarray:
        """Compute Froude number: Fr = v / sqrt(g*h)"""
        g = 9.81
        h_safe = np.maximum(self.h, 0.01)  # Avoid division by zero
        return self.velocity / np.sqrt(g * h_safe)
    
    def _compute_gradients(self) -> Tuple[np.ndarray, np.ndarray]:
        """Compute bed gradients in x and y directions."""
        grad_x = np.gradient(self.dem, self.dx, axis=0)
        grad_y = np.gradient(self.dem, self.dx, axis=1)
        return grad_x, grad_y
    
    def check_intervention(self, candidate: Dict) -> Tuple[bool, str, str]:
        """
        Check if intervention is hydraulically feasible.
        
        Args:
            candidate: Intervention dict with 'type' and 'location'
        
        Returns:
            (feasible, reason, recommended_type)
        """
        itype = candidate['type']
        i, j = candidate['location']
        
        # Bounds check
        if not (0 < i < self.dem.shape[0]-1 and 0 < j < self.dem.shape[1]-1):
            return False, "boundary", itype
        
        # Dispatch to type-specific checks
        if 'culvert' in itype.lower():
            return self._check_culvert(i, j, itype)
        elif 'channel' in itype.lower() or 'drain' in itype.lower():
            return self._check_channel(i, j, itype)
        elif 'pond' in itype.lower() or 'basin' in itype.lower() or 'detention' in itype.lower():
            return self._check_pond(i, j, itype)
        elif 'pump' in itype.lower():
            return self._check_pump(i, j, itype)
        elif 'levee' in itype.lower() or 'wall' in itype.lower():
            return self._check_barrier(i, j, itype)
        elif 'permeable' in itype.lower():
            return self._check_permeable(i, j, itype)
        else:
            # Unknown type, allow but don't recommend
            return True, "unknown_type", itype
    
    def _check_culvert(self, i: int, j: int, itype: str) -> Tuple[bool, str, str]:
        """Check culvert feasibility."""
        
        # Rule 1: Need downstream gradient (gravity flow)
        grad_mag = np.sqrt(self.gradient_x[i,j]**2 + self.gradient_y[i,j]**2)
        
        if grad_mag < 0.001:  # < 0.1% slope
            return False, "no_gradient", "pond_medium"  # Suggest storage instead
        
        # Rule 2: Need sufficient flow to convey
        flow_contrib = self.flow_accum[i, j]
        
        if flow_contrib < 5:  # Very low contributing area
            return False, "no_flow", "permeable_pavement"
        
        # Rule 3: Subcritical flow (Fr < 1) for stable culvert operation
        if self.froude[i, j] > 1.2:  # Allow slight margin
            return False, "supercritical", "channel_upgrade_concrete"
        
        # Rule 4: Not too deep (culvert would be submerged/ineffective)
        if self.h[i, j] > 1.5:
            return False, "too_deep", "pump_medium"
        
        # Feasible! Recommend size based on flow
        if flow_contrib > 100:
            recommended = "channel_upgrade_concrete"  # High flow needs channel
        elif grad_mag > 0.02:
            recommended = "culvert_box_2x2"  # Good gradient, standard size
        else:
            recommended = "culvert_box_2x2"  # Default
        
        return True, "feasible", recommended
    
    def _check_channel(self, i: int, j: int, itype: str) -> Tuple[bool, str, str]:
        """Check channel/drain upgrade feasibility."""
        
        # Channels need good gradient and high flow
        grad_mag = np.sqrt(self.gradient_x[i,j]**2 + self.gradient_y[i,j]**2)
        flow_contrib = self.flow_accum[i, j]
        
        if grad_mag < 0.005:  # < 0.5% slope
            return False, "no_gradient", "pond_medium"
        
        if flow_contrib < 20:  # Channels for significant flow
            return False, "low_flow", "culvert_box_2x2"
        
        # Channels work well in moderate Froude numbers
        if self.froude[i, j] > 1.5:  # Too fast, erosion risk
            return False, "supercritical", "levee_earthen"
        
        return True, "feasible", itype
    
    def _check_pond(self, i: int, j: int, itype: str) -> Tuple[bool, str, str]:
        """Check detention/retention pond feasibility."""
        
        # Ponds need low gradient (to hold water) and depression
        grad_mag = np.sqrt(self.gradient_x[i,j]**2 + self.gradient_y[i,j]**2)
        
        if grad_mag > 0.01:  # > 1% slope, water drains too fast
            return False, "too_steep", "channel_upgrade_concrete"
        
        # Check if in local depression (lower than neighbors)
        neighbors = [
            self.dem[i-1, j], self.dem[i+1, j],
            self.dem[i, j-1], self.dem[i, j+1]
        ]
        if self.dem[i, j] > min(neighbors):  # Not in depression
            return False, "not_lowland", "culvert_box_2x2"
        
        # Ponds work best where water pools (low velocity)
        if self.velocity[i, j] > 0.5:  # Too much flow, won't retain
            return False, "high_velocity", "channel_upgrade_concrete"
        
        # Check depth - need sufficient storage potential
        if self.h[i, j] < 0.2:  # Too shallow to justify pond
            return False, "too_shallow", "permeable_pavement"
        
        # Recommend size based on depth
        if self.h[i, j] > 0.8:
            recommended = "pond_large"
        else:
            recommended = "pond_medium"
        
        return True, "feasible", recommended
    
    def _check_pump(self, i: int, j: int, itype: str) -> Tuple[bool, str, str]:
        """Check pump station feasibility."""
        
        # Pumps for areas where gravity drainage fails
        grad_mag = np.sqrt(self.gradient_x[i,j]**2 + self.gradient_y[i,j]**2)
        
        # If good gradient, gravity drainage is better (cheaper)
        if grad_mag > 0.008:
            return False, "has_gradient", "culvert_box_2x2"
        
        # Pumps need significant water to move
        if self.h[i, j] < 0.3:
            return False, "insufficient_depth", "permeable_pavement"
        
        # Pumps work in backwater zones (low velocity, deep water)
        if self.velocity[i, j] > 0.8:
            return False, "high_velocity", "channel_upgrade_concrete"
        
        return True, "feasible", itype
    
    def _check_barrier(self, i: int, j: int, itype: str) -> Tuple[bool, str, str]:
        """Check levee/floodwall feasibility."""
        
        # Barriers ONLY work in subcritical flow (Fr < 0.7)
        if self.froude[i, j] > 0.7:
            return False, "supercritical", "channel_upgrade_concrete"
        
        # Barriers for moderate depths (not too shallow, not too deep)
        if self.h[i, j] < 0.15:
            return False, "too_shallow", "permeable_pavement"
        
        if self.h[i, j] > 1.2:  # Too deep, barrier would need to be very tall
            return False, "too_deep", "pond_large"
        
        # Barriers should not be in high-velocity zones (will fail)
        if self.velocity[i, j] > 2.0:
            return False, "high_velocity", "channel_upgrade_concrete"
        
        # Recommend type based on depth
        if self.h[i, j] > 0.6:
            recommended = "flood_wall_concrete"  # Need strong structure
        else:
            recommended = "levee_earthen"  # Earthen is cheaper
        
        return True, "feasible", recommended
    
    def _check_permeable(self, i: int, j: int, itype: str) -> Tuple[bool, str, str]:
        """Check permeable pavement feasibility."""
        
        # Permeable surfaces for shallow, slow-moving water
        if self.h[i, j] > 0.4:
            return False, "too_deep", "pond_medium"
        
        if self.velocity[i, j] > 0.5:
            return False, "high_velocity", "culvert_box_2x2"
        
        # Need moderate gradient (not flat, not steep)
        grad_mag = np.sqrt(self.gradient_x[i,j]**2 + self.gradient_y[i,j]**2)
        
        if grad_mag < 0.002:
            return False, "too_flat", "pond_medium"
        
        if grad_mag > 0.015:
            return False, "too_steep", "channel_upgrade_concrete"
        
        return True, "feasible", itype
    
    def recommend_intervention_type(self, i: int, j: int) -> str:
        """
        Recommend best intervention type based on hydraulic conditions.
        
        Returns:
            Recommended intervention type string
        """
        depth = self.h[i, j]
        vel = self.velocity[i, j]
        fr = self.froude[i, j]
        grad = np.sqrt(self.gradient_x[i,j]**2 + self.gradient_y[i,j]**2)
        flow = self.flow_accum[i, j]
        
        # Decision tree based on hydraulic regime
        
        # Fast-moving shallow water → CONVEYANCE
        if depth < 0.4 and vel > 1.0:
            if flow > 100:
                return "channel_upgrade_concrete"
            elif grad > 0.005:
                return "culvert_box_2x2"
            else:
                return "pump_medium"
        
        # Deep standing water → STORAGE
        elif depth > 0.5 and vel < 0.3:
            if grad < 0.005:
                return "pond_large"
            else:
                return "channel_upgrade_concrete"
        
        # Moderate depth, slow flow → INFILTRATION or STORAGE
        elif depth < 0.4 and vel < 0.5:
            if grad < 0.008:
                return "pond_medium"
            else:
                return "permeable_pavement"
        
        # Backwater (no gradient) → PUMPING
        elif grad < 0.003 and depth > 0.3:
            return "pump_medium"
        
        # Moderate flow → CONVEYANCE
        elif vel > 0.3 and grad > 0.005:
            if flow > 50:
                return "channel_upgrade_concrete"
            else:
                return "culvert_box_2x2"
        
        # Overbank flow (subcritical) → BARRIERS (only if protecting area)
        elif fr < 0.7 and 0.2 < depth < 0.8:
            return "levee_earthen"
        
        # Default: culvert (most versatile)
        return "culvert_box_2x2"
    
    def get_physics_context(self, i: int, j: int) -> Dict:
        """
        Extract physics context for a location (for QCA metadata).
        
        Returns:
            Dict with hydraulic parameters
        """
        grad_mag = np.sqrt(self.gradient_x[i,j]**2 + self.gradient_y[i,j]**2)
        
        return {
            'depth': float(self.h[i, j]),
            'velocity': float(self.velocity[i, j]),
            'froude': float(self.froude[i, j]),
            'gradient': float(grad_mag),
            'flow_accumulation': float(self.flow_accum[i, j]),
            'bed_elevation': float(self.dem[i, j])
        }


