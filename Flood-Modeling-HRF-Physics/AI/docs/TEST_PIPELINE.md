# Pipeline Testing Guide

## 🎯 Goal
Test the complete flood modeling pipeline with real Jabalpur data and verify all outputs work before building SaaS.

---

## 📋 Test Checklist

### ✅ Physics Engine
- [ ] HRF solver runs with real DEM/LULC
- [ ] River carving works
- [ ] LULC-based infiltration maps correctly
- [ ] Hydraulic structures (culverts) function

### ✅ Output Generation
- [ ] GeoTIFF export (final_h.tif)
- [ ] PNG visualization (final_h.png)
- [ ] Road overlay (flooded roads highlighted)
- [ ] KMZ for Google Earth
- [ ] Structures debug GeoJSON

### ✅ Data Quality
- [ ] Mass balance checks out
- [ ] No NaN/Inf in outputs
- [ ] Georeferencing correct (check in QGIS)
- [ ] Results look physically reasonable

---

## 🚀 Quick Start (5 minutes)

### Option 1: Quick Test (Fast validation)
```bash
cd "/Users/tiger/Desktop/QCIA_HRF_Flood copy"
./test_quick.sh
```

**What it does:**
- 150×150 grid (~15km²)
- 40mm/hr rainfall for 1.5 hours
- Includes culverts at road-drain crossings
- Takes ~2-5 minutes

**Outputs:** `outputs/jabalpur_quick_test/`
- `final_h.tif` - Flood depth GeoTIFF
- `final_h.png` - Quick visualization
- `structures_debug.geojson` - Placed culverts
- `final_snapshot.npz` - Full state (h, u, v, bed)
- `infiltration_mps.tif` - Applied infiltration rates
- `roughness_n.tif` - Manning roughness field

---

### Option 2: Full Pipeline (Complete test)
```bash
./test_jabalpur_full_pipeline.sh
```

**What it does:**
- Runs **baseline** (no interventions)
- Runs **optimized** (with culverts/drainage)
- Generates comparison plots
- Creates road overlays
- Exports KMZ files

Takes ~10-15 minutes for 200×200 grid.

**Outputs:** `outputs/jabalpur_pipeline_test/`
```
baseline/
  ├── final_h.tif
  ├── final_h.png
  ├── overlay_roads.png
  └── flood_map.kmz

optimized/
  ├── final_h.tif
  ├── final_h.png
  ├── overlay_roads.png
  └── flood_map.kmz

comparison.png
```

---

## 📊 Generating Additional Outputs

After running the simulation, generate visualizations:

### 1. Road Overlay (Flooded Roads)
```bash
python Runners/kpi_overlay_roads.py \
  --depth_tif outputs/jabalpur_quick_test/final_h.tif \
  --roads Data/Jabalpur_Data/Main/roads_aoi.geojson \
  --out outputs/jabalpur_quick_test/roads_overlay.png \
  --title "Jabalpur Flood Impact"
```

**Shows:** Roads color-coded by flood depth (green=safe, red=flooded)

---

### 2. KMZ Export (Google Earth)
```bash
python Runners/export_kmz.py \
  --tif outputs/jabalpur_quick_test/final_h.tif \
  --out outputs/jabalpur_quick_test/flood_map.kmz \
  --name "Jabalpur Flood Simulation"
```

**Usage:** Open `flood_map.kmz` in Google Earth to see flood overlay on satellite imagery

---

### 3. POI Impact Analysis
```bash
python Runners/kpi_pois.py \
  --depth_tif outputs/jabalpur_quick_test/final_h.tif \
  --pois Data/Jabalpur_Data/Main/pois.geojson \
  --out outputs/jabalpur_quick_test/pois_impact.csv
```

**Shows:** Which hospitals, schools, etc. are flooded and by how much

---

## 🔬 Manual Testing (Custom Parameters)

### Test 1: Heavy Monsoon (100mm/hr)
```bash
python Runners/pb_cli.py \
  --dem Data/Jabalpur_Data/DEM_utm44.tif \
  --lulc Data/Jabalpur_Data/LULC_utm44.tif \
  --rivers Data/Jabalpur_Data/Main/rivers_aoi.geojson \
  --roads Data/Jabalpur_Data/Main/roads_aoi.geojson \
  --nx 180 --ny 180 \
  --rain_mm_per_hour 100 \
  --t_hours 2 \
  --out outputs/heavy_monsoon \
  --plot_vmax 3.0
```

---

### Test 2: With Detention Ponds
```bash
python Runners/pb_cli.py \
  --dem Data/Jabalpur_Data/DEM_utm44.tif \
  --lulc Data/Jabalpur_Data/LULC_utm44.tif \
  --rivers Data/Jabalpur_Data/Main/rivers_aoi.geojson \
  --roads Data/Jabalpur_Data/Main/roads_aoi.geojson \
  --ponds Data/qcia_pond_sites.geojson \
  --pond_depth_m 1.0 \
  --nx 180 --ny 180 \
  --rain_mm_per_hour 60 \
  --t_hours 2.5 \
  --out outputs/with_ponds \
  --plot_vmax 2.0
```

---

### Test 3: Larger Domain (300×300 for full city)
```bash
python Runners/pb_cli.py \
  --dem Data/Jabalpur_Data/DEM_utm44.tif \
  --lulc Data/Jabalpur_Data/LULC_utm44.tif \
  --rivers Data/Jabalpur_Data/Main/rivers_aoi.geojson \
  --roads Data/Jabalpur_Data/Main/roads_aoi.geojson \
  --drains Data/Jabalpur_Data/Main/drains_aoi.geojson \
  --nx 300 --ny 300 \
  --rain_mm_per_hour 50 \
  --t_hours 3 \
  --culverts_crossings_only \
  --culvert_area_m2 4.0 \
  --drain_sink_mps 8.0e-8 \
  --out outputs/full_city \
  --plot_vmax 2.5
```

**Note:** Takes ~20-30 minutes for 300×300 grid

---

## 🧪 Validation Checks

### 1. Check Mass Balance
Look at the console output at the end:
```
Mass budget: rain_in=X m^3, infil=Y m^3, dStorage=Z m^3
```

**Expected:** `rain_in ≈ infil + dStorage` (within 10%)

---

### 2. Check GeoTIFF in QGIS
```bash
# Install QGIS if needed
brew install qgis  # macOS

# Open
qgis outputs/jabalpur_quick_test/final_h.tif
```

**Verify:**
- [ ] CRS is UTM Zone 44N (EPSG:32644)
- [ ] Extent matches Jabalpur area (lat ~23°, lon ~80°)
- [ ] No artifacts or weird patterns
- [ ] Values reasonable (0-3m for typical flood)

---

### 3. Check Structures Placement
Open `structures_debug.geojson` in QGIS or web viewer:
```bash
open http://geojson.io
# Drag and drop: outputs/jabalpur_quick_test/structures_debug.geojson
```

**Verify:** Culverts placed at road-drain intersections

---

### 4. Visual Inspection
```bash
open outputs/jabalpur_quick_test/final_h.png
```

**Look for:**
- [ ] Flooding concentrated in valleys/lowlands
- [ ] Rivers show elevated water depth
- [ ] Urban areas have lower infiltration (more ponding)
- [ ] No weird grid artifacts or numerical instabilities

---

## 📦 Expected Outputs Summary

### Core Outputs (Always Generated)
| File | Description | Software to Open |
|------|-------------|------------------|
| `final_h.tif` | Flood depth raster (georeferenced) | QGIS, ArcGIS, rasterio |
| `final_h.png` | Quick visualization | Any image viewer |
| `final_snapshot.npz` | Full simulation state (h, u, v, bed) | Python (numpy.load) |
| `structures_debug.geojson` | Placed culverts/bridges/weirs | QGIS, geojson.io |
| `infiltration_mps.tif` | Applied infiltration rates | QGIS |
| `roughness_n.tif` | Manning roughness field | QGIS |

### Optional Outputs (If Generated)
| File | Description | Tool Used |
|------|-------------|-----------|
| `roads_overlay.png` | Flooded roads highlighted | kpi_overlay_roads.py |
| `flood_map.kmz` | Google Earth overlay | export_kmz.py |
| `pois_impact.csv` | POI flood depths | kpi_pois.py |
| `comparison.png` | Baseline vs Optimized | compare_runs_overlay.py |

---

## ⚡ Performance Tips

### Speed Up Large Runs
1. **Reduce grid size**: Use `--nx 150 --ny 150` instead of 300
2. **Shorter simulation**: Use `--t_hours 1.5` for testing
3. **Lower rain**: `--rain_mm_per_hour 30` finishes faster
4. **Disable rain**: `--rain_off` (test geometry only)

### GPU Acceleration (Future)
`pb_cli.py` currently uses CPU. For GPU:
- Use `pb_cli_spu.py` (if PyTorch/MPS installed)
- 5-10× speedup on Apple Silicon

---

## 🚦 Success Criteria

Before moving to SaaS discussion, verify:

✅ **Physics Works**
- [ ] Simulation completes without errors
- [ ] Mass balance within 10%
- [ ] No NaN/Inf in outputs
- [ ] Results physically plausible

✅ **Outputs Work**
- [ ] GeoTIFF opens in QGIS
- [ ] PNG visualization clear
- [ ] KMZ loads in Google Earth
- [ ] Road overlay shows flooded segments

✅ **Data Quality**
- [ ] Georeferencing correct
- [ ] Structures placed at crossings
- [ ] LULC-based infiltration applied
- [ ] Rivers carved into DEM

✅ **Replicability**
- [ ] Can run with different parameters
- [ ] Results consistent across runs
- [ ] Easy to compare baseline vs intervention

---

## 🐛 Troubleshooting

### Error: "File not found"
- Check data paths in script
- Jabalpur data should be in `Data/Jabalpur_Data/`

### Error: "No module named 'fiona'"
```bash
pip install fiona shapely pyproj rasterio matplotlib
```

### Simulation crashes with "NaN detected"
- Reduce timestep: `--cfl 0.1 --dt_max 0.05`
- Increase min depth: `--h_min 0.05`

### KMZ doesn't load in Google Earth
- Check GeoTIFF CRS: should be geographic (EPSG:4326) or UTM
- Run `gdalinfo outputs/jabalpur_quick_test/final_h.tif` to verify

### Outputs look weird (grid artifacts)
- Check DEM for NoData values: `--h_min 0.02` can help
- Verify LULC mapping is correct
- Try lower CFL: `--cfl 0.1`

---

## 📞 Next Steps

Once all tests pass:

1. **Document typical runtime** for different grid sizes
2. **Benchmark quality** vs commercial tools (HEC-RAS)
3. **Define SaaS pricing tiers** based on grid size/features
4. **Plan API design** for automated runs
5. **Design web UI** for non-experts

---

## 🎓 Understanding the Outputs

### final_h.tif (Flood Depth)
- **Units:** meters
- **Range:** 0 (dry) to ~3m (deep flood)
- **Interpretation:** 
  - 0-0.3m: Passable on foot
  - 0.3-0.6m: Difficult/dangerous
  - 0.6-1.5m: Road impassable, vehicles stuck
  - >1.5m: Life-threatening, building damage

### structures_debug.geojson
- **LineString features** at cell faces
- **Properties:** `structure` (culvert/bridge/weir), `area`, `crest_elev`
- **Use:** Verify AI placed infrastructure correctly

### infiltration_mps.tif
- **Units:** m/s (meters per second)
- **Range:** 2e-9 (urban) to 8e-7 (forest)
- **Interpretation:** Higher = better drainage

---

**Ready to test? Run:**
```bash
./test_quick.sh
```

