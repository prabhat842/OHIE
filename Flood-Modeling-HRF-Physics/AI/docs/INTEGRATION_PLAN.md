# AI-Physics Integration Plan

## ✅ Current Status: Physics Works, AI Not Active

### What's Working:
- ✅ HRF flood simulation (spectral SWE solver)
- ✅ Real data loading (DEM, LULC, roads, drains)
- ✅ Infrastructure placement (culverts at all crossings)
- ✅ Visualization outputs (TIF, PNG, GeoJSON)
- ✅ Road impact analysis (37.3km/186.7km flooded)

### What's NOT Working:
- ❌ AI/QCIA optimization (not active yet!)
- ❌ Budget-constrained selection (places ALL 101 culverts, no selection)
- ❌ Cost estimation (no cost database integrated)
- ❌ Mass balance (storage exceeds input by ~17%)

---

## 🎯 Integration Tasks (A & B)

### **Task B: Fix Mass Balance** (In Progress)

**Problem:** Storage increase (1,434,381 m³) exceeds net rainfall input (1,229,190 m³)

**Possible causes:**
1. Sponge layer adding water at boundaries
2. River stage increases during simulation
3. Numerical artifacts in DW-FV mode
4. Infiltration too low (only 346 m³ out of 1.2M m³ rainfall = 0.03%)

**Actions:**
- [ ] Check if sponge is active (--sponge_width parameter)
- [ ] Verify no river stage schedule
- [ ] Investigate infiltration rates (urban = 2e-9 m/s, very low)
- [ ] Add detailed mass tracking (rain in, infil out, boundary fluxes)

---

### **Task A: Add 3 Extra Tools** (In Progress)

#### **A1: intervention_library.py** - Cost Database

**Purpose:** Real infrastructure costs for budget optimization

**What it provides:**
```python
INTERVENTION_CATALOG = {
    'culvert_box_2x2': {
        cost_base: ₹20,00,000  # ₹20 Lakhs
        capacity: 5 m³/s
        dimensions: '2m × 2m × 10m length'
    },
    'drain_rcc_1m': {
        cost_per_meter: ₹8,000
        capacity: 2 m³/s
    },
    'pond_medium': {
        cost_base: ₹18,00,00,000  # ₹18 Crores
        capacity: 5,000 m³
    }
}
```

**Integration point:** 
```python
# In Runners/qcia_runner.py
from AI.intervention_library import INTERVENTION_CATALOG

# Estimate cost of current design
total_cost = 101 * INTERVENTION_CATALOG['culvert_box_2x2']['cost_base']
# = 101 × ₹20L = ₹20.2 Crores
```

**Status:** Ready to copy from `extra_tools/intervention_library.py`

---

#### **A2: spatial_optimizer.py** - Budget-Constrained Optimization

**Purpose:** Select BEST interventions within budget (not all 101!)

**What it does:**
1. **Find hotspots:** Analyze baseline flood to identify critical locations
2. **Estimate benefit:** For each potential culvert location, estimate flood reduction
3. **Optimize:** Select top-N interventions that maximize benefit/cost ratio within budget

**Example:**
```python
from AI.spatial_optimizer import SpatialQCIA

# After baseline simulation
optimizer = SpatialQCIA(grid, baseline_flood_depth, road_mask)
design = optimizer.optimize(
    budget_cr=12,  # ₹12 Crores
    max_iterations=50
)

# Returns:
# design.interventions = [
#     Culvert at (45, 67) - cost ₹20L - reduces 2.3km flooded roads
#     Culvert at (89, 120) - cost ₹20L - reduces 1.8km flooded roads
#     Culvert at (23, 156) - cost ₹20L - reduces 1.5km flooded roads
#     ... (6 total culverts for ₹12 Cr)
# ]
```

**Current vs AI-Optimized:**
| Metric | Current (No AI) | With AI (₹12Cr budget) |
|--------|-----------------|------------------------|
| Culverts | 101 (all crossings) | 6 (best locations) |
| Cost | ~₹20 Crores | ₹12 Crores |
| Roads flooded | 37.3 km | ~24 km (estimate) |
| Benefit/Cost | Unoptimized | Maximized |

**Status:** Ready to adapt from `extra_tools/spatial_optimizer.py`

---

#### **A3: generate_engineering_drawings.py** - Construction Documents

**Purpose:** Professional outputs for contractors

**What it generates:**
1. **Cross-section drawings** (PDF): Culvert dimensions, reinforcement, bedding
2. **Technical specifications** (PDF): Concrete grade (M30), steel (12mm @ 150mm c/c)
3. **Bill of Materials** (Excel): Cement, steel, labor hours, costs
4. **Site plans** (PDF): GPS locations, access roads, utilities

**Example output:**
```
outputs/engineering_docs/
├── culvert_001_cross_section.pdf
├── culvert_001_specifications.pdf
├── bill_of_materials.xlsx
├── cost_breakdown.pdf
└── site_plan.pdf
```

**Status:** Ready to copy from `extra_tools/generate_engineering_drawings.py`

---

## 🚀 Implementation Steps

### **Step 1: Copy intervention_library.py** (5 min)

```bash
cp extra_tools/intervention_library.py AI/
```

### **Step 2: Adapt spatial_optimizer.py** (30 min)

```bash
cp extra_tools/spatial_optimizer.py AI/
# Edit imports to use our HRFAdapter
# Connect to qcia_runner.py
```

### **Step 3: Add engineering drawings** (20 min)

```bash
cp extra_tools/generate_engineering_drawings.py tools/
# Update paths to use our output structure
```

### **Step 4: Integrate into qcia_runner.py** (30 min)

Add optimization step between baseline and optimized simulations:

```python
# In Runners/qcia_runner.py

# After baseline simulation:
baseline_flood = solver.h.copy()

# NEW: Optimize placement
from AI.spatial_optimizer import SpatialQCIA
optimizer = SpatialQCIA(grid, baseline_flood, road_mask)
design = optimizer.optimize(budget_cr=args.budget)

# Apply optimized design
from AI.intervention_generator import InterventionGenerator
gen = InterventionGenerator(grid, dem, road_mask)
gen.apply_spatial_design(solver, design)

# Run optimized simulation
solver.run(...)

# NEW: Generate engineering docs
from tools.generate_engineering_drawings import create_drawings
create_drawings(design, output_dir, dem, metadata)
```

### **Step 5: Debug mass balance** (30 min)

Add detailed tracking:

```python
# In Physics/hrf.py, add to run() method:

# Track all sources/sinks
rain_total = 0
infil_total = 0
boundary_flux = 0

# In time loop:
if rain_rate is not None:
    rain_total += rain_rate * dt * Lx * Ly
if infil_rate is not None:
    infil_total += infil_rate * dt * Lx * Ly

# At end:
print(f"Detailed mass budget:")
print(f"  Initial mass: {self.mass0:.3f} m³")
print(f"  Rain input: {rain_total:.3f} m³")
print(f"  Infiltration: {infil_total:.3f} m³")
print(f"  Boundary flux: {boundary_flux:.3f} m³")
print(f"  Final mass: {self.total_mass():.3f} m³")
print(f"  Expected final: {self.mass0 + rain_total - infil_total:.3f} m³")
print(f"  Discrepancy: {(self.total_mass() - (self.mass0 + rain_total - infil_total)):.3f} m³")
```

---

## 📊 Expected Results After Integration

### **Test command:**
```bash
./test_jabalpur_with_AI.sh --budget 12
```

### **Before (Current):**
```
✅ Simulation runs
✅ 101 culverts placed at all crossings
❌ No cost estimate
❌ No optimization
❌ No selection based on impact
```

### **After (With AI):**
```
🎯 Phase 1: Baseline simulation (no interventions)
   Result: 37.3 km roads flooded

🤖 Phase 2: AI optimization (budget = ₹12 Crores)
   - Analyzed 101 potential locations
   - Selected 6 best culverts
   - Total cost: ₹12 Crores
   - Expected benefit: Reduce to ~24 km flooded roads

🔧 Phase 3: Optimized simulation (with 6 culverts)
   Result: 24.1 km roads flooded (35% improvement!)

📊 Phase 4: Comparison & Reports
   - baseline_vs_optimized.png
   - cost_benefit_analysis.pdf
   - engineering_drawings.pdf
   - bill_of_materials.xlsx

ROI: ₹12 Cr investment saves ₹45 Cr in flood damage
```

---

## ⏱️ Timeline

- **Step 1-3 (Copy files):** 15 minutes
- **Step 4 (Integration):** 30 minutes
- **Step 5 (Debug mass):** 30 minutes
- **Testing:** 20 minutes

**Total: ~1.5 hours**

---

## 🎯 Success Criteria

✅ **Task B (Mass Balance):**
- [ ] Discrepancy < 5% of net input
- [ ] Detailed budget shows all sources/sinks
- [ ] "mass_err" renamed to "mass_change_pct"

✅ **Task A (AI Integration):**
- [ ] Cost database loaded (`INTERVENTION_CATALOG` accessible)
- [ ] Optimization selects N interventions within budget
- [ ] Engineering drawings generated
- [ ] Comparison shows baseline vs optimized
- [ ] ROI calculated and reported

---

## 🚀 Next Steps

**Do you want me to:**
1. ✅ Start with Task B (fix mass balance first)?
2. ✅ Then do Task A (add 3 tools)?
3. ⚠️ Test with real data after each step?

**Let's proceed!** 🎯

