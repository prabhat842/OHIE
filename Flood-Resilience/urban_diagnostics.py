# ==============================================================================
# Project: Singapore Urban Resilience AI
# FILE NAME: urban_diagnostics.py
# VERSION: 3.4 (Robust Plotting & Numerics)
# PURPOSE: To perform a multi-criteria GIS analysis that generates a strategic
#          atlas of intervention opportunities. This version includes robust
#          NaN handling in hydraulic analysis and generates separate report images.
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

# --- Configuration (MODIFIED FOR SINGAPORE DATA) ---
FLOOD_MAP_PATH = "SGP_Data/Floods/flood_sgp_utm48.tif"
POPULATION_MAP_PATH = "SGP_Data/Population/population_sgp.tif"
DEM_PATH = "SGP_Data/DEM/DEM_SGP_UTM48.tif"
# IMPORTANT: You must create this rasterized LULC file from your lulc.shp
LULC_PATH = "SGP_Data/LULC/lulc_rasterized.tif"
BUILDINGS_SHP_PATH = "SGP_Data/Buildings/buildings.shp"
ROADS_SHP_PATH = "SGP_Data/Roads/roads.shp"
RAIL_SHP_PATH = "SGP_Data/Railways/railways.shp"
WATER_SHP_PATH = "SGP_Data/Water_ways/waterways.shp"
WATER_STATIC_SHP_PATH = "SGP_Data/Water_Static/static_water.shp"
SOIL_1_SHP_PATH = "SGP_Data/Soil_Data/Soil_FL_LP_RG_Rocks.shp"
SOIL_2_SHP_PATH = "SGP_Data/Soil_Data/Soil_LX_AC.shp"
# Using POIs as the general 'places' layer
PLACES_SHP_PATH = "SGP_Data/Points_of_Interest/pois.shp"
POI_SHP_PATH = "SGP_Data/Points_of_Interest/pois.shp"
WORSHIP_SHP_PATH = "SGP_Data/Place_of_worship/pofw.shp"
# Using the main Singapore boundary file for administrative zones
SUBDISTRICTS_SHP_PATH = "SGP_Data/Boundary/SG_Bounds_Fixed.shp"

POND_WEIGHTS = {'twi': 0.40, 'topographic_fit': 0.30, 'land_cost': -0.20, 'engineering_cost': -0.10}
LEVEE_WEIGHTS = {'protection_potential': 0.50, 'proximity_to_channel': 0.20, 'land_cost': -0.20, 'engineering_cost': -0.10}
BIOSWALE_WEIGHTS = {'slope_suitability': 0.5, 'drainage_enhancement': 0.3, 'land_cost': -0.15, 'engineering_cost': -0.05}

# CRITICAL: YOU MUST UPDATE THESE KEYS (10, 12, 8) with the real pixel values
# from your rasterized Singapore LULC map. Use inspector.py to find them.
LULC_COSTS = {
    10: 10.0,       # Example: Residential
    12: 0.5,        # Example: Park
    8: 20.0,        # Example: Commercial
    'default': 1.0
}
DRAINAGE_COST_MAPPING = {1.0: 0.1, 2.0: 0.4, 3.0: 0.7, 4.0: 1.0, 'default': 0.5}
SOIL_COST_WEIGHTS = {'clay': 0.5, 'bulk_density': 0.3, 'drainage': 0.2}

# --- Helper Functions ---

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
    """Performs core hydrological analysis, now with robust NaN/inf handling for TWI."""
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
    print("     - Calculating flow accumulation...")
    flow_acc = grid.accumulation(fdir=flow_dir)
    print("     - Calculating slope and TWI...")
    slope = grid.cell_slopes(dem=flooded_dem, fdir=flow_dir)

    flow_acc_data = np.array(flow_acc)
    slope_data = np.array(slope)

    # Calculate TWI with a very small number to prevent division by zero
    tan_slope = np.tan(slope_data) + 1e-7
    catchment_area = (flow_acc_data + 1) * profile['transform'].a * abs(profile['transform'].e)
    twi = np.log(catchment_area / tan_slope)

    # <<< DEFINITIVE FIX: Clean up any resulting inf or nan values from the log calculation
    twi[np.isinf(twi)] = np.nan # Replace infinities with NaN
    twi_median = np.nanmedian(twi) # Calculate median of valid TWI values
    twi[np.isnan(twi)] = twi_median # Fill NaN values with the median

    print("  -> ✅ Hydraulic Pre-Analysis Complete.")
    return {'flow_acc': flow_acc_data, 'twi': twi, 'slope': slope_data}

def run_strategic_atlas_generation(output_dir):
    """Main function to generate the multi-layered strategic atlas."""
    print("\n🔬 Starting Singapore Strategic Atlas Generation (v3.4)...")
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

        print("  -> Generating Exclusion Mask...")
        exclusion_mask = np.zeros(target_shape, dtype=bool)

        # Core infrastructure exclusions (high priority)
        # Core infrastructure exclusions (high priority)
        # Core infrastructure exclusions (high priority)
        for shp_path in [BUILDINGS_SHP_PATH, # ROADS_SHP_PATH, <-- We comment this out
                        RAIL_SHP_PATH, WATER_STATIC_SHP_PATH]:
            gdf = gpd.read_file(shp_path)
            exclusion_mask = np.logical_or(exclusion_mask, rasterize_shapefile(gdf, profile).astype(bool)) 

        # Cultural/sensitive site exclusions (highest priority)
        print("  -> Adding cultural/sensitive site exclusions...")
        for shp_path in [WORSHIP_SHP_PATH, PLACES_SHP_PATH, POI_SHP_PATH]:
            try:
                gdf = gpd.read_file(shp_path)
                # Create 50m buffer around sensitive sites for cultural preservation
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
        soil_gdf = pd.concat([gpd.read_file(SOIL_1_SHP_PATH), gpd.read_file(SOIL_2_SHP_PATH)], ignore_index=True)
        for col in ['T_CLAY', 'T_BULK_DEN']: soil_gdf[f'{col}_norm'] = (soil_gdf[col] - soil_gdf[col].min()) / (soil_gdf[col].max() - soil_gdf[col].min())
        soil_gdf['drainage_cost'] = soil_gdf['DRAINAGE'].map(DRAINAGE_COST_MAPPING).fillna(DRAINAGE_COST_MAPPING['default'])
        soil_gdf['eng_cost_idx'] = (SOIL_COST_WEIGHTS['clay']*soil_gdf['T_CLAY_norm'] + SOIL_COST_WEIGHTS['bulk_density']*soil_gdf['T_BULK_DEN_norm'] + SOIL_COST_WEIGHTS['drainage']*soil_gdf['drainage_cost'])
        base_maps['engineering_cost'] = np.nan_to_num(rasterize_shapefile(soil_gdf, profile, value_col='eng_cost_idx'), nan=np.nanmedian(soil_gdf['eng_cost_idx']))
        base_maps['topographic_fit'] = np.nanmax(dem) - dem

        # --- 4. Generate Intervention-Specific Suitability Maps ---
        atlas_paths = {}
        
        print("  -> Building Pond Suitability Map...")
        pond_suitability = np.zeros(target_shape, dtype=np.float32)

        # Enhanced pond placement with community consideration
        community_value = np.zeros(target_shape, dtype=np.float32)
        try:
            places_gdf = gpd.read_file(PLACES_SHP_PATH)
            if not places_gdf.empty:
                # Create distance-based community value (closer to places = higher value)
                places_raster = rasterize_shapefile(places_gdf, profile).astype(bool)
                dist_to_places = distance_transform_edt(~places_raster)
                # Convert distance to value (exponential decay)
                community_value = np.exp(-dist_to_places / 200)  # 200m influence radius
                print(f"    - Enhanced community value with {len(places_gdf)} place locations")
        except Exception as e:
            print(f"    ⚠️ Could not incorporate places data for ponds: {e}")

        pond_factors = {'twi': hydraulic_maps['twi'], 'topographic_fit': base_maps['topographic_fit'],
                       'community_value': community_value, 'land_cost': base_maps['land_cost'],
                       'engineering_cost': base_maps['engineering_cost']}

        # Update weights to include community value
        pond_weights = POND_WEIGHTS.copy()
        pond_weights['community_value'] = 0.15  # Add community benefit factor
        pond_weights['land_cost'] = -0.15  # Adjust land cost weight

        for name, weight in pond_weights.items():
            pond_suitability += normalize_map(pond_factors[name]) * weight

        pond_suitability[exclusion_mask] = -9999.0
        pond_path = f'{output_dir}/pond_suitability.tif'
        profile.update(dtype=rasterio.float32, count=1, nodata=-9999.0)
        with rasterio.open(pond_path, 'w', **profile) as dst: dst.write(pond_suitability, 1)
        atlas_paths['pond_suitability_map'] = pond_path

        print("  -> Building Levee/Wall Suitability Map...")
        with rasterio.open(FLOOD_MAP_PATH) as src:
            flood_aligned = np.zeros(target_shape, dtype=src.dtypes[0]); reproject(source=rasterio.band(src, 1), destination=flood_aligned, src_transform=src.transform, src_crs=src.crs, dst_transform=profile['transform'], dst_crs=profile['crs'], resampling=Resampling.nearest)
        with rasterio.open(POPULATION_MAP_PATH) as src:
            pop_aligned = np.zeros(target_shape, dtype=src.dtypes[0]); reproject(source=rasterio.band(src, 1), destination=pop_aligned, src_transform=src.transform, src_crs=src.crs, dst_transform=profile['transform'], dst_crs=profile['crs'], resampling=Resampling.nearest)

        # Enhanced risk assessment with POI consideration
        high_risk_zone = np.logical_or(flood_aligned > 0.5, pop_aligned > np.percentile(pop_aligned[pop_aligned>0], 90))

        # Add POI proximity to risk zones (critical infrastructure/population centers)
        try:
            poi_gdf = gpd.read_file(POI_SHP_PATH)
            if not poi_gdf.empty:
                poi_buffered = poi_gdf.copy()
                poi_buffered['geometry'] = poi_buffered.buffer(100)  # 100m influence zone around POIs
                poi_raster = rasterize_shapefile(poi_buffered, profile).astype(bool)
                high_risk_zone = np.logical_or(high_risk_zone, poi_raster)
                print(f"    - Enhanced risk zones with {len(poi_gdf)} POI locations (100m buffer)")
        except Exception as e:
            print(f"    ⚠️ Could not incorporate POI data: {e}")

        dist_to_risk = distance_transform_edt(~high_risk_zone)
        protection_potential = np.max(dist_to_risk) - dist_to_risk
        dist_to_channel = distance_transform_edt(hydraulic_maps['flow_acc'] < np.percentile(hydraulic_maps['flow_acc'][hydraulic_maps['flow_acc']>0], 95))
        proximity_to_channel = np.max(dist_to_channel) - dist_to_channel
        levee_suitability = np.zeros(target_shape, dtype=np.float32)
        levee_factors = {'protection_potential': protection_potential, 'proximity_to_channel': proximity_to_channel, 'land_cost': base_maps['land_cost'], 'engineering_cost': base_maps['engineering_cost']}
        for name, weight in LEVEE_WEIGHTS.items():
            levee_suitability += normalize_map(levee_factors[name]) * weight
        levee_suitability[exclusion_mask] = -9999.0
        levee_path = f'{output_dir}/levee_suitability.tif'
        with rasterio.open(levee_path, 'w', **profile) as dst: dst.write(levee_suitability, 1)
        atlas_paths['levee_suitability_map'] = levee_path
        
        print("  -> 🌿 Building Bioswale Suitability Map...")
        road_buffer_gdf = roads_gdf.copy()
        road_buffer_gdf['geometry'] = road_buffer_gdf.buffer(10)
        road_buffer_mask = rasterize_shapefile(road_buffer_gdf, profile).astype(bool)
        slope_suitability = normalize_map(1 / (hydraulic_maps['slope'] + 1e-6))
        drainage_buffer_gdf = water_gdf.copy()
        drainage_buffer_gdf['geometry'] = drainage_buffer_gdf.buffer(15)
        drainage_enhancement = rasterize_shapefile(drainage_buffer_gdf, profile)

        # Enhanced bioswale placement with POI consideration
        community_enhancement = np.zeros(target_shape, dtype=np.float32)
        try:
            places_gdf = gpd.read_file(PLACES_SHP_PATH)
            if not places_gdf.empty:
                places_buffered = places_gdf.copy()
                places_buffered['geometry'] = places_buffered.buffer(30)  # 30m community benefit zone
                community_enhancement = rasterize_shapefile(places_buffered, profile).astype(np.float32)
                community_enhancement = gaussian_filter(community_enhancement, sigma=5)  # Smooth influence
                print(f"    - Enhanced community access with {len(places_gdf)} place locations (30m buffer)")
        except Exception as e:
            print(f"    ⚠️ Could not incorporate places data: {e}")

        bioswale_suitability = np.zeros(target_shape, dtype=np.float32)
        bioswale_factors = {'slope_suitability': slope_suitability, 'drainage_enhancement': drainage_enhancement,
                           'community_enhancement': community_enhancement, 'land_cost': base_maps['land_cost'],
                           'engineering_cost': base_maps['engineering_cost']}

        # Update weights to include community enhancement
        bioswale_weights = BIOSWALE_WEIGHTS.copy()
        bioswale_weights['community_enhancement'] = 0.15  # Add community benefit factor
        bioswale_weights['land_cost'] = -0.10  # Reduce land cost weight to balance

        for name, weight in bioswale_weights.items():
            bioswale_suitability += normalize_map(bioswale_factors[name]) * weight

        bioswale_suitability[~road_buffer_mask] = -9999.0  # Must be near roads
        bioswale_suitability[exclusion_mask] = -9999.0
        bioswale_path = f'{output_dir}/bioswale_suitability.tif'
        with rasterio.open(bioswale_path, 'w', **profile) as dst: dst.write(bioswale_suitability, 1)
        atlas_paths['bioswale_suitability_map'] = bioswale_path

        print("  -> 🚧 Identifying Culvert Upgrade Opportunities...")
        major_channels_mask = hydraulic_maps['flow_acc'] > np.percentile(hydraulic_maps['flow_acc'][hydraulic_maps['flow_acc']>0], 98)
        roads_raster = rasterize_shapefile(roads_gdf, profile).astype(bool)
        intersection_mask = np.logical_and(major_channels_mask, roads_raster)

        # Enhanced culvert prioritization with POI consideration
        try:
            poi_gdf = gpd.read_file(POI_SHP_PATH)
            if not poi_gdf.empty:
                poi_raster = rasterize_shapefile(poi_gdf, profile).astype(bool)
                # Dilate POI influence to 150m radius for critical infrastructure protection
                from scipy.ndimage import binary_dilation
                poi_influence = binary_dilation(poi_raster, iterations=15)  # ~150m at 10m resolution
                intersection_mask = np.logical_or(intersection_mask,
                    np.logical_and(major_channels_mask, poi_influence))
                print(f"    - Enhanced culvert prioritization with {len(poi_gdf)} POI locations (150m influence)")
        except Exception as e:
            print(f"    ⚠️ Could not incorporate POI data for culverts: {e}")

        rows, cols = np.where(intersection_mask)
        xs, ys = rasterio.transform.xy(profile['transform'], rows, cols)
        points = [Point(x, y) for x, y in zip(xs, ys)]
        culvert_gdf = gpd.GeoDataFrame(geometry=points, crs=profile['crs'])
        culvert_path = f'{output_dir}/culvert_opportunities.shp'
        culvert_gdf.to_file(culvert_path)
        atlas_paths['culvert_opportunities_map'] = culvert_path
        
        print("  ✅ STRATEGIC ATLAS GENERATION COMPLETE.")
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
        ax.set_title("Pond Suitability (Retention)", fontsize=18, weight='bold')
        ax.set_xticks([]); ax.set_yticks([])
        fig.colorbar(im, ax=ax, shrink=0.7, label='Suitability Score')
        plt.tight_layout()
        png_path = f"{output_dir}/pond_suitability_map.png"
        plt.savefig(png_path, dpi=200)
        plt.close(fig)
        print(f"  - ✅ Saved {png_path}")

        # --- Image 2: Levee Suitability ---
        with rasterio.open(atlas_paths['levee_suitability_map']) as src:
            data = src.read(1)
            masked_data = np.ma.masked_where(data == src.nodata, data)
        fig, ax = plt.subplots(figsize=(10, 10))
        ax.imshow(dem, cmap='gray', alpha=0.6)
        im = ax.imshow(masked_data, cmap='Reds', interpolation='nearest', alpha=0.8)
        ax.set_title("Levee/Wall Suitability (Protection)", fontsize=18, weight='bold')
        ax.set_xticks([]); ax.set_yticks([])
        fig.colorbar(im, ax=ax, shrink=0.7, label='Suitability Score')
        plt.tight_layout()
        png_path = f"{output_dir}/levee_suitability_map.png"
        plt.savefig(png_path, dpi=200)
        plt.close(fig)
        print(f"  - ✅ Saved {png_path}")

        # --- Image 3: Bioswale Suitability ---
        with rasterio.open(atlas_paths['bioswale_suitability_map']) as src:
            data = src.read(1)
            # Create visualization data with proper handling of nodata
            plot_data = np.full_like(data, np.nan, dtype=np.float32)
            valid_mask = data != src.nodata
            if np.any(valid_mask):
                valid_values = data[valid_mask]
                # Shift to ensure all values are positive
                data_min = np.min(valid_values)
                if data_min < 0:
                    plot_data[valid_mask] = valid_values - data_min
                else:
                    plot_data[valid_mask] = valid_values

        fig, ax = plt.subplots(figsize=(10, 10))
        # Show DEM in background
        ax.imshow(dem, cmap='gray', alpha=0.3)
        # Overlay bioswale data - use higher contrast colormap and opacity
        if np.any(~np.isnan(plot_data)):
            im = ax.imshow(plot_data, cmap='viridis', interpolation='nearest', alpha=1.0, vmin=0)
            ax.set_title("Bioswale Suitability (Drainage)", fontsize=18, weight='bold')
            fig.colorbar(im, ax=ax, shrink=0.7, label='Suitability Score')
        else:
            ax.set_title("Bioswale Suitability (Drainage) - No Valid Data", fontsize=18, weight='bold')
        ax.set_xticks([]); ax.set_yticks([])
        plt.tight_layout()
        png_path = f"{output_dir}/bioswale_suitability_map.png"
        plt.savefig(png_path, dpi=200)
        plt.close(fig)
        print(f"  - ✅ Saved {png_path}")

        # --- Image 4: Culvert Opportunities ---
        # Handle NaN/inf values in flow accumulation
        flow_acc_clean = np.copy(hydraulic_maps['flow_acc'])
        flow_acc_clean = np.nan_to_num(flow_acc_clean, nan=0.0, posinf=0.0, neginf=0.0)
        flow_acc_log = np.log1p(np.maximum(flow_acc_clean, 0))  # Ensure non-negative

        culvert_gdf = gpd.read_file(atlas_paths['culvert_opportunities_map'])
        # Sample representative points to avoid clutter (show max 200)
        if len(culvert_gdf) > 200:
            # Random sample for visualization
            sample_indices = np.random.choice(len(culvert_gdf), size=200, replace=False)
            culvert_gdf_sample = culvert_gdf.iloc[sample_indices]
        else:
            culvert_gdf_sample = culvert_gdf

        fig, ax = plt.subplots(figsize=(10, 10))
        ax.imshow(dem, cmap='gray', alpha=0.4)
        im = ax.imshow(flow_acc_log, cmap='viridis', interpolation='nearest', alpha=0.7)

        # Transform points to pixel coordinates for proper plotting
        if len(culvert_gdf_sample) > 0:
            # Get coordinates
            points_x = culvert_gdf_sample.geometry.x.values
            points_y = culvert_gdf_sample.geometry.y.values

            # Transform to pixel coordinates
            pixel_coords = []
            for x, y in zip(points_x, points_y):
                pixel_x, pixel_y = ~dem_profile['transform'] * (x, y)
                pixel_coords.append((pixel_x, pixel_y))

            pixel_x_coords, pixel_y_coords = zip(*pixel_coords)

            # Plot as scatter points in pixel coordinates
            ax.scatter(pixel_x_coords, pixel_y_coords, marker='X', color='red', s=50,
                      label=f'Priority Culverts ({len(culvert_gdf_sample)} shown)', zorder=10)

        ax.set_title("Culvert Opportunities (Bottlenecks)", fontsize=18, weight='bold')
        ax.set_xticks([]); ax.set_yticks([])
        ax.legend(loc='upper right', fontsize=10)
        fig.colorbar(im, ax=ax, shrink=0.7, label='Log(Flow Accumulation)')
        plt.tight_layout()
        png_path = f"{output_dir}/culvert_opportunities_map.png"
        plt.savefig(png_path, dpi=200)
        plt.close(fig)
        print(f"  - ✅ Saved {png_path}")

    except Exception as e:
        print(f"⚠️ Warning: Could not generate atlas images. Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("=" * 80)
    print("🌊 LAUNCHING STAGE 1: URBAN DIAGNOSTICS ENGINE (v3.4 - Robust Plotting)")
    print("=" * 80)
    
    output_dir = os.environ.get('GORAKHPUR_OUTPUT_DIR', f"Outputs/Run_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    os.makedirs(output_dir, exist_ok=True)
    print(f"📁 Using output directory: {output_dir}")
    
    log_file = open(f"{output_dir}/stage1_diagnostics.log", 'w')
    original_stdout, original_stderr = sys.stdout, sys.stderr
    sys.stdout = Tee(original_stdout, log_file)
    sys.stderr = Tee(original_stderr, log_file)
    
    try:
        atlas_paths, profile, hydraulic_maps = run_strategic_atlas_generation(output_dir)
        if atlas_paths:
            print("\n" + "="*60 + "\n🏆 DIAGNOSTICS REPORT (v3.4) 🏆\n" + "="*60)
            for name, path in atlas_paths.items():
                print(f"  - Output Layer '{name}': '{path}'")
            
            generate_separate_atlas_images(atlas_paths, hydraulic_maps, DEM_PATH, output_dir)
            
            print("\n" + "="*60)
            print("🌉 Preparing strategic bridge file for Stage 2...")
            diagnostics_report = {
                'timestamp': datetime.now().isoformat(),
                'city': 'Singapore',
                'analysis_type': 'Strategic Atlas v3.4 (Drainage-Informed)',
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