# ==============================================================================
# Project: [IWMI] Water Resource Management AI
# FILE NAME: water_resource_diagnostics.py
# VERSION: 1.0 (IWMI Adaptation)
# PURPOSE: To perform a multi-criteria GIS analysis that generates a strategic
#          atlas of water management opportunities (harvesting, recharge, NbS).
#          This is adapted from the v3.4 Urban Diagnostics (Flood) engine.
# ==============================================================================
import rasterio
import geopandas as gpd
import pandas as pd
import numpy as np
import os
import sys
import json
from datetime import datetime
import matplotlib.pyplot as plt
from rasterio.features import rasterize
from rasterio.warp import reproject, Resampling
from scipy.ndimage import distance_transform_edt, gaussian_filter
from shapely.geometry import Point

try:
    from pysheds.grid import Grid
    from pysheds.view import Raster
except ImportError:
    print("❌ FATAL ERROR: The 'pysheds' library is required for hydrological analysis.")
    print("Please install it using: pip install pysheds")
    sys.exit(1)


class Tee:
    """Helper class to redirect stdout/stderr to both console and a log file."""
    def __init__(self, *files): self.files = files
    def write(self, obj):
        for f in self.files: f.write(obj); f.flush()
    def flush(self):
        for f in self.files: f.flush()

# --- Configuration (Gorakhpur Data) ---
# <<< ADAPTED >>> Re-purposing FLOOD_MAP_PATH as a proxy for water stress or demand.
WATER_STRESS_MAP_PATH = "Data/GKP/Flood_GKP_UTM.tif" # Used as proxy for water-stressed areas
POPULATION_MAP_PATH = "Data/GKP/Population_GKP_UTM_aligned.tif" # Used as proxy for water demand
DEM_PATH = "Data/GKP/DEM_GKP_UTM.tif"
LULC_PATH = "Data/GKP/LULC_UTM.tif"
BUILDINGS_SHP_PATH = "Data/GKP/Gorakhpur_Buildings.shp"
ROADS_SHP_PATH = "Data/GKP/Gorakhpur_roads.shp"
RAIL_SHP_PATH = "Data/GKP/Gorakhpur_rail.shp"
WATER_SHP_PATH = "Data/GKP/Gorakhpur_water_way.shp"
WATER_STATIC_SHP_PATH = "Data/GKP/Gorakhpur_water_static.shp"
SOIL_1_SHP_PATH = "Data/GKP/Gorakhpur_soil_1.shp"
SOIL_2_SHP_PATH = "Data/GKP/Gorakhpur_soil_2.shp"
PLACES_SHP_PATH = "Data/GKP/Gorakhpur_places.shp" # Proxy for farms/community centers
POI_SHP_PATH = "Data/GKP/Gorakhpur_POI.shp"
WORSHIP_SHP_PATH = "Data/GKP/Gorakhpur_Place_of_Worship.shp"
SUBDISTRICTS_SHP_PATH = "Data/GKP/Gorakhpur_sub_distrcits.shp"

# <<< ADAPTED >>> Weights re-framed for water harvesting.
# TWI and topographic_fit are still the best predictors for where water will naturally collect.
POND_WEIGHTS = {'twi': 0.40, 'topographic_fit': 0.30, 'land_cost': -0.20, 'engineering_cost': -0.10}

# <<< ADAPTED >>> Weights for Groundwater Recharge Structures (formerly Levees).
# We now prioritize infiltration potential and runoff availability, not "protection".
RECHARGE_WEIGHTS = {
    'infiltration_suitability': 0.50, # New factor based on soil drainage
    'runoff_availability': 0.20,      # New factor based on flow accumulation
    'land_cost': -0.20,
    'engineering_cost': -0.10
}

# <<< ADAPTED >>> Weights for Nature-Based Solutions (formerly Bioswales).
# The logic (gentle slopes, near drainage) remains highly relevant for NbS.
NBS_WEIGHTS = {'slope_suitability': 0.5, 'drainage_enhancement': 0.3, 'land_cost': -0.15, 'engineering_cost': -0.05}

# LULC Costs (remain the same)
LULC_COSTS = {
    10: 10.0,       # Example: Residential
    12: 0.5,        # Example: Park
    8: 20.0,        # Example: Commercial
    'default': 1.0
}
DRAINAGE_COST_MAPPING = {1.0: 0.1, 2.0: 0.4, 3.0: 0.7, 4.0: 1.0, 'default': 0.5}
SOIL_COST_WEIGHTS = {'clay': 0.5, 'bulk_density': 0.3, 'drainage': 0.2}

# --- Helper Functions (No changes needed) ---

def normalize_map(data):
    """Normalizes a raster map to a 0-1 scale, handling NaN values."""
    data_masked = np.ma.masked_invalid(data)
    min_val, max_val = data_masked.min(), data_masked.max()
    if max_val > min_val:
        normalized = (data_masked - min_val) / (max_val - min_val)
        return normalized.filled(0)
    return np.zeros_like(data)

def rasterize_shapefile(gdf, profile, value_col=None):
    """Rasterizes a GeoDataFrame to match a given raster profile."""
    if gdf.crs != profile['crs']:
        gdf = gdf.to_crs(profile['crs'])
    if value_col:
        shapes = ((geom, val) for geom, val in zip(gdf.geometry, gdf[value_col]))
        return rasterize(shapes=shapes, out_shape=(profile['height'], profile['width']), transform=profile['transform'], fill=np.nan, dtype='float32')
    else:
        shapes = (geom for geom in gdf.geometry)
        return rasterize(shapes=shapes, out_shape=(profile['height'], profile['width']), transform=profile['transform'], fill=0, default_value=1, dtype='uint8')

# --- Core Analysis Functions ---

def perform_hydraulic_analysis(dem_path, profile):
    """Performs core hydrological analysis. This is essential for both flood and water harvesting."""
    print("  -> 🌊 Starting Hydraulic Pre-Analysis...")
    with rasterio.open(dem_path) as src:
        dem_data = src.read(1).astype(np.float32)
        if src.nodata is not None:
            dem_data[dem_data == src.nodata] = np.nan
    dem_raster = Raster(dem_data, metadata={'crs': profile['crs'], 'transform': profile['transform'], 'nodata': np.nan})
    grid = Grid.from_raster(dem_raster)

    print("     - Filling DEM pits...")
    flooded_dem = grid.fill_pits(dem=dem_raster)
    print("     - Calculating D8 flow direction...")
    flow_dir = grid.flowdir(dem=flooded_dem)
    print("     - Calculating flow accumulation (runoff potential)...")
    flow_acc = grid.accumulation(fdir=flow_dir)
    print("     - Calculating slope and TWI (wetness/collection potential)...")
    slope = grid.cell_slopes(dem=flooded_dem, fdir=flow_dir)

    flow_acc_data = np.array(flow_acc)
    slope_data = np.array(slope)

    # Calculate TWI
    tan_slope = np.tan(slope_data) + 1e-7
    catchment_area = (flow_acc_data + 1) * profile['transform'].a * abs(profile['transform'].e)
    twi = np.log(catchment_area / tan_slope)
    twi[np.isinf(twi)] = np.nan
    twi_median = np.nanmedian(twi)
    twi[np.isnan(twi)] = twi_median 

    print("  -> ✅ Hydraulic Pre-Analysis Complete.")
    return {'flow_acc': flow_acc_data, 'twi': twi, 'slope': slope_data}

def run_strategic_atlas_generation(output_dir):
    """Main function to generate the multi-layered strategic atlas."""
    print("\n🔬 Starting Water Resource Strategic Atlas Generation (v1.0 IWMI)...")
    try:
        # --- 1. Initial Setup & Data Loading ---
        print("  -> Loading base DEM and profile...")
        with rasterio.open(DEM_PATH) as dem_src:
            dem = dem_src.read(1).astype(np.float32)
            profile = dem_src.profile
            if dem_src.nodata is not None:
                dem[dem == dem_src.nodata] = np.nan
        target_shape = (profile['height'], profile['width'])
        
        print("  -> Loading vector data...")
        roads_gdf = gpd.read_file(ROADS_SHP_PATH)
        water_gdf = gpd.read_file(WATER_SHP_PATH)

        print("  -> Generating Exclusion Mask (Areas we cannot build)...")
        exclusion_mask = np.zeros(target_shape, dtype=bool)
        for shp_path in [BUILDINGS_SHP_PATH, RAIL_SHP_PATH, WATER_STATIC_SHP_PATH]:
            gdf = gpd.read_file(shp_path)
            exclusion_mask = np.logical_or(exclusion_mask, rasterize_shapefile(gdf, profile).astype(bool)) 

        print("  -> Adding cultural/sensitive site exclusions...")
        for shp_path in [WORSHIP_SHP_PATH, PLACES_SHP_PATH, POI_SHP_PATH]:
            try:
                gdf = gpd.read_file(shp_path)
                if not gdf.empty:
                    gdf_buffered = gdf.copy()
                    gdf_buffered['geometry'] = gdf_buffered.buffer(50)  # 50m exclusion zone
                    exclusion_mask = np.logical_or(exclusion_mask, rasterize_shapefile(gdf_buffered, profile).astype(bool))
                    print(f"    - Excluded {len(gdf)} {shp_path.split('/')[-1].replace('.shp', '').replace('_', ' ')} (50m buffer)")
            except Exception as e:
                print(f"    ⚠️ Could not process {shp_path}: {e}")

        # --- 2. Core Hydraulic Analysis ---
        hydraulic_maps = perform_hydraulic_analysis(DEM_PATH, profile)

        # --- 3. Generate Base Cost Maps ---
        print("  -> Generating Base Cost & Factor Maps...")
        base_maps = {}
        with rasterio.open(LULC_PATH) as lulc_src:
            lulc_aligned = np.zeros(target_shape, dtype=lulc_src.dtypes[0])
            reproject(source=rasterio.band(lulc_src, 1), destination=lulc_aligned, src_transform=lulc_src.transform, src_crs=lulc_src.crs, dst_transform=profile['transform'], dst_crs=profile['crs'], resampling=Resampling.nearest)
        base_maps['land_cost'] = np.full(target_shape, LULC_COSTS['default'], dtype=np.float32)
        for lulc_val, cost in LULC_COSTS.items():
            if lulc_val != 'default': base_maps['land_cost'][lulc_aligned == lulc_val] = cost
        
        # <<< ADAPTED >>> This 'engineering_cost' map is now CRITICAL.
        # It represents soil suitability. We will use it for both cost AND infiltration potential.
        soil_gdf = pd.concat([gpd.read_file(SOIL_1_SHP_PATH), gpd.read_file(SOIL_2_SHP_PATH)], ignore_index=True)
        for col in ['T_CLAY', 'T_BULK_DEN']: soil_gdf[f'{col}_norm'] = (soil_gdf[col] - soil_gdf[col].min()) / (soil_gdf[col].max() - soil_gdf[col].min())
        soil_gdf['drainage_cost'] = soil_gdf['DRAINAGE'].map(DRAINAGE_COST_MAPPING).fillna(DRAINAGE_COST_MAPPING['default'])
        soil_gdf['eng_cost_idx'] = (SOIL_COST_WEIGHTS['clay']*soil_gdf['T_CLAY_norm'] + SOIL_COST_WEIGHTS['bulk_density']*soil_gdf['T_BULK_DEN_norm'] + SOIL_COST_WEIGHTS['drainage']*soil_gdf['drainage_cost'])
        base_maps['engineering_cost'] = np.nan_to_num(rasterize_shapefile(soil_gdf, profile, value_col='eng_cost_idx'), nan=np.nanmedian(soil_gdf['eng_cost_idx']))
        
        # 'topographic_fit' (low-lying areas) is perfect for water collection.
        base_maps['topographic_fit'] = np.nanmax(dem) - dem

        # --- 4. Generate Intervention-Specific Suitability Maps ---
        atlas_paths = {}
        
        print("  -> 💧 Building Runoff Harvesting Pond Suitability Map...")
        pond_suitability = np.zeros(target_shape, dtype=np.float32)

        # Proximity to "places" (villages/farms) is a good proxy for water demand.
        community_value = np.zeros(target_shape, dtype=np.float32)
        try:
            places_gdf = gpd.read_file(PLACES_SHP_PATH)
            if not places_gdf.empty:
                places_raster = rasterize_shapefile(places_gdf, profile).astype(bool)
                dist_to_places = distance_transform_edt(~places_raster)
                community_value = np.exp(-dist_to_places / 200) # 200m influence
                print(f"    - Factoring in proximity to {len(places_gdf)} demand locations (POIs)")
        except Exception as e:
            print(f"    ⚠️ Could not incorporate places data for ponds: {e}")

        # <<< ADAPTED >>> This logic is almost identical, just re-framed.
        # We *want* high TWI (wetness) and high topographic_fit (low-lying) to capture water.
        pond_factors = {'twi': hydraulic_maps['twi'], 'topographic_fit': base_maps['topographic_fit'],
                       'community_value': community_value, 'land_cost': base_maps['land_cost'],
                       'engineering_cost': base_maps['engineering_cost']}
        pond_weights = POND_WEIGHTS.copy()
        pond_weights['community_value'] = 0.15
        pond_weights['land_cost'] = -0.15
        for name, weight in pond_weights.items():
            pond_suitability += normalize_map(pond_factors[name]) * weight

        pond_suitability[exclusion_mask] = -9999.0
        # <<< ADAPTED >>> New file name
        pond_path = f'{output_dir}/harvesting_pond_suitability.tif'
        profile.update(dtype=rasterio.float32, count=1, nodata=-9999.0)
        with rasterio.open(pond_path, 'w', **profile) as dst: dst.write(pond_suitability, 1)
        atlas_paths['pond_suitability_map'] = pond_path

        print("  -> 🏞️ Building Groundwater Recharge Suitability Map (formerly Levee)...")
        
        # <<< ADAPTED >>> This is the biggest logic change.
        # We replace "protection_potential" with "infiltration_suitability".
        
        # Factor 1: Infiltration Suitability.
        # We invert the 'engineering_cost' map. Low cost = good drainage (low clay, etc.) = high suitability.
        infiltration_suitability = 1.0 - normalize_map(base_maps['engineering_cost'])
        
        # Factor 2: Runoff Availability.
        # We use flow accumulation directly. More water flow = more water to capture for recharge.
        runoff_availability = normalize_map(hydraulic_maps['flow_acc'])

        recharge_suitability = np.zeros(target_shape, dtype=np.float32)
        recharge_factors = {
            'infiltration_suitability': infiltration_suitability, 
            'runoff_availability': runoff_availability, 
            'land_cost': base_maps['land_cost'], 
            'engineering_cost': base_maps['engineering_cost']
        }
        for name, weight in RECHARGE_WEIGHTS.items():
            recharge_suitability += normalize_map(recharge_factors[name]) * weight
        
        recharge_suitability[exclusion_mask] = -9999.0
        # <<< ADAPTED >>> New file name
        recharge_path = f'{output_dir}/recharge_structure_suitability.tif'
        with rasterio.open(recharge_path, 'w', **profile) as dst: dst.write(recharge_suitability, 1)
        atlas_paths['recharge_suitability_map'] = recharge_path
        
        print("  -> 🌿 Building Nature-Based Solutions (NbS) Suitability Map (formerly Bioswale)...")
        # <<< ADAPTED >>> This logic is perfect for NbS (e.g., swales, contour bunding).
        # We still want them near roads (access) and on gentle slopes.
        road_buffer_gdf = roads_gdf.copy()
        road_buffer_gdf['geometry'] = road_buffer_gdf.buffer(10)
        road_buffer_mask = rasterize_shapefile(road_buffer_gdf, profile).astype(bool)
        # Gentle slopes are good (high score for low slope).
        slope_suitability = normalize_map(1 / (hydraulic_maps['slope'] + 1e-6))
        # Proximity to existing drainage is good.
        drainage_buffer_gdf = water_gdf.copy()
        drainage_buffer_gdf['geometry'] = drainage_buffer_gdf.buffer(15)
        drainage_enhancement = rasterize_shapefile(drainage_buffer_gdf, profile)

        # Proximity to communities/farms is also good.
        community_enhancement = np.zeros(target_shape, dtype=np.float32)
        try:
            places_gdf = gpd.read_file(PLACES_SHP_PATH)
            if not places_gdf.empty:
                places_buffered = places_gdf.copy()
                places_buffered['geometry'] = places_buffered.buffer(30) # 30m benefit zone
                community_enhancement = rasterize_shapefile(places_buffered, profile).astype(np.float32)
                community_enhancement = gaussian_filter(community_enhancement, sigma=5)
                print(f"    - Enhanced NbS community access with {len(places_gdf)} place locations")
        except Exception as e:
            print(f"    ⚠️ Could not incorporate places data: {e}")

        nbs_suitability = np.zeros(target_shape, dtype=np.float32)
        nbs_factors = {'slope_suitability': slope_suitability, 'drainage_enhancement': drainage_enhancement,
                           'community_enhancement': community_enhancement, 'land_cost': base_maps['land_cost'],
                           'engineering_cost': base_maps['engineering_cost']}
        nbs_weights = NBS_WEIGHTS.copy()
        nbs_weights['community_enhancement'] = 0.15
        nbs_weights['land_cost'] = -0.10
        for name, weight in nbs_weights.items():
            nbs_suitability += normalize_map(nbs_factors[name]) * weight

        nbs_suitability[~road_buffer_mask] = -9999.0  # Must be near roads/access
        nbs_suitability[exclusion_mask] = -9999.0
        # <<< ADAPTED >>> New file name
        nbs_path = f'{output_dir}/nbs_suitability.tif'
        with rasterio.open(nbs_path, 'w', **profile) as dst: dst.write(nbs_suitability, 1)
        atlas_paths['nbs_suitability_map'] = nbs_path

        print("  -> ☀️ Identifying Solar Pump Opportunities (formerly Culverts)...")
        # <<< ADAPTED >>> New logic. We want to find where water *access* (channels)
        # intersects with water *demand* (population/farms).
        
        # Water Access (major flow paths)
        major_channels_mask = hydraulic_maps['flow_acc'] > np.percentile(hydraulic_maps['flow_acc'][hydraulic_maps['flow_acc']>0], 98)
        
        # Water Demand (proxy with population map)
        with rasterio.open(POPULATION_MAP_PATH) as src:
            pop_aligned = np.zeros(target_shape, dtype=src.dtypes[0]); reproject(source=rasterio.band(src, 1), destination=pop_aligned, src_transform=src.transform, src_crs=src.crs, dst_transform=profile['transform'], dst_crs=profile['crs'], resampling=Resampling.nearest)
        demand_mask = pop_aligned > np.percentile(pop_aligned[pop_aligned>0], 75) # High demand areas

        # Intersect access and demand
        intersection_mask = np.logical_and(major_channels_mask, demand_mask)

        # Also add intersections with POIs (villages, community centers)
        try:
            poi_gdf = gpd.read_file(POI_SHP_PATH)
            if not poi_gdf.empty:
                poi_raster = rasterize_shapefile(poi_gdf, profile).astype(bool)
                from scipy.ndimage import binary_dilation
                poi_influence = binary_dilation(poi_raster, iterations=15) # ~150m radius
                poi_intersection_mask = np.logical_and(major_channels_mask, poi_influence)
                intersection_mask = np.logical_or(intersection_mask, poi_intersection_mask)
                print(f"    - Added {len(poi_gdf)} POI locations as potential pump sites")
        except Exception as e:
            print(f"    ⚠️ Could not incorporate POI data for pumps: {e}")

        rows, cols = np.where(intersection_mask)
        xs, ys = rasterio.transform.xy(profile['transform'], rows, cols)
        points = [Point(x, y) for x, y in zip(xs, ys)]
        pump_gdf = gpd.GeoDataFrame(geometry=points, crs=profile['crs'])
        # <<< ADAPTED >>> New file name
        pump_path = f'{output_dir}/solar_pump_opportunities.shp'
        pump_gdf.to_file(pump_path)
        atlas_paths['pump_opportunities_map'] = pump_path
        
        print("  ✅ STRATEGIC WATER ATLAS GENERATION COMPLETE.")
        return atlas_paths, profile, hydraulic_maps

    except Exception as e:
        print(f"❌ FATAL ERROR in Atlas Generation: {e}")
        import traceback
        traceback.print_exc()
        return None, None, None

def generate_separate_atlas_images(atlas_paths, hydraulic_maps, dem_path, output_dir):
    """
    Generates four separate, high-quality images for the strategic atlas components.
    """
    # <<< ADAPTED >>> All titles and file names are updated.
    print("📊 Generating separate atlas report images...")
    try:
        with rasterio.open(dem_path) as src:
            dem = src.read(1)
            dem_profile = src.profile
        
        # --- Image 1: Pond Suitability ---
        with rasterio.open(atlas_paths['pond_suitability_map']) as src:
            data = src.read(1)
            masked_data = np.ma.masked_where(data == src.nodata, data)
        fig, ax = plt.subplots(figsize=(10, 10))
        ax.imshow(dem, cmap='gray', alpha=0.6)
        im = ax.imshow(masked_data, cmap='Blues', interpolation='nearest', alpha=0.8)
        ax.set_title("Runoff Harvesting Pond Suitability", fontsize=18, weight='bold')
        ax.set_xticks([]); ax.set_yticks([])
        fig.colorbar(im, ax=ax, shrink=0.7, label='Suitability Score')
        plt.tight_layout()
        png_path = f"{output_dir}/harvesting_pond_map.png"
        plt.savefig(png_path, dpi=200)
        plt.close(fig)
        print(f"  - ✅ Saved {png_path}")

        # --- Image 2: Recharge Suitability ---
        with rasterio.open(atlas_paths['recharge_suitability_map']) as src:
            data = src.read(1)
            masked_data = np.ma.masked_where(data == src.nodata, data)
        fig, ax = plt.subplots(figsize=(10, 10))
        ax.imshow(dem, cmap='gray', alpha=0.6)
        # <<< ADAPTED >>> Using a 'growth' colormap like Greens
        im = ax.imshow(masked_data, cmap='Greens', interpolation='nearest', alpha=0.8)
        ax.set_title("Groundwater Recharge Suitability", fontsize=18, weight='bold')
        ax.set_xticks([]); ax.set_yticks([])
        fig.colorbar(im, ax=ax, shrink=0.7, label='Suitability Score')
        plt.tight_layout()
        png_path = f"{output_dir}/recharge_suitability_map.png"
        plt.savefig(png_path, dpi=200)
        plt.close(fig)
        print(f"  - ✅ Saved {png_path}")

        # --- Image 3: NbS Suitability ---
        with rasterio.open(atlas_paths['nbs_suitability_map']) as src:
            data = src.read(1)
            plot_data = np.full_like(data, np.nan, dtype=np.float32)
            valid_mask = data != src.nodata
            if np.any(valid_mask):
                valid_values = data[valid_mask]
                data_min = np.min(valid_values)
                if data_min < 0:
                    plot_data[valid_mask] = valid_values - data_min
                else:
                    plot_data[valid_mask] = valid_values

        fig, ax = plt.subplots(figsize=(10, 10))
        ax.imshow(dem, cmap='gray', alpha=0.3)
        if np.any(~np.isnan(plot_data)):
            im = ax.imshow(plot_data, cmap='viridis', interpolation='nearest', alpha=1.0, vmin=0)
            ax.set_title("Nature-Based Solutions (NbS) Suitability", fontsize=18, weight='bold')
            fig.colorbar(im, ax=ax, shrink=0.7, label='Suitability Score')
        else:
            ax.set_title("NbS Suitability - No Valid Data", fontsize=18, weight='bold')
        ax.set_xticks([]); ax.set_yticks([])
        plt.tight_layout()
        png_path = f"{output_dir}/nbs_suitability_map.png"
        plt.savefig(png_path, dpi=200)
        plt.close(fig)
        print(f"  - ✅ Saved {png_path}")

        # --- Image 4: Pump Opportunities ---
        flow_acc_clean = np.copy(hydraulic_maps['flow_acc'])
        flow_acc_clean = np.nan_to_num(flow_acc_clean, nan=0.0, posinf=0.0, neginf=0.0)
        flow_acc_log = np.log1p(np.maximum(flow_acc_clean, 0))

        culvert_gdf = gpd.read_file(atlas_paths['pump_opportunities_map'])
        if len(culvert_gdf) > 200:
            sample_indices = np.random.choice(len(culvert_gdf), size=200, replace=False)
            culvert_gdf_sample = culvert_gdf.iloc[sample_indices]
        else:
            culvert_gdf_sample = culvert_gdf

        fig, ax = plt.subplots(figsize=(10, 10))
        ax.imshow(dem, cmap='gray', alpha=0.4)
        im = ax.imshow(flow_acc_log, cmap='viridis', interpolation='nearest', alpha=0.7)

        if len(culvert_gdf_sample) > 0:
            points_x = culvert_gdf_sample.geometry.x.values
            points_y = culvert_gdf_sample.geometry.y.values
            pixel_coords = []
            for x, y in zip(points_x, points_y):
                pixel_x, pixel_y = ~dem_profile['transform'] * (x, y)
                pixel_coords.append((pixel_x, pixel_y))
            pixel_x_coords, pixel_y_coords = zip(*pixel_coords)
            
            # <<< ADAPTED >>> Updated marker and label
            ax.scatter(pixel_x_coords, pixel_y_coords, marker='P', color='red', s=50,
                      label=f'Solar Pump Opportunities ({len(culvert_gdf_sample)} shown)', zorder=10)

        ax.set_title("Water Access Points (Pump Opportunities)", fontsize=18, weight='bold')
        ax.set_xticks([]); ax.set_yticks([])
        ax.legend(loc='upper right', fontsize=10)
        fig.colorbar(im, ax=ax, shrink=0.7, label='Log(Flow Accumulation)')
        plt.tight_layout()
        png_path = f"{output_dir}/pump_opportunities_map.png"
        plt.savefig(png_path, dpi=200)
        plt.close(fig)
        print(f"  - ✅ Saved {png_path}")

    except Exception as e:
        print(f"⚠️ Warning: Could not generate atlas images. Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("=" * 80)
    print("🌊 LAUNCHING STAGE 1: WATER RESOURCE DIAGNOSTICS (v1.0 IWMI Adaptation)")
    print("=" * 80)
    
    # <<< ADAPTED >>> Changed default dir name for Gorakhpur
    output_dir = os.environ.get('GORAKHPUR_OUTPUT_DIR', f"Outputs/Water_Run_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    os.makedirs(output_dir, exist_ok=True)
    print(f"📁 Using output directory: {output_dir}")
    
    log_file = open(f"{output_dir}/stage1_diagnostics.log", 'w')
    original_stdout, original_stderr = sys.stdout, sys.stderr
    sys.stdout = Tee(original_stdout, log_file)
    sys.stderr = Tee(original_stderr, log_file)
    
    try:
        atlas_paths, profile, hydraulic_maps = run_strategic_atlas_generation(output_dir)
        if atlas_paths:
            # <<< ADAPTED >>> Updated report titles
            print("\n" + "="*60 + "\n🏆 WATER DIAGNOSTICS REPORT (v1.0) 🏆\n" + "="*60)
            for name, path in atlas_paths.items():
                print(f"  - Output Layer '{name}': '{path}'")
            
            generate_separate_atlas_images(atlas_paths, hydraulic_maps, DEM_PATH, output_dir)
            
            print("\n" + "="*60)
            print("💾 Preparing strategic bridge file for Stage 2...")
            diagnostics_report = {
                'timestamp': datetime.now().isoformat(),
                'city': 'Gorakhpur', # Now using GKP data
                'analysis_type': 'Strategic Water Atlas v1.0 (IWMI Adaptation)',
                'atlas_paths': atlas_paths,
                'raster_profile': {
                    'crs': str(profile['crs']),
                    'transform': list(profile['transform']),
                    'width': profile['width'],
                    'height': profile['height']
                }
            }
            report_path = f"{output_dir}/diagnostics_report.json"
            with open(report_path, 'w') as f:
                json.dump(diagnostics_report, f, indent=4)
            print(f"  - ✅ Saved strategic diagnostics to '{report_path}'")
            print("="*60)
        else:
            print("\n" + "="*60 + "\n❌ ANALYSIS FAILED: Could not generate the strategic atlas.\n" + "="*60)
            
    finally:
        sys.stdout, sys.stderr = original_stdout, original_stderr
        if 'log_file' in locals() and not log_file.closed:
            log_file.close()