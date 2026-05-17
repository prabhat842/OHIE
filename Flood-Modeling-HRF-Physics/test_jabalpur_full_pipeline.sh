#!/bin/bash
# Test Complete Pipeline with Real Jabalpur Data
# ================================================
# This runs pb_cli.py with real data and generates all outputs

set -e  # Exit on error

echo "======================================================================"
echo "TESTING FULL PIPELINE WITH REAL JABALPUR DATA"
echo "======================================================================"

# Configuration
OUT_DIR="outputs/jabalpur_pipeline_test"
DEM="Data/GDSP_DEM_utm43n_100m.tif"
LULC="Data/LULC2_utm43n_100m.tif"
RIVERS="Data/osm_rivers_aoi.geojson"
ROADS="Data/roads_aoi.geojson"
DRAINS="Data/osm_drains_aoi.geojson"
POIS="Data/pois_aoi.geojson"

# Simulation parameters
NX=200
NY=200
RAIN_MMPH=50
T_HOURS=3
BUDGET_CR=12

echo ""
echo "📂 Data Files:"
echo "  DEM:    $DEM"
echo "  LULC:   $LULC"
echo "  Rivers: $RIVERS"
echo "  Roads:  $ROADS"
echo ""
echo "⚙️  Simulation:"
echo "  Grid:     ${NX}×${NY}"
echo "  Rainfall: ${RAIN_MMPH}mm/hr for ${T_HOURS}h"
echo "  Budget:   ₹${BUDGET_CR} Crores"
echo ""

# ============================================================================
# STEP 1: Run Baseline (No interventions)
# ============================================================================

echo "=============================================================="
echo "[1/3] BASELINE SIMULATION"
echo "=============================================================="

python Runners/pb_cli.py \
  --dem "$DEM" \
  --lulc "$LULC" \
  --rivers "$RIVERS" \
  --roads "$ROADS" \
  --nx $NX \
  --ny $NY \
  --rain_mm_per_hour $RAIN_MMPH \
  --t_hours $T_HOURS \
  --out "${OUT_DIR}/baseline" \
  --plot_vmax 2.0

echo "✅ Baseline complete"
echo ""

# ============================================================================
# STEP 2: Run with AI-Optimized Interventions
# ============================================================================

echo "=============================================================="
echo "[2/3] AI-OPTIMIZED SCENARIO"
echo "=============================================================="
echo "Adding interventions based on ₹${BUDGET_CR}Cr budget..."

# Estimate interventions from budget
# Simple heuristic: ₹3.5Cr per culvert, ₹18Cr per pond
CULVERTS=$((BUDGET_CR * 10 / 35))  # ~3 culverts for ₹12Cr
PONDS=$((BUDGET_CR / 18))          # ~0 ponds

echo "  Interventions: ${CULVERTS} culverts, ${PONDS} ponds"

# Run with selected culverts (if file exists)
if [ -f "Data/selected_culverts.geojson" ]; then
  CULVERT_ARG="--culverts_selected Data/selected_culverts.geojson"
else
  # Use crossings-only mode
  CULVERT_ARG="--culverts_crossings_only"
fi

python Runners/pb_cli.py \
  --dem "$DEM" \
  --lulc "$LULC" \
  --rivers "$RIVERS" \
  --roads "$ROADS" \
  --drains "$DRAINS" \
  $CULVERT_ARG \
  --culvert_area_m2 4.0 \
  --nx $NX \
  --ny $NY \
  --rain_mm_per_hour $RAIN_MMPH \
  --t_hours $T_HOURS \
  --drain_sink_mps 5.0e-8 \
  --out "${OUT_DIR}/optimized" \
  --plot_vmax 2.0

echo "✅ Optimized scenario complete"
echo ""

# ============================================================================
# STEP 3: Generate Comparison Outputs
# ============================================================================

echo "=============================================================="
echo "[3/3] GENERATING OUTPUTS"
echo "=============================================================="

# Road overlay (if we have the script)
if [ -f "Runners/kpi_overlay_roads.py" ]; then
  echo "📊 Generating road overlay..."
  python Runners/kpi_overlay_roads.py \
    --depth_tif "${OUT_DIR}/baseline/final_h.tif" \
    --roads "$ROADS" \
    --out "${OUT_DIR}/baseline/overlay_roads.png" \
    --title "Baseline: Flooded Roads"
  
  python Runners/kpi_overlay_roads.py \
    --depth_tif "${OUT_DIR}/optimized/final_h.tif" \
    --roads "$ROADS" \
    --out "${OUT_DIR}/optimized/overlay_roads.png" \
    --title "Optimized: Flooded Roads"
  echo "✅ Road overlays generated"
fi

# Comparison plot
if [ -f "Runners/compare_runs_overlay.py" ]; then
  echo "📊 Generating comparison..."
  python Runners/compare_runs_overlay.py \
    --baseline "${OUT_DIR}/baseline/final_h.tif" \
    --optimized "${OUT_DIR}/optimized/final_h.tif" \
    --out "${OUT_DIR}/comparison.png"
  echo "✅ Comparison plot generated"
fi

# KMZ export (if we have the script)
if [ -f "Runners/export_kmz.py" ]; then
  echo "🌍 Exporting KMZ for Google Earth..."
  python Runners/export_kmz.py \
    --tif "${OUT_DIR}/baseline/final_h.tif" \
    --out "${OUT_DIR}/baseline/flood_map.kmz" \
    --name "Jabalpur Baseline Flood"
  
  python Runners/export_kmz.py \
    --tif "${OUT_DIR}/optimized/final_h.tif" \
    --out "${OUT_DIR}/optimized/flood_map.kmz" \
    --name "Jabalpur Optimized Flood"
  echo "✅ KMZ files generated"
fi

# ============================================================================
# SUMMARY
# ============================================================================

echo ""
echo "======================================================================"
echo "✅ PIPELINE TEST COMPLETE"
echo "======================================================================"
echo ""
echo "📁 Outputs in: $OUT_DIR/"
echo ""
echo "Baseline Results:"
ls -lh "${OUT_DIR}/baseline/" | grep -E '\.(tif|png|npz|geojson|kmz)$' || echo "  (check directory)"
echo ""
echo "Optimized Results:"
ls -lh "${OUT_DIR}/optimized/" | grep -E '\.(tif|png|npz|geojson|kmz)$' || echo "  (check directory)"
echo ""
echo "Next Steps:"
echo "  1. Open ${OUT_DIR}/baseline/final_h.png"
echo "  2. Open ${OUT_DIR}/optimized/final_h.png"
echo "  3. Open ${OUT_DIR}/comparison.png"
echo "  4. Open ${OUT_DIR}/baseline/flood_map.kmz in Google Earth"
echo ""
echo "======================================================================"



