# (Full code for genetic_designer.py - Version 3.3 with Combined KML Export)
# ==============================================================================
# Project: AeroGis - Genetic Airport Layout Designer
# FILE NAME: genetic_designer.py
# VERSION: 3.3 (Combined KML Export)
# ==============================================================================
import random
import json
import time
import sys
import numpy as np
import airport_rules
from deap import base, creator, tools, algorithms
import simplekml
from pyproj import Transformer
from datetime import datetime
import os

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

def generate_random_layout(site_width, site_height):
    # ... (function is unchanged)
    runway = {'id': 1, 'center_x': site_width / 2, 'center_y': random.uniform(250, site_height - 250), 'length': 2800, 'width': 60}
    taxiway_side = random.choice(['top', 'bottom']); taxiway = {'side': taxiway_side, 'offset': 180}
    if taxiway_side == 'top': terminal_y_position = runway['center_y'] + taxiway['offset']
    else: terminal_y_position = runway['center_y'] - taxiway['offset'] - 200
    terminal = {'id': 1, 'footprint_x': random.uniform(300, site_width - 700), 'footprint_y': terminal_y_position, 'width': 400, 'height': 200}
    return {'runways': [runway], 'terminals': [terminal], 'taxiway': taxiway}

def mate_layouts(ind1, ind2):
    # ... (function is unchanged)
    child1_data = {'runways': ind1['runways'], 'taxiway': ind1['taxiway'], 'terminals': ind2['terminals']}
    child2_data = {'runways': ind2['runways'], 'taxiway': ind2['taxiway'], 'terminals': ind1['terminals']}
    return creator.Individual(child1_data), creator.Individual(child2_data)

def mutate_layout(individual):
    # ... (function is unchanged)
    if random.random() < 0.1: return (creator.Individual(generate_random_layout(3000, 800)),)
    individual['runways'][0]['center_y'] += random.uniform(-50, 50)
    individual['runways'][0]['center_y'] = max(250, min(800 - 250, individual['runways'][0]['center_y']))
    individual['terminals'][0]['footprint_x'] += random.uniform(-100, 100)
    runway_y = individual['runways'][0]['center_y']; taxiway_y_offset = individual['taxiway']['offset']
    if individual['taxiway']['side'] == 'top': individual['terminals'][0]['footprint_y'] = runway_y + taxiway_y_offset
    else: individual['terminals'][0]['footprint_y'] = runway_y - taxiway_y_offset - individual['terminals'][0]['height']
    return (individual,)

def calculate_fitness(layout):
    # ... (function is unchanged)
    rule_scores = airport_rules.evaluate_layout_rules(layout)
    if not rule_scores.get('is_valid', False): return (float('inf'),)
    w_efficiency = 0.6; w_cost = 0.4
    total_score = (w_efficiency * rule_scores['efficiency_score'] + w_cost * rule_scores['pavement_cost_score'])
    return (total_score,)

# --- UPGRADED KML EXPORT FUNCTION ---
def export_comprehensive_kml(filename, layout, site_details):
    """Exports a single KML with site boundary and final layout."""
    try:
        print(f"🌍 Exporting comprehensive KML file: '{filename}'...")
        kml = simplekml.Kml(name="AeroGis AI Final Design")
        
        # --- Define Styles ---
        boundary_style = simplekml.Style()
        boundary_style.polystyle.color = simplekml.Color.hexa('000000FF') # Transparent fill
        boundary_style.linestyle.color = simplekml.Color.red; boundary_style.linestyle.width = 3
        
        runway_style = simplekml.Style(); runway_style.polystyle.color = simplekml.Color.hexa('99111111')
        terminal_style = simplekml.Style(); terminal_style.polystyle.color = simplekml.Color.hexa('B3008CFF')

        # --- Coordinate Transformation ---
        transformer = Transformer.from_crs(site_details['crs'], "EPSG:4326", always_xy=True)
        origin_x, origin_y = site_details['transform'][2], site_details['transform'][5]

        # --- 1. Create Site Boundary Polygon ---
        site_px_w = site_details['footprint_shape_px']['width']
        site_px_h = site_details['footprint_shape_px']['height']
        site_loc = site_details['location_px']
        
        # Get global UTM coordinates of the site boundary corners
        transform = site_details['transform']
        corners_utm = [
            (site_loc['x'] * transform[0] + origin_x, site_loc['y'] * transform[4] + origin_y),
            ((site_loc['x'] + site_px_w) * transform[0] + origin_x, site_loc['y'] * transform[4] + origin_y),
            ((site_loc['x'] + site_px_w) * transform[0] + origin_x, (site_loc['y'] + site_px_h) * transform[4] + origin_y),
            (site_loc['x'] * transform[0] + origin_x, (site_loc['y'] + site_px_h) * transform[4] + origin_y),
        ]
        corners_wgs84 = list(transformer.itransform(corners_utm))
        boundary_poly = kml.newpolygon(name="Optimal Site Boundary", outerboundaryis=corners_wgs84)
        boundary_poly.style = boundary_style
        
        # --- 2. Create Runway Polygon ---
        runway = layout['runways'][0]
        r_x, r_y, r_l, r_w = runway['center_x'], runway['center_y'], runway['length'], runway['width']
        runway_corners_local = [(r_x - r_l/2, r_y - r_w/2), (r_x + r_l/2, r_y - r_w/2), (r_x + r_l/2, r_y + r_w/2), (r_x - r_l/2, r_y + r_w/2)]
        runway_corners_utm = [(x + origin_x, y + origin_y) for x, y in runway_corners_local]
        runway_corners_wgs84 = list(transformer.itransform(runway_corners_utm))
        runway_poly = kml.newpolygon(name="Runway", outerboundaryis=runway_corners_wgs84)
        runway_poly.style = runway_style

        # --- 3. Create Terminal Polygon ---
        terminal = layout['terminals'][0]
        t_x, t_y, t_w, t_h = terminal['footprint_x'], terminal['footprint_y'], terminal['width'], terminal['height']
        terminal_corners_local = [(t_x, t_y), (t_x + t_w, t_y), (t_x + t_w, t_y + t_h), (t_x, t_y + t_h)]
        terminal_corners_utm = [(x + origin_x, y + origin_y) for x, y in terminal_corners_local]
        terminal_corners_wgs84 = list(transformer.itransform(terminal_corners_utm))
        terminal_poly = kml.newpolygon(name="Terminal/Apron", outerboundaryis=terminal_corners_wgs84)
        terminal_poly.style = terminal_style

        kml.save(filename); print(f"✅ Comprehensive KML file '{filename}' saved successfully.")
    except Exception as e:
        print(f"❌ ERROR: Failed to export comprehensive KML. Error: {e}")

if __name__ == "__main__":
    print("="*80); print("🏛️  LAUNCHING STAGE 2: GENETIC AIRPORT ARCHITECT (v3.0)"); print("="*80)

    # Get output directory from environment variable or create with timestamp
    output_dir = os.environ.get('AEROGIS_OUTPUT_DIR')
    if not output_dir:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = f"Outputs/Run_{timestamp}"
    os.makedirs(output_dir, exist_ok=True)
    print(f"📁 Using output directory: {output_dir}")

    # Redirect stdout and stderr to log files
    log_file = open(f"{output_dir}/stage2_architect.log", 'w')
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    sys.stdout = Tee(original_stdout, log_file)
    sys.stderr = Tee(original_stderr, log_file)

    try:
        SITE_WIDTH_M = 3000; SITE_HEIGHT_M = 800
        if len(sys.argv) > 1:
            input_file = sys.argv[1]; print(f"🌉 Received input file from orchestrator: '{input_file}'")
            try:
                with open(input_file, 'r') as f: site_details = json.load(f)
                print(f"  - Site confirmed with target elevation: {site_details.get('target_elevation_m', 'N/A'):.2f} m")
            except Exception as e: print(f"❌ ERROR: Could not read or process '{input_file}'. Error: {e}"); site_details = {}
        else: print("⚠️ No input file provided. Running in standalone mode."); site_details = {}

        creator.create("FitnessMin", base.Fitness, weights=(-1.0,)); creator.create("Individual", dict, fitness=creator.FitnessMin)
        toolbox = base.Toolbox(); toolbox.register("individual", lambda: creator.Individual(generate_random_layout(SITE_WIDTH_M, SITE_HEIGHT_M)))
        toolbox.register("population", tools.initRepeat, list, toolbox.individual); toolbox.register("evaluate", calculate_fitness)
        toolbox.register("mate", mate_layouts); toolbox.register("mutate", mutate_layout); toolbox.register("select", tools.selTournament, tournsize=3)

        POP_SIZE = 100; CXPB, MUTPB, NGEN = 0.7, 0.2, 50
        print(f"\n[INFO] Starting evolution with {NGEN} generations and a population of {POP_SIZE}...")
        pop = toolbox.population(n=POP_SIZE); stats = tools.Statistics(lambda ind: ind.fitness.values)
        stats.register("avg", np.mean); stats.register("std", np.std); stats.register("min", np.min); stats.register("max", np.max)
        pop, logbook = algorithms.eaSimple(pop, toolbox, cxpb=CXPB, mutpb=MUTPB, ngen=NGEN, stats=stats, verbose=True)

        best_ind = tools.selBest(pop, 1)[0]; best_fitness = best_ind.fitness.values[0]
        print("\n" + "="*80); print("🏆 EVOLUTION COMPLETE 🏆"); print(f"  - Best layout found with a fitness score of: {best_fitness:.4f}"); print("="*80)
        print("\n--- FINAL OPTIMAL LAYOUT ---"); print(json.dumps(best_ind, indent=2)); print("="*80)

        with open(f'{output_dir}/optimal_layout.json', 'w') as f: json.dump(best_ind, f, indent=4)
        print(f"\n✅ Optimal layout saved to '{output_dir}/optimal_layout.json'")

        if 'transform' in site_details:
            export_comprehensive_kml(f"{output_dir}/final_airport_design.kml", best_ind, site_details)
        elif site_details:
            print("⚠️  Skipping KML export: Required georeferencing data not found in site_details.json.")
    finally:
        # Restore original stdout/stderr and close log file
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        log_file.close()