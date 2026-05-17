# ==============================================================================
# Project: [IWMI] Water Resource Management AI
# FILE NAME: water_opportunity_extractor.py
# VERSION: 1.0 (IWMI Adaptation)
# PURPOSE: To identify the top 3 high-priority water management zones by
#          iteratively searching the entire city-wide dataset for "opportunity hotspots"
#          (e.g., high water stress + high water demand).
# ==============================================================================

import json
import numpy as np
import rasterio
from rasterio.mask import mask
from rasterio.features import rasterize
from rasterio.warp import reproject, Resampling
import geopandas as gpd
import pandas as pd
from shapely.geometry import box, Point
import os
from pathlib import Path

def load_raster_data(filepath):
    """Load raster data and return array + metadata."""
    with rasterio.open(filepath) as src:
        data = src.read(1)
        profile = src.profile
        return data, profile

def create_zone_configuration(zone, output_dir, zone_id):
    """Create configuration file for a specific priority zone."""
    bounds_dict = {
        'left': float(zone['bounds'][0]), 'bottom': float(zone['bounds'][1]),
        'right': float(zone['bounds'][2]), 'top': float(zone['bounds'][3])
    }
    config = {
        'zone_id': zone_id, 
        'zone_name': zone['subdistrict'], 
        'bounds': bounds_dict,
        # <<< ADAPTED >>> Renamed 'population_exposure' to 'demand_score'
        'opportunity_demand_score': float(zone.get('opportunity_demand_score', 0)),
        'priority_pixels': int(zone.get('priority_pixels', 0)),
        'estimated_area_km2': float(zone.get('area_km2', 0))
    }
    # <<< ADAPTED >>> New file name
    config_path = f"{output_dir}/opportunity_zone_{zone_id}.json"
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    return config_path

def main():
    """Main function to extract priority zones from Stage 1 outputs."""
    print("="*70)
    # <<< ADAPTED >>> Updated title
    print("🎯 WATER MANAGEMENT OPPORTUNITY ZONE EXTRACTION (Stage 1.5)")
    print("="*70)

    outputs_dir = Path("Outputs")
    diag_files = list(outputs_dir.glob("**/diagnostics_report.json"))
    if not diag_files:
        print("❌ No diagnostics_report.json found. Run Stage 1 (water_resource_diagnostics.py) first."); return

    diag_file = max(diag_files, key=lambda x: x.stat().st_mtime)
    output_dir = diag_file.parent
    print(f"📂 Using Stage 1 outputs from: {output_dir}")

    with open(diag_file, 'r') as f:
        diagnostics = json.load(f)

    print("📊 Loading base datasets for city-wide analysis...")
    try:
        # <<< ADAPTED >>> Renamed variable for clarity. Using flood map as a proxy for "Water Stress".
        water_stress_data, stress_profile = load_raster_data("Data/GKP/Flood_GKP_UTM.tif")
        # <<< ADAPTED >>> Renamed variable for clarity. Population is our proxy for "Water Demand".
        water_demand_data, demand_profile = load_raster_data("Data/GKP/Population_GKP_UTM_aligned.tif")
        
        STATIC_WATER_PATH = "Data/GKP/Gorakhpur_water_static.shp"
        WATERWAYS_PATH = "Data/GKP/Gorakhpur_water_way.shp"
        static_water_gdf = gpd.read_file(STATIC_WATER_PATH)
        waterways_gdf = gpd.read_file(WATERWAYS_PATH)
        combined_water_gdf = pd.concat([static_water_gdf, waterways_gdf], ignore_index=True)
        # <<< ADAPTED >>> Aligning to the stress_profile (formerly flood_profile)
        combined_water_gdf = combined_water_gdf.to_crs(stress_profile['crs'])
    except Exception as e:
        print(f"❌ Error loading base datasets: {e}"); return

    # <<< ADAPTED >>> The logic is identical, but the *meaning* has changed.
    print("  -> Applying city-wide intersection to find the best water opportunity hotspots...")

    static_water_mask = rasterize(
        shapes=[geom for geom in combined_water_gdf.geometry if geom.is_valid],
        out_shape=water_stress_data.shape, transform=stress_profile['transform'],
        fill=0, default_value=1, dtype='uint8'
    ).astype(bool)
    
    if np.all(water_stress_data <= 0) or np.all(water_demand_data <= 0):
        print("⚠️ No valid water stress or demand data found city-wide."); return
    
    # Find areas of high stress
    stress_thresh_val = np.percentile(water_stress_data[water_stress_data > 0], 50)
    high_stress_mask = water_stress_data >= stress_thresh_val
    # Find areas of high demand
    demand_thresh_val = np.percentile(water_demand_data[water_demand_data > 0], 50)
    high_demand_mask = water_demand_data >= demand_thresh_val
    
    # <<< ADAPTED >>> The "final_spillage_mask" is now the "final_opportunity_mask"
    # This mask finds pixels that are:
    # 1. High Stress (e.g., drought-prone)
    # 2. High Demand (e.g., populated, agricultural)
    # 3. NOT already a water body (so we can build *new* solutions)
    final_opportunity_mask = (high_stress_mask & high_demand_mask & ~static_water_mask)
    
    print(f"     - Found {np.sum(final_opportunity_mask)} potential high-priority opportunity pixels city-wide.")
    
    priority_zones = []
    if np.sum(final_opportunity_mask) < 10:
        print("⚠️ City-wide search found no significant opportunity zones. Creating single fallback AOI.")
        subdistrict_gdf = gpd.read_file("Data/GKP/Gorakhpur_sub_distrcits.shp")
        subdistrict_gdf['area'] = subdistrict_gdf.geometry.area
        target_subdist = subdistrict_gdf.loc[subdistrict_gdf['area'].idxmax()]
        bounds = target_subdist.geometry.bounds
        center_x, center_y = (bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2
        half_size = 750 # 1.5km box
        priority_zones.append({'subdistrict': "Fallback_Global_Center_AOI", 'bounds': (center_x - half_size, center_y - half_size, center_x + half_size, center_y + half_size)})

    else:
        # --- This is the core logic ---
        # <<< ADAPTED >>> Renamed `combined_risk` to `combined_opportunity_score`
        # We are multiplying (Stress * Demand) to find the pixels with the highest combined score.
        combined_opportunity_score = np.zeros_like(water_stress_data, dtype=np.float32)
        combined_opportunity_score[final_opportunity_mask] = water_stress_data[final_opportunity_mask] * water_demand_data[final_opportunity_mask]
        
        num_zones_to_find = 3  # Find the top 3 locations
        aoi_size_meters = 800
        half_size = aoi_size_meters / 2

        for i in range(num_zones_to_find):
            if np.max(combined_opportunity_score) == 0:
                print(f"  -> No more significant opportunity zones found. Stopping at {i} hotspots.")
                break 

            # Find the coordinates of the current BEST pixel
            hotspot_row, hotspot_col = np.unravel_index(np.argmax(combined_opportunity_score), combined_opportunity_score.shape)
            hotspot_x, hotspot_y = stress_profile['transform'] * (hotspot_col, hotspot_row)
            
            print(f"  -> Identified top hotspot #{i+1} at coordinates: ({hotspot_x:.2f}, {hotspot_y:.2f})")
            
            # Create the Micro-AOI around that point
            left, bottom = hotspot_x - half_size, hotspot_y - half_size
            right, top = hotspot_x + half_size, hotspot_y + half_size
            
            priority_zones.append({
                'subdistrict': f"Intelligent_Hotspot_AOI_{i+1}", 
                'bounds': (left, bottom, right, top)
            })
            
            # "Erase" this AOI from the opportunity map so it's not picked again
            row_min_erase, col_min_erase = rasterio.transform.rowcol(stress_profile['transform'], left, top)
            row_max_erase, col_max_erase = rasterio.transform.rowcol(stress_profile['transform'], right, bottom)
            
            row_min_erase = max(0, row_min_erase)
            col_min_erase = max(0, col_min_erase)
            row_max_erase = min(combined_opportunity_score.shape[0], row_max_erase)
            col_max_erase = min(combined_opportunity_score.shape[1], col_max_erase)
            
            combined_opportunity_score[row_min_erase:row_max_erase+1, col_min_erase:col_max_erase+1] = 0

    print(f"\n🎯 IDENTIFIED {len(priority_zones)} TARGET MICRO-AOI(s):")
    zone_configs = []
    for i, zone in enumerate(priority_zones, 1):
        config_path = create_zone_configuration(zone, output_dir, i)
        zone_configs.append(config_path)

    master_config = {
        'stage': '1.5_complete', 'priority_zones': len(priority_zones),
        'zone_configs': zone_configs,
        'stage1_diagnostics': str(diag_file)
    }
    # <<< ADAPTED >>> New file name
    master_config_path = f"{output_dir}/opportunity_zones_config.json"
    with open(master_config_path, 'w') as f:
        json.dump(master_config, f, indent=2)

    print("\n✅ MICRO-AOI EXTRACTION COMPLETE")

if __name__ == "__main__":
    main()