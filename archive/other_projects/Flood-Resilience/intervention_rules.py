# ==============================================================================
# Project: Gorakhpur Urban Resilience AI
# FILE NAME: intervention_rules.py
# VERSION: 3.0 (Physics-Based Surrogate Critic)
# PURPOSE: To provide an expert knowledge base for evaluating intervention plans
#          using a rapid, physics-based flood simulation (RFSM). This replaces
#          the previous heuristic model with a high-fidelity surrogate.
# ==============================================================================

import numpy as np
import math
import rasterio
from rasterio.warp import reproject, Resampling
from scipy.ndimage import convolve

# --- Constants for Evaluation (Can be tuned by experts) ---
TARGET_BUDGET = 750_000_000.0  # User-configurable budget constraint
BUDGET_PENALTY_FACTOR = 2.0   # How severely to penalize plans that exceed the budget

# --- Unit Costs for Different Interventions ---
# (Expressed in a consistent cost unit, e.g., Indian Rupees)
COST_POND_EXCAVATION_PER_M3 = 400.0
COST_LEVEE_CONSTRUCTION_PER_M3 = 1200.0
COST_BIOSWALE_PER_METER = 15000.0
COST_CULVERT_UPGRADE_FIXED = 5_000_000.0


class Critic:
    """
    An intelligent critic that evaluates intervention plans using a
    Rapid Flood Spreading Model (RFSM) surrogate.
    """
    def _align_raster_to_dem(self, raster_path, fill_value=0):
        """Aligns any raster to match the DEM's grid, CRS, and extent."""
        with rasterio.open(raster_path) as src:
            # Create destination array with DEM dimensions
            dest_array = np.full((self.profile['height'], self.profile['width']), fill_value, dtype=src.dtypes[0])

            # Reproject source to match DEM
            reproject(
                source=rasterio.band(src, 1),
                destination=dest_array,
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=self.profile['transform'],
                dst_crs=self.profile['crs'],
                resampling=Resampling.nearest
            )

            return dest_array.astype(np.float32)

    def __init__(self, dem_path, population_map_path, flood_map_path):
        print("  -> 🧠 Initializing Physics-Based Critic...")

        # Load and process DEM first (reference grid)
        with rasterio.open(dem_path) as src:
            self.base_dem = src.read(1).astype(np.float32)
            self.profile = src.profile
            if src.nodata is not None:
                self.base_dem[self.base_dem == src.nodata] = np.nan
            # Replace any remaining NaNs with a high elevation value to act as a boundary
            self.base_dem = np.nan_to_num(self.base_dem, nan=np.nanmax(self.base_dem) + 100)

        print("     - Aligning population map to DEM grid...")
        self.population_map = self._align_raster_to_dem(population_map_path, fill_value=0)
        self.total_population = np.sum(self.population_map)

        print("     - Aligning flood source map to DEM grid...")
        self.flood_source_map = self._align_raster_to_dem(flood_map_path, fill_value=0)

        self.pixel_area = self.profile['transform'].a * abs(self.profile['transform'].e)
        # Account for 3x flood amplification in total volume
        self.total_water_volume = np.sum(self.flood_source_map) * self.pixel_area * 3.0

        # Pre-compute neighbor kernel for RFSM for speed
        self.kernel = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]])
        print("  -> ✅ Critic initialized successfully.")

    def _run_rfsm(self, modified_dem):
        """Core Rapid Flood Spreading Model simulation."""
        water_depth = np.zeros_like(self.base_dem)
        # Initial water distribution based on the 100-year flood map (amplified for demonstration)
        flood_mask = self.flood_source_map > 0.1
        water_depth[flood_mask] = self.flood_source_map[flood_mask] * 3.0  # 3x flood intensity


        # Normalize to ensure total volume is conserved
        initial_volume = np.sum(water_depth) * self.pixel_area
        if initial_volume > 0:
            water_depth *= (self.total_water_volume / initial_volume)

        # Simulation loop - simplified flood modeling for demonstration
        for _ in range(20): # Number of iterations determines how far the water spreads
            water_surface_elev = modified_dem + water_depth
            
            # Find water surface elevation of all neighbors using convolution
            # Use 'nearest' mode to prevent water from flowing out of domain boundaries
            neighbor_surface_elev = convolve(water_surface_elev, self.kernel, mode='nearest')
            neighbor_count = convolve(np.ones_like(water_depth), self.kernel, mode='nearest')
            
            # Calculate average neighbor surface elevation
            avg_neighbor_elev = neighbor_surface_elev / neighbor_count
            
            # Water flows from higher to lower surface elevation
            flow_potential = water_surface_elev - avg_neighbor_elev
            
            # Only allow water to flow out of cells that have water
            flow_potential[water_depth <= 1e-5] = 0
            
            # Simple outflow model: a fraction of the potential flows out
            outflow_depth = flow_potential * 0.1 # Flow coefficient
            outflow_depth[outflow_depth < 0] = 0 # Can't have negative outflow
            
            # Limit outflow to the available water depth in the cell
            outflow_depth = np.minimum(outflow_depth, water_depth)
            
            # Distribute this outflow to all neighbors
            inflow_depth = convolve(outflow_depth, self.kernel, mode='constant', cval=0) / neighbor_count
            
            # Update water depth
            water_depth = water_depth - outflow_depth + inflow_depth
            water_depth[water_depth < 0] = 0

        return water_depth

    def _calculate_impact_score(self, plan):
        """Calculates remaining population risk after running the RFSM."""
        modified_dem = self.base_dem.copy()

        # 1. "Stamp" the plan onto the DEM
        for pond in plan.get('retention_ponds', []):
            # Find pixel coordinates for the pond center
            row, col = rasterio.transform.rowcol(self.profile['transform'], pond['x'], pond['y'])
            radius_pixels = int(pond['radius'] / self.profile['transform'].a)
            # Create a circular mask and lower the elevation
            y, x = np.ogrid[-row:modified_dem.shape[0]-row, -col:modified_dem.shape[1]-col]
            mask = x*x + y*y <= radius_pixels*radius_pixels
            modified_dem[mask] -= pond['depth']

        for levee in plan.get('levees', []):
            # Rasterize the levee line and raise the elevation
            start_r, start_c = rasterio.transform.rowcol(self.profile['transform'], levee['x_start'], levee['y_start'])
            end_r, end_c = rasterio.transform.rowcol(self.profile['transform'], levee['x_end'], levee['y_end'])
            # Bresenham's line algorithm to find pixels along the levee
            points = bresenham_line(start_c, start_r, end_c, end_r)
            for r, c in points:
                if 0 <= r < modified_dem.shape[0] and 0 <= c < modified_dem.shape[1]:
                    modified_dem[r, c] += levee['height']
        
        # Note: Bioswales/Culverts are not stamped on DEM; their effect is implicit in cost/impact.
        # A more advanced RFSM could model their sink/conveyance effects.

        # 2. Run the simulation
        final_water_depth = self._run_rfsm(modified_dem)

        # 3. Calculate remaining risk
        inundated_mask = final_water_depth > 0.1 # 10cm threshold for "flooded"
        population_at_risk = np.sum(self.population_map[inundated_mask])


        if self.total_population == 0: return 0.0

        impact_score = population_at_risk / self.total_population
        return impact_score

    def _calculate_construction_cost(self, plan):
        """Calculates the total construction cost for all intervention types."""
        total_cost = 0.0

        for pond in plan.get('retention_ponds', []):
            volume = math.pi * (pond['radius']**2) * pond['depth']
            total_cost += volume * COST_POND_EXCAVATION_PER_M3

        for levee in plan.get('levees', []):
            levee_length = math.sqrt((levee['x_end'] - levee['x_start'])**2 + (levee['y_end'] - levee['y_start'])**2)
            # Volume of a simple rectangular prism for costing
            volume = levee_length * levee['height'] * 3.0 # Assuming 3m avg width
            total_cost += volume * COST_LEVEE_CONSTRUCTION_PER_M3
            
        for swale in plan.get('bioswales', []):
            length = math.sqrt((swale['x_end'] - swale['x_start'])**2 + (swale['y_end'] - swale['y_start'])**2)
            total_cost += length * COST_BIOSWALE_PER_METER
            
        total_cost += len(plan.get('culvert_upgrades', [])) * COST_CULVERT_UPGRADE_FIXED
            
        return total_cost

    def evaluate(self, plan):
        """
        The main Critic function. Returns a single fitness value for the AI.
        A lower value is better.
        """
        impact_score = self._calculate_impact_score(plan)
        construction_cost = self._calculate_construction_cost(plan)

        # Normalize cost against the target budget
        cost_score = construction_cost / TARGET_BUDGET
        
        # Combine scores with weighting
        fitness = 0.7 * impact_score + 0.3 * cost_score
        
        # Apply budget penalty
        if construction_cost > TARGET_BUDGET:
            fitness *= BUDGET_PENALTY_FACTOR
            
        return (fitness,)

# Helper function for rasterizing lines (outside the class)
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