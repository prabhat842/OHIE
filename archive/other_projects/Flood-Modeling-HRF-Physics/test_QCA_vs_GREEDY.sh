#!/bin/bash
set -e

BASE_DIR="outputs/qca_comparison"
BUDGET="12"

echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║              QCA vs GREEDY COMPARISON TEST                                  ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""

# Clean previous run
rm -rf "$BASE_DIR"
mkdir -p "$BASE_DIR"

# Use existing baseline from previous run
echo "[1/5] Using existing baseline..."
BASELINE_DIR="outputs/qcia_full_demo/baseline"
if [ ! -f "$BASELINE_DIR/final_snapshot.npz" ]; then
    echo "❌ Baseline not found, run test_QCIA_FULL.sh first"
    exit 1
fi
echo "   ✅ Baseline: $BASELINE_DIR"

# Run QCIA optimization (QCA mode already integrated)
echo ""
echo "[2/5] Running QCIA optimization (with QCA manifold)..."
python run_qcia_flood_optimization.py \
  --baseline_dir "$BASELINE_DIR" \
  --budget_cr $BUDGET \
  --target_reduction_pct 20 \
  --output "$BASE_DIR/qcia_design_qca.json"

QCA_DESIGN="$BASELINE_DIR/../qcia_analysis/qcia_design.json"
if [ -f "$QCA_DESIGN" ]; then
    cp "$QCA_DESIGN" "$BASE_DIR/qcia_design_qca.json"
fi

# Run optimized simulation (QCA)
echo ""
echo "[3/5] Running QCA-optimized simulation..."
python Runners/pb_cli.py \
  --dem Data/Jabalpur_Data/DEM_utm44.tif \
  --lulc Data/Jabalpur_Data/LULC_utm44.tif \
  --rivers Data/Jabalpur_Data/Main/rivers_aoi.geojson \
  --roads Data/Jabalpur_Data/Main/roads_aoi.geojson \
  --tile_col0 4474 --tile_row0 4260 \
  --nx 100 --ny 100 \
  --rain_mm_per_hour 60.0 \
  --t_hours 1.5 \
  --qcia_design "$BASE_DIR/qcia_design_qca.json" \
  --out "$BASE_DIR/qca_optimized" \
  --plot_vmax 2.0 \
  > "$BASE_DIR/qca_optimized.log" 2>&1

# Extract metrics from existing greedy run
echo ""
echo "[4/5] Comparing with greedy baseline..."
GREEDY_DIR="outputs/qcia_full_demo/qcia_optimized"

if [ ! -f "$GREEDY_DIR/final_snapshot.npz" ]; then
    echo "⚠️  Greedy run not found, using baseline as reference"
    GREEDY_DIR="$BASELINE_DIR"
fi

# Compare results
echo ""
echo "[5/5] Generating comparison report..."

python -c "
import numpy as np
from pathlib import Path

# Load results
baseline = np.load('$BASELINE_DIR/final_snapshot.npz')
qca = np.load('$BASE_DIR/qca_optimized/final_snapshot.npz')
greedy = np.load('$GREEDY_DIR/final_snapshot.npz')

h_baseline = baseline['h']
h_qca = qca['h']
h_greedy = greedy['h']

# Calculate flooded area (≥0.2m)
baseline_flood = np.sum(h_baseline >= 0.2)
qca_flood = np.sum(h_qca >= 0.2)
greedy_flood = np.sum(h_greedy >= 0.2)

# Calculate reduction
qca_reduction = 100 * (baseline_flood - qca_flood) / baseline_flood
greedy_reduction = 100 * (baseline_flood - greedy_flood) / baseline_flood

# Print comparison
print('╔══════════════════════════════════════════════════════════════════════════════╗')
print('║                    COMPARISON RESULTS                                        ║')
print('╚══════════════════════════════════════════════════════════════════════════════╝')
print('')
print(f'📊 Flooded Area (≥0.2m):')
print(f'   Baseline:  {baseline_flood:6d} cells (100%)')
print(f'   Greedy:    {greedy_flood:6d} cells ({greedy_reduction:+.1f}%)')
print(f'   QCA:       {qca_flood:6d} cells ({qca_reduction:+.1f}%)')
print('')
print(f'🎯 Flood Reduction:')
print(f'   Greedy:  {baseline_flood - greedy_flood:5d} cells ({greedy_reduction:.1f}%)')
print(f'   QCA:     {baseline_flood - qca_flood:5d} cells ({qca_reduction:.1f}%)')
print('')
if qca_reduction > greedy_reduction:
    improvement = qca_reduction - greedy_reduction
    print(f'✅ QCA Improvement: +{improvement:.1f} percentage points better than greedy')
elif qca_reduction < greedy_reduction:
    degradation = greedy_reduction - qca_reduction
    print(f'⚠️  QCA performed {degradation:.1f} percentage points worse than greedy')
else:
    print(f'➖ QCA and Greedy performed equally')
print('')
print(f'📁 Outputs saved to: $BASE_DIR/')
print('   • qca_optimized/ - QCA simulation results')
print('   • qca_optimized.log - Full simulation log')
print('')
print('🎨 Manifold visualization:')
print('   outputs/qcia_full_demo/qcia_analysis/qca_manifold_3d.png')
print('')
print('='*78)
"

echo ""
echo "✅ QCA vs Greedy comparison complete!"
echo ""



