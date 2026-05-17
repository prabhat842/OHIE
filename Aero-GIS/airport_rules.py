# ==============================================================================
# Project: AeroGis - Expert Knowledge Base
# FILE NAME: airport_rules.py
# VERSION: 2.0 (Parallel Taxiway Logic)
# ==============================================================================

import numpy as np

# --- Data Schema (Updated) ---
# LAYOUT_SCHEMA = {
#     'runways': [{'id': 1, 'center_x': 1500, 'center_y': 300, 'length': 2800, 'width': 60}],
#     'terminals': [{'id': 1, 'footprint_x': 800, 'footprint_y': 450, 'width': 400, 'height': 200}],
#     'taxiway': {'side': 'top', 'offset': 180} # Offset from runway centerline
# }

def check_runway_separation(layout):
    """Checks if parallel runways meet the minimum separation distance."""
    runways = layout.get('runways', [])
    if len(runways) < 2:
        return True
    MIN_SEPARATION_M = 1310
    y_positions = [r['center_y'] for r in runways]
    separation = abs(y_positions[0] - y_positions[1])
    return separation >= MIN_SEPARATION_M

# --- UPGRADED EFFICIENCY CALCULATION ---
def calculate_taxi_efficiency_score(layout):
    """
    Calculates a more realistic taxi distance from the terminal, along a parallel
    taxiway, to the runway threshold. Assumes E-W runway.
    """
    try:
        runway = layout['runways'][0]
        terminal = layout['terminals'][0]
        taxiway = layout['taxiway']

        runway_start_x = runway['center_x'] - runway['length'] / 2
        runway_end_x = runway['center_x'] + runway['length'] / 2

        # Taxiway is parallel to runway
        taxiway_y = runway['center_y'] + taxiway['offset'] if taxiway['side'] == 'top' else runway['center_y'] - taxiway['offset']
        
        # Position of terminal relative to the taxiway
        terminal_center_x = terminal['footprint_x'] + terminal['width'] / 2
        
        # Distance from terminal to taxiway (north-south)
        dist_to_taxiway = abs(terminal['footprint_y'] - taxiway_y)

        # Distance from terminal along taxiway to the furthest runway end
        dist_along_taxiway = max(abs(terminal_center_x - runway_start_x), abs(terminal_center_x - runway_end_x))
        
        total_taxi_dist = dist_to_taxiway + dist_along_taxiway
        
        # Normalize score (e.g., a good taxi distance is under 3.5km)
        return total_taxi_dist / 3500.0
    except (IndexError, KeyError):
        return float('inf') # Invalid layout format

def calculate_pavement_cost_score(layout):
    """Calculates a score based on the total area of asphalt/concrete."""
    try:
        total_pavement_area = 0
        runway = layout['runways'][0]
        taxiway_width = 23 # Standard for Code C/D aircraft
        
        # Runway area
        total_pavement_area += runway['length'] * runway['width']
        # Parallel taxiway area
        total_pavement_area += runway['length'] * taxiway_width
        # Terminal/Apron area (approximation)
        total_pavement_area += layout['terminals'][0]['width'] * layout['terminals'][0]['height']

        # Normalize score (e.g., relative to a 300,000 sq m baseline)
        return total_pavement_area / 300000.0
    except (IndexError, KeyError):
        return float('inf')

def evaluate_layout_rules(layout):
    """The main "Critic" function that scores a layout against all rules."""
    scores = {}
    if not check_runway_separation(layout):
        scores['is_valid'] = False
        return scores
    
    scores['is_valid'] = True
    scores['efficiency_score'] = calculate_taxi_efficiency_score(layout)
    scores['pavement_cost_score'] = calculate_pavement_cost_score(layout)
    return scores