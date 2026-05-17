# ==============================================================================
# Project: Culturiq AI-Driven Infrastructure
# FILE NAME: alignment_diagnostics.py
# VERSION: 1.0 (Adapted from urban_diagnostics.py v3.4)
# PURPOSE: To perform a multi-criteria GIS analysis that generates a strategic
#          "Cost Atlas" for linear infrastructure alignment planning.
# ==============================================================================

import rasterio
from rasterio.mask import mask
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
from scipy.ndimage import gaussian_filter

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

# --- Configuration (MTHL Mumbai Data) ---
# <<< MODIFIED >>> Syncing paths to your prepared UTM43 data
DATA_PREFIX = "Data/UTM43_Data_Mumbai/"
DEM_PATH = DATA_PREFIX + "topobathy_utm43.tif"  # Combined TopoBathy
LULC_PATH = DATA_PREFIX + "LULC_UTM43.tif"  # Vegetation/Clearing cost
FLOOD_PATH = DATA_PREFIX + "Mumbai_Flood_UTM43.tif"  # Enhanced flood risk data
POPULATION_PATH = DATA_PREFIX + "Population_UTM43.tif"  # Social impact data
BUILDINGS_SHP_PATH = DATA_PREFIX + "Buildings_UTM43.shp"
ROADS_SHP_PATH = DATA_PREFIX + "Roads_UTM43.shp"
RAIL_SHP_PATH = DATA_PREFIX + "Rails_UTM43.shp"
WATER_SHP_PATH = DATA_PREFIX + "Waterways_UTM43.shp"
WATER_STATIC_SHP_PATH = DATA_PREFIX + "Permanent_Water_UTM43.shp"
# <<< NEW >>> MTHL-specific exclusions and constraints
FLAMINGO_SHP_PATH = DATA_PREFIX + "Flamingo_UTM43.shp"
LANDUSE_SHP_PATH = DATA_PREFIX + "Landuse_UTM43.shp"
SHIPPING_ROUTES_PATH = DATA_PREFIX + "shipping_routes_utm43.shp"
# <<< MTHL SIMPLIFICATION >>> Using simplified/placeholder soil data
SOIL_1_SHP_PATH = DATA_PREFIX + "Soil_UTM43.shp"
SOIL_2_SHP_PATH = None 

# <<< MODIFIED >>> LULC map now represents "clearing cost" (Mangrove cost added)
LULC_COSTS = {
    # CRITICAL: Adjust the value '11' to match the pixel value for Mangroves in your LULC_UTM43.tif
    4: 500.0,       # Mangroves (Extreme Cost)
    7: 20.0,         # Commercial/Industrial (Very high cost)
    5: 0.5,          # Park/Grassland (Low cost)
    2: 25.0,         # Forest (High Cost)
    'default': 1.0   # Default/Barren (Low cost)
}

# <<< NEW >>> Enhanced flood risk mapping
FLOOD_RISK_MULTIPLIER = 2.0  # How much extra weight to give to actual flood data
POPULATION_COST_MULTIPLIER = 0.5  # Scale factor for population impact
ROAD_BUFFER_DISTANCE = 100  # Meters around roads that get bonuses
ROAD_BONUS_MULTIPLIER = 0.8  # Cost reduction factor near roads
SOIL_COST_MODIFIERS = {
    'clay': 1.5,
    'sandy': 0.8,
    'loamy': 1.0,
    'rocky': 2.0,     # High cost for drilling/foundations
    'default': 1.0
}

# <<< MODIFIED >>> CROP_BOUNDS is now set to None as data is pre-clipped.
CROP_BOUNDS = None

# --- Helper Functions (Unaltered) ---

def normalize_map(data):
    """Normalizes a raster map to a 0-1 scale, handling NaN values."""
    data_masked = np.ma.masked_invalid(data)
    min_val, max_val = data_masked.min(), data_masked.max()
    if max_val > min_val:
        normalized = (data_masked - min_val) / (max_val - min_val)
        return normalized.filled(0)
    return np.zeros_like(data)

def crop_raster_to_bounds(raster_path, bounds, target_shape=None, resampling=Resampling.nearest):
    """Crops a raster to the specified bounds and returns the cropped data and updated profile."""
    with rasterio.open(raster_path) as src:
        # Create a polygon from bounds
        from shapely.geometry import box
        bbox = box(bounds['left'], bounds['bottom'], bounds['right'], bounds['top'])
        gdf_bbox = gpd.GeoDataFrame({'geometry': [bbox]}, crs=src.crs)

        # Crop the raster
        cropped_data, cropped_transform = mask(src, gdf_bbox.geometry, crop=True, nodata=src.nodata)
        cropped_data = cropped_data[0]  # Remove single band dimension

        # Update profile
        cropped_profile = src.profile.copy()
        cropped_profile.update({
            'height': cropped_data.shape[0],
            'width': cropped_data.shape[1],
            'transform': cropped_transform
        })

        return cropped_data, cropped_profile

def crop_shapefile_to_bounds(shp_path, bounds):
    """Crops a shapefile to the specified bounds."""
    gdf = gpd.read_file(shp_path)
    if gdf.crs is None:
        gdf.crs = "EPSG:32644"

    from shapely.geometry import box
    bbox = box(bounds['left'], bounds['bottom'], bounds['right'], bounds['top'])
    
    cropped_gdf = gdf[gdf.geometry.intersects(bbox)].copy()
    cropped_gdf = gpd.clip(cropped_gdf, bbox)

    return cropped_gdf

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
    """Performs core hydrological analysis."""
    print("  -> 🌊 Starting Hydraulic Pre-Analysis (for Slope & Flow Accumulation)...")
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
    print("     - Calculating flow accumulation (Hydrology Risk)...")
    flow_acc = grid.accumulation(fdir=flow_dir)
    print("     - Calculating slope (Earthworks Cost)...")
    slope = grid.cell_slopes(dem=flooded_dem, fdir=flow_dir)

    flow_acc_data = np.array(flow_acc)
    slope_data = np.array(slope)
    
    flow_acc_data[np.isinf(flow_acc_data)] = np.nan
    flow_acc_data = np.nan_to_num(flow_acc_data, nan=0.0)
    slope_data[np.isinf(slope_data)] = np.nan
    slope_data = np.nan_to_num(slope_data, nan=0.0)

    print("  -> ✅ Hydraulic Pre-Analysis Complete.")
    return {'flow_acc': flow_acc_data, 'slope': slope_data, 'dem': dem_data} # Return dem_data for depth cost

def run_strategic_atlas_generation(output_dir):
    """Main function to generate the multi-layered strategic "Cost Atlas"."""
    print("\n🔬 Starting Alignment Cost Atlas Generation (v1.0)...")
    try:
        # --- 1. Initial Setup & Data Loading ---
        print("  -> Loading base DEM (TopoBathy) and profile...")

        # Load data directly as CROP_BOUNDS is None (data is pre-clipped)
        with rasterio.open(DEM_PATH) as dem_src:
            dem = dem_src.read(1).astype(np.float32)
            profile = dem_src.profile
            if dem_src.nodata is not None:
                dem[dem == dem_src.nodata] = np.nan
            dem = np.nan_to_num(dem, nan=np.nanmean(dem)) # Fill NaNs for PySHEDS

        target_shape = (profile['height'], profile['width'])

        print("  -> Generating Exclusion Atlas (No-Go Zones)...")
        exclusion_mask = np.zeros(target_shape, dtype=np.uint8)

        # Exclusion GDFs (using pre-clipped names)
        exclusion_gdfs = [gpd.read_file(BUILDINGS_SHP_PATH),
                        gpd.read_file(RAIL_SHP_PATH),
                        gpd.read_file(WATER_STATIC_SHP_PATH),
                        gpd.read_file(FLAMINGO_SHP_PATH), # <<< NEW EXCLUSION >>> Flamingo Sanctuary
                        gpd.read_file(WATER_SHP_PATH), # Waterways
                        gpd.read_file(SHIPPING_ROUTES_PATH)] # <<< CRITICAL >>> Shipping Channels

        # <<< NEW EXCLUSION >>> Filter Landuse for BARC/Port areas
        try:
            landuse_gdf = gpd.read_file(LANDUSE_SHP_PATH)
            # Filter example: Using OSM IDs for Sewri Dockyard (625740777) and Trombay (430072319)
            # You must update these IDs based on your specific Landuse data.
            # Using common tags for high-security/port zones:
            security_zones = landuse_gdf[landuse_gdf['fclass'].isin(['military', 'port', 'dockyard', 'power_station'])]
            exclusion_gdfs.append(security_zones)
            print(f"     - Added {len(security_zones)} security/port areas to exclusion.")
        except Exception as e:
            print(f"     - Warning: Failed to process Landuse exclusions: {e}")


        for gdf in exclusion_gdfs:
            exclusion_mask = np.logical_or(exclusion_mask, rasterize_shapefile(gdf, profile))

        atlas_paths = {}
        exclusion_path = f'{output_dir}/exclusion_atlas.tif'
        profile.update(dtype=rasterio.uint8, count=1, nodata=0)
        with rasterio.open(exclusion_path, 'w', **profile) as dst:
            dst.write(exclusion_mask.astype(np.uint8), 1)
        atlas_paths['exclusion_atlas'] = exclusion_path
        
        # --- 2. Core Hydraulic Analysis ---
        hydraulic_maps = perform_hydraulic_analysis(DEM_PATH, profile)
        dem_raw = hydraulic_maps.pop('dem') # Get raw DEM data for depth calc
        
        # --- 3. Generate Cost Atlases ---
        print("  -> Generating Cost Factor Maps...")
        
        # --- 3A. Earthworks Cost Atlas (Slope + Depth) ---
        print("  -> 1. Earthworks Cost Atlas (Slope + Depth Penalty)...")
        
        # Cost Factor 1: Slope (for land and sea-bed stability)
        slope_cost = normalize_map(hydraulic_maps['slope'])
        
        # Cost Factor 2: Depth (CRITICAL for MTHL pillar cost)
        depth_cost = np.zeros_like(dem_raw, dtype=np.float32)
        water_mask = dem_raw < 0.0 # Everything below sea level is water
        if np.any(water_mask):
            # Penalize proportional to the square of depth for exponential cost increase
            # Normalize depths to a 0-1 scale (0=shallowest, 1=deepest)
            abs_depths = np.abs(dem_raw[water_mask])
            max_abs_depth = np.max(abs_depths) if np.max(abs_depths) > 0 else 1.0
            
            # Cost proportional to normalized depth (linear for now, use exp/square for high penalty)
            normalized_depth_cost = abs_depths / max_abs_depth
            
            # Apply exponential penalty (e.g., square it) for steep cost gradient
            depth_cost[water_mask] = normalized_depth_cost ** 2 
            depth_cost = normalize_map(depth_cost)

        # Combine costs (e.g., 30% slope importance, 70% depth importance)
        earthworks_cost = (0.30 * slope_cost) + (0.70 * depth_cost)
        earthworks_cost = normalize_map(earthworks_cost)

        # Apply soil modifier (Simplified: we assume SOIL_UTM43 exists and has one type)
        soil_modifier = np.ones(target_shape, dtype=np.float32)
        try:
            soil_gdf = gpd.read_file(SOIL_1_SHP_PATH)
            # Assign modifier based on dominant soil type (simplified example)
            soil_modifier[soil_gdf.geometry.intersects(soil_gdf.unary_union)] = SOIL_COST_MODIFIERS['rocky'] 
            print("     - Applied uniform 'rocky' soil modifier (MTHL hardcoded logic).")
        except:
             print("     - Warning: Skipping soil modifier, using default 1.0.")

        earthworks_cost *= soil_modifier
        earthworks_cost = normalize_map(earthworks_cost) 
        earthworks_cost[exclusion_mask > 0] = 9999.0 # Apply exclusion mask
        earthworks_path = f'{output_dir}/earthworks_cost_atlas.tif'
        profile.update(dtype=rasterio.float32, count=1, nodata=9999.0)
        with rasterio.open(earthworks_path, 'w', **profile) as dst: 
            dst.write(earthworks_cost.astype(np.float32), 1)
        atlas_paths['earthworks_cost_atlas'] = earthworks_path

        # --- 3B. Vegetation/Clearing Cost Atlas (from LULC) ---
        print("  -> 2. Vegetation/Clearing Cost Atlas (from LULC)...")
        with rasterio.open(LULC_PATH) as lulc_src:
            lulc_aligned = np.zeros(target_shape, dtype=lulc_src.dtypes[0])
            reproject(source=rasterio.band(lulc_src, 1), destination=lulc_aligned,
                      src_transform=lulc_src.transform, src_crs=lulc_src.crs,
                      dst_transform=profile['transform'], dst_crs=profile['crs'],
                      resampling=Resampling.nearest)
        
        vegetation_cost = np.full(target_shape, LULC_COSTS['default'], dtype=np.float32)
        for lulc_val, cost in LULC_COSTS.items():
            if lulc_val != 'default': 
                vegetation_cost[lulc_aligned == lulc_val] = cost
        
        vegetation_cost = normalize_map(vegetation_cost)
        vegetation_cost = gaussian_filter(vegetation_cost, sigma=1.0)
        vegetation_cost[exclusion_mask > 0] = 9999.0
        vegetation_path = f'{output_dir}/vegetation_cost_atlas.tif'
        with rasterio.open(vegetation_path, 'w', **profile) as dst: 
            dst.write(vegetation_cost.astype(np.float32), 1)
        atlas_paths['vegetation_cost_atlas'] = vegetation_path

        # --- 3C. Enhanced Flood Risk Atlas (Flow Accumulation + Flood Data) ---
        print("  -> 3. Enhanced Flood Risk Atlas (from Flow Accumulation + Flood Data)...")
        base_hydrology_risk = normalize_map(np.log1p(hydraulic_maps['flow_acc']))

        flood_enhanced_risk = base_hydrology_risk.copy()
        try:
            with rasterio.open(FLOOD_PATH) as flood_src:
                flood_data = flood_src.read(1)
                
                flood_resampled = np.zeros(target_shape, dtype=flood_data.dtype)
                reproject(
                    source=flood_data,
                    destination=flood_resampled,
                    src_transform=flood_src.transform,
                    src_crs=flood_src.crs,
                    dst_transform=profile['transform'],
                    dst_crs=profile['crs'],
                    resampling=Resampling.bilinear
                )
                flood_data = flood_resampled

            flood_normalized = normalize_map(flood_data)
            flood_enhanced_risk = base_hydrology_risk + (flood_normalized * FLOOD_RISK_MULTIPLIER)
            flood_enhanced_risk = normalize_map(flood_enhanced_risk)
            flood_enhanced_risk = gaussian_filter(flood_enhanced_risk, sigma=1.0)
            print("     - ✅ Incorporated actual flood data into hydrology risk")
        except Exception as e:
            print(f"     - ⚠️ Could not load flood data ({e}), using flow accumulation only")

        flood_enhanced_risk[exclusion_mask > 0] = 9999.0
        hydrology_path = f'{output_dir}/hydrology_risk_atlas.tif'
        profile.update(dtype=rasterio.float32, count=1, nodata=9999.0)
        with rasterio.open(hydrology_path, 'w', **profile) as dst:
            dst.write(flood_enhanced_risk.astype(np.float32), 1)
        atlas_paths['hydrology_risk_atlas'] = hydrology_path

        # --- 3D. Social Impact Atlas (from Population Density) ---
        print("  -> 4. Social Impact Atlas (from Population Density)...")
        social_impact = np.ones(target_shape, dtype=np.float32)
        try:
            with rasterio.open(POPULATION_PATH) as pop_src:
                pop_data = pop_src.read(1)
                
                pop_resampled = np.zeros(target_shape, dtype=pop_data.dtype)
                reproject(
                    source=pop_data,
                    destination=pop_resampled,
                    src_transform=pop_src.transform,
                    src_crs=pop_src.crs,
                    dst_transform=profile['transform'],
                    dst_crs=profile['crs'],
                    resampling=Resampling.bilinear
                )
                pop_data = pop_resampled

            pop_normalized = normalize_map(pop_data)
            social_impact = 1.0 + (pop_normalized * POPULATION_COST_MULTIPLIER)
            social_impact = gaussian_filter(social_impact, sigma=1.0)
            print("     - ✅ Incorporated population density into social impact costs")
        except Exception as e:
            print(f"     - ⚠️ Could not load population data ({e}), using neutral social impact")

        social_impact[exclusion_mask > 0] = 9999.0
        social_path = f'{output_dir}/social_impact_atlas.tif'
        with rasterio.open(social_path, 'w', **profile) as dst:
            dst.write(social_impact.astype(np.float32), 1)
        atlas_paths['social_impact_atlas'] = social_path

        # --- 3E. Connectivity Atlas (from Road Network Proximity) ---
        print("  -> 5. Connectivity Atlas (from Road Network Proximity)...")
        connectivity_bonus = np.ones(target_shape, dtype=np.float32)
        try:
            roads_for_distance = gpd.read_file(ROADS_SHP_PATH)

            roads_raster = rasterize_shapefile(roads_for_distance, profile)

            distance_pixels = distance_transform_edt(roads_raster == 0)

            pixel_size = abs(profile['transform'].a)
            distance_meters = distance_pixels * pixel_size

            road_bonus_mask = distance_meters <= ROAD_BUFFER_DISTANCE
            connectivity_bonus[road_bonus_mask] = ROAD_BONUS_MULTIPLIER

            print(f"     - ✅ Created road connectivity bonuses within {ROAD_BUFFER_DISTANCE}m of roads")
        except Exception as e:
            print(f"     - ⚠️ Could not create road connectivity data ({e}), using neutral connectivity")

        connectivity_bonus[exclusion_mask > 0] = 9999.0
        connectivity_path = f'{output_dir}/connectivity_atlas.tif'
        with rasterio.open(connectivity_path, 'w', **profile) as dst:
            dst.write(connectivity_bonus.astype(np.float32), 1)
        atlas_paths['connectivity_atlas'] = connectivity_path

        # --- 3F. DEM Elevation Data (for Cut/Fill Calculations) ---
        print("  -> 6. DEM Elevation Data (for Cut/Fill Calculations)...")
        dem_path = f'{output_dir}/dem_elevation_atlas.tif'
        with rasterio.open(dem_path, 'w', **profile) as dst:
            dst.write(dem.astype(np.float32), 1)
        atlas_paths['dem_elevation_atlas'] = dem_path
        print("     - ✅ DEM elevation data saved for cut/fill analysis")

        print("  ✅ STRATEGIC COST ATLAS GENERATION COMPLETE.")
        return atlas_paths, profile, hydraulic_maps

    except Exception as e:
        print(f"❌ FATAL ERROR in Atlas Generation: {e}")
        import traceback
        traceback.print_exc()
        return None, None, None

def generate_separate_atlas_images(atlas_paths, hydraulic_maps, dem_path, output_dir):
    """
    Generates four separate, high-quality images for the cost atlas components with improved visualization.
    """
    print("📊 Generating separate atlas report images with enhanced visualization...")
    try:
        # Load DEM for background and hillshade
        with rasterio.open(dem_path) as src:
            dem = src.read(1).astype(np.float32)
            dem_profile = src.profile
            dem[dem < -1000] = np.nan

            # Create hillshade for terrain visualization
            from matplotlib.colors import LightSource
            ls = LightSource(azdeg=315, altdeg=45)
            hillshade = ls.hillshade(dem, vert_exag=1.0)

        # --- Image 1: Earthworks Cost (Slope) ---
        with rasterio.open(atlas_paths['earthworks_cost_atlas']) as src:
            data = src.read(1)
            masked_data = np.ma.masked_where(data == src.nodata, data)
            valid_data = masked_data.compressed()
            vmin, vmax = np.percentile(valid_data, [5, 95]) if len(valid_data) > 0 else (0, 1)

        fig, ax = plt.subplots(figsize=(12, 10))
        # Hillshade background
        ax.imshow(hillshade, cmap='gray', alpha=0.4)
        # Earthworks overlay
        im = ax.imshow(masked_data, cmap='plasma', vmin=vmin, vmax=vmax, interpolation='nearest', alpha=0.7)
        ax.set_title("Earthworks Cost Atlas (Slope Difficulty)", fontsize=16, weight='bold')
        ax.set_xticks([]); ax.set_yticks([])
        cbar = fig.colorbar(im, ax=ax, shrink=0.8)
        cbar.set_label('Earthworks Difficulty\n(0=Flat, 1=Very Steep)', rotation=270, labelpad=20)
        plt.tight_layout()
        png_path = f"{output_dir}/earthworks_cost_map.png"
        plt.savefig(png_path, dpi=300, bbox_inches='tight')
        plt.close(fig)
        print(f"  - ✅ Saved enhanced {png_path}")

        # --- Image 2: Vegetation Cost (LULC) ---
        # --- Image 2: Vegetation Cost (LULC) ---
        with rasterio.open(atlas_paths['vegetation_cost_atlas']) as src:
            data = src.read(1)
            masked_data = np.ma.masked_where(data == src.nodata, data)
            valid_data = masked_data.compressed()
            vmin, vmax = valid_data.min(), valid_data.max() if len(valid_data) > 0 else (0, 1)

        fig, ax = plt.subplots(figsize=(12, 10))
        ax.imshow(hillshade, cmap='gray', alpha=0.4)
        im = ax.imshow(masked_data, cmap='viridis', vmin=vmin, vmax=vmax, interpolation='nearest', alpha=0.7)
        ax.set_title("Vegetation/Clearing Cost Atlas (LULC)", fontsize=16, weight='bold')
        ax.set_xticks([]); ax.set_yticks([])
        cbar = fig.colorbar(im, ax=ax, shrink=0.8)
        cbar.set_label('Clearing Cost\n(0=Grassland, 1=Urban/Dense Forest)', rotation=270, labelpad=20)
        plt.tight_layout()
        png_path = f"{output_dir}/vegetation_cost_map.png"
        plt.savefig(png_path, dpi=300, bbox_inches='tight')
        plt.close(fig)
        print(f"  - ✅ Saved enhanced {png_path}")

        # --- Image 3: Hydrology Risk (Flow Accumulation) ---
        with rasterio.open(atlas_paths['hydrology_risk_atlas']) as src:
            data = src.read(1)
            masked_data = np.ma.masked_where(data == src.nodata, data)
            valid_data = masked_data.compressed()
            vmin, vmax = np.percentile(valid_data, [5, 95]) if len(valid_data) > 0 else (0, 1)

        fig, ax = plt.subplots(figsize=(12, 10))
        ax.imshow(hillshade, cmap='gray', alpha=0.4)
        im = ax.imshow(masked_data, cmap='Blues', vmin=vmin, vmax=vmax, interpolation='nearest', alpha=0.7)
        ax.set_title("Hydrology Risk Atlas (Water Accumulation)", fontsize=16, weight='bold')
        ax.set_xticks([]); ax.set_yticks([])
        cbar = fig.colorbar(im, ax=ax, shrink=0.8)
        cbar.set_label('Flood Risk\n(0=Dry, 1=High Water Accumulation)', rotation=270, labelpad=20)
        plt.tight_layout()
        png_path = f"{output_dir}/hydrology_risk_map.png"
        plt.savefig(png_path, dpi=300, bbox_inches='tight')
        plt.close(fig)
        print(f"  - ✅ Saved enhanced {png_path}")

        # --- Image 4: Social Impact Atlas (Population Density) ---
        if 'social_impact_atlas' in atlas_paths:
            with rasterio.open(atlas_paths['social_impact_atlas']) as src:
                data = src.read(1)
                masked_data = np.ma.masked_where(data == src.nodata, data)
                valid_data = masked_data.compressed()
                vmin, vmax = np.percentile(valid_data, [5, 95]) if len(valid_data) > 0 else (0, 1)

            fig, ax = plt.subplots(figsize=(12, 10))
            ax.imshow(hillshade, cmap='gray', alpha=0.4)
            im = ax.imshow(masked_data, cmap='RdYlBu_r', vmin=vmin, vmax=vmax, interpolation='nearest', alpha=0.7)
            ax.set_title("Social Impact Atlas (Population Density)", fontsize=16, weight='bold')
            ax.set_xticks([]); ax.set_yticks([])
            cbar = fig.colorbar(im, ax=ax, shrink=0.8)
            cbar.set_label('Social Impact\n(0=Low Population, 1=High Disruption)', rotation=270, labelpad=20)
            plt.tight_layout()
            png_path = f"{output_dir}/social_impact_map.png"
            plt.savefig(png_path, dpi=300, bbox_inches='tight')
            plt.close(fig)
            print(f"  - ✅ Saved enhanced {png_path}")

        # --- Image 5: Connectivity Atlas (Road Proximity) ---
        if 'connectivity_atlas' in atlas_paths:
            with rasterio.open(atlas_paths['connectivity_atlas']) as src:
                data = src.read(1)
                masked_data = np.ma.masked_where(data == src.nodata, data)

            fig, ax = plt.subplots(figsize=(12, 10))
            ax.imshow(hillshade, cmap='gray', alpha=0.4)
            im = ax.imshow(masked_data, cmap='Greens', interpolation='nearest', alpha=0.7, vmin=ROAD_BONUS_MULTIPLIER, vmax=1.0)
            ax.set_title("Connectivity Atlas (Road Proximity Bonus)", fontsize=16, weight='bold')
            ax.set_xticks([]); ax.set_yticks([])
            cbar = fig.colorbar(im, ax=ax, shrink=0.8)
            cbar.set_label('Connectivity Factor\n(Lower = Better Access)', rotation=270, labelpad=20)
            plt.tight_layout()
            png_path = f"{output_dir}/connectivity_map.png"
            plt.savefig(png_path, dpi=300, bbox_inches='tight')
            plt.close(fig)
            print(f"  - ✅ Saved enhanced {png_path}")

        # --- Image 6: Exclusion Atlas (No-Go Zones) ---
        with rasterio.open(atlas_paths['exclusion_atlas']) as src:
            data = src.read(1)
            # Create a custom colormap for exclusion zones
            from matplotlib.colors import ListedColormap
            exclusion_cmap = ListedColormap(['white', 'red'])
            masked_data = np.ma.masked_where(data == 0, data)

        fig, ax = plt.subplots(figsize=(12, 10))
        ax.imshow(hillshade, cmap='gray', alpha=0.5)
        im = ax.imshow(data, cmap=exclusion_cmap, interpolation='nearest', alpha=0.8, vmin=0, vmax=1)
        ax.set_title("Exclusion Atlas (No-Build Zones)", fontsize=16, weight='bold')
        ax.set_xticks([]); ax.set_yticks([])

        # Custom legend for exclusion zones
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor='white', edgecolor='black', label='Buildable'),
            Patch(facecolor='red', edgecolor='black', label='Excluded (Buildings/Rail/Water)')
        ]
        ax.legend(handles=legend_elements, loc='upper right', fontsize=10)

        plt.tight_layout()
        png_path = f"{output_dir}/exclusion_map.png"
        plt.savefig(png_path, dpi=300, bbox_inches='tight')
        plt.close(fig)
        print(f"  - ✅ Saved enhanced {png_path}")

        # Print summary statistics
        print("\n📈 ATLAS STATISTICS SUMMARY:")
        print("=" * 50)

        # Earthworks statistics
        with rasterio.open(atlas_paths['earthworks_cost_atlas']) as src:
            earth_data = src.read(1)
            valid_earth = earth_data[earth_data != src.nodata]
            print(f"🏗️  Earthworks: Mean={np.mean(valid_earth):.2f}, Max={np.max(valid_earth):.2f}, Range={np.max(valid_earth)-np.min(valid_earth):.2f}")
        # Vegetation statistics
        with rasterio.open(atlas_paths['vegetation_cost_atlas']) as src:
            veg_data = src.read(1)
            valid_veg = veg_data[veg_data != src.nodata]
            print(f"🌳 Vegetation: Mean={np.mean(valid_veg):.2f}, Max={np.max(valid_veg):.2f}, Range={np.max(valid_veg)-np.min(valid_veg):.2f}")
        # Hydrology statistics
        with rasterio.open(atlas_paths['hydrology_risk_atlas']) as src:
            hydro_data = src.read(1)
            valid_hydro = hydro_data[hydro_data != src.nodata]
            print(f"💧 Hydrology: Mean={np.mean(valid_hydro):.2f}, Max={np.max(valid_hydro):.2f}, Range={np.max(valid_hydro)-np.min(valid_hydro):.2f}")
        # Social impact statistics
        if 'social_impact_atlas' in atlas_paths:
            with rasterio.open(atlas_paths['social_impact_atlas']) as src:
                social_data = src.read(1)
                valid_social = social_data[social_data != src.nodata]
                print(f"👥 Social Impact: Mean={np.mean(valid_social):.2f}, Max={np.max(valid_social):.2f}")

        # Connectivity statistics
        if 'connectivity_atlas' in atlas_paths:
            with rasterio.open(atlas_paths['connectivity_atlas']) as src:
                conn_data = src.read(1)
                valid_conn = conn_data[conn_data != src.nodata]
                bonus_pixels = np.sum(valid_conn < 1.0)
                total_valid = len(valid_conn)
                bonus_percent = (bonus_pixels / total_valid) * 100 if total_valid > 0 else 0
                print(f"🛣️  Connectivity: {bonus_pixels:,} pixels with road bonus ({bonus_percent:.1f}% of AOI)")

        # Exclusion statistics
        with rasterio.open(atlas_paths['exclusion_atlas']) as src:
            excl_data = src.read(1)
            excl_pixels = np.sum(excl_data > 0)
            total_pixels = excl_data.size
            excl_percent = (excl_pixels / total_pixels) * 100
            print(f"🚫 Exclusions: {excl_pixels:,} pixels ({excl_percent:.1f}% of AOI)")
    except Exception as e:
        print(f"⚠️ Warning: Could not generate enhanced atlas images. Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("=" * 80)
    print("🗺️  LAUNCHING STAGE 1: ALIGNMENT COST ATLAS GENERATOR (v1.0)")
    print("=" * 80)
    
    # <<< ADAPTED >>> Using new environment variable
    output_dir = os.environ.get('PIPELINE_OUTPUT_DIR', f"Outputs/Alignment_Run_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    os.makedirs(output_dir, exist_ok=True)
    print(f"📁 Using output directory: {output_dir}")
    
    log_file = open(f"{output_dir}/stage1_diagnostics.log", 'w')
    original_stdout, original_stderr = sys.stdout, sys.stderr
    sys.stdout = Tee(original_stdout, log_file)
    sys.stderr = Tee(original_stderr, log_file)
    
    try:
        atlas_paths, profile, hydraulic_maps = run_strategic_atlas_generation(output_dir)
        if atlas_paths:
            print("\n" + "="*60 + "\n🏆 COST ATLAS REPORT (v1.0) 🏆\n" + "="*60)
            for name, path in atlas_paths.items():
                print(f"  - Output Layer '{name}': '{path}'")
            
            # NOTE: We use the *base* DEM_PATH (topobathy) for the visualization background
            generate_separate_atlas_images(atlas_paths, hydraulic_maps, DEM_PATH, output_dir)
            
            print("\n" + "="*60)
            print("🌉 Preparing strategic bridge file for Stage 2...")
            diagnostics_report = {
                'timestamp': datetime.now().isoformat(),
                'project_type': 'Linear Infrastructure Alignment',
                'analysis_type': 'Strategic Cost Atlas v1.0',
                'atlas_paths': atlas_paths,
                'raster_profile': {
                    'crs': str(profile['crs']),
                    'transform': list(profile['transform']),
                    'width': profile['width'],
                    'height': profile['height']
                }
            }
            report_path = f"{output_dir}/cost_atlas_report.json"
            with open(report_path, 'w') as f:
                json.dump(diagnostics_report, f, indent=4)
            print(f"  - ✅ Saved strategic cost atlas to '{report_path}'")
            print("="*60)
        else:
            print("\n" + "="*60 + "\n❌ ANALYSIS FAILED: Could not generate the cost atlas.\n" + "="*60)
            
    finally:
        sys.stdout, sys.stderr = original_stdout, original_stderr
        if 'log_file' in locals() and not log_file.closed:
            log_file.close()
