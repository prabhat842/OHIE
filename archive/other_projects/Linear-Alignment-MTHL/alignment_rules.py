# ==============================================================================
# Project: Culturiq AI-Driven Infrastructure
# FILE NAME: alignment_rules.py
# VERSION: 1.0 (Adapted from intervention_rules.py v3.0)
# PURPOSE: To provide an expert knowledge base for evaluating alignment plans (paths)
#          by sampling pre-calculated Cost Atlases. This "Critic" is called by
#          the Stage 2 Genetic Algorithm.
# ==============================================================================

import numpy as np
import math
import rasterio
from rasterio.transform import Affine
from scipy.ndimage import convolve

# --- Constants for Evaluation (Can be tuned by experts) ---
# <<< UPDATED >>> Realistic weights for MTHL bridge with shipping routes & wind data
WEIGHT_EARTHWORKS = 1200.0   # Cost of water depth (highest priority for bridge foundations)
WEIGHT_VEGETATION = 2000.0   # Cost of clearing vegetation/mangroves (environmental protection)
WEIGHT_HYDROLOGY = 2000.0     # Cost/Risk of waterlogging (enhanced flood data)
WEIGHT_SOCIAL = 300.0       # Social impact from population density
WEIGHT_CONNECTIVITY = -250.0 # Connectivity bonus (negative = cost reduction for road access)
WEIGHT_LENGTH = 50000000.0      # Reasonable length cost (penalize excessive bridge length)
WEIGHT_CURVATURE = -2000.0    # Penalize sharp turns (bridges need smooth alignments)
WEIGHT_SHIPPING = 150000.0   # HIGH penalty for crossing shipping channels

# <<< ADAPTED >>> New penalty for "no-go" zones (MTHL exclusions)
PENALTY_EXCLUSION = 50000.0  # Extremely high cost for Flamingo sanctuary, BARC, buildings, shipping routes

# <<< NEW >>> Wind and structural constraints from Global Wind Atlas
WIND_SPEED_MS = 5.42        # Mean wind speed at 100m height (moderate for cable-stayed bridge)
BRIDGE_WIND_FACTOR = 75.0   # Cost multiplier for wind-exposed alignments
# SEISMIC_ZONE_FACTOR = 100.0  # Mumbai seismic zone cost (Zone III - moderate seismicity)

# <<< REMOVED >>> Intervention unit costs are no longer needed.


class Critic:
    """
    An intelligent critic that evaluates alignment paths by "walking" them
    across the Cost Atlases generated in Stage 1.
    """
    # <<< ENHANCED >>> Constructor now takes comprehensive cost atlas arrays
    def __init__(self, earthworks_cost, vegetation_cost, hydrology_risk, exclusion_map,
                 profile, social_impact=None, connectivity_atlas=None, dem_elevation=None):

        print("  -> 🧠 Initializing Enhanced Alignment Critic...")

        # 1. Store the cost atlas arrays
        self.earthworks_cost = earthworks_cost
        self.vegetation_cost = vegetation_cost
        self.hydrology_risk = hydrology_risk
        self.exclusion_map = exclusion_map
        self.social_impact = social_impact if social_impact is not None else np.ones_like(earthworks_cost)
        self.connectivity_atlas = connectivity_atlas if connectivity_atlas is not None else np.ones_like(earthworks_cost)
        self.dem_elevation = dem_elevation  # DEM elevation data for cut/fill calculations
        
        # 2. Store grid/geospatial info
        self.profile = profile
        self.transform = Affine(*self.profile['transform'])
        self.pixel_width = self.transform.a
        self.pixel_height = abs(self.transform.e)
        self.grid_height = self.profile['height']
        self.grid_width = self.profile['width']

        print("  -> ✅ Critic initialized successfully.")

    # <<< REMOVED >>> _run_rfsm and _calculate_impact_score are deleted.
    
    # <<< NEW FUNCTION >>> This replaces all the old cost/impact logic.
    def _calculate_path_cost(self, alignment_path):
        """
        Calculates the total weighted cost of a single alignment path.
        """
        total_cost = 0.0
        total_length_m = 0.0

        if not alignment_path:
            return float('inf')

        # Get the pixel coordinates for the first point
        last_x, last_y = alignment_path[0]
        try:
            r_last, c_last = rasterio.transform.rowcol(self.transform, last_x, last_y)
        except rasterio.errors.OutOfBoundsError:
            return float('inf') # Path starts outside bounds

        # Iterate through each segment of the path
        for (x, y) in alignment_path[1:]:
            total_length_m += math.sqrt((x - last_x)**2 + (y - last_y)**2)
            
            try:
                r_curr, c_curr = rasterio.transform.rowcol(self.transform, x, y)
            except rasterio.errors.OutOfBoundsError:
                total_cost += PENALTY_EXCLUSION * 100 # Path went way off grid
                continue
            
            # <<< PRESERVED METHOD >>> Use bresenham_line to get all pixels on the segment
            pixels_on_segment = bresenham_line(c_last, r_last, c_curr, r_curr)
            
            segment_cost = 0.0
            for (r, c) in pixels_on_segment:
                # Check if pixel is within grid bounds
                if 0 <= r < self.grid_height and 0 <= c < self.grid_width:
                    # 1. Check Exclusion Zone (High Penalty)
                    if self.exclusion_map[r, c] > 0:
                        segment_cost += PENALTY_EXCLUSION
                        continue # No need to add other costs
                    
                    # 2. Add weighted costs from atlases
                    segment_cost += WEIGHT_EARTHWORKS * self.earthworks_cost[r, c]
                    segment_cost += WEIGHT_VEGETATION * self.vegetation_cost[r, c]
                    segment_cost += WEIGHT_HYDROLOGY * self.hydrology_risk[r, c]
                    segment_cost += WEIGHT_SOCIAL * self.social_impact[r, c]
                    segment_cost += WEIGHT_CONNECTIVITY * self.connectivity_atlas[r, c]  # Negative weight = bonus
                else:
                    # Penalize going off-grid (shouldn't happen with planner bounds)
                    segment_cost += PENALTY_EXCLUSION
            
            # Average the cost over the pixels in the segment
            if len(pixels_on_segment) > 0:
                total_cost += segment_cost / len(pixels_on_segment)

            r_last, c_last = r_curr, c_curr
            last_x, last_y = x, y

        # 3. Add curvature penalty for sharp turns (buildability)
        total_curvature_penalty = 0.0
        if len(alignment_path) > 2:
            # Iterate from the 2nd vertex to the 2nd-to-last vertex
            for i in range(1, len(alignment_path) - 1):
                p_prev = alignment_path[i-1]
                p_curr = alignment_path[i]
                p_next = alignment_path[i+1]

                # Create vectors
                v1_x = p_curr[0] - p_prev[0]
                v1_y = p_curr[1] - p_prev[1]
                v2_x = p_next[0] - p_curr[0]
                v2_y = p_next[1] - p_curr[1]

                # Get magnitudes
                mag_v1 = math.sqrt(v1_x**2 + v1_y**2)
                mag_v2 = math.sqrt(v2_x**2 + v2_y**2)

                # Use dot product to find cosine of the angle
                if mag_v1 > 0 and mag_v2 > 0:
                    dot_product = v1_x * v2_x + v1_y * v2_y
                    cos_theta = dot_product / (mag_v1 * mag_v2)
                    cos_theta = max(-1.0, min(1.0, cos_theta)) # Clamp
                else:
                    cos_theta = -1.0 # Treat as straight

                # Penalty is 0 for straight (cos_theta=-1)
                # Penalty is 2 for U-turn (cos_theta=1)
                curvature_penalty = (1.0 + cos_theta)
                total_curvature_penalty += curvature_penalty

            # Add the normalized penalty to the total cost
            avg_curvature_penalty = total_curvature_penalty / (len(alignment_path) - 2)
            total_cost += WEIGHT_CURVATURE * avg_curvature_penalty

        # 4. Add the normalized length cost
        # Normalize length by pixel size to make it comparable to other 0-1 costs
        normalized_length = total_length_m / (self.grid_width * self.pixel_width)
        total_cost += WEIGHT_LENGTH * normalized_length

        return total_cost

    def _calculate_cut_fill_volume(self, alignment_path):
        """
        Calculate cut/fill volumes along the alignment path using DEM elevations.
        Returns (cut_volume_m3, fill_volume_m3, net_volume_m3)
        """
        if self.dem_elevation is None:
            return 0.0, 0.0, 0.0

        cut_volume = 0.0
        fill_volume = 0.0

        # Simple linear grade assumption between start and end points
        start_elev = None
        end_elev = None

        try:
            # Get start elevation
            r_start, c_start = rasterio.transform.rowcol(self.transform, alignment_path[0][0], alignment_path[0][1])
            if 0 <= r_start < self.grid_height and 0 <= c_start < self.grid_width:
                start_elev = self.dem_elevation[r_start, c_start]

            # Get end elevation
            r_end, c_end = rasterio.transform.rowcol(self.transform, alignment_path[-1][0], alignment_path[-1][1])
            if 0 <= r_end < self.grid_height and 0 <= c_end < self.grid_width:
                end_elev = self.dem_elevation[r_end, c_end]

        except rasterio.errors.OutOfBoundsError:
            return 0.0, 0.0, 0.0

        if start_elev is None or end_elev is None:
            return 0.0, 0.0, 0.0

        # Calculate linear grade
        total_length = sum(math.sqrt((x2-x1)**2 + (y2-y1)**2)
                          for (x1,y1), (x2,y2) in zip(alignment_path[:-1], alignment_path[1:]))
        grade = (end_elev - start_elev) / total_length if total_length > 0 else 0

        # Calculate cut/fill along path
        distance_along_path = 0.0
        for i, (x, y) in enumerate(alignment_path):
            try:
                r, c = rasterio.transform.rowcol(self.transform, x, y)
                if 0 <= r < self.grid_height and 0 <= c < self.grid_width:
                    current_elev = self.dem_elevation[r, c]
                    design_elev = start_elev + grade * distance_along_path

                    # Calculate volume for this segment (simplified)
                    volume_diff = design_elev - current_elev
                    segment_length = math.sqrt((alignment_path[i][0] - alignment_path[i-1][0])**2 +
                                             (alignment_path[i][1] - alignment_path[i-1][1])**2) if i > 0 else 0

                    if volume_diff > 0:
                        fill_volume += volume_diff * segment_length * 1.0  # 1m width assumption
                    else:
                        cut_volume += abs(volume_diff) * segment_length * 1.0

                if i < len(alignment_path) - 1:
                    distance_along_path += math.sqrt((alignment_path[i+1][0] - x)**2 +
                                                   (alignment_path[i+1][1] - y)**2)

            except rasterio.errors.OutOfBoundsError:
                continue

        net_volume = fill_volume - cut_volume
        return cut_volume, fill_volume, net_volume

    def _calculate_environmental_score(self, alignment_path):
        """
        Calculate a composite environmental suitability score (0-100 scale).
        Lower scores = more suitable (less environmental impact).
        """
        if not alignment_path:
            return 100.0

        total_score = 0.0
        pixel_count = 0

        # Walk through all pixels on the path
        for i in range(len(alignment_path) - 1):
            x1, y1 = alignment_path[i]
            x2, y2 = alignment_path[i+1]

            try:
                r1, c1 = rasterio.transform.rowcol(self.transform, x1, y1)
                r2, c2 = rasterio.transform.rowcol(self.transform, x2, y2)

                pixels = bresenham_line(c1, r1, c2, r2)

                for r, c in pixels:
                    if 0 <= r < self.grid_height and 0 <= c < self.grid_width:
                        if self.exclusion_map[r, c] > 0:
                            total_score += 100.0  # Maximum penalty for exclusion zones
                        else:
                            # Weighted composite of all environmental factors
                            env_score = (
                                0.25 * self.earthworks_cost[r, c] +      # Earthworks impact
                                0.25 * self.vegetation_cost[r, c] +      # Vegetation clearance
                                0.20 * self.hydrology_risk[r, c] +       # Flood risk
                                0.15 * self.social_impact[r, c] +        # Social disruption
                                0.15 * (1.0 - self.connectivity_atlas[r, c])  # Connectivity bonus (inverted)
                            )
                            total_score += env_score * 100.0  # Scale to 0-100
                        pixel_count += 1

            except rasterio.errors.OutOfBoundsError:
                continue

        # Add curvature penalty to environmental score
        curvature_penalty = 0.0
        if len(alignment_path) > 2:
            for i in range(1, len(alignment_path) - 1):
                p_prev = alignment_path[i-1]
                p_curr = alignment_path[i]
                p_next = alignment_path[i+1]

                v1_x = p_curr[0] - p_prev[0]
                v1_y = p_curr[1] - p_prev[1]
                v2_x = p_next[0] - p_curr[0]
                v2_y = p_next[1] - p_curr[1]

                mag_v1 = math.sqrt(v1_x**2 + v1_y**2)
                mag_v2 = math.sqrt(v2_x**2 + v2_y**2)

                if mag_v1 > 0 and mag_v2 > 0:
                    dot_product = v1_x * v2_x + v1_y * v2_y
                    cos_theta = dot_product / (mag_v1 * mag_v2)
                    cos_theta = max(-1.0, min(1.0, cos_theta))
                else:
                    cos_theta = -1.0

                curvature_penalty += (1.0 + cos_theta)

            avg_curvature_penalty = curvature_penalty / (len(alignment_path) - 2)
            total_score += avg_curvature_penalty * 20.0  # Add curvature impact

        return total_score / pixel_count if pixel_count > 0 else 100.0

    # <<< REMOVED >>> _calculate_construction_cost (for ponds/levees) is deleted.

    # <<< ENHANCED >>> Evaluate function now returns multiple metrics
    def evaluate(self, alignment_path):
        """
        The main Critic function. Returns fitness value plus additional metrics.
        Returns: (fitness_score, cut_volume_m3, fill_volume_m3, environmental_score)
        """
        # 1. Calculate the total path cost (fitness)
        fitness_score = self._calculate_path_cost(alignment_path)

        # 2. Calculate cut/fill volumes
        cut_volume, fill_volume, net_volume = self._calculate_cut_fill_volume(alignment_path)

        # 3. Calculate environmental score
        environmental_score = self._calculate_environmental_score(alignment_path)

        return (fitness_score, cut_volume, fill_volume, environmental_score)

# <<< PRESERVED METHOD >>>
# Helper function for rasterizing lines (outside the class)
# This core method from intervention_rules.py is preserved.
def bresenham_line(x0, y0, x1, y1):
    """Generates the integer coordinates for a line between two points."""
    points = []
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        points.append((y0, x0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy
    return points