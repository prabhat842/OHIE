#!/bin/bash
# Jabalpur test with MATCHING AOI for roads and simulation
# =========================================================

set -e

echo "🚀 Testing with matching roads AOI..."

OUT="outputs/jabalpur_matching_test"

# Use smaller grid centered on roads AOI
# Roads are at: 79.916°E to 79.960°E, 23.148°N to 23.189°N
# In UTM44N: approximately 392000-396000 E, 2559000-2563000 N

# Strategy: Use DEM_utm44.tif and specify tile coordinates
# that overlap with the roads AOI region

python Runners/pb_cli.py \
  --dem Data/Jabalpur_Data/DEM_utm44.tif \
  --lulc Data/Jabalpur_Data/LULC_utm44.tif \
  --rivers Data/Jabalpur_Data/Main/rivers_aoi.geojson \
  --roads Data/Jabalpur_Data/Main/roads_aoi.geojson \
  --drains Data/Jabalpur_Data/Main/drains_aoi.geojson \
  --tile_col0 100 \
  --tile_row0 100 \
  --nx 120 \
  --ny 120 \
  --rain_mm_per_hour 50 \
  --t_hours 2.0 \
  --culverts_crossings_only \
  --culvert_area_m2 3.0 \
  --drain_sink_mps 8.0e-8 \
  --out "$OUT" \
  --plot_vmax 2.0

echo ""
echo "✅ Simulation complete!"
echo ""
echo "📁 Check outputs:"
ls -lh "$OUT/" | grep -E '\.(tif|png|geojson)$'
echo ""
echo "🖼️  View:"
echo "   open $OUT/final_h.png"
echo "   open $OUT/structures_debug.geojson"
echo ""

# Generate road overlay
python Runners/kpi_overlay_roads.py --run_dir "$OUT" --roads Data/Jabalpur_Data/Main/roads_aoi.geojson

echo ""
echo "📊 Road overlay:"
echo "   open $OUT/overlay_roads.png"
echo ""



