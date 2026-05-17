#!/usr/bin/env python3
"""
HRF-QCIA Adapter
================
Bridge layer between HRF flood solver and QCIA causal AI.

This module converts HRF simulation results into QCIA-compatible format
and vice versa. It does NOT modify existing HRF or QCIA code.

Usage:
    adapter = HRFAdapter()
    
    # After HRF simulation
    causal_data = adapter.extract_causal_variables(solver, scenario_params)
    
    # After QCIA optimization
    hrf_params = adapter.prepare_hrf_scenario(optimization_result)
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Any
from pathlib import Path
import json
from datetime import datetime


class HRFAdapter:
    """
    Adapter pattern to bridge HRF solver and QCIA without modifying either.
    """
    
    def __init__(self):
        """Initialize adapter with scenario history storage."""
        self.scenario_history: List[Dict] = []
        self.baseline_metrics: Optional[Dict] = None
        
    def extract_causal_variables(self, 
                                 solver: Any,  # HRFSolver instance
                                 scenario_params: Dict,
                                 scenario_id: str = None) -> Dict[str, float]:
        """
        Extract causal variables from HRF simulation results.
        
        Args:
            solver: HRFSolver instance after .run() has completed
            scenario_params: Dict with intervention parameters
                - budget_cr: float (budget in Crores)
                - culvert_count: int
                - pond_count: int
                - drain_length_km: float
                - drainage_multiplier: float
            scenario_id: Optional identifier for this scenario
        
        Returns:
            Dict with causal variables for QCIA analysis
        """
        # Import here to avoid circular dependencies
        try:
            from Physics.hrf import HRFSolver
        except:
            pass  # HRFSolver might be imported differently
        
        # Extract flood metrics from solver
        h_final = solver.h if hasattr(solver, 'h') else np.zeros((10, 10))
        
        # Convert to numpy if needed (for PyTorch backend)
        try:
            h_final_np = h_final.cpu().numpy() if hasattr(h_final, 'cpu') else np.asarray(h_final)
        except:
            h_final_np = np.asarray(h_final)
        
        # Calculate flood metrics
        dx = solver.grid.dx
        dy = solver.grid.dy
        cell_area = dx * dy / 1e6  # Convert to km²
        
        flooded_05m = float(np.sum(h_final_np > 0.5) * cell_area)
        flooded_10m = float(np.sum(h_final_np > 1.0) * cell_area)
        flooded_15m = float(np.sum(h_final_np > 1.5) * cell_area)
        max_depth = float(np.max(h_final_np))
        mean_depth = float(np.mean(h_final_np[h_final_np > 0.1])) if np.any(h_final_np > 0.1) else 0.0
        
        # Extract input parameters
        budget_cr = scenario_params.get('budget_cr', 0.0)
        culvert_count = scenario_params.get('culvert_count', 0)
        pond_count = scenario_params.get('pond_count', 0)
        drain_length_km = scenario_params.get('drain_length_km', 0.0)
        drainage_mult = scenario_params.get('drainage_multiplier', 1.0)
        
        # Estimate damage (simplified model)
        # Damage scales with flooded area and depth
        damage_per_km2 = 100  # ₹100 lakh per km² at 0.5m depth
        damage_lakh = flooded_05m * damage_per_km2 * (1 + mean_depth)
        
        # Calculate ROI
        cost_lakh = budget_cr * 100
        if self.baseline_metrics and cost_lakh > 0:
            baseline_damage = self.baseline_metrics.get('damage_lakh', damage_lakh)
            damage_avoided = baseline_damage - damage_lakh
            roi = damage_avoided / cost_lakh if cost_lakh > 0 else 0.0
        else:
            roi = 0.0
        
        # Build result dict
        result = {
            # INPUT VARIABLES (causes)
            'scenario_id': scenario_id or f"S{len(self.scenario_history):03d}",
            'budget_cr': float(budget_cr),
            'culvert_count': int(culvert_count),
            'pond_count': int(pond_count),
            'drain_length_km': float(drain_length_km),
            'drainage_multiplier': float(drainage_mult),
            
            # OUTPUT VARIABLES (effects)
            'flooded_area_05m_km2': flooded_05m,
            'flooded_area_10m_km2': flooded_10m,
            'flooded_area_15m_km2': flooded_15m,
            'max_depth_m': max_depth,
            'mean_depth_m': mean_depth,
            'damage_lakh': damage_lakh,
            'roi': roi,
            
            # METADATA
            'timestamp': datetime.now().isoformat(),
            'grid_size': (solver.grid.nx, solver.grid.ny),
            'sim_time': float(solver.time) if hasattr(solver, 'time') else 0.0,
        }
        
        # Store in history
        self.scenario_history.append(result)
        
        # Set baseline if this is first scenario
        if self.baseline_metrics is None and budget_cr == 0:
            self.baseline_metrics = result.copy()
        
        return result
    
    def get_dataframe(self) -> pd.DataFrame:
        """
        Convert scenario history to pandas DataFrame for QCIA.
        
        Returns:
            DataFrame with all scenarios, ready for causal discovery
        """
        if not self.scenario_history:
            return pd.DataFrame()
        
        # Select only numeric causal variables
        causal_cols = [
            'budget_cr', 'culvert_count', 'pond_count', 'drain_length_km',
            'drainage_multiplier', 'flooded_area_05m_km2', 'flooded_area_10m_km2',
            'max_depth_m', 'mean_depth_m', 'damage_lakh', 'roi'
        ]
        
        data = [{k: v for k, v in scenario.items() if k in causal_cols} 
                for scenario in self.scenario_history]
        
        return pd.DataFrame(data)
    
    def prepare_hrf_scenario(self, optimization_result: Dict) -> Dict:
        """
        Convert QCIA optimization result to HRF simulation parameters.
        
        Args:
            optimization_result: Dict from QCIA optimizer with keys:
                - budget_cr: float
                - culvert_count: int
                - pond_count: int
                - drainage_multiplier: float
        
        Returns:
            Dict ready for HRF simulation setup
        """
        return {
            'budget_cr': float(optimization_result.get('budget_cr', 0)),
            'culvert_count': int(optimization_result.get('culvert_count', 0)),
            'pond_count': int(optimization_result.get('pond_count', 0)),
            'drain_length_km': float(optimization_result.get('drain_length_km', 0)),
            'drainage_multiplier': float(optimization_result.get('drainage_multiplier', 1.0)),
        }
    
    def compare_scenarios(self, baseline_id: str, optimized_id: str) -> Dict:
        """
        Compare two scenarios and calculate improvement metrics.
        
        Args:
            baseline_id: Scenario ID for baseline
            optimized_id: Scenario ID for optimized design
        
        Returns:
            Dict with comparison metrics
        """
        # Find scenarios
        baseline = next((s for s in self.scenario_history if s['scenario_id'] == baseline_id), None)
        optimized = next((s for s in self.scenario_history if s['scenario_id'] == optimized_id), None)
        
        if not baseline or not optimized:
            raise ValueError(f"Scenario not found: {baseline_id} or {optimized_id}")
        
        # Calculate improvements
        flood_reduction = (baseline['flooded_area_05m_km2'] - optimized['flooded_area_05m_km2'])
        flood_reduction_pct = (flood_reduction / baseline['flooded_area_05m_km2'] * 100) if baseline['flooded_area_05m_km2'] > 0 else 0
        
        depth_reduction = (baseline['max_depth_m'] - optimized['max_depth_m'])
        depth_reduction_pct = (depth_reduction / baseline['max_depth_m'] * 100) if baseline['max_depth_m'] > 0 else 0
        
        damage_avoided = baseline['damage_lakh'] - optimized['damage_lakh']
        
        return {
            'baseline_scenario': baseline_id,
            'optimized_scenario': optimized_id,
            'cost_cr': optimized['budget_cr'],
            'flood_reduction_km2': flood_reduction,
            'flood_reduction_pct': flood_reduction_pct,
            'depth_reduction_m': depth_reduction,
            'depth_reduction_pct': depth_reduction_pct,
            'damage_avoided_lakh': damage_avoided,
            'roi': optimized['roi'],
        }
    
    def save_history(self, filepath: Path):
        """Save scenario history to JSON file."""
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, 'w') as f:
            json.dump({
                'scenarios': self.scenario_history,
                'baseline': self.baseline_metrics,
                'created': datetime.now().isoformat()
            }, f, indent=2)
    
    def load_history(self, filepath: Path):
        """Load scenario history from JSON file."""
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        self.scenario_history = data.get('scenarios', [])
        self.baseline_metrics = data.get('baseline')
    
    def get_summary(self) -> str:
        """Get human-readable summary of scenario history."""
        if not self.scenario_history:
            return "No scenarios recorded yet."
        
        df = self.get_dataframe()
        
        lines = [
            "="*60,
            "HRF-QCIA Adapter Summary",
            "="*60,
            f"Total scenarios: {len(self.scenario_history)}",
            f"Budget range: ₹{df['budget_cr'].min():.1f} - ₹{df['budget_cr'].max():.1f} Cr",
            f"Flooded area range: {df['flooded_area_05m_km2'].min():.2f} - {df['flooded_area_05m_km2'].max():.2f} km²",
            "",
            "Top 3 scenarios by ROI:",
        ]
        
        top_scenarios = df.nlargest(3, 'roi')
        for idx, row in top_scenarios.iterrows():
            lines.append(f"  • Budget: ₹{row['budget_cr']:.1f}Cr, Flooded: {row['flooded_area_05m_km2']:.2f}km², ROI: {row['roi']:.1f}x")
        
        lines.append("="*60)
        return "\n".join(lines)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def quick_extract(solver, budget_cr: float = 0.0, **kwargs) -> Dict:
    """
    Quick extraction without creating adapter instance.
    
    Usage:
        from AI.hrf_adapter import quick_extract
        metrics = quick_extract(solver, budget_cr=12.0, culvert_count=10)
    """
    adapter = HRFAdapter()
    return adapter.extract_causal_variables(solver, {
        'budget_cr': budget_cr,
        **kwargs
    })


if __name__ == "__main__":
    # Demo / Test
    print("HRF-QCIA Adapter Module")
    print("="*60)
    print("This module bridges HRF solver and QCIA AI.")
    print("")
    print("Usage:")
    print("  from AI.hrf_adapter import HRFAdapter")
    print("  adapter = HRFAdapter()")
    print("  metrics = adapter.extract_causal_variables(solver, params)")
    print("  df = adapter.get_dataframe()  # For QCIA")
    print("")
    print("See INTEGRATION_ARCHITECTURE.md for complete workflow.")
    print("="*60)



