#!/bin/bash
# Quick test with Jabalpur data - smaller grid for fast validation
# ================================================================

set -e

echo "🚀 Testing pipeline with real Jabalpur data..."
echo ""

OUT="outputs/jabalpur_quick_test"

# Quick test: small grid, 1 hour
python Runners/pb_cli.py \
  --dem Data/Jabalpur_Data/DEM_utm44.tif \
  --lulc Data/Jabalpur_Data/LULC_utm44.tif \
  --rivers Data/Jabalpur_Data/Main/rivers_aoi.geojson \
  --roads Data/Jabalpur_Data/Main/roads_aoi.geojson \
  --drains Data/Jabalpur_Data/Main/drains_aoi.geojson \
  --nx 150 \
  --ny 150 \
  --rain_mm_per_hour 40 \
  --t_hours 1.5 \
  --culverts_crossings_only \
  --culvert_area_m2 3.0 \
  --drain_sink_mps 5.0e-8 \
  --out "$OUT" \
  --plot_vmax 1.5

echo ""
echo "✅ Simulation complete!"
echo ""
echo "📁 Outputs:"
ls -lh "$OUT/" | grep -E '\.(tif|png|npz|geojson)$'
echo ""
echo "🖼️  View results:"
echo "   open $OUT/final_h.png"
echo ""
echo "🌍 Generate KMZ for Google Earth:"
echo "   python Runners/export_kmz.py --tif $OUT/final_h.tif --out $OUT/flood_map.kmz"
echo ""
echo "📊 Road overlay:"
echo "   python Runners/kpi_overlay_roads.py --depth_tif $OUT/final_h.tif --roads Data/Jabalpur_Data/Main/roads_aoi.geojson --out $OUT/roads_overlay.png"
echo ""



