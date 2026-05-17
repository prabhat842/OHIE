# Experience-Based Learning System

## Overview

The QCIA optimizer now includes **experience-based learning** that remembers intervention performance across runs and uses that knowledge to improve future plans. This transforms the system from "rolling dice each time" to "learning like a seasoned planner."

## How It Works

### 1. **Experience Recording** (After Physics Validation)

After each budget evaluation completes and the optimized simulation runs, the system records:
- Intervention type (culvert_2x2, pump_medium, etc.)
- Location
- Cost
- **Physics-validated** damage reduction
- **Physics-validated** road km reduction  
- ROI (Return on Investment)
- Success/failure flag (ROI > 0)

These records are saved to `experience_store.json` in the workspace root.

### 2. **Learning from History** (Before Optimization)

Before the next optimization run, the system:
- Loads all past intervention records
- Computes statistics per intervention type:
  - Success rate (% with ROI > 0)
  - Average ROI
  - Average damage reduction
  - Average road km saved
  
### 3. **Adjusting Candidate Scores** (Experience-Guided Planning)

The learned statistics are used to adjust candidate scores:

**Boost proven winners:**
- Types with high success rate (e.g., 80% success) get multipliers > 1.0
- Example: `culvert_2x2` with 90% success → 1.5x multiplier

**Penalize poor performers:**
- Types with low success rate (e.g., 20% success) get multipliers < 1.0
- Example: `smart_valve` with 15% success → 0.3x multiplier

**Prune consistent failures:**
- Types with < 20% success (after 5+ samples) are flagged for avoidance
- Their `causal_impact` is multiplied by 0.05 to de-prioritize

### 4. **Incremental Improvement Loop**

Each run:
1. Loads experience → adjusts candidates
2. Optimizes with adjusted scores
3. Validates with physics
4. Records actual performance
5. **Next run starts with more knowledge**

## Key Insight: Concept.py Inspiration

This mirrors the pruning mechanism in `extra_tools/concept.py.bak`:

| Concept.py (Hyperparameter Tuning) | QCIA (Intervention Planning) |
|-------------------------------------|------------------------------|
| Learns bad solver parameter regions | Learns poor intervention types |
| Prunes failed zones from search     | Penalizes/prunes failed types |
| Exploits manifold structure         | Exploits type statistics     |
| Meta-optimizes over episodes        | Improves across runs         |

## Expected Results

### First Run (No Experience)
```
📚 PHASE 4.25: EXPERIENCE-BASED LEARNING
======================================================================
   ℹ️  No prior experiences found (first run)
   The system will learn from this run and improve next time
```
- Operates like before (baseline causal reasoning + QCA)
- Records all intervention outcomes

### Second Run (Learning Begins)
```
📚 PHASE 4.25: EXPERIENCE-BASED LEARNING
======================================================================
📊 Experience Store Summary (10 interventions)

✅ culvert_2x2_concrete          | Success:  80.0% | ROI:  1.45x | Multiplier: 1.32x | Count:   5
⚠️  pump_medium                   | Success:  50.0% | ROI:  0.65x | Multiplier: 0.92x | Count:   2
❌ smart_valve                    | Success:  0.0%  | ROI:  0.05x | Multiplier: 0.35x | Count:   3

   📚 Applying experience-based learning to 47 candidates:
   Learned from 10 past interventions
   ✅ Adjusted 35 candidates, pruned 8 poor performers
   ⬆️  Boosted: culvert_2x2_concrete (1.32x)
   ⬇️  Penalized: smart_valve (0.35x), pump_medium (0.92x)
```
- culverts get priority (proven winners)
- smart valves are de-prioritized (consistent failures)

### Third+ Runs (Mature Learning)
- With 20-50+ experiences, the system has robust statistics
- Type selection converges to locally effective patterns
- ROI should improve run-over-run as poor options are pruned

## Specific Improvements vs. Baseline

### Problem: Flat Results (Previous Runs)
```
Budget ₹12.9 Cr → ROI 0.00x (no improvement)
Same 10 interventions every budget
```

### Solution: Experience-Guided Adaptation
- **If culverts work:** Future runs prioritize more culverts, fewer pumps
- **If pumps fail:** System learns to avoid them in similar contexts
- **If mix is wrong:** Portfolio composition shifts toward proven types

### Analogous to Urban Planner Workflow

**Old System (Dice Roll):**
```
planner.select_random_portfolio(budget)
```

**New System (Learning Planner):**
```
1. Review past projects in this neighborhood
2. Note: culverts @ crossings worked, pumps @ lowlands failed
3. Adjust scores: boost culvert candidates, penalize pumps
4. Optimize with adjusted scores
5. Validate with physics
6. Remember outcome for next project
```

## Files Modified

1. **`AI/qcia_core/experience_store.py`** (NEW)
   - `ExperienceStore`: Persistent intervention database
   - `InterventionRecord`: Single intervention outcome
   - `apply_experience_learning()`: Adjust candidate scores

2. **`run_qcia_flood_optimization.py`**
   - Added PHASE 4.25: Experience-Based Learning
   - Loads store, applies learning before optimization

3. **`run_budget_sweep.py`**
   - Added `record_intervention_experiences()`
   - Records after each budget's physics validation
   - Records after autonomous/greedy-fill refinements

## Validation Strategy

### Short-term (Next Run)
- Experience store should populate with 5-15 records
- Console shows learning summary with type statistics
- Some candidates boosted, some penalized
- Different portfolio mix selected (if physics validates different types)

### Medium-term (3-5 Runs)
- ROI trend should show improvement (or stability if already optimal)
- Poor-performing types should be pruned from plans
- Experience store summary shows mature statistics (20-50 records)

### Long-term (10+ Runs)
- System converges to locally optimal type mix
- New AOIs start fresh (experiences tagged by AOI name)
- Transfer learning potential (global type priors)

## Troubleshooting

### Issue: No learning visible
**Cause:** Experience store not persisting
**Fix:** Check `experience_store.json` exists in workspace root

### Issue: All types penalized
**Cause:** Physics validation shows zero improvement (baseline problem)
**Fix:** Address root physics/AOI configuration issues first

### Issue: Learning too aggressive
**Cause:** Small sample sizes → noisy statistics
**Fix:** System already handles this (1.0x multiplier if < 3 samples)

## Future Enhancements

1. **Spatial Learning:** Remember which locations work for which types
2. **Context Learning:** Different priors for different flood regimes (shallow vs. deep)
3. **Synergy Detection:** Learn which intervention pairs amplify each other
4. **Active Exploration:** Occasionally try low-probability types to avoid local optima
5. **Transfer Learning:** Share experiences across similar AOIs

---

**Bottom Line:** The system now learns from every run. Each optimization makes the next one smarter. This is the quantum leap from "search" to "learning."



