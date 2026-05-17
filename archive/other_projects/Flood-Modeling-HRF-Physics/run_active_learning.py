#!/usr/bin/env python3
"""
QCIA Active Learning - Iterative Discovery
===========================================
Tests multiple intervention types to discover what works.

This demonstrates "AlphaGo for flood infrastructure":
- Try intervention → Measure result → Learn → Explain → Repeat
"""

import sys
from pathlib import Path

# Add project root to path
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from AI.active_agent import QCIAActiveAgent

def main():
    """Run active learning workflow."""
    
    print("="*70)
    print("🤖 QCIA ACTIVE LEARNING - ITERATIVE DISCOVERY")
    print("="*70)
    print()
    print("This will test multiple intervention types to discover what works.")
    print("Each test takes ~1 minute (short simulation).")
    print()
    
    # Configuration
    baseline_dir = Path("outputs/qcia_full_demo/baseline")
    
    data_config = {
        'dem': Path('Data/Jabalpur_Data/DEM_utm44.tif'),
        'lulc': Path('Data/Jabalpur_Data/LULC_utm44.tif'),
        'rivers': Path('Data/Jabalpur_Data/Main/rivers_aoi.geojson'),
        'roads': Path('Data/Jabalpur_Data/Main/roads_aoi.geojson'),
        'tile_col0': 4474,
        'tile_row0': 4260,
        'nx': 100,
        'ny': 100,
        'rain_mm_per_hour': 60,
        't_hours': 1.5
    }
    
    # Initialize agent
    agent = QCIAActiveAgent(baseline_dir, data_config, verbose=True)
    
    # Test intervention types in order of expected effectiveness
    intervention_types = [
        'pond_medium',      # Should work well (targets lowlands)
        'pump_small',       # Should work very well (active removal)
        'culvert_box_2x2',  # Should work poorly (doesn't target root cause)
    ]
    
    budget_cr = 12.0
    
    print(f"💰 Budget: ₹{budget_cr} Crores")
    print(f"🎯 Testing {len(intervention_types)} intervention types\n")
    
    input("Press ENTER to start active learning...")
    
    # ACTIVE LEARNING LOOP
    for i, itype in enumerate(intervention_types, 1):
        print(f"\n{'='*70}")
        print(f"TEST {i}/{len(intervention_types)}: {itype}")
        print(f"{'='*70}")
        
        # 1. PROPOSE: Generate hypothesis
        proposal = agent.propose_intervention(itype, budget_cr)
        
        # 2. TEST: Run physics simulation  
        test_result = agent.test_intervention(proposal)
        
        if test_result is None:
            print(f"   ⚠️  Test failed, skipping")
            continue
        
        # 3. LEARN: Update knowledge base
        agent.learn(test_result)
        
        # 4. EXPLAIN: Show reasoning
        explanation = agent.explain(test_result)
        print(explanation)
    
    # FINAL SUMMARY
    print(f"\n{'='*70}")
    print(f"📊 ACTIVE LEARNING COMPLETE")
    print(f"{'='*70}")
    
    summary = agent.get_summary()
    
    print(f"\n**Total tests:** {summary['total_tests']}")
    print(f"\n**Results by intervention type:**")
    
    for itype, stats in summary['by_type'].items():
        print(f"\n   **{itype}:**")
        print(f"      Tests: {stats['tests']}")
        print(f"      Avg ROI: {stats['avg_roi']:.1f}:1")
        print(f"      Success rate: {stats['success_rate']:.0%}")
        print(f"      Prediction accuracy: {stats['avg_accuracy']:.0%}")
    
    if summary['best_intervention']:
        best = summary['best_intervention']
        print(f"\n🏆 **Best intervention discovered:**")
        print(f"      Type: {best.intervention_type}")
        print(f"      Impact: {best.actual_impact:.2f} km reduction")
        print(f"      ROI: {best.roi:.1f}:1")
        print(f"      Cost: ₹{best.cost/1e7:.2f} Crores")
    
    print(f"\n{'='*70}")
    print(f"✅ QCIA has learned which interventions work!")
    print(f"   Next project will start with this knowledge.")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()



