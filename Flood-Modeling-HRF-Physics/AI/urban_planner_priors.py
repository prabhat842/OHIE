#!/usr/bin/env python3
"""
Urban Planner Priors for QCIA
==============================
Adds criticality, feasibility, and network-thinking to intervention selection.
"""
import numpy as np
from typing import Dict, List, Tuple
from scipy.ndimage import label


def compute_road_criticality(road_mask: np.ndarray) -> np.ndarray:
    """
    Compute road network criticality via connected component sizes.
    Larger components = arterial/collector roads = higher priority.
    """
    structure = np.array([[0,1,0],[1,1,1],[0,1,0]], dtype=np.uint8)
    labels, num = label(road_mask.astype(np.uint8), structure=structure)
    
    if num == 0:
        return np.zeros_like(road_mask, dtype=np.int32)
    
    # Count sizes per component
    counts = np.bincount(labels.ravel())
    # Map back to grid
    road_comp_size = counts[labels]
    return road_comp_size


def add_urban_planner_bonuses(
    candidate: Dict,
    road_comp_size: np.ndarray,
    flow_accum: np.ndarray | None,
    head_drop: np.ndarray | None
) -> Dict:
    """
    Add urban-planner-aware bonuses to a candidate intervention.
    
    Returns updated candidate with:
    - road_criticality_score: 0-1, higher for arterials
    - network_bonus: 0-1, prioritizes conveyance along high-accum corridors
    - feasibility_score: 0-1, based on context (simplified for now)
    """
    i, j = candidate['location']
    nx, ny = road_comp_size.shape
    
    # 1. Road criticality (component size)
    try:
        ii0, ii1 = max(0, i-1), min(nx, i+2)
        jj0, jj1 = max(0, j-1), min(ny, j+2)
        comp_size = int(np.max(road_comp_size[ii0:ii1, jj0:jj1]))
        # Normalize: assume max ~500 cells for a major arterial in 100x100 grid
        road_crit = min(1.0, comp_size / 500.0)
    except Exception:
        road_crit = 0.0
    
    # 2. Network bonus (conveyance along high-accumulation corridors)
    network = 0.0
    is_conveyance = any(x in candidate['type'] for x in ['channel', 'culvert', 'pump', 'drain', 'smart_valve'])
    if is_conveyance and flow_accum is not None:
        try:
            accum_val = float(flow_accum[i, j])
            # Normalize by grid size
            network = min(1.0, accum_val / (nx * ny * 0.1))  # 10% of grid = major corridor
        except Exception:
            network = 0.0
    
    # Add head_drop bonus for conveyance
    if is_conveyance and head_drop is not None:
        try:
            hd_val = float(head_drop[i, j])
            # Higher head = better hydraulic advantage
            network += min(0.3, hd_val / 0.5)  # 0.5m = strong gradient
        except Exception:
            pass
    
    network = min(1.0, network)
    
    # 3. Feasibility (simplified: reject barriers in critical roads, prefer conveyance)
    feasibility = 1.0
    is_barrier = any(x in candidate['type'] for x in ['wall', 'levee'])
    if is_barrier and road_crit > 0.5:
        feasibility = 0.1  # Barriers on arterials = low feasibility
    
    candidate['road_criticality_score'] = road_crit
    candidate['network_bonus'] = network
    candidate['feasibility_score'] = feasibility
    
    return candidate


def extend_replay_context(candidate: Dict) -> str:
    """
    Build extended context key for replay, including urban-planner features.
    """
    t = candidate['type']
    
    # Connectivity bin
    ddr = candidate.get('distance_to_drain', 1e6)
    conn_bin = 'near' if ddr < 200 else ('mid' if ddr < 400 else 'far')
    
    # Criticality bin
    crit = candidate.get('road_criticality_score', 0.0)
    crit_bin = 'arterial' if crit > 0.5 else ('collector' if crit > 0.2 else 'local')
    
    # Network bin
    net = candidate.get('network_bonus', 0.0)
    net_bin = 'corridor' if net > 0.5 else ('secondary' if net > 0.2 else 'isolated')
    
    # Capacity bin
    cap = candidate.get('rated_capacity', 0.0)
    cap_bin = 'large' if cap > 6.0 else ('med' if cap > 2.0 else 'small')
    
    return f"{t}|conn:{conn_bin}|crit:{crit_bin}|net:{net_bin}|cap:{cap_bin}"


def compute_planner_reward_adjustment(candidate: Dict, base_reward: float) -> float:
    """
    Adjust reward based on urban-planner priors.
    """
    reward = base_reward
    
    # Bonus for critical roads
    crit = candidate.get('road_criticality_score', 0.0)
    reward += crit * 0.3  # Up to 30% bonus for arterials
    
    # Bonus for network position
    net = candidate.get('network_bonus', 0.0)
    reward += net * 0.4  # Up to 40% bonus for corridor/high-accum
    
    # Feasibility penalty
    feas = candidate.get('feasibility_score', 1.0)
    reward *= feas
    
    return reward



