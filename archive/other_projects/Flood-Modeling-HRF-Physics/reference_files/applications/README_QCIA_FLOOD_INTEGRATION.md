# QCIA + HRF Flood Integration

## Status: LEVEL 1 & 2 COMPLETE ✅

### What Works:
- ✅ HRF solver + QCIA fully integrated
- ✅ Interventions apply to physics simulation
- ✅ Causal graph learning from simulation data
- ✅ Iterative optimization loop functional
- ✅ 100+ experiences collected successfully

### Current Limitation:
- ⚠️ Grid search optimization gets stuck in local minima
- ⚠️ Small sample causal discovery needs more diverse data
- ⚠️ Need gradient-based optimization (LEVEL 3)

### Next: LEVEL 3 (Differentiable Physics)
Implementing gradient-based optimization for faster, better learning.

## Quick Start

### Simple Demo (5 min):
```bash
python AI/applications/demo_flood_qcia_simple.py --nx 80 --ny 80
```

### Learning Demo (30 min):
```bash
python AI/applications/demo_flood_qcia_learning.py --iterations 25
```

### Real Jabalpur Data (15 min):
```bash
cd Flood_Resilience_Demo/Runners
python pb_cli.py --dem data/Jabalpur_Data/Main/DEM_utm44.tif --qcia_design design.json
```
