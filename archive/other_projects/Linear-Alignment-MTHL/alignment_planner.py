# ==============================================================================
# Project: Culturiq AI-Driven Infrastructure
# FILE NAME: alignment_planner.py
# VERSION: 1.0 (Adapted from intervention_planner.py v3.0)
# PURPOSE: To use a Genetic Algorithm (GA) to evolve an optimal, low-cost
#          alignment (path) for linear infrastructure, guided by the Cost
#          Atlases from Stage 1 and evaluated by a path-based critic.
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

# <<< ADAPTED >>> Import the new, path-based critic.
# This file (alignment_rules.py) will be created in the next step.
from alignment_rules import Critic

class Tee:
    def __init__(self, *files): self.files = files
    def write(self, obj):
        for f in self.files: f.write(obj); f.flush()
    def flush(self):
        for f in self.files: f.flush()

# --- Global variables for Cost Atlases and Critic ---
# <<< ADAPTED >>> Replaced SUITABILITY_DATA with COST_ATLASES
COST_ATLASES = {
    'earthworks': None,
    'vegetation': None,
    'hydrology': None,
    'exclusion': None
}
RASTER_PROFILE = None
CRITIC = None # The single instance of our path-based critic
AOI_BOUNDS = None # Will be set to the full raster extent

# Point A to Point B definition
ALIGNMENT_START_X = None
ALIGNMENT_START_Y = None
ALIGNMENT_END_X = None
ALIGNMENT_END_Y = None
USE_USER_DEFINED_POINTS = False

def load_cost_atlases(atlas_paths, profile, start_coords=None, end_coords=None):
    """Loads the four cost atlas rasters for the full AOI."""
    print("  -> Loading Cost Atlas rasters...")
    global RASTER_PROFILE, AOI_BOUNDS, ALIGNMENT_START_X, ALIGNMENT_START_Y, ALIGNMENT_END_X, ALIGNMENT_END_Y, USE_USER_DEFINED_POINTS
    RASTER_PROFILE = profile

    # Set AOI bounds to the full extent of the rasters
    width = profile['width']
    height = profile['height']
    transform = Affine(*profile['transform'])
    AOI_BOUNDS = {
        'left': transform.c,
        'bottom': transform.f + transform.e * height,
        'right': transform.c + transform.a * width,
        'top': transform.f
    }

    # Handle user-defined Point A and Point B
    if start_coords and end_coords:
        ALIGNMENT_START_X, ALIGNMENT_START_Y = start_coords
        ALIGNMENT_END_X, ALIGNMENT_END_Y = end_coords
        USE_USER_DEFINED_POINTS = True
        print(f"  -> Using user-defined Point A: ({ALIGNMENT_START_X:.1f}, {ALIGNMENT_START_Y:.1f})")
        print(f"  -> Using user-defined Point B: ({ALIGNMENT_END_X:.1f}, {ALIGNMENT_END_Y:.1f})")
    else:
        # Define start/end X-coordinates for the alignment (e.g., 10% from edges)
        alignment_padding = (AOI_BOUNDS['right'] - AOI_BOUNDS['left']) * 0.1
        ALIGNMENT_START_X = AOI_BOUNDS['left'] + alignment_padding
        ALIGNMENT_END_X = AOI_BOUNDS['right'] - alignment_padding
        ALIGNMENT_START_Y = None  # Will be randomized
        ALIGNMENT_END_Y = None    # Will be randomized
        USE_USER_DEFINED_POINTS = False
        print("  -> Using random start/end Y-coordinates within AOI bounds")


    for key, path in atlas_paths.items():
        if not path.endswith('.tif'):
            continue
            
        atlas_key = None
        if 'earthworks' in path: atlas_key = 'earthworks'
        elif 'vegetation' in path: atlas_key = 'vegetation'
        elif 'hydrology' in path: atlas_key = 'hydrology'
        elif 'social_impact' in path: atlas_key = 'social_impact'
        elif 'connectivity' in path: atlas_key = 'connectivity'
        elif 'exclusion' in path: atlas_key = 'exclusion'
        elif 'DEM' in path or 'dem' in path: atlas_key = 'dem_elevation'
        
        if atlas_key:
            try:
                with rasterio.open(path) as src:
                    COST_ATLASES[atlas_key] = src.read(1)
                    print(f"    - Loaded '{atlas_key}' atlas.")
            except Exception as e:
                print(f"    ⚠️ Could not load {atlas_key} atlas from {path}: {e}")

    print("  - ✅ Cost Atlases loaded successfully.")
    return True

# --- Genetic Algorithm Core Functions (Adapted for Alignments) ---

# <<< ADAPTED >>> The "Individual" is now a list of (x, y) vertices.
# We define how to create one random alignment.
def generate_random_alignment(num_vertices=20):
    """Generates a random path from Point A to Point B."""
    vertices = []

    if USE_USER_DEFINED_POINTS:
        # Use user-defined fixed points
        start_y = ALIGNMENT_START_Y
        end_y = ALIGNMENT_END_Y
        print(f"    -> Generating alignment from fixed Point A ({ALIGNMENT_START_X:.1f}, {ALIGNMENT_START_Y:.1f}) to Point B ({ALIGNMENT_END_X:.1f}, {ALIGNMENT_END_Y:.1f})")
    else:
        # Use random Y coordinates within AOI bounds
        start_y = random.uniform(AOI_BOUNDS['bottom'], AOI_BOUNDS['top'])
        end_y = random.uniform(AOI_BOUNDS['bottom'], AOI_BOUNDS['top'])
        print(f"    -> Generating alignment from random start Y={start_y:.1f} to random end Y={end_y:.1f}")

    vertices.append((ALIGNMENT_START_X, start_y)) # Start point

    # Add intermediate points
    x_coords = np.linspace(ALIGNMENT_START_X, ALIGNMENT_END_X, num_vertices)[1:-1]
    for x in x_coords:
        # Random walk for y-coordinate
        last_y = vertices[-1][1]
        step = (AOI_BOUNDS['top'] - AOI_BOUNDS['bottom']) * 0.1 # 10% of height
        new_y = last_y + random.uniform(-step, step)
        new_y = np.clip(new_y, AOI_BOUNDS['bottom'], AOI_BOUNDS['top']) # Clamp to bounds
        vertices.append((x, new_y))

    vertices.append((ALIGNMENT_END_X, end_y)) # End point
    return creator.Individual(vertices)

# <<< ADAPTED >>> Mating function performs single-point crossover on two paths.
def mate_alignments(ind1, ind2):
    """Mates two alignment paths using single-point crossover."""
    size = min(len(ind1), len(ind2))
    cxpoint = random.randint(1, size - 2) # Crossover point, avoiding start/end
    
    # Swap segments
    child1_data = ind1[:cxpoint] + ind2[cxpoint:]
    child2_data = ind2[:cxpoint] + ind1[cxpoint:]
    
    return creator.Individual(child1_data), creator.Individual(child2_data)

# <<< ADAPTED >>> Mutation function nudges vertices.
def mutate_alignment(individual):
    """Mutates an alignment by nudging one or more vertices."""
    for i in range(1, len(individual) - 1): # Don't mutate start/end points
        if random.random() < 0.2: # 20% chance to mutate a vertex
            x, y = individual[i]
            
            # Nudge Y coordinate
            step = (AOI_BOUNDS['top'] - AOI_BOUNDS['bottom']) * 0.1 # 10% of height
            new_y = y + random.uniform(-step, step)
            new_y = np.clip(new_y, AOI_BOUNDS['bottom'], AOI_BOUNDS['top'])
            
            # Nudge X coordinate (less, just to vary density)
            step_x = (ALIGNMENT_END_X - ALIGNMENT_START_X) * 0.05
            new_x = x + random.uniform(-step_x, step_x)
            # Ensure X stays between neighbors
            new_x = np.clip(new_x, individual[i-1][0], individual[i+1][0])
            
            individual[i] = (new_x, new_y)
            
    return (individual,)

# <<< ADAPTED >>> Fitness function calls the new Critic.
def calculate_fitness(alignment):
    """Calculates the fitness score (total cost) using the path-based critic."""
    if CRITIC is None: 
        return (float('inf'),)
    # The Critic's evaluate method will take the list of vertices (the path)
    return CRITIC.evaluate(alignment)

# <<< ENHANCED >>> Export alignments to both KML and SHP formats
def export_alignment_kml(filename, hall_of_fame, diagnostics_report):
    """Exports the top N alignments from the Hall of Fame to KML and SHP files."""
    try:
        import geopandas as gpd
        from shapely.geometry import LineString
        print(f"🌍 Exporting top {len(hall_of_fame)} alignments to KML and SHP...")

        kml = simplekml.Kml(name="AI-Generated Alignments")

        # Define styles for ranks
        styles = [
            simplekml.Style(linestyle=simplekml.LineStyle(color=simplekml.Color.green, width=5)), # Rank 1 (Best)
            simplekml.Style(linestyle=simplekml.LineStyle(color=simplekml.Color.yellow, width=4)), # Rank 2
            simplekml.Style(linestyle=simplekml.LineStyle(color=simplekml.Color.orange, width=3)), # Rank 3
            simplekml.Style(linestyle=simplekml.LineStyle(color=simplekml.Color.red, width=2)),      # Rank 4
            simplekml.Style(linestyle=simplekml.LineStyle(color=simplekml.Color.white, width=2))     # Rank 5
        ]

        transformer = Transformer.from_crs(diagnostics_report['raster_profile']['crs'], "EPSG:4326", always_xy=True)

        # Prepare data for shapefile
        gdf_data = []

        for i, alignment in enumerate(hall_of_fame):
            # Vertices are already (x, y)
            coords_utm = [(v[0], v[1]) for v in alignment]
            coords_wgs84 = list(transformer.itransform(coords_utm))

            # Create KML linestring
            line = kml.newlinestring(name=f"Rank {i+1} (Fitness: {alignment.fitness.values[0]:.2f}, Cut: {alignment.fitness.values[1]:.0f}m³, Fill: {alignment.fitness.values[2]:.0f}m³, Env: {alignment.fitness.values[3]:.1f})",
                                     coords=coords_wgs84)
            line.style = styles[i % len(styles)] # Apply style

            # Prepare data for shapefile
            line_geom = LineString(coords_wgs84)
            gdf_data.append({
                'rank': i + 1,
                'fitness': float(alignment.fitness.values[0]),
                'cut_volume_m3': float(alignment.fitness.values[1]),
                'fill_volume_m3': float(alignment.fitness.values[2]),
                'environmental_score': float(alignment.fitness.values[3]),
                'geometry': line_geom
            })

        # Save KML
        kml.save(filename)
        print(f"✅ KML file '{filename}' saved successfully.")

        # Save shapefile
        shp_filename = filename.replace('.kml', '.shp')
        gdf = gpd.GeoDataFrame(gdf_data, crs="EPSG:4326")
        gdf.to_file(shp_filename)
        print(f"✅ SHP file '{shp_filename}' saved successfully.")

    except ImportError:
        print("⚠️ GeoPandas not available, skipping SHP export.")
        # Fallback to KML only
        kml = simplekml.Kml(name="AI-Generated Alignments")

        styles = [
            simplekml.Style(linestyle=simplekml.LineStyle(color=simplekml.Color.green, width=5)),
            simplekml.Style(linestyle=simplekml.LineStyle(color=simplekml.Color.yellow, width=4)),
            simplekml.Style(linestyle=simplekml.LineStyle(color=simplekml.Color.orange, width=3)),
            simplekml.Style(linestyle=simplekml.LineStyle(color=simplekml.Color.red, width=2)),
            simplekml.Style(linestyle=simplekml.LineStyle(color=simplekml.Color.white, width=2))
        ]

        transformer = Transformer.from_crs(diagnostics_report['raster_profile']['crs'], "EPSG:4326", always_xy=True)

        for i, alignment in enumerate(hall_of_fame):
            coords_utm = [(v[0], v[1]) for v in alignment]
            coords_wgs84 = list(transformer.itransform(coords_utm))

            line = kml.newlinestring(name=f"Rank {i+1} (Fitness: {alignment.fitness.values[0]:.2f}, Cut: {alignment.fitness.values[1]:.0f}m³, Fill: {alignment.fitness.values[2]:.0f}m³, Env: {alignment.fitness.values[3]:.1f})",
                                     coords=coords_wgs84)
            line.style = styles[i % len(styles)]

        kml.save(filename)
        print(f"✅ KML file '{filename}' saved successfully (SHP export skipped - GeoPandas not available).")

    except Exception as e:
        print(f"❌ ERROR: Failed to export alignments. Error: {e}")


# <<< REMOVED >>> crop_rasters_to_zone (not needed, critic will load full atlases)
# <<< REMOVED >>> generate_elevation_outputs / generate_intervention_visualization (not relevant)

def generate_alignment_visualization(top_alignments, diagnostics_report, output_dir):
    """
    Generates enhanced PNG visualizations of alignments on combined DEM/topobathy data.
    """
    print("📊 Generating enhanced land/water/depth alignment visualization...")
    try:
        import matplotlib.pyplot as plt
        import matplotlib.colors as mcolors
        from rasterio.plot import show as rasterio_show

        # Load both DEM (land) and topobathy (water depths) for combined visualization
        dem_path = "Data/UTM43_Data_Mumbai/DEM_UTM43.tif"  # Land elevations
        topobathy_path = "Data/UTM43_Data_Mumbai/topobathy_utm43.tif"  # Water depths

        # Load DEM data
        with rasterio.open(dem_path) as dem_src:
            dem_bounds = dem_src.bounds
            dem_data = dem_src.read(1).astype(np.float32)
            dem_data[dem_data == dem_src.nodata] = np.nan

        # Load topobathy data
        with rasterio.open(topobathy_path) as topo_src:
            topo_bounds = topo_src.bounds
            topo_data = topo_src.read(1).astype(np.float32)
            topo_data[topo_data == topo_src.nodata] = np.nan
            topo_transform = topo_src.transform

        # Create combined land/water visualization
        # Use topobathy as base (it has both land and water)
        combined_data = topo_data.copy()

        # For land areas where we have both DEM and topobathy, prefer DEM elevations
        # This gives better land elevation detail
        try:
            # Create a mask for areas where both datasets have valid data and topobathy shows land
            land_overlap = (~np.isnan(dem_data)) & (~np.isnan(topo_data)) & (topo_data >= -1)  # Near sea level
            combined_data[land_overlap] = dem_data[land_overlap]
        except:
            # If sampling fails, just use topobathy as is
            pass

        # Define colors for top alignments
        colors = ['red', 'orange', 'yellow', 'green', 'blue']
        labels = ['Rank 1 (Best)', 'Rank 2', 'Rank 3', 'Rank 4', 'Rank 5']

        # Create custom colormap for land/water/depth visualization
        # Deep blue for deep water, light blue for shallow water, brown/green for land
        colors_list = [
            (0.0, '#000080'),    # Deep water - dark blue (-10m+)
            (0.2, '#4169E1'),    # Medium water - royal blue (-5m to -2m)
            (0.4, '#00BFFF'),    # Shallow water - sky blue (-2m to -0.5m)
            (0.5, '#F4A460'),    # Coast/beach - sandy (-0.5m to 0m)
            (0.6, '#90EE90'),    # Low land - light green (0m to 5m)
            (0.8, '#228B22'),    # Medium land - forest green (5m to 20m)
            (1.0, '#8B4513')     # High land - brown (20m+)
        ]
        custom_cmap = mcolors.LinearSegmentedColormap.from_list('land_water_depth', colors_list)

        # Create single comprehensive visualization
        fig, ax = plt.subplots(figsize=(16, 10))

        # Plot combined DEM/topobathy data with custom depth/elevation colors
        vmin, vmax = -15, 50  # Show depth range from -15m to +50m
        im = ax.imshow(combined_data, cmap=custom_cmap, alpha=0.85,
                      extent=[topo_bounds.left, topo_bounds.right,
                             topo_bounds.bottom, topo_bounds.top],
                      vmin=vmin, vmax=vmax)

        # Plot alignments on top (clip to plot area if needed)
        for i, alignment in enumerate(top_alignments[:5]):  # Plot top 5
            # Handle DEAP Individual objects (they are lists with fitness attribute)
            if hasattr(alignment, 'fitness'):
                path = alignment  # The individual itself is the path (list of coordinates)
                fitness_value = alignment.fitness.values[0]
                cut_volume = alignment.fitness.values[1]
                fill_volume = alignment.fitness.values[2]
                environmental_score = alignment.fitness.values[3]
            else:
                # Handle dictionary format from JSON
                path = alignment['path']
                fitness_value = alignment['fitness']
                cut_volume = alignment.get('cut_volume', 0)
                fill_volume = alignment.get('fill_volume', 0)
                environmental_score = alignment.get('environmental_score', 0)

            if len(path) > 1:
                x_coords = [p[0] for p in path]
                y_coords = [p[1] for p in path]

                # Plot the alignment path
                ax.plot(x_coords, y_coords, color=colors[i], linewidth=4-i*0.4,
                        label=f"{labels[i]} (Cost: {fitness_value:.0f})", alpha=0.9, zorder=10)

        # Add start and end markers
        if top_alignments and len(top_alignments) > 0:
            if hasattr(top_alignments[0], 'fitness'):
                start_point = top_alignments[0][0]
                end_point = top_alignments[0][-1]
            else:
                start_point = top_alignments[0]['path'][0]
                end_point = top_alignments[0]['path'][-1]

            ax.scatter([start_point[0]], [start_point[1]], color='black', s=150,
                      marker='o', label='Sewri (Start)', zorder=11, edgecolors='white', linewidth=2)
            ax.scatter([end_point[0]], [end_point[1]], color='black', s=150,
                      marker='s', label='Nhava Sheva (End)', zorder=11, edgecolors='white', linewidth=2)

        ax.set_title("MTHL Bridge Alignment Options\nLand Elevations + Water Depths with AI-Optimized Routes", fontsize=18, weight='bold', pad=20)
        ax.set_xlabel("Easting (UTM Zone 43N, meters)", fontsize=12)
        ax.set_ylabel("Northing (UTM Zone 43N, meters)", fontsize=12)
        ax.legend(loc='upper right', fontsize=10, framealpha=0.9)
        ax.grid(True, alpha=0.3)

        # Add comprehensive colorbar
        cbar = plt.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
        cbar.set_label('Elevation/Depth (meters)', rotation=270, labelpad=20, fontsize=12)

        # Add detailed colorbar labels
        tick_locations = [-15, -10, -5, -2, 0, 5, 20, 50]
        tick_labels = ['-15m\n(Deep\nWater)', '-10m', '-5m', '-2m', '0m\n(Sea\nLevel)', '5m\n(Low\nLand)', '20m\n(Med\nLand)', '50m+\n(High\nLand)']
        cbar.set_ticks(tick_locations)
        cbar.set_ticklabels(tick_labels)

        # Add text annotations for water depth ranges
        ax.text(0.02, 0.98, 'Water Depths:', transform=ax.transAxes,
               fontsize=11, fontweight='bold', verticalalignment='top',
               bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
        ax.text(0.02, 0.93, '• Dark Blue: Deep water (-15m to -5m)', transform=ax.transAxes,
               fontsize=9, verticalalignment='top')
        ax.text(0.02, 0.88, '• Light Blue: Shallow water (-5m to 0m)', transform=ax.transAxes,
               fontsize=9, verticalalignment='top')
        ax.text(0.02, 0.83, '• Brown/Green: Land elevations (0m+)', transform=ax.transAxes,
               fontsize=9, verticalalignment='top')

        plt.tight_layout()
        png_path = f"{output_dir}/alignment_visualization.png"
        plt.savefig(png_path, dpi=300, bbox_inches='tight')
        plt.close(fig)
        print(f"  - ✅ Saved enhanced land/water/depth alignment visualization to '{png_path}'")

    except Exception as e:
        print(f"⚠️ Warning: Could not generate alignment visualization. Error: {e}")
        import traceback
        traceback.print_exc()

# <<< ADAPTED >>> Renamed from optimize_zone to optimize_alignment_task
def optimize_alignment_task(atlas_paths, profile, output_dir, start_coords=None, end_coords=None):
    """Run genetic algorithm optimization for the alignment task."""
    print(f"\n🗺️  OPTIMIZING ALIGNMENT CORRIDOR")
    print("-" * 50)

    # 1. Load the full-area Cost Atlases
    if not load_cost_atlases(atlas_paths, profile, start_coords, end_coords):
        print("❌ CRITICAL: Failed to load Cost Atlases. Aborting optimization.")
        return None

    # 2. Initialize the Critic with the loaded atlases
    global CRITIC
    CRITIC = Critic(
        earthworks_cost=COST_ATLASES['earthworks'],
        vegetation_cost=COST_ATLASES['vegetation'],
        hydrology_risk=COST_ATLASES['hydrology'],
        exclusion_map=COST_ATLASES['exclusion'],
        profile=RASTER_PROFILE,
        social_impact=COST_ATLASES.get('social_impact'),
        connectivity_atlas=COST_ATLASES.get('connectivity'),
        dem_elevation=COST_ATLASES.get('dem_elevation')
    )

    # 3. Setup genetic algorithm
    # Multi-objective: minimize fitness, cut_volume, fill_volume, environmental_score
    # (net_volume is derived from cut/fill, so not included in fitness)
    creator.create("FitnessMin", base.Fitness, weights=(-1.0, -1.0, -1.0, -1.0))
    # <<< ADAPTED >>> Individual is now a 'list'
    creator.create("Individual", list, fitness=creator.FitnessMin) 
    toolbox = base.Toolbox()
    
    # <<< ADAPTED >>> Register new GA functions
    toolbox.register("individual", lambda: creator.Individual(generate_random_alignment()))
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)
    toolbox.register("evaluate", calculate_fitness)
    toolbox.register("mate", mate_alignments)
    toolbox.register("mutate", mutate_alignment)
    toolbox.register("select", tools.selTournament, tournsize=3)

    # GA parameters (can be tuned)
    POP_SIZE = 200
    CXPB, MUTPB = 0.7, 0.3
    NGEN = 1000 # More generations for a complex path-finding problem
    
    print(f"  [INFO] Starting GA: {NGEN} generations, population of {POP_SIZE}...")

    pop = toolbox.population(n=POP_SIZE)
    # <<< ADAPTED >>> Add a HallOfFame to store the top 5 best alignments
    hof = tools.HallOfFame(5) 
    
    # Multi-objective statistics - focus on primary fitness score
    stats = tools.Statistics(lambda ind: ind.fitness.values[0])
    stats.register("avg", np.mean); stats.register("min", np.min)
    
    # Run the algorithm
    algorithms.eaSimple(pop, toolbox, cxpb=CXPB, mutpb=MUTPB, ngen=NGEN, 
                        stats=stats, halloffame=hof, verbose=True)

    best_plan = hof[0] # Best alignment is the first item in HOF
    result = {
        'task_name': 'AlignmentOptimization',
        'best_fitness': best_plan.fitness.values[0],
        'cut_volume_m3': best_plan.fitness.values[1],
        'fill_volume_m3': best_plan.fitness.values[2],
        'environmental_score': best_plan.fitness.values[3],
        'optimal_alignment': best_plan,
        'top_5_alignments': list(hof) # Save all top 5
    }

    print(f"  ✅ Alignment optimization complete - Best fitness: {best_plan.fitness.values[0]:.4f}")
    return result

if __name__ == "__main__":
    print("="*80); print("🛤️  LAUNCHING STAGE 2: AI ALIGNMENT PLANNER (v1.0)"); print("="*80)
    
    # <<< ADAPTED >>> Using new environment variable
    output_dir = os.environ.get('PIPELINE_OUTPUT_DIR', f"Outputs/Alignment_Run_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    os.makedirs(output_dir, exist_ok=True); print(f"📁 Using output directory: {output_dir}")
    
    log_file = open(f"{output_dir}/stage2_planner.log", 'w'); sys.stdout = Tee(sys.stdout, log_file); sys.stderr = Tee(sys.stderr, log_file)

    try:
        # Parse command line arguments for Point A and Point B
        import argparse
        parser = argparse.ArgumentParser(description='AI Alignment Planner - Point A to Point B')
        parser.add_argument('config_file', help='Path to cost_atlas_report.json')
        parser.add_argument('--start-x', type=float, help='Starting point X coordinate (UTM)')
        parser.add_argument('--start-y', type=float, help='Starting point Y coordinate (UTM)')
        parser.add_argument('--end-x', type=float, help='Ending point X coordinate (UTM)')
        parser.add_argument('--end-y', type=float, help='Ending point Y coordinate (UTM)')

        args = parser.parse_args()

        config_file = args.config_file
        print(f"🎯 Received Cost Atlas from: '{config_file}'")
        with open(config_file, 'r') as f: diagnostics_report = json.load(f)

        atlas_paths = diagnostics_report['atlas_paths']
        RASTER_PROFILE = diagnostics_report['raster_profile']

        # Check for user-defined Point A and Point B
        start_coords = None
        end_coords = None
        if args.start_x is not None and args.start_y is not None and args.end_x is not None and args.end_y is not None:
            start_coords = (args.start_x, args.start_y)
            end_coords = (args.end_x, args.end_y)
            print(f"📍 Using user-defined Point A: ({args.start_x}, {args.start_y})")
            print(f"📍 Using user-defined Point B: ({args.end_x}, {args.end_y})")
        else:
            print("🎲 Using random start/end Y-coordinates within AOI bounds")

        # <<< ADAPTED >>> Run the single alignment task with optional Point A/B
        optimization_result = optimize_alignment_task(atlas_paths, RASTER_PROFILE, output_dir, start_coords, end_coords)
        if optimization_result is None:
            raise Exception("Optimization task failed to run.")

        print(f"\n🏆 ALIGNMENT OPTIMIZATION COMPLETE 🏆")
        best_plan = optimization_result['optimal_alignment']
        print(f"Best overall fitness: {optimization_result['best_fitness']:.4f}")

        # --- Save comprehensive results ---
        def make_json_serializable(obj):
            if isinstance(obj, np.integer): return int(obj)
            elif isinstance(obj, np.floating): return float(obj)
            elif isinstance(obj, np.ndarray): return obj.tolist()
            elif isinstance(obj, dict): return {key: make_json_serializable(value) for key, value in obj.items()}
            elif isinstance(obj, list): return [make_json_serializable(item) for item in obj]
            elif hasattr(obj, 'fitness'): # Handle DEAP Individual
                return {
                    'fitness': obj.fitness.values[0],
                    'cut_volume_m3': obj.fitness.values[1],
                    'fill_volume_m3': obj.fitness.values[2],
                    'environmental_score': obj.fitness.values[3],
                    'path': [tuple(p) for p in obj]
                }
            else: return obj

        # Convert hall of fame to proper format
        top_5_formatted = []
        for i, individual in enumerate(optimization_result['top_5_alignments']):
            if hasattr(individual, 'fitness'):
                top_5_formatted.append({
                    'rank': i + 1,
                    'fitness': float(individual.fitness.values[0]),
                    'cut_volume_m3': float(individual.fitness.values[1]),
                    'fill_volume_m3': float(individual.fitness.values[2]),
                    'environmental_score': float(individual.fitness.values[3]),
                    'path': [(float(x), float(y)) for x, y in individual]
                })
            else:
                top_5_formatted.append(individual)

        comprehensive_result = {
            'optimization_summary': {
                'best_fitness': float(optimization_result['best_fitness'])
            },
            # <<< ADAPTED >>> Save the best alignment as 'optimal_plan' for Stage 3
            'optimal_plan': {
                'fitness': float(best_plan.fitness.values[0]) if hasattr(best_plan, 'fitness') else None,
                'cut_volume_m3': float(best_plan.fitness.values[1]) if hasattr(best_plan, 'fitness') else None,
                'fill_volume_m3': float(best_plan.fitness.values[2]) if hasattr(best_plan, 'fitness') else None,
                'environmental_score': float(best_plan.fitness.values[3]) if hasattr(best_plan, 'fitness') else None,
                'path': [(float(x), float(y)) for x, y in best_plan] if hasattr(best_plan, 'fitness') else best_plan
            },
            'top_5_alignments': top_5_formatted
        }

        # <<< ADAPTED >>> New output file name
        plan_path = f'{output_dir}/alignment_plan.json'
        with open(plan_path, 'w') as f: json.dump(comprehensive_result, f, indent=2)
        print(f"\n✅ Comprehensive alignment results saved to '{plan_path}'")

        # Export KML for the top 5 alignments
        export_alignment_kml(f"{output_dir}/alignment_plan.kml", optimization_result['top_5_alignments'], diagnostics_report)
        print(f"🌍 Exporting top 5 alignments to KML: '{output_dir}/alignment_plan.kml'")
        print(f"🗺️  Exporting top 5 alignments to SHP: '{output_dir}/alignment_plan.shp'")

        # Generate alignment visualization
        generate_alignment_visualization(optimization_result['top_5_alignments'], diagnostics_report, output_dir)

        # <<< REMOVED >>> generate_intervention_visualization / generate_elevation_outputs

    finally:
        sys.stdout = sys.stdout.files[0] if isinstance(sys.stdout, Tee) else sys.stdout
        sys.stderr = sys.stderr.files[0] if isinstance(sys.stderr, Tee) else sys.stderr
        if 'log_file' in locals() and not log_file.closed: log_file.close()