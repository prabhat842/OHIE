# QCA Integration Checklist
## Week 2 Day 2 - Complete Integration

**Target:** 4-6 hours to full QCA-enabled budget sweep  
**Goal:** 5-10x ROI improvement (0.01x → 0.05-0.10x)

---

## ✅ Pre-Integration (COMPLETE)

- [x] QCA Manifold Optimizer implemented (`qca_manifold_optimizer.py`)
- [x] Flood State Encoder implemented (`flood_encoder.py`)
- [x] Both modules tested and verified
- [x] Imports working correctly
- [x] Week 1 test results available (8 budget scenarios)

---

## 📝 Integration Tasks (TODO)

### Task 1: Update `run_qcia_flood_optimization.py` (2-3 hours)

**Location:** `/Users/tiger/Desktop/QCIA_HRF_Flood copy/run_qcia_flood_optimization.py`

**Changes needed:**

```python
# At top of file (after existing imports)
from AI.qcia_core.flood_encoder import FloodStateEncoder
from AI.qcia_core.qca_manifold_optimizer import QCAOptimizer, Experience, QuantumState

# After loading baseline simulation
encoder = FloodStateEncoder(
    severe_threshold=0.5,
    moderate_threshold=0.2,
    minor_threshold=0.05
)
baseline_state = encoder.encode(baseline_h)

# Initialize QCA (will accumulate experiences)
qca = QCAOptimizer(manifold_dim=3, n_neighbors=5)

# In the evaluation loop (for each candidate intervention):
# BEFORE: Just calculate benefit/cost
# AFTER: Also collect experience for QCA

for candidate in candidate_interventions:
    # Simulate intervention
    test_h = simulate_with_intervention(candidate)
    optimized_state = encoder.encode(test_h)
    
    # Calculate reward (flood reduction)
    reward = calculate_flood_reduction(baseline_state, optimized_state)
    
    # Add experience to QCA
    exp = Experience(
        state_before=baseline_state,
        action=candidate,
        state_after=optimized_state,
        reward=reward,
        metadata={'cost': candidate['cost'], 'type': candidate['type']}
    )
    qca.add_experience(exp)
    
    # Still do greedy scoring (for comparison)
    candidate['benefit_cost_ratio'] = reward / candidate['cost']

# AFTER evaluation loop: Learn manifold
print("\n🧠 Learning causal manifold from experiences...")
qca.learn(verbose=True)

# Save manifold for later use
qca.save_to_file(f"{output_dir}/qca_manifold.json")

# Find optimal plan using QCA
print("\n🎯 Planning optimal intervention sequence...")
qca_plan = qca.find_optimal_plan(baseline_state, verbose=True)

# OPTION A: Use QCA plan exclusively
selected_interventions = qca_plan

# OPTION B: Hybrid (QCA-guided greedy)
# Use QCA to rank intervention types, then greedy for locations
qca_types = [action['type'] for action in qca_plan]
selected = greedy_select_with_type_preference(candidates, qca_types, budget)

# Generate both outputs for comparison
save_design(selected_interventions, f"{output_dir}/qcia_design_qca.json")
save_design(greedy_selected, f"{output_dir}/qcia_design_greedy.json")
```

**Checklist:**
- [ ] Add imports
- [ ] Initialize encoder and QCA
- [ ] Encode baseline state
- [ ] Add experience collection in evaluation loop
- [ ] Learn manifold after evaluation
- [ ] Save manifold to JSON
- [ ] Generate QCA plan
- [ ] Output both QCA and greedy designs
- [ ] Add verbose logging

---

### Task 2: Run Comparison Test (1 hour)

**Script:** Create `test_QCA_vs_GREEDY.sh`

```bash
#!/bin/bash
set -e

BASE_DIR="outputs/qca_comparison_test"
BUDGET="12"  # ₹12 Cr for quick test

echo "🔬 QCA vs Greedy Comparison Test"
echo "================================"

# 1. Run baseline
echo "[1/4] Baseline simulation..."
python Runners/pb_cli.py \
  --dem Data/Jabalpur_Data/DEM_utm44.tif \
  --lulc Data/Jabalpur_Data/LULC_utm44.tif \
  --rivers Data/Jabalpur_Data/Main/rivers_aoi.geojson \
  --roads Data/Jabalpur_Data/Main/roads_aoi.geojson \
  --tile_col0 4474 --tile_row0 4260 \
  --nx 100 --ny 100 \
  --rain_mm_per_hour 60.0 \
  --t_hours 1.5 \
  --out "$BASE_DIR/baseline" \
  --plot_vmax 2.0

# 2. Run QCIA optimization (generates both QCA and greedy designs)
echo "[2/4] QCIA optimization..."
python run_qcia_flood_optimization.py \
  --baseline_dir "$BASE_DIR/baseline" \
  --output_dir "$BASE_DIR/qcia" \
  --budget_cr $BUDGET \
  --target_reduction_pct 20

# 3. Run optimized simulation (QCA)
echo "[3/4] QCA-optimized simulation..."
python Runners/pb_cli.py \
  ... \
  --qcia_design "$BASE_DIR/qcia/qcia_design_qca.json" \
  --out "$BASE_DIR/qca_optimized"

# 4. Run optimized simulation (Greedy)
echo "[4/4] Greedy-optimized simulation..."
python Runners/pb_cli.py \
  ... \
  --qcia_design "$BASE_DIR/qcia/qcia_design_greedy.json" \
  --out "$BASE_DIR/greedy_optimized"

# 5. Compare results
echo "📊 Results:"
echo "Baseline: $(grep 'Flooded roads' $BASE_DIR/baseline/*.log)"
echo "QCA:      $(grep 'Flooded roads' $BASE_DIR/qca_optimized/*.log)"
echo "Greedy:   $(grep 'Flooded roads' $BASE_DIR/greedy_optimized/*.log)"
```

**Checklist:**
- [ ] Create test script
- [ ] Run baseline
- [ ] Run QCIA (both modes)
- [ ] Run both optimized simulations
- [ ] Compare ROI metrics
- [ ] Generate comparison plots

---

### Task 3: Visualize Manifold (30 min)

**Script:** Create `visualize_qca_results.py`

```python
#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/tiger/Desktop/QCIA_HRF_Flood copy')

from AI.qcia_core.qca_manifold_optimizer import QCAOptimizer, visualize_manifold
from AI.qcia_core.flood_encoder import FloodStateEncoder
import json

# Load learned manifold
qca = QCAOptimizer()
encoder = FloodStateEncoder()

# Load experiences from saved file
qca.load_from_file('outputs/qca_comparison_test/qcia/qca_manifold.json', 
                   hypotheses=encoder.hypotheses)

# Visualize
visualize_manifold(qca, save_path='outputs/qca_manifold_3d.png')

print("✅ Manifold visualization saved")

# Print synergies (clusters)
clusters = qca.engine.get_experience_clusters(n_clusters=3)
print(f"\n🔍 Discovered {len(clusters)} intervention clusters:")
for i, cluster in enumerate(clusters):
    types = [qca.engine.experiences[idx].action['type'] for idx in cluster[:5]]
    print(f"   Cluster {i+1}: {', '.join(set(types))}")
```

**Checklist:**
- [ ] Create visualization script
- [ ] Load learned manifold
- [ ] Generate 3D plot
- [ ] Identify clusters (synergies)
- [ ] Annotate plot with intervention types

---

### Task 4: Full Budget Sweep with QCA (2 hours)

**Update:** Modify `test_QCIA_FULL.sh` to use QCA mode

```bash
# Add flag to run_qcia_flood_optimization.py
python run_qcia_flood_optimization.py \
  ... \
  --use_qca  # <-- NEW FLAG
```

**In `run_qcia_flood_optimization.py`:**
```python
if args.use_qca:
    # Use QCA manifold learning
    selected = qca.find_optimal_plan(baseline_state)
else:
    # Use greedy (baseline)
    selected = greedy_select(candidates, budget)
```

**Checklist:**
- [ ] Add `--use_qca` flag
- [ ] Run budget sweep (₹5-40 Cr) with QCA enabled
- [ ] Compare with Week 1 greedy results
- [ ] Check ROI improvement across all budgets
- [ ] Generate comparison report

---

## 📊 Success Criteria

### Minimum (Must Achieve)
- [ ] QCA learns manifold without errors (80+ experiences)
- [ ] QCA-selected interventions differ from greedy
- [ ] ROI improves by 2x (0.01x → 0.02x)
- [ ] Manifold visualization shows structure

### Target (Expected)
- [ ] ROI improves by 5-10x (0.01x → 0.05-0.10x)
- [ ] QCA discovers 2-3 intervention synergies
- [ ] Diverse intervention selection (3+ types)
- [ ] Clear clustering in manifold visualization

### Stretch (Exceptional)
- [ ] ROI improves by 10-20x (0.01x → 0.10-0.20x)
- [ ] QCA discovers novel combos (e.g., "pump + pond + drain")
- [ ] Dynamic sizing (1.5 vs 3.0 vs 5.0 m³/s)
- [ ] Transferable learning (apply to new AOI)

---

## 🐛 Potential Issues & Solutions

### Issue 1: Not enough experiences for Isomap
**Symptom:** `ValueError: n_neighbors=5 must be <= n_samples=4`  
**Solution:** Ensure at least 7 experiences before learning manifold. Add more candidate interventions or reduce `n_neighbors` to 3.

### Issue 2: Manifold has no clear structure
**Symptom:** Visualization shows uniform scatter (no clusters)  
**Solution:** This means interventions are too similar. Try:
- More diverse intervention types (use all 25 types)
- Vary sizing parameters (small/medium/large)
- Different locations (upstream vs downstream)

### Issue 3: QCA plan is worse than greedy
**Symptom:** ROI decreases after QCA integration  
**Solution:** Check if:
- Planning is finding shortest path to *highest reward* (not just any path)
- Experiences are correctly labeled (reward = flood reduction, not cost)
- Manifold learning converged (check reconstruction error < 0.5)

### Issue 4: Very slow manifold learning
**Symptom:** Isomap takes >5 minutes for 100 experiences  
**Solution:** Reduce `manifold_dim` from 3 to 2, or use approximate neighbors (sklearn `n_jobs=-1`)

---

## 📈 Expected Timeline

| Task | Duration | Status |
|------|----------|--------|
| 1. Update run_qcia_flood_optimization.py | 2-3 hours | ⏸️ Pending |
| 2. Run comparison test | 1 hour | ⏸️ Pending |
| 3. Visualize manifold | 30 min | ⏸️ Pending |
| 4. Full budget sweep with QCA | 2 hours | ⏸️ Pending |
| **TOTAL** | **5-6.5 hours** | **0% complete** |

**Start:** October 5, 2025, 9:00 AM  
**Target completion:** October 5, 2025, 3:00 PM  
**Buffer:** 2 hours for debugging/iteration

---

## 📁 Outputs to Generate

### Comparison Plots
- [ ] `qca_manifold_3d.png` - Manifold visualization with clusters
- [ ] `roi_comparison_qca_vs_greedy.png` - ROI across budgets
- [ ] `intervention_mix_comparison.png` - Type diversity bar chart
- [ ] `synergy_heatmap.png` - Which interventions cluster together

### Reports
- [ ] `WEEK2_COMPLETION_REPORT.md` - Full results
- [ ] `qca_vs_greedy_comparison.json` - Quantitative metrics
- [ ] `discovered_synergies.txt` - Qualitative analysis

### Manifold Data
- [ ] `qca_manifold.json` - Learned manifold (for reuse)
- [ ] `qca_experiences.json` - All experiences (for analysis)

---

## 🎯 Next Steps After Week 2

**If Week 2 succeeds (ROI 0.05-0.10x):**
→ Week 3: Calibration to real data (target ROI 0.2-0.5x)

**If Week 2 partially succeeds (ROI 0.02-0.05x):**
→ Strengthen intervention physics first (larger sinks, better culverts)
→ Then retry QCA

**If Week 2 fails (ROI < 0.02x):**
→ Debug manifold learning (check experiences, encoding, planning)
→ May need more training data (run more intervention scenarios)

---

**Checklist created:** October 4, 2025, 11:59 PM  
**Ready to begin:** October 5, 2025, 9:00 AM

