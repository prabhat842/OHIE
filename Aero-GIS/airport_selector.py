# (Full code for airport_selector.py - Version 1.4 with KML export removed)
# ==============================================================================
# Project: Urbanist AI - Airport Site Selector
# FILE NAME: airport_selector.py
# Version: 1.4 (KML export disabled)
# ==============================================================================
import rasterio
from rasterio.mask import mask
from rasterio.transform import xy, Affine
from rasterio.warp import reproject, Resampling
import geopandas as gpd
from shapely.geometry import Polygon
import numpy as np
from scipy.ndimage import distance_transform_edt
import time
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from mpl_toolkits.mplot3d import Axes3D
import os
import json
from datetime import datetime

class Tee:
    def __init__(self, *files):
        self.files = files
    def write(self, obj):
        for f in self.files:
            f.write(obj)
            f.flush()
    def flush(self):
        for f in self.files:
            f.flush()

DEM_FILE_PATH = "Data/Hyd/DEM_UTM.tif"
LULC_FILE_PATH = "Data/Hyd/LULC_UTM.tif"
ROADS_FILE_PATH = "Data/Hyd/roads_hyd.geojson"
EXCLUSION_MASK_FILE_PATH = "Data/Hyd/exclusion_mask_UTM.tif"
FLOOD_MAP_FILE_PATH = "Data/Hyd/flood_map_UTM.tif"
BUFFER_RADIUS_M = 10000
AIRPORT_LENGTH_M = 800
AIRPORT_WIDTH_M = 3000
SEARCH_STRIDE = 25
FLIGHT_PATH_CHECK_DISTANCE_M = 15000
GLIDE_SLOPE_DEG = 3.0
RUNWAY_ANGLES_TO_CHECK = [110, 290] 
W = { 'earthworks': 0.30, 'obstruction': 0.40, 'lulc': 0.20, 'roads': 0.10 }
LULC_PENALTIES = { 1: 10.0, 2: 5.0, 3: 20.0, 4: 0.8, 5: 0.5, 'default': 1.0 }

def get_aoi_and_clip_data(buffer_m):
    # ... (function is unchanged)
    print(f"🌍 Preparing Area of Interest (AOI)...")
    for path in [DEM_FILE_PATH, LULC_FILE_PATH, ROADS_FILE_PATH, EXCLUSION_MASK_FILE_PATH, FLOOD_MAP_FILE_PATH]:
        if not os.path.exists(path): print(f"❌ FATAL ERROR: Input file not found at: {path}"); exit()
    try:
        ghmc_center_lon, ghmc_center_lat = 78.0941, 18.6725 #78.4294, 17.2403 #18.6725° N, 78.0941° E

        aoi_gdf = gpd.GeoDataFrame(geometry=gpd.points_from_xy([ghmc_center_lon], [ghmc_center_lat]), crs="EPSG:4326")
        print(f"🎯 Using precise RGIA center for AOI: ({ghmc_center_lat}°N, {ghmc_center_lon}°E)")
        with rasterio.open(DEM_FILE_PATH) as src:
            dem_crs, dem_nodata = src.crs, src.nodata; aoi_proj = aoi_gdf.to_crs(dem_crs); aoi_buffered = aoi_proj.buffer(buffer_m)
            clipped_dem, dem_transform = mask(src, aoi_buffered, crop=True, nodata=dem_nodata); clipped_dem = clipped_dem[0]
        target_shape = clipped_dem.shape
        def align_raster_to_dem(filepath):
            with rasterio.open(filepath) as src:
                aligned_array = np.zeros(target_shape, dtype=src.dtypes[0])
                reproject(source=rasterio.band(src, 1), destination=aligned_array, src_transform=src.transform, src_crs=src.crs, dst_transform=dem_transform, dst_crs=dem_crs, resampling=Resampling.nearest)
            return aligned_array
        print("📐 Aligning all raster layers to the DEM grid...")
        clipped_lulc = align_raster_to_dem(LULC_FILE_PATH); original_exclusion_data = align_raster_to_dem(EXCLUSION_MASK_FILE_PATH); flood_data = align_raster_to_dem(FLOOD_MAP_FILE_PATH)
        print("🌊 Combining original exclusion mask with flood map...")
        original_exclusion_mask = (original_exclusion_data > 0); flood_mask = (flood_data > 0); combined_exclusion_mask = np.logical_or(original_exclusion_mask, flood_mask)
        roads_gdf = gpd.read_file(ROADS_FILE_PATH).to_crs(dem_crs); clipped_roads = gpd.clip(roads_gdf, aoi_buffered)
        print("✅ All data clipped and aligned.")
        return clipped_dem, clipped_lulc, clipped_roads, combined_exclusion_mask, dem_transform, dem_nodata, dem_crs
    except Exception as e: print(f"❌ ERROR during data preparation: {e}"); exit()

def create_penalty_maps(clipped_lulc, clipped_roads, dem_shape, transform):
    # ... (function is unchanged)
    print("🗺️  Generating penalty maps..."); lulc_penalty_map = np.full(clipped_lulc.shape, LULC_PENALTIES['default'], dtype=np.float32)
    for lulc_val, penalty in LULC_PENALTIES.items():
        if lulc_val != 'default': lulc_penalty_map[clipped_lulc == lulc_val] = penalty
    if not clipped_roads.empty: road_raster = rasterio.features.rasterize(shapes=clipped_roads.geometry, out_shape=dem_shape, transform=transform, fill=0, all_touched=True, default_value=1).astype(bool)
    else: road_raster = np.zeros(dem_shape, dtype=bool)
    road_dist_map = distance_transform_edt(~road_raster); print("✅ Penalty maps generated."); return lulc_penalty_map, road_dist_map

def calculate_cost_to_flatten(dem_subset, pixel_area):
    # ... (function is unchanged)
    if dem_subset.size == 0: return float('inf'), 0
    target_elevation = np.mean(dem_subset); diff = dem_subset - target_elevation; volume = np.sum(np.abs(diff)) * pixel_area / 2; return volume, target_elevation

def calculate_flight_path_penalty(dem, runway_center_px, runway_len_px, runway_angle_deg, pixel_size, target_elevation, nodata_val):
    # ... (function is unchanged)
    penalty = 0.0; dem_h, dem_w = dem.shape; angle_rad = np.deg2rad(runway_angle_deg); direction_vector = np.array([np.sin(angle_rad), np.cos(angle_rad)]) 
    for sign in [-1, 1]:
        start_pos = runway_center_px + sign * (runway_len_px / 2) * direction_vector; num_steps = int(FLIGHT_PATH_CHECK_DISTANCE_M / pixel_size)
        for i in range(1, num_steps):
            check_pos = start_pos + sign * i * direction_vector; check_py, check_px = int(round(check_pos[0])), int(round(check_pos[1]))
            if not (0 <= check_py < dem_h and 0 <= check_px < dem_w): break
            ground_elev = dem[check_py, check_px];
            if ground_elev == nodata_val: continue
            distance = i * pixel_size; cone_floor = target_elevation + distance * np.tan(np.deg2rad(GLIDE_SLOPE_DEG))
            if ground_elev > cone_floor: penalty += (ground_elev - cone_floor)
    return penalty

def find_best_site(dem, lulc_map, road_map, exclusion_mask, transform, footprint_shape_px, stride, nodata_val):
    # ... (function is unchanged)
    print("\n🔬 Starting multi-constraint site analysis..."); analysis_result, lowest_score = {}, float('inf')
    fp_h, fp_w = footprint_shape_px; dem_h, dem_w = dem.shape; px_w, px_h = abs(transform.a), abs(transform.e)
    pixel_area = px_w * px_h; start_time = time.time(); total_steps = len(range(0, dem_h - fp_h, stride)) * len(range(0, dem_w - fp_w, stride))
    for i, (y, x) in enumerate((y, x) for y in range(0, dem_h - fp_h, stride) for x in range(0, dem_w - fp_w, stride)):
        if i % 100 == 0: print(f"  -> Analyzing... {i}/{total_steps} locations checked.", end='\r')
        if np.any(exclusion_mask[y:y+fp_h, x:x+fp_w]): continue
        dem_subset = dem[y:y+fp_h, x:x+fp_w]
        if np.any(dem_subset == nodata_val): continue
        earthworks_vol, target_elev = calculate_cost_to_flatten(dem_subset, pixel_area)
        min_obstruction_penalty, best_angle = float('inf'), 0; runway_center = np.array([y + fp_h / 2, x + fp_w / 2]); runway_len_px_ew = fp_w 
        for angle in RUNWAY_ANGLES_TO_CHECK:
            penalty = calculate_flight_path_penalty(dem, runway_center, runway_len_px_ew, angle, px_w, target_elev, nodata_val)
            if penalty < min_obstruction_penalty: min_obstruction_penalty, best_angle = penalty, angle
        lulc_penalty = np.mean(lulc_map[y:y+fp_h, x:x+fp_w]); road_dist_m = np.mean(road_map[y:y+fp_h, x:x+fp_w]) * px_w
        scores = {'earthworks': earthworks_vol / (dem_subset.size * pixel_area * 10), 'obstruction': min_obstruction_penalty / 1000, 'lulc': lulc_penalty, 'roads': road_dist_m / 1000}
        total_score = sum(W[key] * scores[key] for key in W)
        if total_score < lowest_score:
            lowest_score = total_score
            analysis_result = {
                'location_px': {'x': x, 'y': y}, 'target_elevation_m': target_elev, 'best_runway_angle': best_angle, 'score': total_score,
                'dem_subset': dem_subset,
                'footprint_shape_px': {'width': fp_w, 'height': fp_h},
                'details': {'Earthworks Volume (approx m³)': earthworks_vol, 'Obstruction Penalty Score': min_obstruction_penalty, 'Avg LULC Penalty': lulc_penalty, 'Avg Road Distance (m)': road_dist_m}
            }
    print(f"\n✅ Analysis complete in {time.time() - start_time:.2f} seconds."); return analysis_result

def generate_stakeholder_report(dem, exclusion_mask, result, footprint_shape_px, nodata_val, output_dir):
    # ... (function is unchanged)
    print("📊 Generating 2D stakeholder map..."); loc, (fp_h, fp_w) = result['location_px'], footprint_shape_px
    fig, ax = plt.subplots(figsize=(16, 9), facecolor='#F0F0F0'); fig.suptitle(f'Airport Site Selection Report (GHMC AOI)', fontsize=20, weight='bold')
    dem_masked = np.ma.masked_where(dem == nodata_val, dem); ax.imshow(dem_masked, cmap='terrain', vmin=np.percentile(dem[dem != nodata_val], 5), vmax=np.percentile(dem[dem != nodata_val], 95))
    exclusion_rgba = np.zeros((*exclusion_mask.shape, 4)); exclusion_rgba[exclusion_mask] = [1, 0, 0, 0.5]; ax.imshow(exclusion_rgba)
    ax.add_patch(patches.Rectangle((loc['x'], loc['y']), fp_w, fp_h, lw=2, ec='yellow', fc='none', ls='--'))
    report_text = (f"--- OPTIMAL SITE FOUND ---\nScore: {result['score']:.4f} (Lower is better)\n\n--- LOCATION ---\nPixel (X, Y): ({loc['x']}, {loc['y']})\nTarget Elevation: {result['target_elevation_m']:.2f} m\nRunway Angle: {result['best_runway_angle']}° (E-W Axis)\n\n--- JUSTIFICATION (COST FACTORS) ---\n")
    for key, val in result['details'].items(): report_text += f"- {key:<28}: {val:,.2f}\n"
    fig.text(0.75, 0.5, report_text, transform=fig.transFigure, fontsize=10, va='center', bbox=dict(boxstyle='round', facecolor='white', alpha=0.85), fontfamily='monospace')
    ax.legend(handles=[patches.Patch(color='red', alpha=0.5, label='Exclusion Zone (No-Go)'), plt.Line2D([0], [0], color='yellow', lw=2, ls='--', label='Optimal Site Location')], loc='lower right', frameon=True, facecolor='white')
    ax.set_title("Analysis Map: Viable land with optimal site selected"); ax.set_xticks([]); ax.set_yticks([]); plt.tight_layout(rect=[0, 0, 0.75, 0.95]); plt.savefig(f"{output_dir}/stakeholder_report.png", dpi=300, bbox_inches='tight'); print(f"✅ Report saved to '{output_dir}/stakeholder_report.png'")

def generate_3d_visualization(dem, result, footprint_shape_px, nodata_val, output_dir):
    # ... (function is unchanged)
    print("🏗️  Generating 3D earthworks visualization..."); loc, (fp_h, fp_w), target_elev = result['location_px'], footprint_shape_px, result['target_elevation_m']
    dem_subset = dem[loc['y']:loc['y']+fp_h, loc['x']:loc['x']+fp_w].copy(); dem_after = dem_subset.copy(); dem_after[dem_after != nodata_val] = target_elev
    X, Y = np.meshgrid(np.arange(dem_subset.shape[1]), np.arange(dem_subset.shape[0])); fig = plt.figure(figsize=(12, 6)); fig.suptitle('3D Site Visualization: Before & After Excavation', fontsize=16)
    for i, (data, title) in enumerate([(dem_subset, 'Before Excavation'), (dem_after, 'After Excavation')]):
        ax = fig.add_subplot(1, 2, i+1, projection='3d'); ax.plot_surface(X, Y, data, cmap='terrain', rstride=5, cstride=5, edgecolor='none'); ax.set_title(title); ax.set_zlabel('Elevation (m)'); ax.view_init(elev=30, azim=225)
    plt.savefig(f"{output_dir}/3d_excavation_report.png", dpi=200); print(f"✅ Report saved to '{output_dir}/3d_excavation_report.png'")

def convert_numpy_types(obj):
    # ... (function is unchanged)
    if isinstance(obj, (np.integer, np.int_, np.intc, np.intp, np.int8, np.int16, np.int32, np.int64, np.uint8, np.uint16, np.uint32, np.uint64)): return int(obj)
    elif isinstance(obj, (np.floating, np.float16, np.float32, np.float64)): return float(obj)
    elif isinstance(obj, np.ndarray): return obj.tolist()
    elif isinstance(obj, dict): return {key: convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, (list, tuple)): return [convert_numpy_types(item) for item in obj]
    return obj

if __name__ == "__main__":
    # Get output directory from environment variable or create with timestamp
    output_dir = os.environ.get('AEROGIS_OUTPUT_DIR')
    if not output_dir:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = f"Outputs/Run_{timestamp}"
    os.makedirs(output_dir, exist_ok=True)
    print(f"📁 Using output directory: {output_dir}")

    # Redirect stdout and stderr to log files
    import sys
    log_file = open(f"{output_dir}/stage1_selector.log", 'w')
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    sys.stdout = Tee(original_stdout, log_file)
    sys.stderr = Tee(original_stderr, log_file)

    try:
        dem, lulc, roads, exclusion_mask, transform, dem_nodata, dem_crs = get_aoi_and_clip_data(BUFFER_RADIUS_M)
        px_w, px_h = abs(transform.a), abs(transform.e)
        lulc_penalty_map, road_dist_map = create_penalty_maps(lulc, roads, dem.shape, transform)
        footprint_shape = (int(AIRPORT_LENGTH_M / px_h), int(AIRPORT_WIDTH_M / px_w))
        result = find_best_site(dem, lulc_penalty_map, road_dist_map, exclusion_mask, transform, footprint_shape, SEARCH_STRIDE, dem_nodata)
        if not result:
            print("\n" + "="*60 + "\n❌ ANALYSIS FAILED: NO SUITABLE SITE FOUND\n" + "="*60); print("Suggestion: Increase buffer radius or review exclusion data.")
        else:
            print("\n" + "="*60 + "\n🏆 MULTI-CONSTRAINT SITE SELECTION REPORT 🏆\n" + "="*60)
            print(f"Optimal site identified in a {BUFFER_RADIUS_M/1000}km buffer around the GHMC.")
            print(f"\n--- JUSTIFICATION (Final Score: {result['score']:.4f}) ---")
            printable_details = convert_numpy_types(result['details'])
            for key, val in printable_details.items(): print(f"  - {key:<28}: {val:,.2f}")
            print("="*60 + "\n"); generate_stakeholder_report(dem, exclusion_mask, result, footprint_shape, dem_nodata, output_dir)
            generate_3d_visualization(dem, result, footprint_shape, dem_nodata, output_dir)
            # --- KML EXPORT FOR THIS FILE IS NOW DISABLED ---
            # export_to_kml(result, transform, dem_crs, footprint_shape)
            print("\n" + "="*60); print("🌉 Preparing bridge files for Stage 2...");
            dem_subset_to_save = result.get('dem_subset')
            if dem_subset_to_save is not None:
                loc = result['location_px']; top_left_x, top_left_y = transform * (loc['x'], loc['y'])
                subset_transform = Affine(transform.a, transform.b, top_left_x, transform.d, transform.e, top_left_y)
                profile = {'driver': 'GTiff', 'height': dem_subset_to_save.shape[0], 'width': dem_subset_to_save.shape[1], 'count': 1, 'dtype': dem_subset_to_save.dtype, 'crs': dem_crs, 'transform': subset_transform, 'nodata': dem_nodata}
                with rasterio.open(f'{output_dir}/selected_site.tif', 'w', **profile) as dst: dst.write(dem_subset_to_save, 1)
                print(f"  - ✅ Saved DEM of selected site to '{output_dir}/selected_site.tif'")
                result.pop('dem_subset', None); serializable_result = convert_numpy_types(result)
                serializable_result['transform'] = [transform.a, transform.b, transform.c, transform.d, transform.e, transform.f]
                serializable_result['crs'] = str(dem_crs)
                with open(f'{output_dir}/site_details.json', 'w') as f: json.dump(serializable_result, f, indent=4)
                print(f"  - ✅ Saved site metadata to '{output_dir}/site_details.json'")
            else: print("  - ❌ Could not save bridge files: dem_subset not found in result.")
            print("="*60)
    finally:
        # Restore original stdout/stderr and close log file
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        log_file.close()