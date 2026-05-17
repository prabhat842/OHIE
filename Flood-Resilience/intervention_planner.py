# ==============================================================================
# Project: Gorakhpur Urban Resilience AI
# FILE NAME: intervention_planner.py
# VERSION: 3.0 (Strategic Atlas Integration)
# PURPOSE: To use a genetic algorithm to evolve an optimal, multi-component
#          flood intervention plan. This version is guided by the full strategic
#          atlas from Stage 1 and evaluated by a physics-based critic.
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

# Import the new, intelligent Critic
from intervention_rules import Critic

class Tee:
    def __init__(self, *files): self.files = files
    def write(self, obj):
        for f in self.files: f.write(obj); f.flush()
    def flush(self):
        for f in self.files: f.flush()

# --- Global variables for suitability maps and critic ---
# These dictionaries will hold the loaded suitability data
SUITABILITY_DATA = {
    'pond': {'map': None, 'indices': None, 'probs': None},
    'levee': {'map': None, 'indices': None, 'probs': None},
    'bioswale': {'map': None, 'indices': None, 'probs': None},
    'culvert': {'locations': []}
}
RASTER_PROFILE = None
CRITIC = None # The single instance of our physics-based critic

def load_zone_suitability_maps(atlas_paths, zone_bounds):
    """Loads suitability maps cropped to a specific zone bounds."""
    print(f"  -> Loading Strategic Atlas for zone: {zone_bounds}")

    # Create geometry for zone bounds
    zone_geom = box(zone_bounds['left'], zone_bounds['bottom'],
                   zone_bounds['right'], zone_bounds['top'])

    for intervention_type, path in atlas_paths.items():
        if path.endswith('.tif'):
            map_key = intervention_type.split('_')[0] # 'pond', 'levee', 'bioswale'
            with rasterio.open(path) as src:
                # Crop to zone bounds
                try:
                    cropped_data, cropped_transform = mask(src, [zone_geom], crop=True, nodata=src.nodata)
                    suitability_map = cropped_data[0]  # Remove single band dimension
                    suitability_map[suitability_map < 0] = 0 # Ignore negative scores
                    total_score = np.sum(suitability_map)

                    SUITABILITY_DATA[map_key]['map'] = suitability_map
                    SUITABILITY_DATA[map_key]['indices'] = np.arange(suitability_map.size)
                    if total_score > 0:
                        SUITABILITY_DATA[map_key]['probs'] = (suitability_map / total_score).flatten()
                    else: # Fallback if map has no positive scores
                        SUITABILITY_DATA[map_key]['probs'] = np.ones(suitability_map.size) / suitability_map.size
                except Exception as e:
                    print(f"    ⚠️ Could not crop {map_key} map to zone: {e}")
                    # Fallback to full map if cropping fails
                    suitability_map = src.read(1)
                    suitability_map[suitability_map < 0] = 0
                    SUITABILITY_DATA[map_key]['map'] = suitability_map
                    SUITABILITY_DATA[map_key]['indices'] = np.arange(suitability_map.size)

        elif path.endswith('.shp'):
            gdf = gpd.read_file(path)
            # Filter culvert locations to zone bounds
            zone_culverts = gdf[gdf.geometry.within(zone_geom)]
            SUITABILITY_DATA['culvert']['locations'] = [(p.x, p.y) for p in zone_culverts.geometry]
            print(f"    - Found {len(zone_culverts)} culvert opportunities in zone")

    # Set zone-specific transform for coordinate generation
    global ZONE_TRANSFORM, RASTER_PROFILE
    # Use the profile from the cropped DEM that will be used by the Critic
    # For now, keep the original - will be updated when cropped rasters are created
    ZONE_TRANSFORM = Affine(*RASTER_PROFILE['transform'])

    print("  - ✅ Zone atlas loaded successfully.")

def get_weighted_random_coords(intervention_type, min_suitability=0.1):
    """Selects random coordinates, guided by suitability map and spatially constrained."""
    data = SUITABILITY_DATA[intervention_type]

    # Option 2: Spatial constraints - only place interventions in high-suitability areas
    suitability_map = data['map']

    # Find pixels with sufficient suitability (above threshold and not nodata)
    if hasattr(suitability_map, 'mask'):  # Handle masked arrays
        valid_pixels = (~suitability_map.mask) & (suitability_map >= min_suitability)
    else:
        valid_pixels = (suitability_map >= min_suitability)

    if not np.any(valid_pixels):
        # Fallback: use any non-zero pixels
        valid_pixels = suitability_map > 0

    if not np.any(valid_pixels):
        # Ultimate fallback: any pixel
        valid_pixels = np.ones_like(suitability_map, dtype=bool)

    # Get indices of valid pixels
    valid_indices = np.where(valid_pixels.flatten())[0]

    if len(valid_indices) == 0:
        # Should not happen, but fallback to original method
        chosen_index = np.random.choice(data['indices'], p=data['probs'])
    else:
        # Choose from valid pixels only
        chosen_index = np.random.choice(valid_indices)

    row, col = np.unravel_index(chosen_index, suitability_map.shape)

    # Use zone-specific transform (will be set when zone is loaded)
    global ZONE_TRANSFORM
    if 'ZONE_TRANSFORM' in globals():
        transform = ZONE_TRANSFORM
    else:
        transform = Affine(*RASTER_PROFILE['transform'])

    x, y = transform * (col + 0.5, row + 0.5)
    return x, y

def generate_random_intervention_plan():
    """Generates a comprehensive plan using ALL four intervention types with higher counts."""
    plan = {'retention_ponds': [], 'levees': [], 'bioswales': [], 'culvert_upgrades': []}

    # Add 2 to 5 retention ponds (increased for comprehensive coverage)
    for i in range(random.randint(2, 5)):
        x, y = get_weighted_random_coords('pond')
        plan['retention_ponds'].append({
            'id': i, 'x': x, 'y': y,
            'radius': random.uniform(30, 100), 'depth': random.uniform(2, 5)
        })

    # Add 3 to 6 levees (increased for comprehensive coverage)
    for i in range(random.randint(3, 6)):
        x1, y1 = get_weighted_random_coords('levee')
        x2, y2 = get_weighted_random_coords('levee')
        plan['levees'].append({
            'id': i, 'x_start': x1, 'y_start': y1, 'x_end': x2, 'y_end': y2,
            'height': random.uniform(1.0, 3.0)
        })

    # Add 4 to 8 bioswales (increased for comprehensive coverage)
    for i in range(random.randint(4, 8)):
        x1, y1 = get_weighted_random_coords('bioswale')
        x2, y2 = get_weighted_random_coords('bioswale')
        plan['bioswales'].append({
            'id': i, 'x_start': x1, 'y_start': y1, 'x_end': x2, 'y_end': y2
        })

    # Add 2 to 4 culvert upgrades from the high-priority list
    culvert_locs = SUITABILITY_DATA['culvert']['locations']
    if culvert_locs:
        num_culverts = min(random.randint(2, 4), len(culvert_locs))
        for i in range(num_culverts):
            x, y = random.choice(culvert_locs)
            plan['culvert_upgrades'].append({'id': i, 'x': x, 'y': y})
            
    return plan

def mate_plans(ind1, ind2):
    """Mates two plans by swapping their components."""
    # A simple crossover that swaps entire component lists
    child1_data, child2_data = {}, {}
    for key in ['retention_ponds', 'levees', 'bioswales', 'culvert_upgrades']:
        if random.random() < 0.5:
            child1_data[key] = ind1.get(key, [])[:]
            child2_data[key] = ind2.get(key, [])[:]
        else:
            child1_data[key] = ind2.get(key, [])[:]
            child2_data[key] = ind1.get(key, [])[:]
    return creator.Individual(child1_data), creator.Individual(child2_data)

def mutate_plan(individual):
    """Mutates a plan by intelligently altering one of its components."""
    # Choose a component type that actually exists in the plan
    possible_mutations = [key for key, val in individual.items() if val]
    if not possible_mutations: return (individual,) # Cannot mutate an empty plan

    component_type = random.choice(possible_mutations)
    component = random.choice(individual[component_type])

    if component_type == 'retention_ponds':
        if random.random() < 0.5: component['x'], component['y'] = get_weighted_random_coords('pond')
        else: component['radius'] = max(20, component['radius'] + random.uniform(-20, 20))
    elif component_type == 'levees':
        if random.random() < 0.5: component['x_start'], component['y_start'] = get_weighted_random_coords('levee')
        else: component['height'] = max(0.5, component['height'] + random.uniform(-0.5, 0.5))
    elif component_type == 'bioswales':
        component['x_start'], component['y_start'] = get_weighted_random_coords('bioswale')
    elif component_type == 'culvert_upgrades':
        culvert_locs = SUITABILITY_DATA['culvert']['locations']
        if culvert_locs: component['x'], component['y'] = random.choice(culvert_locs)
        
    return (individual,)

def calculate_fitness(plan):
    """Calculates the fitness score using the external physics-based critic."""
    if CRITIC is None: return (float('inf'),)
    # The complex simulation is now handled by one simple call
    return CRITIC.evaluate(plan)

def export_intervention_kml(filename, plan, diagnostics_report):
    """Exports the full, multi-component plan to a KML file."""
    try:
        print(f"🌍 Exporting full intervention plan to KML: '{filename}'...")
        kml = simplekml.Kml(name="Gorakhpur Flood Intervention Plan (v3.0)")
        # Define styles for each intervention type
        pond_style = simplekml.Style(); pond_style.polystyle.color = simplekml.Color.hexa('A0FFD700')
        levee_style = simplekml.Style(); levee_style.linestyle.color = simplekml.Color.red; levee_style.linestyle.width = 4
        swale_style = simplekml.Style(); swale_style.linestyle.color = simplekml.Color.green; swale_style.linestyle.width = 3
        culvert_style = simplekml.Style(); culvert_style.iconstyle.icon.href = 'http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png'
        
        transformer = Transformer.from_crs(diagnostics_report['raster_profile']['crs'], "EPSG:4326", always_xy=True)
        
        for pond in plan.get('retention_ponds', []):
            center_x, center_y, radius = pond['x'], pond['y'], pond['radius']
            coords_utm = [(center_x + radius * math.cos(a), center_y + radius * math.sin(a)) for a in np.linspace(0, 2*math.pi, 37)]
            poly = kml.newpolygon(name=f"Pond {pond['id']}", outerboundaryis=list(transformer.itransform(coords_utm)))
            poly.style = pond_style

        for levee in plan.get('levees', []):
            coords_utm = [(levee['x_start'], levee['y_start']), (levee['x_end'], levee['y_end'])]
            line = kml.newlinestring(name=f"Levee {levee['id']}", coords=list(transformer.itransform(coords_utm)))
            line.style = levee_style

        for swale in plan.get('bioswales', []):
            coords_utm = [(swale['x_start'], swale['y_start']), (swale['x_end'], swale['y_end'])]
            line = kml.newlinestring(name=f"Bioswale {swale['id']}", coords=list(transformer.itransform(coords_utm)))
            line.style = swale_style

        for culvert in plan.get('culvert_upgrades', []):
            lon, lat = transformer.transform(culvert['x'], culvert['y'])
            pnt = kml.newpoint(name=f"Culvert Upgrade {culvert['id']}", coords=[(lon, lat)])
            pnt.style = culvert_style
        
        kml.save(filename)
        print(f"✅ KML file '{filename}' saved successfully.")
    except Exception as e: print(f"❌ ERROR: Failed to export KML. Error: {e}")

def crop_rasters_to_zone(zone_bounds, output_dir, zone_suffix):
    """Crop DEM, population, and flood rasters to zone bounds for micro-AOI performance."""
    from shapely.geometry import box

    # Create zone geometry
    zone_geom = box(zone_bounds['left'], zone_bounds['bottom'],
                   zone_bounds['right'], zone_bounds['top'])

    cropped_files = []

    # Source files
    raster_files = [
        ("SGP_Data/DEM/DEM_SGP_UTM48.tif", f"{output_dir}/cropped_dem_{zone_suffix}.tif"),
        ("SGP_Data/Population/population_sgp.tif", f"{output_dir}/cropped_pop_{zone_suffix}.tif"),
        ("SGP_Data/Floods/flood_sgp_utm48.tif", f"{output_dir}/cropped_flood_{zone_suffix}.tif")
    ]

    for src_path, dst_path in raster_files:
        try:
            with rasterio.open(src_path) as src:
                # Crop to zone bounds
                cropped_data, cropped_transform = mask(src, [zone_geom], crop=True, nodata=src.nodata)

                # Create new profile for cropped raster
                cropped_profile = src.profile.copy()
                cropped_profile.update({
                    'height': cropped_data.shape[1],
                    'width': cropped_data.shape[2],
                    'transform': cropped_transform
                })

                # Save cropped raster
                with rasterio.open(dst_path, 'w', **cropped_profile) as dst:
                    dst.write(cropped_data[0], 1)  # Remove band dimension

            cropped_files.append(dst_path)
            print(f"    ✅ Cropped {src_path.split('/')[-1]}: {cropped_data.shape[1]}×{cropped_data.shape[2]} pixels")

        except Exception as e:
            print(f"    ⚠️ Failed to crop {src_path}: {e}")
            # Fallback to original file
            cropped_files.append(src_path)

    return cropped_files[0], cropped_files[1], cropped_files[2]  # dem, pop, flood

def generate_elevation_outputs(output_dir, zone_results, atlas_paths):
    """Generate elevation data outputs: TIF, contour PNG, and SHP boundary."""
    try:
        import matplotlib.pyplot as plt
        import geopandas as gpd
        from shapely.geometry import box
        from matplotlib.patches import Circle, Rectangle
        import matplotlib.lines as mlines

        print("🏔️ Generating elevation data outputs...")

        # Get the best zone
        best_zone = min(zone_results, key=lambda x: x['best_fitness'])
        zone_bounds = best_zone['bounds']
        best_plan = best_zone['intervention_plan']

        # Load the actual DEM for elevation data (not suitability maps)
        dem_path = "SGP_Data/DEM/DEM_SGP_UTM48.tif"
        if not os.path.exists(dem_path):
            # Fallback to suitability maps if DEM not found
            dem_path = atlas_paths.get('pond_suitability_map', atlas_paths.get('levee_suitability_map', atlas_paths.get('elevation_map')))

        if '.tif' in dem_path:
            with rasterio.open(dem_path) as src:
                # Crop DEM to zone bounds
                from shapely.geometry import box
                zone_geom = box(zone_bounds['left'], zone_bounds['bottom'],
                              zone_bounds['right'], zone_bounds['top'])
                dem_data, dem_transform = mask(src, [zone_geom], crop=True, nodata=src.nodata)
                dem_data = dem_data[0]  # Remove band dimension

                # Handle nodata values - convert to float for NaN handling
                dem_data = dem_data.astype(np.float32)
                if src.nodata is not None:
                    dem_data[dem_data == src.nodata] = np.nan

                # 1. Save elevation TIF
                tif_path = f"{output_dir}/micro_aoi_elevation.tif"
                profile = src.profile.copy()
                profile.update({
                    'height': dem_data.shape[0],
                    'width': dem_data.shape[1],
                    'transform': dem_transform
                })
                with rasterio.open(tif_path, 'w', **profile) as dst:
                    dst.write(dem_data, 1)
                print(f"    ✅ Elevation TIF saved: {tif_path}")

                # 2. Create contour PNG with infrastructure overlay
                # Use a larger figure with space for legend outside plot area
                fig = plt.figure(figsize=(16, 10))
                # Create main axis for map, leaving space on right for legend
                ax = fig.add_axes([0.05, 0.05, 0.75, 0.9])  # [left, bottom, width, height]

                # Plot DEM as background with terrain colormap
                extent = [zone_bounds['left'], zone_bounds['right'],
                         zone_bounds['bottom'], zone_bounds['top']]
                im = ax.imshow(dem_data, extent=extent, cmap='terrain', alpha=0.8, origin='upper')

                # Add elevation contours (remove inline labels for cleaner look)
                # Create custom contour levels based on elevation range
                elev_min = np.nanmin(dem_data)
                elev_max = np.nanmax(dem_data)
                elev_range = elev_max - elev_min

                if elev_range > 50:  # Significant elevation variation
                    levels = np.linspace(elev_min, elev_max, 10)
                else:  # Flat terrain
                    levels = np.linspace(elev_min, elev_max, 5)

                contours = ax.contour(dem_data, levels=levels, colors='black', linewidths=0.8,
                                    extent=extent, alpha=0.6)
                # Remove inline labels for cleaner appearance

                # Add colorbar in the space to the right
                cbar_ax = fig.add_axes([0.82, 0.05, 0.03, 0.9])  # [left, bottom, width, height]
                cbar = plt.colorbar(im, cax=cbar_ax)
                cbar.set_label('Elevation (m)', rotation=270, labelpad=15)

                # Load and overlay infrastructure (roads, buildings, etc.)
                try:
                    # Try to load roads
                    roads_gdf = gpd.read_file("SGP_Data/Roads/roads.shp")
                    if not roads_gdf.empty:
                        roads_gdf = roads_gdf.cx[zone_bounds['left']:zone_bounds['right'],
                                                zone_bounds['bottom']:zone_bounds['top']]
                        if not roads_gdf.empty:
                            roads_gdf.plot(ax=ax, color='gray', linewidth=1, alpha=0.6, label='Roads')
                except:
                    pass

                try:
                    # Try to load buildings
                    buildings_gdf = gpd.read_file("SGP_Data/Buildings/buildings.shp")
                    if not buildings_gdf.empty:
                        buildings_gdf = buildings_gdf.cx[zone_bounds['left']:zone_bounds['right'],
                                                       zone_bounds['bottom']:zone_bounds['top']]
                        if not buildings_gdf.empty:
                            buildings_gdf.plot(ax=ax, color='red', alpha=0.3, label='Buildings')
                except:
                    pass

                # Plot interventions with semi-transparent colors
                # Ponds (blue)
                for pond in best_plan.get('retention_ponds', []):
                    circle = Circle((pond['x'], pond['y']), pond['radius'],
                                  facecolor='blue', alpha=0.7, edgecolor='darkblue', linewidth=2)
                    ax.add_patch(circle)
                    ax.text(pond['x'], pond['y'], f"P{pond['id']}", ha='center', va='center',
                           fontsize=12, fontweight='bold', color='white',
                           bbox=dict(boxstyle="round,pad=0.2", facecolor="blue", alpha=0.8))

                # Levees (red)
                for levee in best_plan.get('levees', []):
                    ax.plot([levee['x_start'], levee['x_end']],
                           [levee['y_start'], levee['y_end']],
                           color='red', linewidth=4, alpha=0.9)
                    mid_x = (levee['x_start'] + levee['x_end']) / 2
                    mid_y = (levee['y_start'] + levee['y_end']) / 2
                    ax.text(mid_x, mid_y, f"L{levee['id']}", ha='center', va='center',
                           fontsize=11, fontweight='bold', color='white',
                           bbox=dict(boxstyle="round,pad=0.3", facecolor="red", alpha=0.9))

                # Bioswales (green)
                for swale in best_plan.get('bioswales', []):
                    ax.plot([swale['x_start'], swale['x_end']],
                           [swale['y_start'], swale['y_end']],
                           color='green', linewidth=3, alpha=0.8, linestyle='--')
                    mid_x = (swale['x_start'] + swale['x_end']) / 2
                    mid_y = (swale['y_start'] + swale['y_end']) / 2
                    ax.text(mid_x, mid_y, f"S{swale['id']}", ha='center', va='center',
                           fontsize=10, fontweight='bold', color='white',
                           bbox=dict(boxstyle="round,pad=0.2", facecolor="green", alpha=0.8))

                # Culverts (orange)
                for culvert in best_plan.get('culvert_upgrades', []):
                    ax.scatter(culvert['x'], culvert['y'], c='orange', s=150,
                             marker='s', alpha=0.9, edgecolors='darkorange', linewidth=3)
                    ax.text(culvert['x'], culvert['y'], f"C{culvert['id']}",
                           ha='center', va='center', fontsize=10, fontweight='bold', color='white')

                # Set labels and title
                ax.set_xlabel('Easting (UTM Zone 48N)', fontsize=12)
                ax.set_ylabel('Northing (UTM Zone 48N)', fontsize=12)
                ax.set_title(f'Micro-AOI Elevation & Interventions\n{zone_bounds["left"]:.0f} to {zone_bounds["right"]:.0f} E, {zone_bounds["bottom"]:.0f} to {zone_bounds["top"]:.0f} N',
                           fontsize=14, fontweight='bold')

                # Add legend with elevation range info
                elev_range_text = '.0f' if elev_range > 50 else '.1f'
                legend_elements = [
                    mlines.Line2D([], [], color='black', linewidth=0.8,
                                label=f'Elevation Contours ({elev_min:{elev_range_text}} - {elev_max:{elev_range_text}} m)'),
                    Circle((0, 0), 1, facecolor='blue', alpha=0.7, edgecolor='darkblue', label='Retention Ponds'),
                    mlines.Line2D([], [], color='red', linewidth=4, label='Levees'),
                    mlines.Line2D([], [], color='green', linewidth=3, linestyle='--', label='Bioswales'),
                    plt.scatter([], [], c='orange', s=150, marker='s', edgecolors='darkorange', label='Culvert Upgrades'),
                    mlines.Line2D([], [], color='gray', linewidth=1, alpha=0.6, label='Roads'),
                    plt.Rectangle((0, 0), 1, 1, facecolor='red', alpha=0.3, label='Buildings')
                ]
                # Add legend outside the main plot area
                legend_ax = fig.add_axes([0.87, 0.05, 0.12, 0.9])  # [left, bottom, width, height]
                legend_ax.legend(handles=legend_elements, loc='upper left', fontsize=10)
                legend_ax.axis('off')  # Hide the axes

                # Set equal aspect ratio and exact AOI bounds
                ax.set_aspect('equal')
                ax.set_xlim(zone_bounds['left'], zone_bounds['right'])
                ax.set_ylim(zone_bounds['bottom'], zone_bounds['top'])

                contour_png_path = f"{output_dir}/micro_aoi_elevation_contours.png"
                plt.savefig(contour_png_path, dpi=300, bbox_inches='tight')
                plt.close()

                print(f"    ✅ Elevation contour PNG saved: {contour_png_path}")

                # 3. Create SHP file for QGIS
                boundary_geom = box(zone_bounds['left'], zone_bounds['bottom'],
                                  zone_bounds['right'], zone_bounds['top'])
                boundary_gdf = gpd.GeoDataFrame({
                    'id': [1],
                    'name': [f'{best_zone["zone_name"]}'],
                    'area_km2': [best_zone.get('area_km2', 0)],
                    'fitness': [best_zone['best_fitness']]
                }, geometry=[boundary_geom], crs='EPSG:32644')  # UTM Zone 44N

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
    try:
        import matplotlib.pyplot as plt
        from matplotlib.patches import Circle, Rectangle
        import matplotlib.lines as mlines

        print("🖼️ Generating micro-AOI intervention visualization...")

        # Get the best zone for visualization
        best_zone = min(zone_results, key=lambda x: x['best_fitness'])
        zone_bounds = best_zone['bounds']
        best_plan = best_zone['intervention_plan']

        # Load the DEM for background
        dem_path = atlas_paths.get('pond_suitability_map', atlas_paths.get('levee_suitability_map', atlas_paths.get('elevation_map')))
        if '.tif' in dem_path:
            with rasterio.open(dem_path) as src:
                # Crop DEM to zone bounds
                from shapely.geometry import box
                zone_geom = box(zone_bounds['left'], zone_bounds['bottom'],
                              zone_bounds['right'], zone_bounds['top'])
                dem_data, dem_transform = mask(src, [zone_geom], crop=True, nodata=src.nodata)
                dem_data = dem_data[0]  # Remove band dimension

                # Create figure
                fig, ax = plt.subplots(1, 1, figsize=(12, 10))

                # Plot DEM as background
                extent = [zone_bounds['left'], zone_bounds['right'],
                         zone_bounds['bottom'], zone_bounds['top']]
                im = ax.imshow(dem_data, extent=extent, cmap='terrain', alpha=0.7, origin='upper')

                # Add colorbar
                cbar = plt.colorbar(im, ax=ax, shrink=0.8)
                cbar.set_label('Elevation (m)', rotation=270, labelpad=15)

                # Plot interventions
                # Ponds (circles)
                for pond in best_plan.get('retention_ponds', []):
                    circle = Circle((pond['x'], pond['y']), pond['radius'],
                                  facecolor='blue', alpha=0.6, edgecolor='darkblue', linewidth=2)
                    ax.add_patch(circle)
                    ax.text(pond['x'], pond['y'], f"P{pond['id']}", ha='center', va='center',
                           fontsize=10, fontweight='bold', color='white')

                # Levees (lines)
                for levee in best_plan.get('levees', []):
                    ax.plot([levee['x_start'], levee['x_end']],
                           [levee['y_start'], levee['y_end']],
                           color='red', linewidth=3, alpha=0.8)
                    # Add label at midpoint
                    mid_x = (levee['x_start'] + levee['x_end']) / 2
                    mid_y = (levee['y_start'] + levee['y_end']) / 2
                    ax.text(mid_x, mid_y, f"L{levee['id']}", ha='center', va='center',
                           fontsize=9, fontweight='bold', color='red',
                           bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.8))

                # Bioswales (green lines)
                for swale in best_plan.get('bioswales', []):
                    ax.plot([swale['x_start'], swale['x_end']],
                           [swale['y_start'], swale['y_end']],
                           color='green', linewidth=2, alpha=0.8, linestyle='--')
                    # Add label at midpoint
                    mid_x = (swale['x_start'] + swale['x_end']) / 2
                    mid_y = (swale['y_start'] + swale['y_end']) / 2
                    ax.text(mid_x, mid_y, f"S{swale['id']}", ha='center', va='center',
                           fontsize=8, fontweight='bold', color='green',
                           bbox=dict(boxstyle="round,pad=0.1", facecolor="white", alpha=0.8))

                # Culverts (points)
                for culvert in best_plan.get('culvert_upgrades', []):
                    ax.scatter(culvert['x'], culvert['y'], c='orange', s=100,
                             marker='s', alpha=0.9, edgecolors='darkorange', linewidth=2)
                    ax.text(culvert['x'], culvert['y'], f"C{culvert['id']}",
                           ha='center', va='center', fontsize=8, fontweight='bold', color='white')

                # Set labels and title
                ax.set_xlabel('Easting (UTM Zone 44N)', fontsize=12)
                ax.set_ylabel('Northing (UTM Zone 44N)', fontsize=12)
                # Format area safely
                area_info = best_zone.get("area_km2", "N/A")
                if isinstance(area_info, (int, float)):
                    area_text = f'Fitness: {best_zone["best_fitness"]:.4f} | Area: {area_info:.1f} km²'
                else:
                    area_text = f'Fitness: {best_zone["best_fitness"]:.4f} | Area: {area_info}'

                ax.set_title(f'Micro-AOI Intervention Plan: {best_zone["zone_name"]}\n{area_text}',
                           fontsize=14, fontweight='bold')

                # Add legend
                legend_elements = [
                    Circle((0, 0), 1, facecolor='blue', alpha=0.6, edgecolor='darkblue', label='Retention Ponds'),
                    mlines.Line2D([], [], color='red', linewidth=3, label='Levees'),
                    mlines.Line2D([], [], color='green', linewidth=2, linestyle='--', label='Bioswales'),
                    plt.scatter([], [], c='orange', s=100, marker='s', edgecolors='darkorange', label='Culvert Upgrades')
                ]
                ax.legend(handles=legend_elements, loc='upper right', fontsize=10)

                # Set equal aspect ratio
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

    # Load zone-specific suitability maps
    zone_bounds = zone_config['bounds']
    load_zone_suitability_maps(atlas_paths, zone_bounds)

    # Option 1: Crop rasters to zone bounds for true micro-AOI performance
    print("  -> 🎯 Creating cropped rasters for micro-AOI performance...")
    cropped_dem_path, cropped_pop_path, cropped_flood_path = crop_rasters_to_zone(
        zone_bounds, output_dir, f"zone_{zone_id}"
    )

    # Update zone transform to match cropped DEM
    global ZONE_TRANSFORM
    with rasterio.open(cropped_dem_path) as src:
        ZONE_TRANSFORM = src.transform

    # Initialize zone-specific critic with cropped rasters
    global CRITIC
    CRITIC = Critic(
        dem_path=cropped_dem_path,
        population_map_path=cropped_pop_path,
        flood_map_path=cropped_flood_path
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

    # Demo parameters for micro-AOI with interventions (balanced speed/results)
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
        'population_exposure': zone_config.get('population_exposure', 0)
    }

    print(f"  ✅ Zone {zone_id} optimized - Best fitness: {best_plan.fitness.values[0]:.4f}")

    return zone_result

if __name__ == "__main__":
    print("="*80); print("🏛️  LAUNCHING STAGE 2: AI INTERVENTION ARCHITECT (v3.0)"); print("="*80)
    output_dir = os.environ.get('GORAKHPUR_OUTPUT_DIR', f"Outputs/Run_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    os.makedirs(output_dir, exist_ok=True); print(f"📁 Using output directory: {output_dir}")
    log_file = open(f"{output_dir}/stage2_planner.log", 'w'); sys.stdout = Tee(sys.stdout, log_file); sys.stderr = Tee(sys.stderr, log_file)

    try:
        if len(sys.argv) < 2: print("❌ FATAL ERROR: Requires priority_zones_config.json as input."); sys.exit(1)

        config_file = sys.argv[1]; print(f"🎯 Received Priority Zones from: '{config_file}'")
        with open(config_file, 'r') as f: zones_config = json.load(f)

        # Load original diagnostics for atlas paths
        diag_file = zones_config['stage1_diagnostics']
        with open(diag_file, 'r') as f: diagnostics_report = json.load(f)

        atlas_paths = diagnostics_report['atlas_paths']
        RASTER_PROFILE = diagnostics_report['raster_profile']

        # Optimize each priority zone
        zone_results = []
        for zone_config_file in zones_config['zone_configs']:
            with open(zone_config_file, 'r') as f:
                zone_config = json.load(f)

            zone_result = optimize_zone(zone_config, atlas_paths, output_dir)
            zone_results.append(zone_result)

        # Aggregate results from all zones
        print(f"\n🏆 MULTI-ZONE OPTIMIZATION COMPLETE 🏆")
        print(f"Optimized {len(zone_results)} priority zones")

        # Find overall best plan (could be weighted by population exposure)
        best_overall = min(zone_results, key=lambda x: x['best_fitness'])
        best_plan = best_overall['intervention_plan']

        print(f"Best overall fitness: {best_overall['best_fitness']:.4f} (Zone {best_overall['zone_id']}: {best_overall['zone_name']})")

        # Save comprehensive results (convert numpy types to JSON-serializable)
        def make_json_serializable(obj):
            if isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, np.floating):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            elif isinstance(obj, dict):
                return {key: make_json_serializable(value) for key, value in obj.items()}
            elif isinstance(obj, list):
                return [make_json_serializable(item) for item in obj]
            else:
                return obj

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

        plan_path = f'{output_dir}/intervention_plan.json'
        with open(plan_path, 'w') as f: json.dump(comprehensive_result, f, indent=2)
        print(f"\n✅ Comprehensive results saved to '{plan_path}'")

        # Export KML for best plan
        export_intervention_kml(f"{output_dir}/intervention_plan.kml", best_plan, diagnostics_report)

        # Generate visualizations of micro-AOI with interventions
        generate_intervention_visualization(output_dir, zone_results, atlas_paths)

        # Generate elevation data outputs
        generate_elevation_outputs(output_dir, zone_results, atlas_paths)

    finally:
        sys.stdout = sys.stdout.files[0] if isinstance(sys.stdout, Tee) else sys.stdout
        sys.stderr = sys.stderr.files[0] if isinstance(sys.stderr, Tee) else sys.stderr
        if 'log_file' in locals() and not log_file.closed: log_file.close()