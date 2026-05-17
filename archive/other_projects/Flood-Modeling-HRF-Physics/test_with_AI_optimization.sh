#!/bin/bash
# Test AI-Integrated Workflow
# ============================
# This demonstrates baseline vs AI-optimized intervention selection

set -e

echo "======================================================================"
echo "🤖 AI-INTEGRATED FLOOD OPTIMIZATION TEST"
echo "======================================================================"
echo ""
echo "This will:"
echo "  1. Run BASELINE simulation (no interventions)"
echo "  2. Use AI to select BEST interventions within budget"
echo "  3. Run OPTIMIZED simulation (with AI-selected interventions)"
echo "  4. Compare results"
echo ""

# Configuration
OUT_DIR="outputs/ai_optimization_demo"
BUDGET=12  # ₹12 Crores

# Data files
DEM="Data/Jabalpur_Data/DEM_utm44.tif"
LULC="Data/Jabalpur_Data/LULC_utm44.tif"
RIVERS="Data/Jabalpur_Data/Main/rivers_aoi.geojson"
ROADS="Data/Jabalpur_Data/Main/roads_aoi.geojson"
DRAINS="Data/Jabalpur_Data/Main/drains_aoi.geojson"

# Simulation parameters
NX=120
NY=120
TILE_COL=4474
TILE_ROW=4260
RAIN_MMPH=60
T_HOURS=2.0

echo "Budget: ₹${BUDGET} Crores"
echo "Grid: ${NX}×${NY}, Rainfall: ${RAIN_MMPH}mm/hr for ${T_HOURS}h"
echo ""

# ============================================================================
# STEP 1: BASELINE SIMULATION (No interventions)
# ============================================================================

echo "======================================================================"
echo "[1/3] BASELINE SIMULATION (No Interventions)"
echo "======================================================================"

python Runners/pb_cli.py \
  --dem "$DEM" \
  --lulc "$LULC" \
  --rivers "$RIVERS" \
  --roads "$ROADS" \
  --tile_col0 $TILE_COL \
  --tile_row0 $TILE_ROW \
  --nx $NX \
  --ny $NY \
  --rain_mm_per_hour $RAIN_MMPH \
  --t_hours $T_HOURS \
  --out "${OUT_DIR}/baseline" \
  --plot_vmax 2.5

echo ""
echo "✅ Baseline complete"
echo ""

# Generate baseline road overlay
python Runners/kpi_overlay_roads.py \
  --run_dir "${OUT_DIR}/baseline" \
  --roads "$ROADS"

# ============================================================================
# STEP 2: WITH ALL CULVERTS (Simple rule-based, no AI)
# ============================================================================

echo "======================================================================"
echo "[2/3] ALL CULVERTS (Rule-Based, No Optimization)"
echo "======================================================================"
echo "Placing culverts at ALL road-drain crossings..."
echo ""

python Runners/pb_cli.py \
  --dem "$DEM" \
  --lulc "$LULC" \
  --rivers "$RIVERS" \
  --roads "$ROADS" \
  --drains "$DRAINS" \
  --tile_col0 $TILE_COL \
  --tile_row0 $TILE_ROW \
  --nx $NX \
  --ny $NY \
  --rain_mm_per_hour $RAIN_MMPH \
  --t_hours $T_HOURS \
  --culverts_crossings_only \
  --culvert_area_m2 4.0 \
  --drain_sink_mps 1.0e-7 \
  --out "${OUT_DIR}/all_culverts" \
  --plot_vmax 2.5

echo ""
echo "✅ All culverts simulation complete"
echo ""

# Generate overlay
python Runners/kpi_overlay_roads.py \
  --run_dir "${OUT_DIR}/all_culverts" \
  --roads "$ROADS"

# ============================================================================
# STEP 3: SUMMARY
# ============================================================================

echo ""
echo "======================================================================"
echo "✅ TEST COMPLETE"
echo "======================================================================"
echo ""
echo "📁 Outputs in: $OUT_DIR/"
echo ""
echo "📊 Results:"
echo "   Baseline:      ${OUT_DIR}/baseline/overlay_roads.png"
echo "   All Culverts:  ${OUT_DIR}/all_culverts/overlay_roads.png"
echo ""
echo "📋 Next Steps:"
echo "   1. Check mass balance summary (should now be detailed)"
echo "   2. Compare flooded road lengths"
echo "   3. Note: AI optimization coming next (will select best N culverts)"
echo ""
echo "======================================================================"



