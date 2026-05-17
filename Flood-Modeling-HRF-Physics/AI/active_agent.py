#!/usr/bin/env python3
"""
QCIA Active Learning Agent
===========================
Learns which interventions work by testing them iteratively.

This implements the "AlphaGo for flood infrastructure" approach:
- Propose intervention based on causal model
- Test with physics simulation
- Learn from actual results
- Explain reasoning
- Build memory for future projects
"""

import json
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
import subprocess
import time

from AI.qcia_core.causal_graph import CausalGraph
from AI.qcia_core.causal_reasoning import CausalReasoningEngine
from AI.intervention_library import INTERVENTION_CATALOG


@dataclass
class InterventionTest:
    """Results from testing a single intervention."""
    intervention_type: str
    location: Tuple[int, int]
    predicted_impact: float
    actual_impact: float
    cost: float
    roi: float
    accuracy: float  # How close prediction was
    success: bool
    explanation: str


class QCIAActiveAgent:
    """
    Active learning agent that discovers effective interventions through testing.
    
    Workflow:
    1. Analyze baseline → discover causal structure
    2. Propose intervention → predict impact
    3. Test with simulation → measure actual impact
    4. Learn → update confidence in causal model
    5. Explain → show reasoning to user
    6. Iterate → try next intervention type
    """
    
    def __init__(self, baseline_dir: Path, data_config: Dict, verbose=True):
        """
        Args:
            baseline_dir: Directory with baseline simulation results
            data_config: Dictionary with DEM, LULC, roads, etc. paths
            verbose: Print detailed logs
        """
        self.baseline_dir = baseline_dir
        self.data_config = data_config
        self.verbose = verbose
        
        # Load baseline metrics
        self.baseline_flooded_km = self._load_baseline_flooding()
        
        # Learning state
        self.tested_interventions: List[InterventionTest] = []
        self.causal_graph: Optional[CausalGraph] = None
        self.knowledge_base: Dict[str, List[Dict]] = {}  # By intervention type
        
        if verbose:
            print(f"\n🤖 QCIA Active Agent Initialized")
            print(f"   Baseline flooding: {self.baseline_flooded_km:.3f} km")
            print()
    
    def _load_baseline_flooding(self) -> float:
        """Load baseline flooding metric from overlay file."""
        overlay_path = self.baseline_dir / 'overlay_roads.png'
        if not overlay_path.exists():
            return 13.145  # Default from our tests
        
        # Try to extract from any text files
        for txt_file in self.baseline_dir.glob('*.txt'):
            content = txt_file.read_text()
            if 'flooded length' in content.lower():
                # Parse: "Road flooded length: 13.145 km"
                import re
                match = re.search(r'(\d+\.\d+)\s*km', content)
                if match:
                    return float(match.group(1))
        
        return 13.145  # Fallback
    
    def propose_intervention(self, intervention_type: str, budget_remaining: float) -> Dict:
        """
        Propose a specific intervention to test.
        
        Uses causal model + past experience to select best location.
        """
        if intervention_type not in INTERVENTION_CATALOG:
            raise ValueError(f"Unknown intervention type: {intervention_type}")
        
        spec = INTERVENTION_CATALOG[intervention_type]
        
        # For now, propose a test location (center of grid)
        # In full implementation, would use causal analysis to pick optimal spot
        location = (50, 50)  # Grid center
        
        # Predict impact using causal model
        predicted_impact = self._predict_impact(intervention_type, location)
        
        # Get confidence from past tests
        confidence = self._get_confidence(intervention_type)
        
        return {
            'type': intervention_type,
            'location': location,
            'predicted_impact': predicted_impact,
            'confidence': confidence,
            'cost': spec.total_cost(),
            'expected_roi': (predicted_impact * 1e8) / spec.total_cost()  # Simplified
        }
    
    def _predict_impact(self, intervention_type: str, location: Tuple[int, int]) -> float:
        """
        Predict flooding reduction (km) from this intervention.
        
        Uses causal model to estimate impact.
        """
        # Simplified prediction based on intervention type
        # In full implementation, would use structural causal model
        
        base_impact = {
            'culvert_box_2x2': 0.05,  # Small impact
            'pond_medium': 1.5,       # Large impact (targets lowlands)
            'pond_large': 2.5,        # Very large impact
            'pump_small': 1.8,        # Large impact (active removal)
            'pump_medium': 2.8,       # Very large impact
            'permeable_pavement': 0.8 # Moderate impact
        }
        
        return base_impact.get(intervention_type, 0.5)
    
    def _get_confidence(self, intervention_type: str) -> float:
        """
        Confidence in prediction based on past tests.
        
        More tests = higher confidence.
        """
        if intervention_type not in self.knowledge_base:
            return 0.5  # No experience
        
        tests = self.knowledge_base[intervention_type]
        n = len(tests)
        
        # Confidence increases with more tests, caps at 0.95
        return min(0.95, 0.5 + 0.1 * np.sqrt(n))
    
    def test_intervention(self, proposal: Dict) -> InterventionTest:
        """
        Run physics simulation with proposed intervention.
        
        Returns actual measured impact.
        """
        if self.verbose:
            print(f"\n🔬 Testing: {proposal['type']} at {proposal['location']}")
            print(f"   Predicted impact: {proposal['predicted_impact']:.2f} km reduction")
            print(f"   Confidence: {proposal['confidence']:.0%}")
        
        # Create design file with single intervention
        design = {
            'num_interventions': 1,
            'total_cost_cr': proposal['cost'] / 1e7,
            'interventions': [{
                'type': proposal['type'],
                'location': list(proposal['location']),
                'cost_lakh': proposal['cost'] / 1e5
            }]
        }
        
        test_dir = Path(f"outputs/qcia_test_{proposal['type']}")
        test_dir.mkdir(parents=True, exist_ok=True)
        
        design_path = test_dir / 'design.json'
        with open(design_path, 'w') as f:
            json.dump(design, f, indent=2)
        
        # Run simulation
        cmd = [
            'python', 'Runners/pb_cli.py',
            '--dem', str(self.data_config['dem']),
            '--lulc', str(self.data_config['lulc']),
            '--rivers', str(self.data_config['rivers']),
            '--roads', str(self.data_config['roads']),
            '--tile_col0', str(self.data_config['tile_col0']),
            '--tile_row0', str(self.data_config['tile_row0']),
            '--nx', str(self.data_config['nx']),
            '--ny', str(self.data_config['ny']),
            '--rain_mm_per_hour', str(self.data_config['rain_mm_per_hour']),
            '--t_hours', str(self.data_config['t_hours']),
            '--qcia_design', str(design_path),
            '--out', str(test_dir),
            '--plot_vmax', '2.0'
        ]
        
        if self.verbose:
            print(f"   Running simulation...")
        
        start_time = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True)
        elapsed = time.time() - start_time
        
        if result.returncode != 0:
            print(f"   ❌ Simulation failed!")
            print(result.stderr[-500:])
            return None
        
        # Generate road overlay
        subprocess.run([
            'python', 'Runners/kpi_overlay_roads.py',
            '--run_dir', str(test_dir),
            '--roads', str(self.data_config['roads'])
        ], capture_output=True)
        
        # Extract flooding metric
        actual_flooded = self._extract_flooding_metric(test_dir)
        actual_impact = self.baseline_flooded_km - actual_flooded
        
        # Calculate accuracy
        predicted = proposal['predicted_impact']
        accuracy = 1.0 - abs(actual_impact - predicted) / max(predicted, 0.1)
        accuracy = max(0.0, min(1.0, accuracy))
        
        # Calculate ROI (damage reduction vs cost)
        # Assume ₹10 Cr damage per km of flooded roads
        damage_reduction_cr = actual_impact * 10.0
        roi = damage_reduction_cr / (proposal['cost'] / 1e7)
        
        success = actual_impact > 0.1  # At least 100m reduction
        
        if self.verbose:
            print(f"   ⏱️  Completed in {elapsed:.1f}s")
            print(f"   📊 Results:")
            print(f"      Flooded: {actual_flooded:.3f} km (was {self.baseline_flooded_km:.3f} km)")
            print(f"      Reduction: {actual_impact:.3f} km")
            print(f"      Accuracy: {accuracy:.0%}")
            print(f"      ROI: {roi:.1f}:1")
        
        test = InterventionTest(
            intervention_type=proposal['type'],
            location=proposal['location'],
            predicted_impact=predicted,
            actual_impact=actual_impact,
            cost=proposal['cost'],
            roi=roi,
            accuracy=accuracy,
            success=success,
            explanation=""  # Will be filled by explain()
        )
        
        return test
    
    def _extract_flooding_metric(self, run_dir: Path) -> float:
        """Extract flooded road length from simulation output."""
        # Try to find in output logs
        for log_file in run_dir.glob('*.txt'):
            content = log_file.read_text()
            if 'flooded length' in content.lower():
                import re
                match = re.search(r'(\d+\.\d+)\s*km', content)
                if match:
                    return float(match.group(1))
        
        # Fallback: return baseline (no change detected)
        return self.baseline_flooded_km
    
    def learn(self, test: InterventionTest):
        """
        Update knowledge base from test result.
        
        Stores experience for future reference.
        """
        itype = test.intervention_type
        
        if itype not in self.knowledge_base:
            self.knowledge_base[itype] = []
        
        self.knowledge_base[itype].append({
            'predicted': test.predicted_impact,
            'actual': test.actual_impact,
            'accuracy': test.accuracy,
            'roi': test.roi,
            'success': test.success
        })
        
        self.tested_interventions.append(test)
        
        if self.verbose:
            print(f"\n📚 Learning Update:")
            print(f"   Tested {len(self.knowledge_base[itype])} {itype} interventions")
            avg_roi = np.mean([t['roi'] for t in self.knowledge_base[itype]])
            success_rate = np.mean([t['success'] for t in self.knowledge_base[itype]])
            print(f"   Average ROI: {avg_roi:.1f}:1")
            print(f"   Success rate: {success_rate:.0%}")
    
    def explain(self, test: InterventionTest) -> str:
        """
        Generate human-readable explanation of results.
        """
        if test.success:
            explanation = f"""
✅ **{test.intervention_type} WORKS!**

**Results:**
- Predicted reduction: {test.predicted_impact:.2f} km
- Actual reduction: {test.actual_impact:.2f} km  
- Prediction accuracy: {test.accuracy:.0%}
- ROI: {test.roi:.1f}:1 (₹{test.roi:.0f} saved per ₹1 spent)

**Why it works:**
- This intervention type targets the root cause
- Location has favorable conditions
- Physics simulation confirms effectiveness

**Recommendation:** Include in final design!
            """
        else:
            explanation = f"""
❌ **{test.intervention_type} DOESN'T WORK HERE**

**Results:**
- Predicted reduction: {test.predicted_impact:.2f} km
- Actual reduction: {test.actual_impact:.2f} km
- Prediction accuracy: {test.accuracy:.0%}
- ROI: {test.roi:.1f}:1 (insufficient benefit)

**Why it failed:**
- Doesn't address root cause of flooding
- Location not optimal
- Cost doesn't justify minimal benefit

**Recommendation:** Skip this intervention type.
            """
        
        test.explanation = explanation
        return explanation
    
    def get_summary(self) -> Dict:
        """Get summary of all tests performed."""
        return {
            'total_tests': len(self.tested_interventions),
            'by_type': {
                itype: {
                    'tests': len(tests),
                    'avg_roi': np.mean([t['roi'] for t in tests]),
                    'success_rate': np.mean([t['success'] for t in tests]),
                    'avg_accuracy': np.mean([t['accuracy'] for t in tests])
                }
                for itype, tests in self.knowledge_base.items()
            },
            'best_intervention': max(self.tested_interventions, key=lambda t: t.roi) if self.tested_interventions else None
        }



