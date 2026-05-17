# ==============================================================================
# Project: [IWMI] Water Resource Management AI
# FILE NAME: water_intervention_planner.py
# VERSION: 1.0 (IWMI Adaptation)
# PURPOSE: To use a genetic algorithm to evolve an optimal, multi-component
#          water management plan (harvesting, recharge, access). This version
#          is guided by the strategic atlas from Stage 1.
# ==============================================================================

import random
import json
import sys
import os
import math
import numpy as np
import rasterio
from rasterio.mask import mask
import geopandas as gpd
from deap import base, creator, tools, algorithms
import simplekml
from pyproj import Transformer
from datetime import datetime
from affine import Affine
from shapely.geometry import box

# Import the Critic
# <<< ADAPTED >>> We will create this adapted file in the *next* step.
# The *name* of the file and class remains the same for code compatibility.
from intervention_rules import Critic

class Tee:
    def __init__(self, *files): self.files = files
    def write(self, obj):
        for f in self.files: f.write(obj); f.flush()
    def flush(self):
        for f in self.files: f.flush()

# --- Global variables for suitability maps and critic ---
# <<< ADAPTED >>> Renamed keys to match our new water management goals.
SUITABILITY_DATA = {
    'harvesting_pond': {'map': None, 'indices': None, 'probs': None},
    'recharge_structure': {'map': None, 'indices': None, 'probs': None},
    'nbs_swale': {'map': None, 'indices': None, 'probs': None},
    'solar_pump': {'locations': []}
}
RASTER_PROFILE = None
CRITIC = None # The single instance of our physics-based critic

def load_zone_suitability_maps(atlas_paths, zone_bounds):
    """Loads suitability maps cropped to a specific zone bounds."""
    print(f"  -> Loading Strategic Atlas for zone: {zone_bounds}")

    zone_geom = box(zone_bounds['left'], zone_bounds['bottom'],
                   zone_bounds['right'], zone_bounds['top'])

    for intervention_type, path in atlas_paths.items():
        if path.endswith('.tif'):
            # <<< ADAPTED >>> Logic to map new .tif filenames to new keys
            data_key = None
            if 'harvesting_pond' in path:
                data_key = 'harvesting_pond'
            elif 'recharge_structure' in path:
                data_key = 'recharge_structure'
            elif 'nbs_suitability' in path:
                data_key = 'nbs_swale'
            
            if data_key is None:
                continue

            with rasterio.open(path) as src:
                try:
                    cropped_data, cropped_transform = mask(src, [zone_geom], crop=True, nodata=src.nodata)
                    suitability_map = cropped_data[0]
                    suitability_map[suitability_map < 0] = 0 
                    total_score = np.sum(suitability_map)

                    SUITABILITY_DATA[data_key]['map'] = suitability_map
                    SUITABILITY_DATA[data_key]['indices'] = np.arange(suitability_map.size)
                    if total_score > 0:
                        SUITABILITY_DATA[data_key]['probs'] = (suitability_map / total_score).flatten()
                    else: 
                        SUITABILITY_DATA[data_key]['probs'] = np.ones(suitability_map.size) / suitability_map.size
                except Exception as e:
                    print(f"    ⚠️ Could not crop {data_key} map to zone: {e}")
                    suitability_map = src.read(1)
                    suitability_map[suitability_map < 0] = 0
                    SUITABILITY_DATA[data_key]['map'] = suitability_map
                    SUITABILITY_DATA[data_key]['indices'] = np.arange(suitability_map.size)

        # <<< ADAPTED >>> Load the new solar pump opportunities shapefile
        elif path.endswith('.shp') and 'solar_pump' in path:
            gdf = gpd.read_file(path)
            zone_pumps = gdf[gdf.geometry.within(zone_geom)]
            SUITABILITY_DATA['solar_pump']['locations'] = [(p.x, p.y) for p in zone_pumps.geometry]
            print(f"    - Found {len(zone_pumps)} solar pump opportunities in zone")

    global ZONE_TRANSFORM, RASTER_PROFILE
    ZONE_TRANSFORM = Affine(*RASTER_PROFILE['transform'])

    print("  - ✅ Zone atlas loaded successfully.")

def get_weighted_random_coords(intervention_type, min_suitability=0.1):
    """Selects random coordinates, guided by suitability map and spatially constrained."""
    data = SUITABILITY_DATA[intervention_type]
    suitability_map = data['map']
    if hasattr(suitability_map, 'mask'):
        valid_pixels = (~suitability_map.mask) & (suitability_map >= min_suitability)
    else:
        valid_pixels = (suitability_map >= min_suitability)
    if not np.any(valid_pixels):
        valid_pixels = suitability_map > 0
    if not np.any(valid_pixels):
        valid_pixels = np.ones_like(suitability_map, dtype=bool)
    valid_indices = np.where(valid_pixels.flatten())[0]
    if len(valid_indices) == 0:
        chosen_index = np.random.choice(data['indices'], p=data['probs'])
    else:
        chosen_index = np.random.choice(valid_indices)
    row, col = np.unravel_index(chosen_index, suitability_map.shape)

    global ZONE_TRANSFORM
    if 'ZONE_TRANSFORM' in globals():
        transform = ZONE_TRANSFORM
    else:
        transform = Affine(*RASTER_PROFILE['transform'])
    x, y = transform * (col + 0.5, row + 0.5)
    return x, y

def generate_random_intervention_plan():
    """Generates a comprehensive plan using ALL four intervention types."""
    # <<< ADAPTED >>> Renamed keys
    plan = {'harvesting_ponds': [], 'recharge_structures': [], 'nbs_swales': [], 'solar_pumps': []}

    # Add 2 to 5 harvesting ponds
    for i in range(random.randint(2, 5)):
        x, y = get_weighted_random_coords('harvesting_pond')
        plan['harvesting_ponds'].append({
            'id': i, 'x': x, 'y': y,
            'radius': random.uniform(30, 100), 'depth': random.uniform(2, 5)
        })

    # Add 3 to 6 recharge structures (e.g., check dams, percolation tanks)
    # The 'levee' geometry (a line) is a good representation for a check dam.
    for i in range(random.randint(3, 6)):
        x1, y1 = get_weighted_random_coords('recharge_structure')
        x2, y2 = get_weighted_random_coords('recharge_structure')
        plan['recharge_structures'].append({
            'id': i, 'x_start': x1, 'y_start': y1, 'x_end': x2, 'y_end': y2,
            'height': random.uniform(0.5, 2.0) # Check dams are typically lower than levees
        })

    # Add 4 to 8 NbS swales
    for i in range(random.randint(4, 8)):
        x1, y1 = get_weighted_random_coords('nbs_swale')
        x2, y2 = get_weighted_random_coords('nbs_swale')
        plan['nbs_swales'].append({
            'id': i, 'x_start': x1, 'y_start': y1, 'x_end': x2, 'y_end': y2
        })

    # Add 2 to 4 solar pumps from the high-priority list
    pump_locs = SUITABILITY_DATA['solar_pump']['locations']
    if pump_locs:
        num_pumps = min(random.randint(2, 4), len(pump_locs))
        for i in range(num_pumps):
            x, y = random.choice(pump_locs)
            plan['solar_pumps'].append({
                'id': i, 'x': x, 'y': y,
                # <<< ADAPTED >>> Added a new parameter for the critic to evaluate
                'capacity_m3_day': random.uniform(50, 500) # Pumping capacity in m^3/day
            })
            
    return plan

def mate_plans(ind1, ind2):
    """Mates two plans by swapping their components."""
    child1_data, child2_data = {}, {}
    # <<< ADAPTED >>> Renamed keys
    for key in ['harvesting_ponds', 'recharge_structures', 'nbs_swales', 'solar_pumps']:
        if random.random() < 0.5:
            child1_data[key] = ind1.get(key, [])[:]
            child2_data[key] = ind2.get(key, [])[:]
        else:
            child1_data[key] = ind2.get(key, [])[:]
            child2_data[key] = ind1.get(key, [])[:]
    return creator.Individual(child1_data), creator.Individual(child2_data)

def mutate_plan(individual):
    """Mutates a plan by intelligently altering one of its components."""
    # <<< ADAPTED >>> Renamed keys
    possible_mutations = [key for key, val in individual.items() if val]
    if not possible_mutations: return (individual,)

    component_type = random.choice(possible_mutations)
    component = random.choice(individual[component_type])

    # <<< ADAPTED >>> Updated all component types and logic
    if component_type == 'harvesting_ponds':
        if random.random() < 0.5: component['x'], component['y'] = get_weighted_random_coords('harvesting_pond')
        else: component['radius'] = max(20, component['radius'] + random.uniform(-20, 20))
    
    elif component_type == 'recharge_structures':
        if random.random() < 0.5: component['x_start'], component['y_start'] = get_weighted_random_coords('recharge_structure')
        else: component['height'] = max(0.5, component['height'] + random.uniform(-0.5, 0.5))
    
    elif component_type == 'nbs_swales':
        component['x_start'], component['y_start'] = get_weighted_random_coords('nbs_swale')
    
    elif component_type == 'solar_pumps':
        pump_locs = SUITABILITY_DATA['solar_pump']['locations']
        if random.random() < 0.5 and pump_locs:
             component['x'], component['y'] = random.choice(pump_locs)
        else:
            # Mutate the new capacity parameter
            component['capacity_m3_day'] = max(50, component['capacity_m3_day'] + random.uniform(-100, 100))
        
    return (individual,)

def calculate_fitness(plan):
    """Calculates the fitness score using the external physics-based critic."""
    if CRITIC is None: return (float('inf'),)
    # <<< ADAPTED >>> This function call remains identical.
    # The *logic* inside the Critic will be changed in the next step.
    return CRITIC.evaluate(plan)

def export_intervention_kml(filename, plan, diagnostics_report):
    """Exports the full, multi-component plan to a KML file."""
    # <<< ADAPTED >>> Updated all titles, keys, and styles
    try:
        print(f"🌍 Exporting full water management plan to KML: '{filename}'...")
        kml = simplekml.Kml(name="Water Management Plan (v1.0 IWMI)")
        
        # Define styles
        pond_style = simplekml.Style(); pond_style.polystyle.color = simplekml.Color.hexa('A0FFD700') # Blue
        recharge_style = simplekml.Style(); recharge_style.linestyle.color = simplekml.Color.green; recharge_style.linestyle.width = 4
        swale_style = simplekml.Style(); swale_style.linestyle.color = simplekml.Color.brown; swale_style.linestyle.width = 3
        pump_style = simplekml.Style(); pump_style.iconstyle.icon.href = 'http://maps.google.com/mapfiles/kml/shapes/water.png'
        
        transformer = Transformer.from_crs(diagnostics_report['raster_profile']['crs'], "EPSG:4326", always_xy=True)
        
        for pond in plan.get('harvesting_ponds', []):
            center_x, center_y, radius = pond['x'], pond['y'], pond['radius']
            coords_utm = [(center_x + radius * math.cos(a), center_y + radius * math.sin(a)) for a in np.linspace(0, 2*math.pi, 37)]
            poly = kml.newpolygon(name=f"Harvesting Pond {pond['id']}", outerboundaryis=list(transformer.itransform(coords_utm)))
            poly.style = pond_style

        for structure in plan.get('recharge_structures', []):
            coords_utm = [(structure['x_start'], structure['y_start']), (structure['x_end'], structure['y_end'])]
            line = kml.newlinestring(name=f"Recharge Structure {structure['id']}", coords=list(transformer.itransform(coords_utm)))
            line.style = recharge_style

        for swale in plan.get('nbs_swales', []):
            coords_utm = [(swale['x_start'], swale['y_start']), (swale['x_end'], swale['y_end'])]
            line = kml.newlinestring(name=f"NbS Swale {swale['id']}", coords=list(transformer.itransform(coords_utm)))
            line.style = swale_style

        for pump in plan.get('solar_pumps', []):
            lon, lat = transformer.transform(pump['x'], pump['y'])
            pnt = kml.newpoint(name=f"Solar Pump {pump['id']}", coords=[(lon, lat)])
            pnt.style = pump_style
        
        kml.save(filename)
        print(f"✅ KML file '{filename}' saved successfully.")
    except Exception as e: print(f"❌ ERROR: Failed to export KML. Error: {e}")

def crop_rasters_to_zone(zone_bounds, output_dir, zone_suffix):
    """Crop DEM, population (demand), and stress (flood) rasters to zone bounds."""
    # <<< ADAPTED >>> This function's logic is sound. We are still using
    # these three exact files as our core inputs for the Critic.
    from shapely.geometry import box
    zone_geom = box(zone_bounds['left'], zone_bounds['bottom'],
                   zone_bounds['right'], zone_bounds['top'])
    cropped_files = []
    
    raster_files = [
        ("Data/GKP/DEM_GKP_UTM.tif", f"{output_dir}/cropped_dem_{zone_suffix}.tif"),
        ("Data/GKP/Population_GKP_UTM_aligned.tif", f"{output_dir}/cropped_pop_demand_{zone_suffix}.tif"),
        ("Data/GKP/Flood_GKP_UTM.tif", f"{output_dir}/cropped_water_stress_{zone_suffix}.tif")
    ]

    for src_path, dst_path in raster_files:
        try:
            with rasterio.open(src_path) as src:
                cropped_data, cropped_transform = mask(src, [zone_geom], crop=True, nodata=src.nodata)
                cropped_profile = src.profile.copy()
                cropped_profile.update({
                    'height': cropped_data.shape[1],
                    'width': cropped_data.shape[2],
                    'transform': cropped_transform
                })
                with rasterio.open(dst_path, 'w', **cropped_profile) as dst:
                    dst.write(cropped_data[0], 1)
            cropped_files.append(dst_path)
            print(f"    ✅ Cropped {src_path.split('/')[-1]}: {cropped_data.shape[1]}×{cropped_data.shape[2]} pixels")
        except Exception as e:
            print(f"    ⚠️ Failed to crop {src_path}: {e}")
            cropped_files.append(src_path)

    return cropped_files[0], cropped_files[1], cropped_files[2]  # dem, pop (demand), flood (stress)

def generate_elevation_outputs(output_dir, zone_results, atlas_paths):
    """Generate elevation data outputs: TIF, contour PNG, and SHP boundary."""
    # <<< ADAPTED >>> Updated all titles, labels, keys, and colors
    try:
        import matplotlib.pyplot as plt
        import geopandas as gpd
        from shapely.geometry import box
        from matplotlib.patches import Circle
        import matplotlib.lines as mlines

        print("🏔️ Generating elevation data outputs...")
        best_zone = min(zone_results, key=lambda x: x['best_fitness'])
        zone_bounds = best_zone['bounds']
        best_plan = best_zone['intervention_plan']

        dem_path = "Data/GKP/DEM_GKP_UTM.tif"
        if not os.path.exists(dem_path):
            dem_path = atlas_paths.get('harvesting_pond_suitability.tif')

        if '.tif' in dem_path:
            with rasterio.open(dem_path) as src:
                zone_geom = box(zone_bounds['left'], zone_bounds['bottom'],
                              zone_bounds['right'], zone_bounds['top'])
                dem_data, dem_transform = mask(src, [zone_geom], crop=True, nodata=src.nodata)
                dem_data = dem_data[0].astype(np.float32)
                if src.nodata is not None:
                    dem_data[dem_data == src.nodata] = np.nan

                # 1. Save elevation TIF
                tif_path = f"{output_dir}/micro_aoi_elevation.tif"
                profile = src.profile.copy()
                profile.update({'height': dem_data.shape[0], 'width': dem_data.shape[1], 'transform': dem_transform})
                with rasterio.open(tif_path, 'w', **profile) as dst:
                    dst.write(dem_data, 1)
                print(f"    ✅ Elevation TIF saved: {tif_path}")

                # 2. Create contour PNG
                fig = plt.figure(figsize=(16, 10))
                ax = fig.add_axes([0.05, 0.05, 0.75, 0.9])
                extent = [zone_bounds['left'], zone_bounds['right'], zone_bounds['bottom'], zone_bounds['top']]
                im = ax.imshow(dem_data, extent=extent, cmap='terrain', alpha=0.8, origin='upper')
                elev_min, elev_max = np.nanmin(dem_data), np.nanmax(dem_data)
                levels = np.linspace(elev_min, elev_max, 10)
                ax.contour(dem_data, levels=levels, colors='black', linewidths=0.8, extent=extent, alpha=0.6)
                cbar_ax = fig.add_axes([0.82, 0.05, 0.03, 0.9])
                cbar = plt.colorbar(im, cax=cbar_ax)
                cbar.set_label('Elevation (m)', rotation=270, labelpad=15)

                # Overlay infrastructure
                try:
                    roads_gdf = gpd.read_file("Data/GKP/Gorakhpur_roads.shp").cx[zone_bounds['left']:zone_bounds['right'], zone_bounds['bottom']:zone_bounds['top']]
                    if not roads_gdf.empty: roads_gdf.plot(ax=ax, color='gray', linewidth=1, alpha=0.6, label='Roads')
                except: pass
                try:
                    buildings_gdf = gpd.read_file("Data/GKP/Gorakhpur_Buildings.shp").cx[zone_bounds['left']:zone_bounds['right'], zone_bounds['bottom']:zone_bounds['top']]
                    if not buildings_gdf.empty: buildings_gdf.plot(ax=ax, color='red', alpha=0.3, label='Buildings')
                except: pass

                # Plot interventions
                for pond in best_plan.get('harvesting_ponds', []):
                    circle = Circle((pond['x'], pond['y']), pond['radius'], facecolor='blue', alpha=0.7, edgecolor='darkblue', linewidth=2)
                    ax.add_patch(circle)
                    ax.text(pond['x'], pond['y'], f"P{pond['id']}", ha='center', va='center', fontsize=12, fontweight='bold', color='white')
                
                for structure in best_plan.get('recharge_structures', []):
                    ax.plot([structure['x_start'], structure['x_end']], [structure['y_start'], structure['y_end']], color='green', linewidth=4, alpha=0.9)
                    mid_x, mid_y = (structure['x_start'] + structure['x_end']) / 2, (structure['y_start'] + structure['y_end']) / 2
                    ax.text(mid_x, mid_y, f"R{structure['id']}", ha='center', va='center', fontsize=11, fontweight='bold', color='white', bbox=dict(boxstyle="round,pad=0.3", facecolor="green", alpha=0.9))

                for swale in best_plan.get('nbs_swales', []):
                    ax.plot([swale['x_start'], swale['x_end']], [swale['y_start'], swale['y_end']], color='brown', linewidth=3, alpha=0.8, linestyle='--')
                    mid_x, mid_y = (swale['x_start'] + swale['x_end']) / 2, (swale['y_start'] + swale['y_end']) / 2
                    ax.text(mid_x, mid_y, f"S{swale['id']}", ha='center', va='center', fontsize=10, fontweight='bold', color='white', bbox=dict(boxstyle="round,pad=0.2", facecolor="brown", alpha=0.8))

                for pump in best_plan.get('solar_pumps', []):
                    ax.scatter(pump['x'], pump['y'], c='orange', s=150, marker='P', alpha=0.9, edgecolors='darkorange', linewidth=3)
                    ax.text(pump['x'], pump['y'], f"SP{pump['id']}", ha='center', va='center', fontsize=10, fontweight='bold', color='white')

                ax.set_xlabel('Easting (UTM Zone 48N)', fontsize=12) # <<< ADAPTED >>> Corrected UTM Zone
                ax.set_ylabel('Northing (UTM Zone 48N)', fontsize=12)
                ax.set_title(f'Micro-AOI Elevation & Water Interventions\n{zone_bounds["left"]:.0f} to {zone_bounds["right"]:.0f} E, {zone_bounds["bottom"]:.0f} to {zone_bounds["top"]:.0f} N', fontsize=14, fontweight='bold')

                # Legend
                legend_elements = [
                    mlines.Line2D([], [], color='black', linewidth=0.8, label=f'Elevation Contours ({elev_min:.1f} - {elev_max:.1f} m)'),
                    Circle((0, 0), 1, facecolor='blue', alpha=0.7, edgecolor='darkblue', label='Harvesting Ponds'),
                    mlines.Line2D([], [], color='green', linewidth=4, label='Recharge Structures'),
                    mlines.Line2D([], [], color='brown', linewidth=3, linestyle='--', label='NbS Swales'),
                    plt.scatter([], [], c='orange', s=150, marker='P', edgecolors='darkorange', label='Solar Pumps'),
                    mlines.Line2D([], [], color='gray', linewidth=1, alpha=0.6, label='Roads'),
                    plt.Rectangle((0, 0), 1, 1, facecolor='red', alpha=0.3, label='Buildings')
                ]
                legend_ax = fig.add_axes([0.87, 0.05, 0.12, 0.9])
                legend_ax.legend(handles=legend_elements, loc='upper left', fontsize=10)
                legend_ax.axis('off')

                ax.set_aspect('equal')
                ax.set_xlim(zone_bounds['left'], zone_bounds['right'])
                ax.set_ylim(zone_bounds['bottom'], zone_bounds['top'])

                contour_png_path = f"{output_dir}/micro_aoi_elevation_contours.png"
                plt.savefig(contour_png_path, dpi=300, bbox_inches='tight')
                plt.close()
                print(f"    ✅ Elevation contour PNG saved: {contour_png_path}")

                # 3. Create SHP file for QGIS
                boundary_geom = box(zone_bounds['left'], zone_bounds['bottom'], zone_bounds['right'], zone_bounds['top'])
                # <<< ADAPTED >>> Corrected CRS to EPSG:32648 for Singapore UTM 48N
                boundary_gdf = gpd.GeoDataFrame({
                    'id': [1], 'name': [f'{best_zone["zone_name"]}'],
                    'area_km2': [best_zone.get('area_km2', 0)], 'fitness': [best_zone['best_fitness']]
                }, geometry=[boundary_geom], crs='EPSG:32648') 
                shp_path = f"{output_dir}/micro_aoi_boundary.shp"
                boundary_gdf.to_file(shp_path)
                print(f"    ✅ QGIS boundary SHP saved: {shp_path}")
        print("✅ Elevation data outputs complete!")
    except Exception as e:
        print(f"❌ ERROR generating elevation outputs: {e}")
        import traceback
        traceback.print_exc()

def generate_intervention_visualization(output_dir, zone_results, atlas_paths):
    """Generate PNG visualization of micro-AOI with intervention locations."""
    # <<< ADAPTED >>> This function is a simplified version of the one above.
    # All keys, titles, labels, and colors are updated.
    try:
        import matplotlib.pyplot as plt
        from matplotlib.patches import Circle
        import matplotlib.lines as mlines

        print("🖼️ Generating micro-AOI intervention visualization...")
        best_zone = min(zone_results, key=lambda x: x['best_fitness'])
        zone_bounds = best_zone['bounds']
        best_plan = best_zone['intervention_plan']

        dem_path = atlas_paths.get('harvesting_pond_suitability.tif', list(atlas_paths.values())[0])
        if '.tif' in dem_path:
            with rasterio.open(dem_path) as src:
                zone_geom = box(zone_bounds['left'], zone_bounds['bottom'], zone_bounds['right'], zone_bounds['top'])
                dem_data, dem_transform = mask(src, [zone_geom], crop=True, nodata=src.nodata)
                dem_data = dem_data[0]
                fig, ax = plt.subplots(1, 1, figsize=(12, 10))
                extent = [zone_bounds['left'], zone_bounds['right'], zone_bounds['bottom'], zone_bounds['top']]
                im = ax.imshow(dem_data, extent=extent, cmap='terrain', alpha=0.7, origin='upper')
                cbar = plt.colorbar(im, ax=ax, shrink=0.8)
                cbar.set_label('Suitability / Elevation (m)', rotation=270, labelpad=15)

                for pond in best_plan.get('harvesting_ponds', []):
                    circle = Circle((pond['x'], pond['y']), pond['radius'], facecolor='blue', alpha=0.6, edgecolor='darkblue', linewidth=2)
                    ax.add_patch(circle)
                    ax.text(pond['x'], pond['y'], f"P{pond['id']}", ha='center', va='center', fontsize=10, fontweight='bold', color='white')

                for structure in best_plan.get('recharge_structures', []):
                    ax.plot([structure['x_start'], structure['x_end']], [structure['y_start'], structure['y_end']], color='green', linewidth=3, alpha=0.8)
                    mid_x, mid_y = (structure['x_start'] + structure['x_end']) / 2, (structure['y_start'] + structure['y_end']) / 2
                    ax.text(mid_x, mid_y, f"R{structure['id']}", ha='center', va='center', fontsize=9, fontweight='bold', color='green', bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.8))

                for swale in best_plan.get('nbs_swales', []):
                    ax.plot([swale['x_start'], swale['x_end']], [swale['y_start'], swale['y_end']], color='brown', linewidth=2, alpha=0.8, linestyle='--')
                    mid_x, mid_y = (swale['x_start'] + swale['x_end']) / 2, (swale['y_start'] + swale['y_end']) / 2
                    ax.text(mid_x, mid_y, f"S{swale['id']}", ha='center', va='center', fontsize=8, fontweight='bold', color='brown', bbox=dict(boxstyle="round,pad=0.1", facecolor="white", alpha=0.8))

                for pump in best_plan.get('solar_pumps', []):
                    ax.scatter(pump['x'], pump['y'], c='orange', s=100, marker='P', alpha=0.9, edgecolors='darkorange', linewidth=2)
                    ax.text(pump['x'], pump['y'], f"SP{pump['id']}", ha='center', va='center', fontsize=8, fontweight='bold', color='white')
                
                # <<< ADAPTED >>> Corrected UTM Zone
                ax.set_xlabel('Easting (UTM Zone 48N)', fontsize=12)
                ax.set_ylabel('Northing (UTM Zone 48N)', fontsize=12)
                area_info = best_zone.get("area_km2", "N/A")
                area_text = f'Fitness: {best_zone["best_fitness"]:.4f} | Area: {area_info:.1f} km²' if isinstance(area_info, (int, float)) else f'Fitness: {best_zone["best_fitness"]:.4f}'
                ax.set_title(f'Micro-AOI Water Management Plan: {best_zone["zone_name"]}\n{area_text}', fontsize=14, fontweight='bold')

                legend_elements = [
                    Circle((0, 0), 1, facecolor='blue', alpha=0.6, edgecolor='darkblue', label='Harvesting Ponds'),
                    mlines.Line2D([], [], color='green', linewidth=3, label='Recharge Structures'),
                    mlines.Line2D([], [], color='brown', linewidth=2, linestyle='--', label='NbS Swales'),
                    plt.scatter([], [], c='orange', s=100, marker='P', edgecolors='darkorange', label='Solar Pumps')
                ]
                ax.legend(handles=legend_elements, loc='upper right', fontsize=10)
                ax.set_aspect('equal')
                plt.tight_layout()
                png_path = f"{output_dir}/micro_aoi_interventions.png"
                plt.savefig(png_path, dpi=300, bbox_inches='tight')
                plt.close()
                print(f"✅ Intervention visualization saved: '{png_path}'")
    except Exception as e:
        print(f"❌ ERROR generating visualization: {e}")

def optimize_zone(zone_config, atlas_paths, output_dir):
    """Run genetic algorithm optimization for a specific zone."""
    zone_id = zone_config['zone_id']
    zone_name = zone_config['zone_name']
    print(f"\n🏙️ OPTIMIZING ZONE {zone_id}: {zone_name}")
    print("-" * 50)
    zone_bounds = zone_config['bounds']
    load_zone_suitability_maps(atlas_paths, zone_bounds)

    print("  -> 🎯 Creating cropped rasters for micro-AOI performance...")
    # <<< ADAPTED >>> Updated filenames for clarity
    cropped_dem_path, cropped_pop_demand_path, cropped_water_stress_path = crop_rasters_to_zone(
        zone_bounds, output_dir, f"zone_{zone_id}"
    )
    global ZONE_TRANSFORM
    with rasterio.open(cropped_dem_path) as src:
        ZONE_TRANSFORM = src.transform

    # Initialize zone-specific critic
    global CRITIC
    # <<< ADAPTED >>> Pass the new paths to the Critic.
    # The Critic class (in the *next* file) will be adapted to understand
    # that "population_map" is now "demand" and "flood_map" is now "stress".
    CRITIC = Critic(
        dem_path=cropped_dem_path,
        population_map_path=cropped_pop_demand_path,
        flood_map_path=cropped_water_stress_path
    )

    # Setup genetic algorithm
    creator.create("FitnessMin", base.Fitness, weights=(-1.0,))
    creator.create("Individual", dict, fitness=creator.FitnessMin)
    toolbox = base.Toolbox()
    toolbox.register("individual", lambda: creator.Individual(generate_random_intervention_plan()))
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)
    toolbox.register("evaluate", calculate_fitness)
    toolbox.register("mate", mate_plans)
    toolbox.register("mutate", mutate_plan)
    toolbox.register("select", tools.selTournament, tournsize=3)
    
    POP_SIZE = 50; CXPB, MUTPB, NGEN = 0.7, 0.3, 15
    print(f"  [INFO] Zone {zone_id}: {NGEN} generations, population of {POP_SIZE}...")

    pop = toolbox.population(n=POP_SIZE)
    stats = tools.Statistics(lambda ind: ind.fitness.values)
    stats.register("avg", np.mean); stats.register("min", np.min)
    pop, logbook = algorithms.eaSimple(pop, toolbox, cxpb=CXPB, mutpb=MUTPB, ngen=NGEN, stats=stats, verbose=False)

    best_plan = tools.selBest(pop, 1)[0]
    zone_result = {
        'zone_id': zone_id,
        'zone_name': zone_name,
        'bounds': zone_bounds,
        'best_fitness': best_plan.fitness.values[0],
        'intervention_plan': best_plan,
        # <<< ADAPTED >>> Renamed key
        'opportunity_demand_score': zone_config.get('opportunity_demand_score', 0)
    }
    print(f"  ✅ Zone {zone_id} optimized - Best fitness: {best_plan.fitness.values[0]:.4f}")
    return zone_result

if __name__ == "__main__":
    # <<< ADAPTED >>> Updated all titles and file names
    print("="*80); print("🏛️  LAUNCHING STAGE 2: AI WATER MANAGEMENT PLANNER (v1.0 IWMI)"); print("="*80)
    output_dir = os.environ.get('GORAKHPUR_OUTPUT_DIR', f"Outputs/Water_Run_{datetime.now().strftime('%Y%m%d_%HM%S')}")
    os.makedirs(output_dir, exist_ok=True); print(f"📁 Using output directory: {output_dir}")
    log_file = open(f"{output_dir}/stage2_planner.log", 'w'); sys.stdout = Tee(sys.stdout, log_file); sys.stderr = Tee(sys.stderr, log_file)

    try:
        if len(sys.argv) < 2: print("❌ FATAL ERROR: Requires opportunity_zones_config.json as input."); sys.exit(1)
        
        config_file = sys.argv[1]; print(f"🎯 Received Priority Zones from: '{config_file}'")
        with open(config_file, 'r') as f: zones_config = json.load(f)

        diag_file = zones_config['stage1_diagnostics']
        with open(diag_file, 'r') as f: diagnostics_report = json.load(f)

        atlas_paths = diagnostics_report['atlas_paths']
        RASTER_PROFILE = diagnostics_report['raster_profile']

        zone_results = []
        for zone_config_file in zones_config['zone_configs']:
            with open(zone_config_file, 'r') as f:
                zone_config = json.load(f)
            zone_result = optimize_zone(zone_config, atlas_paths, output_dir)
            zone_results.append(zone_result)

        print(f"\n🏆 MULTI-ZONE OPTIMIZATION COMPLETE 🏆")
        print(f"Optimized {len(zone_results)} priority zones")
        best_overall = min(zone_results, key=lambda x: x['best_fitness'])
        best_plan = best_overall['intervention_plan']
        print(f"Best overall fitness: {best_overall['best_fitness']:.4f} (Zone {best_overall['zone_id']}: {best_overall['zone_name']})")

        # Save comprehensive results
        def make_json_serializable(obj):
            if isinstance(obj, np.integer): return int(obj)
            elif isinstance(obj, np.floating): return float(obj)
            elif isinstance(obj, np.ndarray): return obj.tolist()
            elif isinstance(obj, dict): return {key: make_json_serializable(value) for key, value in obj.items()}
            elif isinstance(obj, list): return [make_json_serializable(item) for item in obj]
            else: return obj

        comprehensive_result = {
            'optimization_summary': {
                'total_zones': len(zone_results),
                'best_zone': best_overall['zone_id'],
                'best_zone_name': best_overall['zone_name'],
                'best_fitness': float(best_overall['best_fitness'])
            },
            'zone_results': make_json_serializable(zone_results),
            'optimal_plan': make_json_serializable(best_plan)
        }
        
        plan_path = f'{output_dir}/water_management_plan.json'
        with open(plan_path, 'w') as f: json.dump(comprehensive_result, f, indent=2)
        print(f"\n✅ Comprehensive results saved to '{plan_path}'")

        export_intervention_kml(f"{output_dir}/water_management_plan.kml", best_plan, diagnostics_report)
        generate_intervention_visualization(output_dir, zone_results, atlas_paths)
        generate_elevation_outputs(output_dir, zone_results, atlas_paths)

    finally:
        sys.stdout = sys.stdout.files[0] if isinstance(sys.stdout, Tee) else sys.stdout
        sys.stderr = sys.stderr.files[0] if isinstance(sys.stderr, Tee) else sys.stderr
        if 'log_file' in locals() and not log_file.closed: log_file.close()