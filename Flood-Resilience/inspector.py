# ==============================================================================
# Project: Singapore Urban Resilience AI - Data Inspector
# FILE NAME: data_inspector.py
# VERSION: 1.0
# PURPOSE: To inspect a full stack of geospatial data at a specific coordinate.
#          This script samples raster values and queries vector attributes for a
#          user-defined point, helping to verify data alignment and values.
#
# HOW TO USE:
# 1. Make sure you have the required libraries:
#    pip install geopandas rasterio shapely
#
# 2. Set the `BASE_DATA_DIR` to your "SGP_Data" folder.
#
# 3. CRITICAL: Set the `INSPECTION_COORDINATES` to the point you want to inspect.
#    These coordinates MUST be in the same projection as your data (UTM Zone 48N).
#
# 4. Run the script from your terminal: python data_inspector.py
# ==============================================================================

import os
import geopandas as gpd
import rasterio
from shapely.geometry import Point

# --- 1. CONFIGURATION ---
# Set the base path to your main data folder.
BASE_DATA_DIR = "SGP_Data"

# CRITICAL: Define the X and Y coordinates you want to inspect.
# These MUST be in your project's Coordinate Reference System (CRS),
# which is EPSG:32648 (WGS 84 / UTM zone 48N).
INSPECTION_COORDINATES = {
    "x": 381250.0,  # Example Easting coordinate, CHANGE THIS
    "y": 144500.0   # Example Northing coordinate, CHANGE THIS
}

# Define all the files you want to inspect.
# The script will automatically detect if they are rasters (.tif) or vectors (.shp).
FILE_PATHS = {
    # --- Foundational Rasters ---
    "DEM": "DEM/DEM_SGP_UTM48.tif",
    "Population": "Population/population_sgp.tif",
    "Flood_Map": "Floods/flood_sgp_utm48.tif",
    # Note: Ensure you have a rasterized version of your LULC data for this inspection.
    # "LULC_Raster": "LULC/lulc_rasterized.tif",

    # --- Foundational Vectors ---
    "LULC_Vector": "LULC/lulc.shp",
    "Buildings": "Buildings/buildings.shp",
    "Roads": "Roads/roads.shp",
    "Railways": "Railways/railways.shp",
    "Waterways": "Water_ways/waterways.shp",
    "Static_Water": "Water_Static/static_water.shp",
    "Places_of_Worship": "Place_of_worship/pofw.shp",
    "Points_of_Interest": "Points_of_Interest/pois.shp",
    "Soil_Type_1": "Soil_Data/Soil_FL_LP_RG_Rocks.shp",
    "Soil_Type_2": "Soil_Data/Soil_LX_AC.shp",
    "Traffic_Areas": "Traffic/traffic.shp",
    "Transport_Areas": "Transport_Areas/transport.shp",
    "Natural_Areas": "Natural/natural.shp",
    "Boundary": "Boundary/SG_Bounds.shp",
}

def inspect_data():
    """
    Main function to loop through data files and inspect them at the specified point.
    """
    print("=" * 70)
    print("      SINGAPORE GEOSPATIAL DATA INSPECTOR")
    print("=" * 70)

    # Create the Shapely Point object for spatial queries
    inspection_point = Point(INSPECTION_COORDINATES["x"], INSPECTION_COORDINATES["y"])
    print(f"📍 Inspecting coordinate (UTM Zone 48N): X={inspection_point.x}, Y={inspection_point.y}\n")

    # Loop through each file defined in the configuration
    for name, relative_path in FILE_PATHS.items():
        full_path = os.path.join(BASE_DATA_DIR, relative_path)
        print(f"--- Inspecting Layer: {name} ---")
        print(f"File: {full_path}")

        if not os.path.exists(full_path):
            print("  ❌ ERROR: File not found. Skipping.\n")
            continue

        try:
            # --- Vector Data Inspection (.shp) ---
            if full_path.endswith(".shp"):
                gdf = gpd.read_file(full_path)

                # Find the feature that contains the inspection point
                # For lines (like roads/waterways), we can buffer the point to find nearby lines
                if gdf.geom_type[0] in ['LineString', 'MultiLineString']:
                    search_area = inspection_point.buffer(10) # 10-meter buffer for lines
                    found_feature = gdf[gdf.geometry.intersects(search_area)]
                else: # For polygons (buildings, LULC)
                    found_feature = gdf[gdf.geometry.contains(inspection_point)]

                if not found_feature.empty:
                    print("  ✅ Feature found at this location.")
                    print("  Attributes:")
                    # Print the full attribute row, excluding the bulky geometry column for clarity
                    print(found_feature.drop(columns='geometry').to_string(index=False))
                else:
                    print("  - No feature found at this location.")

            # --- Raster Data Inspection (.tif) ---
            elif full_path.endswith(".tif"):
                with rasterio.open(full_path) as src:
                    # The sample method takes a list of (x, y) coordinates
                    coords = [(inspection_point.x, inspection_point.y)]
                    
                    # Use a generator to sample the value and get the first result
                    value_generator = src.sample(coords)
                    pixel_value = next(value_generator)[0]

                    print(f"  ✅ Pixel value at this location: {pixel_value:.2f}")

            else:
                print("  - Unsupported file type.")

        except Exception as e:
            print(f"  ❌ An error occurred while processing this file: {e}")

        print("-" * 35 + "\n")

if __name__ == "__main__":
    inspect_data()