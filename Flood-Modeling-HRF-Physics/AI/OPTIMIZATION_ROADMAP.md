# QCIA Optimization & Expansion Roadmap
**Analysis of Project Chimera Integration, Library Expansion, Mass Balance Fix, and Calibration**

Date: October 4, 2025

---

## 1️⃣ Project Chimera Integration (opt.py.bak)

### What It Is
A **Geometric Causal Learning Engine** that:
- Uses Isomap to learn low-dimensional causal manifolds
- Plans intervention sequences via Dijkstra shortest path
- Adapts in real-time using experience replay
- Successfully controlled fluid simulations (V17)

### How It Could Help Us

#### ✅ **Potential Benefits**
1. **Meta-Optimization of Intervention Parameters**
   - Learn optimal pump drawdown rates, pond drainage times
   - Discover emergent placement strategies (clustering, sequencing)
   - Adapt infrastructure during simulation (e.g., activate pumps only when needed)

2. **Causal Discovery Enhancement**
   - Our current PC algorithm finds correlations
   - Chimera learns **manifold geometry** of causation
   - Could discover non-linear intervention synergies

3. **Real-Time Adaptive Control**
   - Currently: static interventions
   - With Chimera: adaptive pumping rates, dynamic drainage opening

#### ⚠️ **Challenges**
1. **Architectural Mismatch**
   - Chimera: continuous parameter tuning (damper strength)
   - Our system: discrete infrastructure placement
   - **Solution:** Treat intervention *parameters* (pump rate, pond size) as continuous actions

2. **Computational Cost**
   - Chimera re-learns manifold every 7 experiences
   - For 8 budget scenarios: expensive
   - **Solution:** Cache manifolds, run once for parameter tuning phase

3. **Data Requirements**
   - Needs ~50+ experiences to learn stable manifolds
   - Our budget sweep: 8 scenarios
   - **Solution:** Synthetic augmentation (interpolate budgets)

### 🎯 **Recommended Integration Path**

**Phase 1: Parameter Tuning (Quick Win)**
```python
# Use Chimera to optimize pump drawdown rates
action = {'pump_rate_multiplier': 1.2, 'pond_drawdown_hours': 10}
reward = baseline_flooded_km - optimized_flooded_km
```

**Phase 2: Placement Strategy Learning**
```python
# Encode intervention locations as quantum states
q_state = encode_intervention_pattern(locations, types)
# Learn optimal spatial patterns
```

**Phase 3: Hybrid System**
- PC algorithm for causal discovery (what interventions work)
- Chimera for parameter/strategy optimization (how to tune them)

---

## 2️⃣ Expanding the Intervention Library

### Current Inventory (9 types)
- Culverts: 2m×2m, 3m×3m
- Drains: 1m, 1.5m RCC
- Ponds: 5,000 m³, 10,000 m³
- Pumps: 1.5 m³/s, 3.0 m³/s
- Permeable pavement

### 🏗️ **Proposed Expansions**

#### **A. Structural Flood Protection**

```python
# Flood walls / levees
'flood_wall_3m': InterventionSpec(
    type='barrier',
    name='Flood Wall (3m height)',
    description='RCC wall with earthen backing',
    capacity_m3_s=None,  # Prevents flow, doesn't convey
    dimensions='3m height × 0.5m thick × per meter length',
    cost_base=50_000,  # ₹50k base (design, permits)
    cost_per_unit=25_000,  # ₹25k/meter
    maintenance_annual=500,  # ₹500/m/year
    lifespan_years=50,
    min_spacing=100,
    requires_land_acquisition=True,
),

# Retention basins (larger than ponds)
'retention_basin_50k': InterventionSpec(
    type='storage',
    name='Retention Basin (50,000 m³)',
    description='Large excavated basin with outlet control',
    capacity_m3_s=0,
    dimensions='50,000 m³ capacity, ~20,000 m² area, 3m depth',
    cost_base=5_000_000,  # ₹50 Lakhs
    cost_per_unit=0,
    maintenance_annual=100_000,  # ₹1 Lakh/year
    lifespan_years=50,
    requires_land_acquisition=True,
),

# Underground storage (urban)
'underground_tank_5k': InterventionSpec(
    type='storage',
    name='Underground Storage Tank (5,000 m³)',
    description='RCC underground tank for space-constrained areas',
    capacity_m3_s=0,
    dimensions='5,000 m³, modular RCC construction',
    cost_base=10_000_000,  # ₹1 Cr (expensive but saves land)
    cost_per_unit=0,
    maintenance_annual=50_000,
    lifespan_years=75,
    requires_land_acquisition=False,  # Below ground
),
```

#### **B. Green Infrastructure**

```python
# Bioswales
'bioswale_3m': InterventionSpec(
    type='green_infra',
    name='Bioswale (3m wide)',
    description='Vegetated drainage channel with infiltration',
    capacity_m3_s=1.0,
    dimensions='3m wide × per meter length',
    cost_base=20_000,
    cost_per_unit=5_000,  # ₹5k/meter
    maintenance_annual=500,
    lifespan_years=25,
    min_slope=0.002,
),

# Rain gardens
'rain_garden_50m2': InterventionSpec(
    type='green_infra',
    name='Rain Garden (50 m²)',
    description='Depression with native plants for infiltration',
    capacity_m3_s=0,
    dimensions='50 m² × 0.5m depression',
    cost_base=50_000,  # ₹50k
    cost_per_unit=0,
    maintenance_annual=2_000,
    lifespan_years=20,
),

# Constructed wetlands
'wetland_5000m2': InterventionSpec(
    type='green_infra',
    name='Constructed Wetland (5,000 m²)',
    description='Engineered wetland for flood storage + treatment',
    capacity_m3_s=0,
    dimensions='5,000 m² × 1m depth',
    cost_base=2_000_000,  # ₹20 Lakhs
    cost_per_unit=0,
    maintenance_annual=50_000,
    lifespan_years=30,
    requires_land_acquisition=True,
),
```

#### **C. Advanced Drainage**

```python
# Smart gates (IoT-controlled)
'smart_gate_2m': InterventionSpec(
    type='active',
    name='Smart Drainage Gate (2m)',
    description='Automated gate with sensors + real-time control',
    capacity_m3_s=5.0,  # When open
    dimensions='2m wide gate',
    cost_base=500_000,  # ₹5 Lakhs (includes IoT)
    cost_per_unit=0,
    maintenance_annual=25_000,
    lifespan_years=25,
    requires_power=True,
),

# Siphons (under-road drainage)
'siphon_1m': InterventionSpec(
    type='culvert',
    name='Siphon (1m diameter)',
    description='Under-road pipe with automatic air vent',
    capacity_m3_s=3.0,
    dimensions='1m diameter × per meter length',
    cost_base=100_000,
    cost_per_unit=15_000,  # ₹15k/meter
    maintenance_annual=5_000,
    lifespan_years=40,
),
```

#### **D. Rapid Deployment (Emergency)**

```python
# Portable barriers
'portable_barrier_100m': InterventionSpec(
    type='barrier',
    name='Portable Flood Barrier (100m)',
    description='Rapid deployment water-filled tubes',
    capacity_m3_s=None,
    dimensions='100m × 1.2m height',
    cost_base=200_000,  # ₹2 Lakhs (reusable)
    cost_per_unit=0,
    maintenance_annual=10_000,
    lifespan_years=10,
),

# Mobile pumps
'mobile_pump_2m3s': InterventionSpec(
    type='active',
    name='Mobile Pump (2 m³/s)',
    description='Trailer-mounted pump for emergency response',
    capacity_m3_s=2.0,
    dimensions='Diesel-powered, trailer-mounted',
    cost_base=500_000,  # ₹5 Lakhs
    cost_per_unit=0,
    maintenance_annual=30_000,
    lifespan_years=15,
    requires_power=False,  # Self-powered
),
```

### 📊 **Total Expanded Library: 25+ Interventions**

---

## 3️⃣ Novel Intervention Design (Material Science + AI)

### Can Chimera Create Novel Interventions?

**Not directly, but we can build a system:**

#### **Approach: Intervention Generator AI**

```python
class NovelInterventionGenerator:
    """Uses material science + geometry optimization"""
    
    def generate_novel_design(self, site_conditions: Dict, budget: float):
        """
        Inputs:
        - site_conditions: slope, soil type, available space
        - budget: cost constraint
        
        Outputs:
        - novel_intervention: optimized design
        - material_spec: concrete mix, steel grade, etc.
        - performance_estimate: capacity, lifespan
        """
        
        # 1. Material optimization
        materials = self.optimize_materials(site_conditions)
        
        # 2. Geometry optimization (Chimera manifold learning)
        geometry = self.optimize_geometry(materials, budget)
        
        # 3. Validate with physics simulation
        capacity = self.simulate_performance(geometry, materials)
        
        return NovelIntervention(
            geometry=geometry,
            materials=materials,
            capacity=capacity,
            cost=self.estimate_cost(materials, geometry)
        )
```

#### **Example: AI-Designed Hybrid Pond-Culvert**

```python
'ai_hybrid_pond_culvert': InterventionSpec(
    type='hybrid',
    name='AI-Optimized Hybrid Storage-Conveyance',
    description='Detention basin with integrated high-flow bypass culvert',
    capacity_m3_s=8.0,  # Culvert capacity
    dimensions='3000 m³ storage + 2.5m×2.5m culvert',
    cost_base=3_500_000,  # ₹35 Lakhs
    cost_per_unit=0,
    maintenance_annual=40_000,
    lifespan_years=45,
    # AI-optimized shape: elliptical basin + curved culvert inlet
    ai_designed=True,
    material_optimization='High-strength fiber concrete (50% cost saving)',
),
```

#### **Material Science Integration**

```python
MATERIALS_DATABASE = {
    'concrete_fiber_reinforced': {
        'strength_mpa': 60,
        'cost_per_m3': 8000,
        'lifespan_years': 75,
        'co2_footprint_kg': 150,  # Lower than traditional
    },
    'geopolymer_concrete': {
        'strength_mpa': 55,
        'cost_per_m3': 6500,
        'lifespan_years': 80,
        'co2_footprint_kg': 80,  # Eco-friendly
    },
    'hdpe_corrugated': {
        'strength_mpa': None,
        'cost_per_m3': 12000,
        'lifespan_years': 100,
        'weight_savings': '90% vs concrete',
    },
}

def optimize_material_selection(site: Dict, budget: float):
    """AI-driven material selection based on:
    - Soil conditions (corrosive, expansive)
    - Load requirements
    - Budget constraints
    - Sustainability goals
    """
    pass
```

---

## 4️⃣ Mass Balance Fix (22-29% Discrepancy)

### Current Issue
```
Rainfall input:    409,845 m³
Infiltration:      -60 to -32,470 m³
Expected final:    409,772 m³
Actual final:      500,914 m³
Discrepancy:       91,142 m³ (22.2% of rainfall) ⚠️
```

### Root Causes

#### **A. Boundary Conditions**
```python
# Physics/hrf.py - likely issue
def run(self, ...):
    # Sponge layer at boundaries absorbs/reflects
    # May not be accounting for this in mass budget
```

**Fix:**
```python
# Track boundary flux explicitly
self.boundary_flux_out = 0.0
self.boundary_flux_in = 0.0

# In each timestep, measure flux across boundaries
boundary_cells = self.get_boundary_cells()
flux_out = np.sum(self.u[boundary_cells] * self.h[boundary_cells] * self.grid.dy * dt)
self.boundary_flux_out += flux_out

# Update expected mass
expected_mass = self.mass0 + rain_total - infil_total - self.boundary_flux_out
```

#### **B. Infiltration Accounting**
```python
# Runners/pb_cli.py - line 865
infil_vol = solver.infil_total

# But infil_rate is modified by intervention_applier!
# Pump sinks are added to infil_rate, but not tracked separately
```

**Fix:**
```python
# Separate tracking
self.intervention_sink_total = 0.0  # Pumps, ponds
self.natural_infil_total = 0.0      # Soil infiltration

expected_final = (self.mass0 + rain_total 
                  - self.natural_infil_total 
                  - self.intervention_sink_total
                  - self.boundary_flux_out)
```

#### **C. Numerical Artifacts (Spectral Method)**
```python
# Exponential filter may introduce mass conservation errors
# Especially with high-frequency noise
```

**Fix:**
```python
def apply(self, grid: Grid, f):
    # Current: aggressive filtering
    sigma = _xp.exp(-self.alpha * (eta**self.p))
    
    # Fix: preserve zero-frequency mode (mean)
    f_mean = _xp.mean(f)
    f_filtered = _xp.fft.ifft2(_xp.fft.fft2(f) * sigma).real
    f_filtered += (f_mean - _xp.mean(f_filtered))  # Restore mean
    return f_filtered
```

### 🔧 **Action Plan**

1. **Add boundary flux tracking** (30 min)
2. **Separate intervention sinks from natural infiltration** (1 hr)
3. **Mass-conserving filter** (1 hr)
4. **Validation test:** Run with no interventions, measure discrepancy (should be <1%)

---

## 5️⃣ Calibration to Real Data

### Current State
- Generic infiltration (LULC-based heuristics)
- Generic roughness (n=0.03)
- Uncalibrated culvert sizing

### 🎯 **Calibration Strategy**

#### **A. Infiltration Map Calibration**

```python
# Need: Soil texture map + field measurements
SOIL_INFILTRATION_RATES = {
    'clay': 0.5e-6,      # m/s (very slow)
    'loam': 5.0e-6,      # m/s (moderate)
    'sand': 15.0e-6,     # m/s (fast)
    'urban_paved': 0.01e-6,  # m/s (minimal)
}

# Calibrate against observed flood extent
def calibrate_infiltration(observed_flood_extent, dem, lulc):
    """
    Use observed flood data (satellite imagery, field surveys)
    to tune infiltration rates via optimization
    """
    params = {'clay_rate': 0.5e-6, 'loam_rate': 5.0e-6, ...}
    
    def objective(params):
        sim_flood = run_simulation_with_params(params)
        return mse(sim_flood, observed_flood_extent)
    
    optimal_params = scipy.optimize.minimize(objective, params)
    return optimal_params
```

#### **B. Roughness (Manning's n) Calibration**

```python
# Need: Flood depth time series (gauge data)
ROUGHNESS_CALIBRATION = {
    'urban_concrete': 0.015,
    'urban_asphalt': 0.016,
    'grass': 0.035,
    'dense_veg': 0.10,
}

# Calibrate against gauge data
def calibrate_roughness(gauge_timeseries, dem, lulc):
    """
    Tune Manning's n to match observed flood depths
    at specific gauge locations
    """
    pass
```

#### **C. Culvert Sizing Calibration**

```python
# Current: Fixed 2m×2m or 3m×3m
# Reality: Varies widely

def infer_culvert_sizes_from_roads(roads_geojson, drains_geojson):
    """
    Estimate culvert sizes from:
    - Road hierarchy (national highway vs local)
    - Drain width at crossing
    - Upstream drainage area
    """
    for crossing in crossings:
        road_class = crossing['road_type']
        drain_width = crossing['drain_width']
        
        if road_class == 'highway':
            size = max(3.0, drain_width * 1.2)
        elif road_class == 'arterial':
            size = max(2.0, drain_width)
        else:
            size = max(1.5, drain_width * 0.8)
        
        crossing['estimated_culvert_size'] = size
```

#### **D. Validation Data Requirements**

```python
CALIBRATION_DATA_NEEDED = {
    'flood_extent': {
        'source': 'Sentinel-1 SAR (Sept 2023 Jabalpur flood)',
        'format': 'GeoTIFF (binary: flooded/not flooded)',
        'use': 'Calibrate infiltration, roughness',
    },
    'gauge_data': {
        'source': 'CWC gauge station (if available)',
        'format': 'CSV (timestamp, depth_m)',
        'use': 'Calibrate roughness, validate timing',
    },
    'infrastructure_inventory': {
        'source': 'Municipal records / field survey',
        'format': 'GeoJSON (culvert locations, sizes)',
        'use': 'Validate intervention assumptions',
    },
    'soil_data': {
        'source': 'NBSS&LUP soil maps',
        'format': 'Shapefile (soil texture classes)',
        'use': 'Calibrate infiltration rates',
    },
}
```

---

## 🎯 **Recommended Priority**

### **Immediate (Week 1)**
1. ✅ **Mass balance fix** - Critical for credibility
2. ✅ **Add 5-10 new intervention types** - Quick library expansion

### **Short-term (Week 2-3)**
3. ✅ **Basic calibration** - Tune infiltration, roughness using literature values
4. ✅ **Strengthen intervention physics** - Larger pump sinks, better pond drainage

### **Medium-term (Month 1-2)**
5. ⚠️ **Project Chimera integration** - For parameter optimization
6. ⚠️ **Material science DB** - Add alternative materials

### **Long-term (Month 3+)**
7. ⚠️ **Novel intervention generator** - AI-designed hybrids
8. ⚠️ **Full calibration with real data** - Requires data acquisition

---

## 💡 **Immediate Next Steps (for you to decide)**

**Option A: Fix Core Issues First** (Recommended)
```bash
1. Fix mass balance (1 day)
2. Strengthen intervention physics (1 day)
3. Add 10 new intervention types (1 day)
4. Re-run budget sweep with better physics
```

**Option B: Expand Library & Demo**
```bash
1. Add 20+ intervention types (2 days)
2. Create "intervention showcase" with all types
3. Demo current system as-is (for SaaS pitch)
4. Fix physics in next iteration
```

**Option C: Deep Integration (Ambitious)**
```bash
1. Integrate Project Chimera for meta-optimization (1 week)
2. Build novel intervention generator (2 weeks)
3. Full calibration pipeline (3 weeks)
4. Production-ready system with bleeding-edge AI
```

---

## 📊 **Decision Matrix**

| Priority | Effort | Impact | Recommended? |
|----------|--------|--------|--------------|
| Mass balance fix | 1 day | HIGH (credibility) | ✅ YES |
| Strengthen pump physics | 1 day | HIGH (visible results) | ✅ YES |
| Add 10 interventions | 1 day | MEDIUM (variety) | ✅ YES |
| Chimera integration | 1 week | MEDIUM (optimization) | ⚠️ LATER |
| Novel intervention AI | 2 weeks | LOW (niche) | ⚠️ LATER |
| Full calibration | 3 weeks | HIGH (accuracy) | ⚠️ DATA NEEDED |

---

**Which path should we take?** 🤔



