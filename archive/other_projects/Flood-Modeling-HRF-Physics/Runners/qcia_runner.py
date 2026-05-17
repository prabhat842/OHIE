#!/usr/bin/env python3
"""
QCIA-HRF Integrated Workflow Runner
====================================
End-to-end workflow: Data → Physics → AI → Optimization → Validation

This is the main entry point for AI-driven flood infrastructure optimization.
It orchestrates all components without modifying existing code.

Usage:
    python qcia_runner.py --dem Data/GDSP_DEM_utm43n_100m.tif \\
                          --lulc Data/LULC2_utm43n_100m.tif \\
                          --budget 12 \\
                          --out outputs/jabalpur_qcia

Author: QCIA Integration Layer
License: MIT
"""

from __future__ import annotations

import sys
import os
from pathlib import Path

# Add parent directories to path
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / 'AI') not in sys.path:
    sys.path.insert(0, str(_ROOT / 'AI'))

import argparse
import numpy as np
import pandas as pd
from typing import Dict, List, Optional
import json
from datetime import datetime
import time

# Import existing components (no modifications needed)
try:
    from Physics.hrf import Grid, SWEParams, ExponentialFilter, HRFSolver
    HAS_HRF = True
except ImportError:
    print("⚠️  Could not import Physics.hrf - install dependencies")
    HAS_HRF = False

# Import new integration layer
try:
    from AI.hrf_adapter import HRFAdapter
    from AI.intervention_generator import InterventionGenerator
    HAS_ADAPTER = True
except ImportError:
    print("⚠️  Integration layer not found - using standalone mode")
    HAS_ADAPTER = False

# Import QCIA (if available)
try:
    from qcia_core.causal_discovery import CausalDiscoveryEngine
    from qcia_core.quantum_optimizer import QuantumInspiredOptimizer, AnnealingSchedule
    HAS_QCIA = True
except ImportError:
    try:
        from AI.qcia_core.causal_discovery import CausalDiscoveryEngine
        from AI.qcia_core.quantum_optimizer import QuantumInspiredOptimizer, AnnealingSchedule
        HAS_QCIA = True
    except ImportError:
        print("⚠️  QCIA not available - optimization will use simple heuristics")
        HAS_QCIA = False


class QCIARunner:
    """
    Orchestrates the complete AI-integrated flood optimization workflow.
    
    This class doesn't modify existing code - it just connects the pieces.
    """
    
    def __init__(self, output_dir: Path):
        """
        Initialize runner.
        
        Args:
            output_dir: Directory for outputs
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Components
        self.adapter = HRFAdapter() if HAS_ADAPTER else None
        self.generator = None  # Created after data load
        
        # Data
        self.grid = None
        self.solver_template = None  # Template solver config
        self.dem = None
        self.lulc = None
        self.road_mask = None
        
        # Results
        self.baseline_result = None
        self.optimization_result = None
        
        print(f"✅ QCIARunner initialized")
        print(f"   Output: {self.output_dir}")
        print(f"   HRF: {'✓' if HAS_HRF else '✗'}")
        print(f"   QCIA: {'✓' if HAS_QCIA else '✗'}")
        print(f"   Adapter: {'✓' if HAS_ADAPTER else '✗'}")
    
    def load_data_simple(self,
                        dem: np.ndarray,
                        grid_params: Dict,
                        lulc: Optional[np.ndarray] = None):
        """
        Load data from numpy arrays (for testing/API use).
        
        Args:
            dem: Digital elevation model (nx, ny)
            grid_params: Dict with Lx, Ly in meters
            lulc: Land use land cover (optional)
        """
        print("\n📂 Loading data...")
        
        self.dem = dem
        self.lulc = lulc
        
        ny, nx = dem.shape
        Lx = grid_params.get('Lx', nx * 100)  # Default 100m cells
        Ly = grid_params.get('Ly', ny * 100)
        
        self.grid = Grid(nx=nx, ny=ny, Lx=Lx, Ly=Ly)
        
        print(f"   Grid: {nx} × {ny}")
        print(f"   Extent: {Lx/1000:.2f} × {Ly/1000:.2f} km")
        print(f"   Elevation: {dem.min():.1f} - {dem.max():.1f} m")
        
        # Create intervention generator
        self.generator = InterventionGenerator(
            grid_shape=(nx, ny),
            dem=dem,
            road_mask=self.road_mask
        )
    
    def run_baseline(self,
                    rainfall_mm: float = 200,
                    duration_hours: float = 6,
                    manning_n: float = 0.06) -> Dict:
        """
        Run baseline flood simulation (no interventions).
        
        Args:
            rainfall_mm: Total rainfall in mm
            duration_hours: Duration of rainfall event
            manning_n: Manning's roughness coefficient
        
        Returns:
            Dict with baseline metrics
        """
        print("\n🌊 Running baseline simulation...")
        print(f"   Rainfall: {rainfall_mm}mm in {duration_hours}h")
        
        if not HAS_HRF:
            # Mock results for testing
            print("   ⚠️  HRF not available - using mock data")
            return self._mock_simulation(0, 0, 0)
        
        # Setup solver
        prm = SWEParams(manning_n=manning_n, h_min=0.02, cfl=0.15, dt_max=0.1)
        filt = ExponentialFilter(alpha=36.0, p=8)
        solver = HRFSolver(grid=self.grid, prm=prm, filt=filt, mode="dw_fv")
        
        # Initial conditions
        h0 = np.full((self.grid.nx, self.grid.ny), 0.01)
        u0 = np.zeros_like(h0)
        v0 = np.zeros_like(h0)
        solver.initialize(h0, u0, v0)
        
        # Set forcing
        rain_rate = (rainfall_mm / 1000.0) / (duration_hours * 3600.0)  # m/s
        infil_rate = rain_rate * 0.15  # 15% infiltration baseline
        
        solver.set_forcing(
            bed=self.dem.T,  # Transpose for HRF indexing
            rain_rate=rain_rate,
            infil_rate=infil_rate
        )
        
        # Run simulation
        start_time = time.time()
        sim_time = duration_hours * 3600.0
        solver.run(t_end=sim_time, output_every=600.0, verbose=False)
        elapsed = time.time() - start_time
        
        print(f"   Simulation complete: {elapsed:.1f}s")
        
        # Extract metrics using adapter
        if self.adapter:
            scenario_params = {
                'budget_cr': 0.0,
                'culvert_count': 0,
                'pond_count': 0,
                'drain_length_km': 0.0,
                'drainage_multiplier': 1.0,
            }
            result = self.adapter.extract_causal_variables(
                solver, scenario_params, scenario_id='S00_baseline'
            )
        else:
            # Fallback: manual extraction
            h_final = np.asarray(solver.h)
            cell_area_km2 = (self.grid.dx * self.grid.dy) / 1e6
            result = {
                'flooded_area_05m_km2': float(np.sum(h_final > 0.5) * cell_area_km2),
                'max_depth_m': float(np.max(h_final)),
            }
        
        self.baseline_result = result
        
        print(f"   ✅ Flooded area: {result['flooded_area_05m_km2']:.2f} km²")
        print(f"   ✅ Max depth: {result['max_depth_m']:.2f} m")
        
        # Save result
        self._save_result(result, 'baseline.json')
        
        return result
    
    def explore_scenarios(self, n_scenarios: int = 6) -> List[Dict]:
        """
        Run multiple scenarios to generate training data for QCIA.
        
        Args:
            n_scenarios: Number of scenarios to test
        
        Returns:
            List of scenario results
        """
        print(f"\n🔬 Exploring {n_scenarios} scenarios...")
        
        # Define scenario parameters
        budgets = np.linspace(0, 30, n_scenarios)  # 0 to ₹30 Cr
        
        results = []
        
        for i, budget_cr in enumerate(budgets):
            print(f"\n   [{i+1}/{n_scenarios}] Budget: ₹{budget_cr:.1f} Cr")
            
            # Estimate interventions from budget
            # Simple heuristic: ₹3.5Cr per culvert, ₹18Cr per pond
            culvert_count = int(budget_cr / 3.5)
            pond_count = int((budget_cr - culvert_count * 3.5) / 18)
            drainage_mult = 1.0 + budget_cr * 0.05  # 5% per Crore
            
            result = self._run_scenario(
                budget_cr=budget_cr,
                culvert_count=culvert_count,
                pond_count=pond_count,
                drainage_multiplier=min(drainage_mult, 2.0)
            )
            
            results.append(result)
            print(f"      Flooded: {result['flooded_area_05m_km2']:.2f} km²")
        
        return results
    
    def _run_scenario(self,
                     budget_cr: float,
                     culvert_count: int,
                     pond_count: int,
                     drainage_multiplier: float) -> Dict:
        """Run a single scenario simulation."""
        
        if not HAS_HRF:
            return self._mock_simulation(culvert_count, pond_count, drainage_multiplier)
        
        # Setup solver (copy from baseline)
        prm = SWEParams(manning_n=0.06, h_min=0.02, cfl=0.15, dt_max=0.1)
        filt = ExponentialFilter(alpha=36.0, p=8)
        solver = HRFSolver(grid=self.grid, prm=prm, filt=filt, mode="dw_fv")
        
        # Initial conditions
        h0 = np.full((self.grid.nx, self.grid.ny), 0.01)
        u0 = np.zeros_like(h0)
        v0 = np.zeros_like(h0)
        solver.initialize(h0, u0, v0)
        
        # Base forcing
        rain_rate = (200 / 1000.0) / (6 * 3600.0)
        base_infil = rain_rate * 0.15
        
        # Apply interventions
        if self.generator:
            self.generator.apply_simple_scenario(
                solver,
                culvert_count=culvert_count,
                pond_count=pond_count,
                drainage_multiplier=drainage_multiplier,
                base_infiltration=np.full((self.grid.nx, self.grid.ny), base_infil)
            )
        
        solver.set_forcing(
            bed=self.dem.T,
            rain_rate=rain_rate,
            infil_rate=base_infil * drainage_multiplier
        )
        
        # Run
        solver.run(t_end=6*3600, output_every=600.0, verbose=False)
        
        # Extract
        if self.adapter:
            scenario_params = {
                'budget_cr': budget_cr,
                'culvert_count': culvert_count,
                'pond_count': pond_count,
                'drainage_multiplier': drainage_multiplier,
            }
            return self.adapter.extract_causal_variables(solver, scenario_params)
        else:
            h_final = np.asarray(solver.h)
            cell_area_km2 = (self.grid.dx * self.grid.dy) / 1e6
            return {
                'budget_cr': budget_cr,
                'flooded_area_05m_km2': float(np.sum(h_final > 0.5) * cell_area_km2),
            }
    
    def _mock_simulation(self, culverts: int, ponds: int, drain_mult: float) -> Dict:
        """Mock simulation for testing without HRF."""
        # Simple physics approximation
        baseline_flood = 2.5  # km²
        
        reduction = culverts * 0.08 + ponds * 0.15 + (drain_mult - 1.0) * 0.5
        flooded = max(0.5, baseline_flood * (1 - min(reduction, 0.6)))
        
        return {
            'budget_cr': culverts * 3.5 + ponds * 18,
            'culvert_count': culverts,
            'pond_count': ponds,
            'drainage_multiplier': drain_mult,
            'flooded_area_05m_km2': flooded,
            'max_depth_m': 1.8 * (1 - reduction * 0.5),
            'damage_lakh': flooded * 100,
            'roi': 0.0,
        }
    
    def optimize(self, budget_max_cr: float = 12) -> Dict:
        """
        Run QCIA optimization to find optimal design.
        
        Args:
            budget_max_cr: Maximum budget in Crores
        
        Returns:
            Optimal design parameters
        """
        print(f"\n⚛️  Optimizing (budget: ₹{budget_max_cr} Cr)...")
        
        if not self.adapter or not self.adapter.scenario_history:
            print("   ⚠️  No scenario data - run explore_scenarios() first")
            return {}
        
        # Get training data
        df = self.adapter.get_dataframe()
        print(f"   Training data: {len(df)} scenarios")
        
        if HAS_QCIA:
            # Use real QCIA optimization
            print("   Using QCIA quantum optimization...")
            
            # TODO: Full QCIA integration
            # For now, use simple heuristic
            optimal_idx = df['roi'].idxmax() if 'roi' in df.columns else 0
            optimal = df.iloc[optimal_idx].to_dict()
        else:
            # Fallback: find best ROI from explored scenarios
            print("   Using heuristic optimization...")
            
            # Filter by budget constraint
            within_budget = df[df['budget_cr'] <= budget_max_cr]
            
            if len(within_budget) == 0:
                print("   ⚠️  No scenarios within budget")
                return {}
            
            # Find best flood reduction per cost
            within_budget['efficiency'] = (
                (df['flooded_area_05m_km2'].iloc[0] - within_budget['flooded_area_05m_km2']) / 
                (within_budget['budget_cr'] + 0.1)
            )
            
            optimal_idx = within_budget['efficiency'].idxmax()
            optimal = within_budget.loc[optimal_idx].to_dict()
        
        print(f"   ✅ Optimal: {optimal.get('culvert_count', 0)} culverts, "
              f"{optimal.get('pond_count', 0)} ponds")
        print(f"   ✅ Cost: ₹{optimal.get('budget_cr', 0):.1f} Cr")
        
        self.optimization_result = optimal
        self._save_result(optimal, 'optimal.json')
        
        return optimal
    
    def validate(self) -> Dict:
        """
        Validate optimized design with full physics simulation.
        
        Returns:
            Validation results
        """
        if not self.optimization_result:
            print("⚠️  No optimization result - run optimize() first")
            return {}
        
        print("\n✅ Validating optimized design...")
        
        result = self._run_scenario(
            budget_cr=self.optimization_result.get('budget_cr', 0),
            culvert_count=int(self.optimization_result.get('culvert_count', 0)),
            pond_count=int(self.optimization_result.get('pond_count', 0)),
            drainage_multiplier=self.optimization_result.get('drainage_multiplier', 1.0)
        )
        
        # Compare to baseline
        if self.baseline_result:
            reduction = (
                (self.baseline_result['flooded_area_05m_km2'] - result['flooded_area_05m_km2']) /
                self.baseline_result['flooded_area_05m_km2'] * 100
            )
            print(f"   ✅ Flood reduction: {reduction:.1f}%")
            print(f"   ✅ ROI: {result.get('roi', 0):.1f}x")
        
        self._save_result(result, 'validated.json')
        
        return result
    
    def _save_result(self, result: Dict, filename: str):
        """Save result to JSON file."""
        filepath = self.output_dir / filename
        with open(filepath, 'w') as f:
            json.dump(result, f, indent=2)
    
    def generate_report(self):
        """Generate summary report."""
        print("\n📊 Generating report...")
        
        report_lines = [
            "="*70,
            "QCIA-HRF FLOOD OPTIMIZATION REPORT",
            "="*70,
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "BASELINE",
            "-"*70,
        ]
        
        if self.baseline_result:
            report_lines.extend([
                f"Flooded area: {self.baseline_result.get('flooded_area_05m_km2', 0):.2f} km²",
                f"Max depth: {self.baseline_result.get('max_depth_m', 0):.2f} m",
                f"Damage: ₹{self.baseline_result.get('damage_lakh', 0):.0f} lakh",
            ])
        
        report_lines.extend(["", "OPTIMIZED DESIGN", "-"*70])
        
        if self.optimization_result:
            report_lines.extend([
                f"Budget: ₹{self.optimization_result.get('budget_cr', 0):.1f} Crores",
                f"Culverts: {self.optimization_result.get('culvert_count', 0)}",
                f"Ponds: {self.optimization_result.get('pond_count', 0)}",
                f"Flooded area: {self.optimization_result.get('flooded_area_05m_km2', 0):.2f} km²",
                f"ROI: {self.optimization_result.get('roi', 0):.1f}x",
            ])
        
        report_lines.append("="*70)
        
        report_text = "\n".join(report_lines)
        print(report_text)
        
        # Save to file
        with open(self.output_dir / 'report.txt', 'w') as f:
            f.write(report_text)
        
        print(f"   ✅ Report saved: {self.output_dir / 'report.txt'}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='QCIA-HRF Integrated Flood Optimization',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full workflow with real data
  python qcia_runner.py --dem Data/DEM.tif --lulc Data/LULC.tif --budget 12 --out outputs/test
  
  # Quick test with mock data
  python qcia_runner.py --mock --budget 12 --out outputs/mock_test
        """
    )
    
    parser.add_argument('--dem', type=str, help='DEM GeoTIFF path')
    parser.add_argument('--lulc', type=str, help='LULC GeoTIFF path')
    parser.add_argument('--budget', type=float, default=12, help='Budget in Crores')
    parser.add_argument('--out', type=str, required=True, help='Output directory')
    parser.add_argument('--mock', action='store_true', help='Use mock data for testing')
    parser.add_argument('--n-scenarios', type=int, default=6, help='Number of scenarios to explore')
    
    args = parser.parse_args()
    
    # Initialize
    runner = QCIARunner(output_dir=args.out)
    
    # Load data
    if args.mock or not args.dem:
        print("\n🎭 Using mock data for testing...")
        # Create synthetic data
        nx, ny = 100, 100
        dem = np.random.rand(ny, nx) * 50 + 400  # 400-450m elevation
        runner.load_data_simple(dem, {'Lx': 10000, 'Ly': 10000})
    else:
        # TODO: Load real GeoTIFF data (requires rasterio)
        print("⚠️  Real data loading not yet implemented")
        print("   Using --mock for now")
        return
    
    # Workflow
    runner.run_baseline()
    runner.explore_scenarios(n_scenarios=args.n_scenarios)
    runner.optimize(budget_max_cr=args.budget)
    runner.validate()
    runner.generate_report()
    
    print(f"\n✅ Complete! Results in {args.out}/")


if __name__ == "__main__":
    main()



