#!/bin/bash
# Jabalpur test with CORRECT tile coordinates for roads AOI
# =========================================================

set -e

echo "🚀 Testing with CORRECT roads AOI coordinates..."

OUT="outputs/jabalpur_correct_test"

# Correct tile coordinates calculated from DEM/roads overlap:
# Roads AOI is at UTM44: (388998, 2560299) to (393542, 2564778)
# This corresponds to DEM tile starting at col0=4474, row0=4260

python Runners/pb_cli.py \
  --dem Data/Jabalpur_Data/DEM_utm44.tif \
  --lulc Data/Jabalpur_Data/LULC_utm44.tif \
  --rivers Data/Jabalpur_Data/Main/rivers_aoi.geojson \
  --roads Data/Jabalpur_Data/Main/roads_aoi.geojson \
  --drains Data/Jabalpur_Data/Main/drains_aoi.geojson \
  --tile_col0 4474 \
  --tile_row0 4260 \
  --nx 150 \
  --ny 150 \
  --rain_mm_per_hour 60 \
  --t_hours 2.0 \
  --culverts_crossings_only \
  --culvert_area_m2 4.0 \
  --drain_sink_mps 1.0e-7 \
  --out "$OUT" \
  --plot_vmax 2.5

echo ""
echo "✅ Simulation complete!"
echo ""
echo "📁 Check outputs:"
ls -lh "$OUT/" | grep -E '\.(tif|png|geojson)$'
echo ""

# Generate road overlay
python Runners/kpi_overlay_roads.py --run_dir "$OUT" --roads Data/Jabalpur_Data/Main/roads_aoi.geojson

echo ""
echo "🎉 RESULTS:"
echo ""
cat "$OUT/structures_debug.geojson" | head -5
echo ""
echo "📊 View outputs:"
echo "   open $OUT/final_h.png"
echo "   open $OUT/overlay_roads.png"
echo ""



