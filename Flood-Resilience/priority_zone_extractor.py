# ==============================================================================
# Project: Gorakhpur Urban Resilience AI
# FILE NAME: priority_zone_extractor.py
# VERSION: 2.9 (Multi-Hotspot Detection)
# PURPOSE: To identify the top 3 high-priority flood intervention zones by
#          iteratively searching the entire city-wide dataset.
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
        'zone_id': zone_id, 'zone_name': zone['subdistrict'], 'bounds': bounds_dict,
        'population_exposure': float(zone.get('population_exposure', 0)),
        'priority_pixels': int(zone.get('priority_pixels', 0)),
        'estimated_area_km2': float(zone.get('area_km2', 0))
    }
    config_path = f"{output_dir}/priority_zone_{zone_id}.json"
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    return config_path

def main():
    """Main function to extract priority zones from Stage 1 outputs."""
    print("="*70)
    print("🎯 PRIORITY ZONE EXTRACTION (Stage 1.5 - Multi-Hotspot Search)")
    print("="*70)

    outputs_dir = Path("Outputs")
    diag_files = list(outputs_dir.glob("**/diagnostics_report.json"))
    if not diag_files:
        print("❌ No diagnostics_report.json found. Run Stage 1 first."); return

    diag_file = max(diag_files, key=lambda x: x.stat().st_mtime)
    output_dir = diag_file.parent
    print(f"📂 Using Stage 1 outputs from: {output_dir}")

    with open(diag_file, 'r') as f:
        diagnostics = json.load(f)

    print("📊 Loading base datasets for city-wide analysis...")
    try:
        flood_data, flood_profile = load_raster_data("SGP_Data/Floods/flood_sgp_utm48.tif")
        pop_data, pop_profile = load_raster_data("SGP_Data/Population/population_sgp.tif")
        STATIC_WATER_PATH = "SGP_Data/Water_Static/static_water.shp"
        WATERWAYS_PATH = "SGP_Data/Water_ways/waterways.shp"
        static_water_gdf = gpd.read_file(STATIC_WATER_PATH)
        waterways_gdf = gpd.read_file(WATERWAYS_PATH)
        combined_water_gdf = pd.concat([static_water_gdf, waterways_gdf], ignore_index=True)
        combined_water_gdf = combined_water_gdf.to_crs(flood_profile['crs'])
    except Exception as e:
        print(f"❌ Error loading base datasets: {e}"); return

    print("  -> Applying city-wide intersection to find the best spillage hotspots...")

    static_water_mask = rasterize(
        shapes=[geom for geom in combined_water_gdf.geometry if geom.is_valid],
        out_shape=flood_data.shape, transform=flood_profile['transform'],
        fill=0, default_value=1, dtype='uint8'
    ).astype(bool)
    
    if np.all(flood_data <= 0) or np.all(pop_data <= 0):
        print("⚠️ No valid flood or population data found city-wide."); return
    
    flood_thresh_val = np.percentile(flood_data[flood_data > 0], 50)
    pop_thresh_val = np.percentile(pop_data[pop_data > 0], 50)
    high_flood_mask = flood_data >= flood_thresh_val
    high_pop_mask = pop_data >= pop_thresh_val
    final_spillage_mask = (high_flood_mask & high_pop_mask & ~static_water_mask)
    
    print(f"     - Found {np.sum(final_spillage_mask)} potential high-priority pixels city-wide.")
    
    priority_zones = []
    if np.sum(final_spillage_mask) < 10:
        print("⚠️ City-wide search found no significant spillage zones. Creating single fallback AOI.")
        subdistrict_gdf = gpd.read_file("SGP_Data/Boundary/SG_Bounds.shp")
        subdistrict_gdf['area'] = subdistrict_gdf.geometry.area
        target_subdist = subdistrict_gdf.loc[subdistrict_gdf['area'].idxmax()]
        bounds = target_subdist.geometry.bounds
        center_x, center_y = (bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2
        half_size = 750 # 1.5km box
        priority_zones.append({'subdistrict': "Fallback_Global_Center_AOI", 'bounds': (center_x - half_size, center_y - half_size, center_x + half_size, center_y + half_size)})

    else:
        # --- THE FIX IS HERE ---
        # Instead of finding just one hotspot, we loop to find the top 3.
        combined_risk = np.zeros_like(flood_data, dtype=np.float32)
        combined_risk[final_spillage_mask] = flood_data[final_spillage_mask] * pop_data[final_spillage_mask]
        
        num_zones_to_find = 3  # Find the top 3 locations
        aoi_size_meters = 800
        half_size = aoi_size_meters / 2

        for i in range(num_zones_to_find):
            if np.max(combined_risk) == 0:
                print(f"  -> No more significant risk zones found. Stopping at {i} hotspots.")
                break # Stop if there are no more risk zones left

            # Find the coordinates of the current BEST pixel
            hotspot_row, hotspot_col = np.unravel_index(np.argmax(combined_risk), combined_risk.shape)
            hotspot_x, hotspot_y = flood_profile['transform'] * (hotspot_col, hotspot_row)
            
            print(f"  -> Identified top hotspot #{i+1} at coordinates: ({hotspot_x:.2f}, {hotspot_y:.2f})")
            
            # Create the Micro-AOI around that point
            left, bottom = hotspot_x - half_size, hotspot_y - half_size
            right, top = hotspot_x + half_size, hotspot_y + half_size
            
            priority_zones.append({
                'subdistrict': f"Intelligent_Hotspot_AOI_{i+1}", 
                'bounds': (left, bottom, right, top)
            })
            
            # "Erase" this AOI from the risk map so it's not picked again
            # Convert the AOI bounds back to pixel coordinates to create a mask
            row_min_erase, col_min_erase = rasterio.transform.rowcol(flood_profile['transform'], left, top)
            row_max_erase, col_max_erase = rasterio.transform.rowcol(flood_profile['transform'], right, bottom)
            
            # Clamp to array dimensions
            row_min_erase = max(0, row_min_erase)
            col_min_erase = max(0, col_min_erase)
            row_max_erase = min(combined_risk.shape[0], row_max_erase)
            col_max_erase = min(combined_risk.shape[1], col_max_erase)
            
            combined_risk[row_min_erase:row_max_erase+1, col_min_erase:col_max_erase+1] = 0
        # --- END OF FIX ---

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
    master_config_path = f"{output_dir}/priority_zones_config.json"
    with open(master_config_path, 'w') as f:
        json.dump(master_config, f, indent=2)

    print("\n✅ MICRO-AOI EXTRACTION COMPLETE")

if __name__ == "__main__":
    main()