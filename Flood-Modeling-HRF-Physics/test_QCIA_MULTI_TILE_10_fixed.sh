#!/bin/bash
# Multi-Tile Agentic QCIA Workflow
# =================================
# Divides large AOI into focused tiles, runs QCIA on each, combines results

set -e

echo "======================================================================"
echo "🔥 MULTI-TILE AGENTIC QCIA WORKFLOW"
echo "======================================================================"
echo ""
echo "Strategy: Divide large AOI into focused high-resolution tiles"
echo "  • Each tile: 2km × 2km @ 20m resolution (100×100 cells)"
echo "  • Run QCIA independently on each tile"
echo "  • Combine results into master design"
echo ""
echo "Benefits:"
echo "  ✅ 25× higher resolution per tile"
echo "  ✅ AI sees proper intervention physics"
echo "  ✅ Each tile optimized for local flooding"
echo "  ✅ Parallel execution possible"
echo ""

# Configuration
OUT_DIR="outputs/multi_tile_10"
BASE_TILE_COL=4474
BASE_TILE_ROW=4260
TILE_SIZE_CELLS=20  # Each tile is 20×20 cells @ 100m = 2km
TILES_X=5  # 5×5 = 25 tiles total
TILES_Y=5
BUDGET_PER_TILE_CR=4  # ₹4 Cr per tile × 25 = ₹100 Cr total
RESOLUTION_M=20  # 20m per cell

# Data files
DEM="Data/Jabalpur_Data/DEM_utm44.tif"
LULC="Data/Jabalpur_Data/LULC_utm44.tif"
RIVERS="Data/Jabalpur_Data/Main/rivers_aoi.geojson"
ROADS="Data/Jabalpur_Data/Main/roads_aoi.geojson"
DRAINS="Data/Jabalpur_Data/Main/drains_aoi.geojson"

RAIN_MMPH=60
T_HOURS=1.5

mkdir -p "$OUT_DIR"

echo "📊 Configuration:"
echo "   Base tile: ($BASE_TILE_COL, $BASE_TILE_ROW)"
echo "   Grid: ${TILES_X}×${TILES_Y} tiles"
echo "   Tile size: ${TILE_SIZE_CELLS}×${TILE_SIZE_CELLS} cells @ 100m = 2km × 2km"
echo "   Resolution: ${RESOLUTION_M}m (100×100 cells per tile)"
echo "   Budget per tile: ₹${BUDGET_PER_TILE_CR} Cr"
echo "   Total budget: ₹$((BUDGET_PER_TILE_CR * TILES_X * TILES_Y)) Cr"
echo ""

read -p "Press ENTER to start multi-tile optimization..." || true

# ============================================================================
# PHASE 1: Analyze each tile to find hotspots
# ============================================================================

echo ""
echo "======================================================================"
echo "[1/3] ANALYZING TILES TO PRIORITIZE HOTSPOTS"
echo "======================================================================"
echo ""

# Run baseline on full AOI first to identify hotspots
echo "🔍 Running baseline on full 10km AOI to identify flooding hotspots..."
python Runners/pb_cli.py \
  --dem "$DEM" \
  --lulc "$LULC" \
  --rivers "$RIVERS" \
  --roads "$ROADS" \
  --tile_col0 $BASE_TILE_COL \
  --tile_row0 $BASE_TILE_ROW \
  --nx 100 \
  --ny 100 \
  --upsample 1 \
  --rain_mm_per_hour $RAIN_MMPH \
  --t_hours $T_HOURS \
  --out "${OUT_DIR}/baseline_full" \
  --plot_vmax 2.0

# Analyze and rank tiles by flooding severity
echo ""
echo "📊 Ranking tiles by flooding severity..."

python -c "
import rasterio
import numpy as np
import json

with rasterio.open('${OUT_DIR}/baseline_full/final_h.tif') as src:
    h = src.read(1)

# Divide into tiles and rank
tile_rankings = []
for ti in range(${TILES_Y}):
    for tj in range(${TILES_X}):
        i0 = ti * ${TILE_SIZE_CELLS}
        j0 = tj * ${TILE_SIZE_CELLS}
        i1 = min(i0 + ${TILE_SIZE_CELLS}, 100)
        j1 = min(j0 + ${TILE_SIZE_CELLS}, 100)
        
        tile_h = h[i0:i1, j0:j1]
        
        # Calculate severity metrics
        max_depth = tile_h.max()
        mean_depth = tile_h.mean()
        flooded_cells = (tile_h > 0.2).sum()
        severe_cells = (tile_h > 0.5).sum()
        
        # Severity score (weighted)
        score = (max_depth * 2) + (mean_depth * 10) + (severe_cells * 0.1)
        
        tile_rankings.append({
            'tile_id': f't{ti}_{tj}',
            'tile_i': ti,
            'tile_j': tj,
            'tile_col': ${BASE_TILE_COL} + j0,
            'tile_row': ${BASE_TILE_ROW} + i0,
            'max_depth': float(max_depth),
            'mean_depth': float(mean_depth),
            'flooded_cells': int(flooded_cells),
            'severe_cells': int(severe_cells),
            'severity_score': float(score)
        })

# Sort by severity (highest first)
tile_rankings.sort(key=lambda x: x['severity_score'], reverse=True)

# Save rankings
with open('${OUT_DIR}/tile_rankings.json', 'w') as f:
    json.dump(tile_rankings, f, indent=2)

# Print top 10 tiles
print('🔥 Top 10 flooding hotspot tiles:')
print('='*70)
for rank, tile in enumerate(tile_rankings[:10], 1):
    print(f'{rank:2d}. Tile {tile[\"tile_id\"]:4s} @ ({tile[\"tile_col\"]}, {tile[\"tile_row\"]}): ')
    print(f'    Max: {tile[\"max_depth\"]:.2f}m, Flooded: {tile[\"flooded_cells\"]:3d} cells, Score: {tile[\"severity_score\"]:.1f}')

print('')
print(f'💾 Saved rankings to: ${OUT_DIR}/tile_rankings.json')
"

# ============================================================================
# PHASE 2: Run QCIA on top N tiles (agentic optimization)
# ============================================================================

echo ""
echo "======================================================================"
echo "[2/3] AGENTIC OPTIMIZATION ON PRIORITY TILES"
echo "======================================================================"
echo ""

# Process top 10 tiles (or fewer if low severity)
TOP_N_TILES=10

echo "🤖 Running QCIA on top ${TOP_N_TILES} flooding hotspots..."
echo ""

for tile_rank in $(seq 1 $TOP_N_TILES); do
    # Extract tile info from rankings
    tile_info=$(python -c "
import json
with open('${OUT_DIR}/tile_rankings.json') as f:
    tiles = json.load(f)
if $tile_rank <= len(tiles):
    tile = tiles[$tile_rank - 1]
    print(f\"{tile['tile_id']} {tile['tile_col']} {tile['tile_row']} {tile['max_depth']:.2f} {tile['severity_score']:.1f}\")
else:
    print('SKIP 0 0 0 0')
")
    
    read -r tile_id tile_col tile_row max_depth severity <<< "$tile_info"
    
    # Skip if severity too low
    if [ "$tile_id" = "SKIP" ]; then
        continue
    fi
    
    echo "────────────────────────────────────────────────────────────────────"
    echo "🎯 Tile $tile_rank/${TOP_N_TILES}: $tile_id"
    echo "   Location: (${tile_col}, ${tile_row})"
    echo "   Max depth: ${max_depth}m, Severity: ${severity}"
    echo "────────────────────────────────────────────────────────────────────"
    
    TILE_DIR="${OUT_DIR}/tiles/${tile_id}"
    mkdir -p "$TILE_DIR"
    
    # Run QCIA workflow on this tile (NO CD - use absolute paths!)
    # Baseline
    echo "  [1/4] Baseline simulation..."
    python Runners/pb_cli.py \
      --dem "$DEM" \
      --lulc "$LULC" \
      --rivers "$RIVERS" \
      --roads "$ROADS" \
      --tile_col0 $tile_col \
      --tile_row0 $tile_row \
      --nx $TILE_SIZE_CELLS \
      --ny $TILE_SIZE_CELLS \
      --upsample 5 \
      --rain_mm_per_hour $RAIN_MMPH \
      --t_hours $T_HOURS \
      --out "${TILE_DIR}/baseline" \
      --plot_vmax 2.0 > "${TILE_DIR}/baseline.log" 2>&1
    
    # QCIA optimization
    echo "  [2/4] Running QCIA optimization..."
    python run_qcia_flood_optimization.py \
      --baseline_dir "${TILE_DIR}/baseline" \
      --budget_cr $BUDGET_PER_TILE_CR \
      --output "${TILE_DIR}/qcia_design.json" \
      --max_actions 5 \
      --force_greedy > "${TILE_DIR}/qcia.log" 2>&1
    
    # Optimized simulation
    echo "  [3/4] Testing optimized design..."
    python Runners/pb_cli.py \
      --dem "$DEM" \
      --lulc "$LULC" \
      --rivers "$RIVERS" \
      --roads "$ROADS" \
      --drains "$DRAINS" \
      --tile_col0 $tile_col \
      --tile_row0 $tile_row \
      --nx $TILE_SIZE_CELLS \
      --ny $TILE_SIZE_CELLS \
      --upsample 5 \
      --rain_mm_per_hour $RAIN_MMPH \
      --t_hours $T_HOURS \
      --out "${TILE_DIR}/optimized" \
      --qcia_design "${TILE_DIR}/qcia_design.json" \
      --plot_vmax 2.0 > "${TILE_DIR}/optimized.log" 2>&1
        
    # Calculate impact
    echo "  [4/4] Measuring impact..."
    python -c "
import rasterio
import numpy as np
import json

with rasterio.open('${TILE_DIR}/baseline/final_h.tif') as src:
    baseline_h = src.read(1)
with rasterio.open('${TILE_DIR}/optimized/final_h.tif') as src:
    opt_h = src.read(1)

baseline_flooded = (baseline_h >= 0.2).sum()
opt_flooded = (opt_h >= 0.2).sum()
reduction = baseline_flooded - opt_flooded
reduction_pct = (reduction / baseline_flooded * 100) if baseline_flooded > 0 else 0

# Load design
with open('${TILE_DIR}/qcia_design.json') as f:
    design = json.load(f)

result = {
    'tile_id': '$tile_id',
    'baseline_flooded_cells': int(baseline_flooded),
    'optimized_flooded_cells': int(opt_flooded),
    'reduction_cells': int(reduction),
    'reduction_pct': float(reduction_pct),
    'cost_cr': design.get('total_cost_cr', 0),
    'num_interventions': len(design.get('interventions', []))
}

with open('${TILE_DIR}/tile_result.json', 'w') as f:
    json.dump(result, f, indent=2)

print(f'  ✅ Reduction: {reduction} cells ({reduction_pct:.1f}%), Cost: ₹{result[\"cost_cr\"]:.1f} Cr')
" > "${TILE_DIR}/result.log" 2>&1
    
    cat "${TILE_DIR}/result.log"
    
    echo ""
done

# ============================================================================
# PHASE 3: Combine results into master design
# ============================================================================

echo ""
echo "======================================================================"
echo "[3/3] COMBINING TILE DESIGNS INTO MASTER PLAN"
echo "======================================================================"
echo ""

python -c "
import json
import glob
from pathlib import Path

# Collect all tile designs
master_interventions = []
total_cost = 0
total_reduction = 0

for tile_result_file in sorted(glob.glob('${OUT_DIR}/tiles/*/tile_result.json')):
    tile_dir = Path(tile_result_file).parent
    
    # Load result
    with open(tile_result_file) as f:
        result = json.load(f)
    
    # Load design
    design_file = tile_dir / 'qcia_design.json'
    if design_file.exists():
        with open(design_file) as f:
            design = json.load(f)
        
        # Add interventions with tile offset
        for intervention in design.get('interventions', []):
            master_interventions.append(intervention)
        
        total_cost += result.get('cost_cr', 0)
        total_reduction += result.get('reduction_cells', 0)

# Create master design
master_design = {
    'num_interventions': len(master_interventions),
    'total_cost_cr': total_cost,
    'expected_total_impact': total_reduction,
    'multi_tile_design': True,
    'num_tiles_optimized': len(glob.glob('${OUT_DIR}/tiles/*/tile_result.json')),
    'interventions': master_interventions
}

with open('${OUT_DIR}/master_design.json', 'w') as f:
    json.dump(master_design, f, indent=2)

print('✅ MASTER DESIGN CREATED!')
print('='*70)
print(f'Total interventions: {len(master_interventions)}')
print(f'Total cost: ₹{total_cost:.1f} Crores')
print(f'Total reduction: {total_reduction} cells')
print(f'Tiles optimized: {master_design[\"num_tiles_optimized\"]}')
print('')
print('📁 Saved to: ${OUT_DIR}/master_design.json')
"

echo ""
echo "======================================================================"
echo "✅ MULTI-TILE AGENTIC OPTIMIZATION COMPLETE!"
echo "======================================================================"
echo ""
echo "🎯 Results:"
echo "   • Analyzed entire 10km × 10km AOI"
echo "   • Optimized top ${TOP_N_TILES} flooding hotspots at 20m resolution"
echo "   • Each tile got full QCIA workflow independently"
echo "   • Combined into master flood mitigation plan"
echo ""
echo "📁 Outputs:"
echo "   • ${OUT_DIR}/master_design.json - Combined design"
echo "   • ${OUT_DIR}/tile_rankings.json - Severity analysis"
echo "   • ${OUT_DIR}/tiles/ - Individual tile results"
echo ""
echo "🚀 Next steps:"
echo "   1. Test master design on full AOI"
echo "   2. Generate engineering drawings"
echo "   3. Export KMZ for stakeholder review"
echo ""

