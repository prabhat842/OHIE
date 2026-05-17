# ==============================================================================
# Project: [IWMI] Water Resource Management AI
# FILE NAME: intervention_rules.py
# VERSION: 1.0 (Water Balance Critic Adaptation)
# PURPOSE: To provide an expert knowledge base for evaluating water management
#          plans using a rapid, physics-based water balance model (RFSM).
# ==============================================================================

import numpy as np
import math
import rasterio
from rasterio.warp import reproject, Resampling
from scipy.ndimage import convolve

# --- Constants for Evaluation (Can be tuned by experts) ---
TARGET_BUDGET = 750_000_000.0  # Budget constraint (remains the same)
BUDGET_PENALTY_FACTOR = 2.0   # Penalty for exceeding budget (remains the same)

# <<< ADAPTED >>> New constants for water balance calculation
# We assume the plan needs to meet demand over a 30-day dry period
SIMULATION_DURATION_DAYS = 30.0 
# We assume each "demand unit" (person) needs 0.1 m^3/day (100 liters)
DEMAND_PER_PERSON_M3_DAY = 0.1 

# --- Unit Costs for Different Interventions ---
# <<< ADAPTED >>> Renamed for new intervention types
COST_POND_EXCAVATION_PER_M3 = 400.0
COST_RECHARGE_STRUCTURE_PER_M3 = 1200.0 # e.g., for check dams
COST_NBS_SWALE_PER_METER = 15000.0
COST_SOLAR_PUMP_FIXED = 250_000.0 # Fixed cost per pump unit


class Critic:
    """
    An intelligent critic that evaluates intervention plans using a
    Rapid Flood Spreading Model (RFSM) adapted for water balance.
    """
    def _align_raster_to_dem(self, raster_path, fill_value=0):
        """Aligns any raster to match the DEM's grid, CRS, and extent."""
        with rasterio.open(raster_path) as src:
            dest_array = np.full((self.profile['height'], self.profile['width']), fill_value, dtype=src.dtypes[0])
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
        # <<< ADAPTED >>> Renamed variables for clarity
        print("  -> 🧠 Initializing Water Balance Critic...")
        
        # 1. Load DEM (Reference Grid)
        with rasterio.open(dem_path) as src:
            self.base_dem = src.read(1).astype(np.float32)
            self.profile = src.profile
            if src.nodata is not None:
                self.base_dem[self.base_dem == src.nodata] = np.nan
            self.base_dem = np.nan_to_num(self.base_dem, nan=np.nanmax(self.base_dem) + 100)

        # 2. Load Population Map (as Water Demand)
        print("     - Aligning population map (as Water Demand) to DEM grid...")
        self.demand_map = self._align_raster_to_dem(population_map_path, fill_value=0)
        self.total_demand_units = np.sum(self.demand_map) # Total "people" to supply
        self.total_demand_volume = (
            self.total_demand_units * DEMAND_PER_PERSON_M3_DAY * SIMULATION_DURATION_DAYS
        )
        print(f"     - Calculated Total Demand: {self.total_demand_volume:,.0f} m³ over {SIMULATION_DURATION_DAYS} days")

        # 3. Load Flood Map (as Runoff/Water Supply)
        print("     - Aligning flood map (as Runoff Supply) to DEM grid...")
        # <<< ADAPTED >>> Renamed variable
        self.runoff_source_map = self._align_raster_to_dem(flood_map_path, fill_value=0)

        self.pixel_area = self.profile['transform'].a * abs(self.profile['transform'].e)
        # <<< ADAPTED >>> This is now total *available* water, not an amplified flood.
        self.total_water_supply_volume = np.sum(self.runoff_source_map) * self.pixel_area
        print(f"     - Calculated Total Available Runoff: {self.total_water_supply_volume:,.0f} m³")

        # 4. Pre-compute kernel for RFSM
        self.kernel = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]])
        print("  -> ✅ Critic initialized successfully.")

    def _run_rfsm(self, modified_dem):
        """
        Core Rapid Flood Spreading Model simulation.
        <<< ADAPTED >>> We re-use this to simulate how runoff *collects*
        in the ponds and behind recharge structures.
        """
        water_depth = np.zeros_like(self.base_dem)
        
        # Initial water distribution based on the available runoff map
        # <<< ADAPTED >>> Using runoff_source_map, no 3x amplification
        runoff_mask = self.runoff_source_map > 0.1
        water_depth[runoff_mask] = self.runoff_source_map[runoff_mask]

        # Normalize to ensure total volume is conserved
        initial_volume = np.sum(water_depth) * self.pixel_area
        if initial_volume > 0:
            water_depth *= (self.total_water_supply_volume / initial_volume)

        # Simulation loop - 20 iterations to let water flow and settle
        for _ in range(20): 
            water_surface_elev = modified_dem + water_depth
            neighbor_surface_elev = convolve(water_surface_elev, self.kernel, mode='nearest')
            neighbor_count = convolve(np.ones_like(water_depth), self.kernel, mode='nearest')
            avg_neighbor_elev = neighbor_surface_elev / neighbor_count
            flow_potential = water_surface_elev - avg_neighbor_elev
            flow_potential[water_depth <= 1e-5] = 0
            outflow_depth = flow_potential * 0.1 
            outflow_depth[outflow_depth < 0] = 0 
            outflow_depth = np.minimum(outflow_depth, water_depth)
            inflow_depth = convolve(outflow_depth, self.kernel, mode='constant', cval=0) / neighbor_count
            water_depth = water_depth - outflow_depth + inflow_depth
            water_depth[water_depth < 0] = 0

        # <<< ADAPTED >>> The final water_depth map now represents all
        # water *captured and held* by the interventions.
        return water_depth

    def _calculate_water_balance_score(self, plan):
        """
        Calculates the water deficit score after running the RFSM.
        A score of 0 is best (demand met), 1 is worst (no demand met).
        """
        modified_dem = self.base_dem.copy()

        # 1. "Stamp" the plan onto the DEM
        # <<< ADAPTED >>> Use new 'harvesting_ponds' key
        for pond in plan.get('harvesting_ponds', []):
            row, col = rasterio.transform.rowcol(self.profile['transform'], pond['x'], pond['y'])
            radius_pixels = int(pond['radius'] / self.profile['transform'].a)
            y, x = np.ogrid[-row:modified_dem.shape[0]-row, -col:modified_dem.shape[1]-col]
            mask = x*x + y*y <= radius_pixels*radius_pixels
            modified_dem[mask] -= pond['depth'] # Dig the pond

        # <<< ADAPTED >>> Use new 'recharge_structures' key (same logic as levee)
        for structure in plan.get('recharge_structures', []):
            start_r, start_c = rasterio.transform.rowcol(self.profile['transform'], structure['x_start'], structure['y_start'])
            end_r, end_c = rasterio.transform.rowcol(self.profile['transform'], structure['x_end'], structure['y_end'])
            points = bresenham_line(start_c, start_r, end_c, end_r)
            for r, c in points:
                if 0 <= r < modified_dem.shape[0] and 0 <= c < modified_dem.shape[1]:
                    modified_dem[r, c] += structure['height'] # Build the check dam wall
        
        # Note: NbS Swales are not stamped on DEM; their effect is implicit in cost.
        # A more advanced model could treat them as infiltration zones.

        # 2. Run the simulation to see how much water is *captured*
        final_water_depth = self._run_rfsm(modified_dem)

        # 3. Calculate Water Supply vs. Demand
        
        # Supply from captured surface water
        captured_volume_m3 = np.sum(final_water_depth) * self.pixel_area

        # Supply from new pumps (assumes pumps access a different source, e.g., groundwater)
        # <<< ADAPTED >>> Use new 'solar_pumps' key and new parameters
        pumped_volume_m3 = 0.0
        for pump in plan.get('solar_pumps', []):
            pumped_volume_m3 += pump.get('capacity_m3_day', 0) * SIMULATION_DURATION_DAYS
        
        total_supply_m3 = captured_volume_m3 + pumped_volume_m3

        # 4. Calculate final score (Water Deficit)
        if self.total_demand_volume == 0: 
            return 0.0 # No demand, score is perfect.

        # Calculate the unmet demand
        water_deficit_m3 = max(0, self.total_demand_volume - total_supply_m3)
        
        # Normalize score: (Unmet Demand) / (Total Demand)
        # A score of 0.0 is perfect (deficit is 0).
        # A score of 1.0 is total failure (deficit = total demand).
        deficit_score = water_deficit_m3 / self.total_demand_volume
        
        return deficit_score

    def _calculate_construction_cost(self, plan):
        """Calculates the total construction cost for all intervention types."""
        # <<< ADAPTED >>> Updated with new keys and costs
        total_cost = 0.0

        for pond in plan.get('harvesting_ponds', []):
            volume = math.pi * (pond['radius']**2) * pond['depth']
            total_cost += volume * COST_POND_EXCAVATION_PER_M3

        for structure in plan.get('recharge_structures', []):
            length = math.sqrt((structure['x_end'] - structure['x_start'])**2 + (structure['y_end'] - structure['y_start'])**2)
            # Volume of a simple rectangular prism for costing
            volume = length * structure['height'] * 3.0 # Assuming 3m avg width
            total_cost += volume * COST_RECHARGE_STRUCTURE_PER_M3
            
        for swale in plan.get('nbs_swales', []):
            length = math.sqrt((swale['x_end'] - swale['x_start'])**2 + (swale['y_end'] - swale['y_start'])**2)
            total_cost += length * COST_NBS_SWALE_PER_METER
            
        total_cost += len(plan.get('solar_pumps', [])) * COST_SOLAR_PUMP_FIXED
            
        return total_cost

    def evaluate(self, plan):
        """
        The main Critic function. Returns a single fitness value for the AI.
        A lower value is better.
        """
        # <<< ADAPTED >>> Changed to the new water balance score
        # The core fitness logic remains the same.
        
        # 1. Calculate the water deficit score (0 = good, 1 = bad)
        water_deficit_score = self._calculate_water_balance_score(plan)
        
        # 2. Calculate the construction cost
        construction_cost = self._calculate_construction_cost(plan)

        # 3. Normalize cost against the target budget
        cost_score = construction_cost / TARGET_BUDGET
        
        # 4. Combine scores with weighting (70% for solving the problem, 30% for cost)
        fitness = 0.7 * water_deficit_score + 0.3 * cost_score
        
        # 5. Apply budget penalty
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