#!/bin/bash
# Monitor multi-tile optimization progress

clear
echo "🔍 MULTI-TILE OPTIMIZATION MONITOR"
echo "══════════════════════════════════════════════════════════"
echo ""

# Check if running
if pgrep -f "test_QCIA_MULTI_TILE.sh" > /dev/null; then
    echo "✅ Status: RUNNING"
else
    echo "⚠️  Status: NOT RUNNING (completed or stopped)"
fi

echo ""
echo "📊 PROGRESS:"
echo "──────────────────────────────────────────────────────────"

# Check tile completion
for tile in outputs/multi_tile/tiles/t*; do
    if [ -d "$tile" ]; then
        tile_name=$(basename "$tile")
        if [ -f "$tile/tile_result.json" ]; then
            result=$(python3 -c "import json; r=json.load(open('$tile/tile_result.json')); print(f'✅ {r[\"tile_id\"]}: {r[\"reduction_pct\"]:.1f}% reduction (₹{r[\"cost_cr\"]:.1f} Cr, {r[\"num_interventions\"]} interventions)')")
            echo "$result"
        elif [ -f "$tile/qcia.log" ]; then
            echo "🔄 $tile_name: QCIA optimization..."
        elif [ -f "$tile/baseline.log" ]; then
            echo "🔄 $tile_name: Baseline simulation..."
        else
            echo "⏳ $tile_name: Queued"
        fi
    fi
done

echo ""
echo "📁 FILES:"
echo "──────────────────────────────────────────────────────────"
if [ -f "outputs/multi_tile/tile_rankings.json" ]; then
    echo "✅ Tile rankings"
fi
if [ -f "outputs/multi_tile/master_design.json" ]; then
    echo "✅ Master design (COMPLETE!)"
fi

echo ""
echo "📜 LATEST LOG (last 15 lines):"
echo "──────────────────────────────────────────────────────────"
tail -15 outputs/multi_tile/run.log 2>/dev/null || echo "No log yet"

echo ""
echo "══════════════════════════════════════════════════════════"
echo "💡 Commands:"
echo "   • Watch live: tail -f outputs/multi_tile/run.log"
echo "   • Refresh: bash monitor_multi_tile.sh"
echo "   • Stop: pkill -f test_QCIA_MULTI_TILE"



