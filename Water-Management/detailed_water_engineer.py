# ==============================================================================
# Project: [IWMI] Water Resource Management AI
# FILE NAME: detailed_water_engineer.py
# VERSION: 1.0 (HRF Water Balance Adaptation)
# PURPOSE: To perform high-fidelity physics-based optimization of a
#          water management plan using the advanced HRF solver.
# ==============================================================================
import time
import os
import sys
import json
import rasterio
import numpy as np
import trimesh
import matplotlib.cm as cm
import matplotlib.colors as colors
from datetime import datetime
from scipy.ndimage import gaussian_filter
from skopt import gp_minimize
from skopt.space import Real
from rasterio.warp import reproject, Resampling

# Import the professional-grade solver engine
import hrf

# --- Helper function to convert recharge structure (line) to solver-compatible faces ---
# <<< ADAPTED >>> Renamed function and variables for clarity
def convert_structure_to_faces(structure_geom, grid, dem_transform):
    """
    Translates a recharge structure's line geometry into a list of grid faces
    for the hrf.Weir structure (which models a check dam).
    """
    faces = []
    start_r, start_c = rasterio.transform.rowcol(dem_transform, structure_geom['x_start'], structure_geom['y_start'])
    end_r, end_c = rasterio.transform.rowcol(dem_transform, structure_geom['x_end'], structure_geom['y_end'])

    # Bresenham's line algorithm
    dx, dy = abs(end_c - start_c), -abs(end_r - start_r)
    sx, sy = 1 if start_c < end_c else -1, 1 if start_r < end_r else -1
    err = dx + dy
    c, r = start_c, start_r

    while True:
        last_c, last_r = c, r
        if c == end_c and r == end_r: break
        e2 = 2 * err
        moved_x, moved_y = False, False
        if e2 >= dy:
            err += dy
            c += sx
            moved_x = True
        if e2 <= dx:
            err += dx
            r += sy
            moved_y = True
        
        if moved_x and not moved_y:
            face_c = min(last_c, c)
            faces.append(hrf.FaceIndex(i=face_c, j=r, dir='x'))
        elif moved_y and not moved_x:
            face_r = min(last_r, r)
            faces.append(hrf.FaceIndex(i=c, j=face_r, dir='y'))
    return faces

def generate_excavated_terrain(grid, base_plan, params, initial_bed):
    """
    Generates a new terrain by ONLY excavating ponds. Recharge structures are
    handled as separate hydraulic 'weir' structures.
    """
    if initial_bed.shape != (grid.ny, grid.nx):
        min_rows = min(initial_bed.shape[0], grid.ny)
        min_cols = min(initial_bed.shape[1], grid.nx)
        reshaped = np.full((grid.ny, grid.nx), np.mean(initial_bed), dtype=initial_bed.dtype)
        reshaped[:min_rows, :min_cols] = initial_bed[:min_rows, :min_cols]
        initial_bed = reshaped

    X, Y = hrf.to_numpy(grid.X), hrf.to_numpy(grid.Y)
    engineered_bed = initial_bed.copy().astype(np.float32)
    
    # <<< ADAPTED >>> Use new 'harvesting_ponds' key
    for i, p in enumerate(base_plan.get('harvesting_ponds', [])):
        radius_key, depth_key = f'pond_{i}_radius', f'pond_{i}_depth'
        if radius_key in params and depth_key in params:
            r, d = params[radius_key], params[depth_key]
            dist_sq = (X - p['x'])**2 + (Y - p['y'])**2
            excavation = -d * np.exp(-dist_sq / (r**2))
            if excavation.shape != engineered_bed.shape:
                if excavation.size == engineered_bed.size:
                    excavation = excavation.reshape(engineered_bed.shape)
                else: continue
            engineered_bed += excavation
            
    return engineered_bed

memoization_cache = {}
def objective_function(params, param_space, base_plan, initial_bed, grid, dem_transform,
                       initial_runoff_map, total_demand_volume, simulation_days):
    """
    <<< ADAPTED >>>
    This function now calculates the total water *deficit* for a given plan.
    It uses HRF to get a high-fidelity estimate of *captured* water and adds
    the *pumped* water from the optimized parameters.
    The score is the (Unmet Demand) / (Total Demand).
    """
    param_tuple = tuple(float(p) if np.isscalar(p) else str(p) for p in params)
    if param_tuple in memoization_cache:
        return memoization_cache[param_tuple]

    params_dict = {p.name: v for p, v in zip(param_space, params)}
    
    # 1. Generate terrain with ponds excavated
    engineered_bed = generate_excavated_terrain(grid, base_plan, params_dict, initial_bed)
    
    # 2. Instantiate and configure the HRF Solver
    prm = hrf.SWEParams(manning_n=0.04, cfl=0.15, dt_max=0.5)
    filt = hrf.ExponentialFilter()
    solver = hrf.HRFSolver(grid, prm, filt)
    solver.mode = "dw_fv" # Use robust Finite Volume mode
    
    # 3. Set forcing conditions (terrain only, no rain)
    if engineered_bed.shape != (grid.nx, grid.ny):
        engineered_bed = engineered_bed.T  # Transpose to (nx, ny)
    solver.set_forcing(bed=engineered_bed, rain_rate=0.0)
    
    # 4. Translate the plan into realistic hydraulic structures (check dams)
    weir_structures = []
    # <<< ADAPTED >>> Use new 'recharge_structures' key
    for i, structure in enumerate(base_plan.get('recharge_structures', [])):
        height_key = f'structure_{i}_height'
        if height_key in params_dict:
            faces = convert_structure_to_faces(structure, grid, dem_transform)
            if not faces: continue
            
            rows, cols = zip(*[(f.j, f.i) for f in faces])
            ground_elev = np.mean(initial_bed[rows, cols])
            crest_elevation = ground_elev + params_dict[height_key]
            
            weir_structures.append(hrf.Weir(faces=faces, crest_elev=crest_elevation, Cd=1.6))
    
    solver.structures["weirs"] = weir_structures
    
    # 5. Initialize and run simulation to *settle* the available water
    
    # <<< ADAPTED >>> The initial condition 'h0' is now the available runoff supply
    h0 = initial_runoff_map.copy().astype(np.float32)
    # Ensure h0 is in (nx, ny) format for HRF
    if h0.shape != (grid.nx, grid.ny):
        h0 = h0.T 
        
    solver.initialize(h0, np.zeros_like(h0), np.zeros_like(h0))
    # Run for 30 minutes (1800s) to let water settle into ponds and behind dams
    solver.run(t_end=1800.0, verbose=False) 
    
    # 6. Calculate Captured Surface Water Supply
    final_flood_map = hrf.to_numpy(solver.h)
    # Convert back to (ny, nx) if needed
    if final_flood_map.shape != (grid.ny, grid.nx):
        final_flood_map = final_flood_map.T
    
    # Calculate volume of all water held on the map
    captured_volume_m3 = np.sum(final_flood_map[final_flood_map > 0.01]) * grid.dx * grid.dy

    # 7. Calculate Pumped Water Supply
    # <<< ADAPTED >>> Get pumped volume from new optimized parameters
    pumped_volume_m3 = 0.0
    for i, pump in enumerate(base_plan.get('solar_pumps', [])):
        capacity_key = f'pump_{i}_capacity'
        if capacity_key in params_dict:
            pumped_volume_m3 += params_dict[capacity_key] * simulation_days

    # 8. Calculate the final score (Water Deficit Score)
    total_supply_m3 = captured_volume_m3 + pumped_volume_m3
    
    if total_demand_volume <= 0:
        score = 0.0 # No demand, perfect score
    else:
        water_deficit_m3 = max(0, total_demand_volume - total_supply_m3)
        score = water_deficit_m3 / total_demand_volume # 0 = good, 1 = bad
    
    print(f"  -> Testing Design... Water Deficit Score: {score:.4f}")
    memoization_cache[param_tuple] = score
    return score

def export_to_3d_cad_format(filename, grid, bed, base_plan=None, params_dict=None, initial_bed=None):
    # <<< ADAPTED >>> Updated all titles, keys, and component styles
    print(f"📦 Exporting comprehensive 3D water management model to '{filename}'...")
    try:
        X = hrf.to_numpy(grid.X)
        Y = hrf.to_numpy(grid.Y)
        Z = bed.copy()
        X_local, Y_local = X - np.min(X), Y - np.min(Y)

        if initial_bed is not None:
            modifications = Z - initial_bed
            Z = initial_bed + modifications * 10  # Exaggerate changes
        print(f"    -> Terrain dimensions: {X_local.shape}, Elevation range: {np.min(Z):.1f}m - {np.max(Z):.1f}m")

        vertices = np.stack([X_local.flatten(), Y_local.flatten(), Z.flatten()], axis=1)
        faces = []
        ny, nx = grid.ny, grid.nx
        for y in range(ny - 1):
            for x in range(nx - 1):
                v1, v2 = y * nx + x, y * nx + (x + 1)
                v3, v4 = (y + 1) * nx + x, (y + 1) * nx + (x + 1)
                faces.append([v1, v3, v2]); faces.append([v2, v3, v4])
        
        terrain_mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
        elevations = vertices[:, 2]
        norm = colors.Normalize(vmin=np.min(elevations), vmax=np.max(elevations))
        try: cmap = cm.colormaps['terrain']
        except: cmap = plt.colormaps['terrain']
        terrain_colors = (cmap(norm(elevations)) * 255).astype(np.uint8)
        terrain_mesh.visual.vertex_colors = terrain_colors
        meshes = [terrain_mesh]

        if base_plan and params_dict:
            print("    -> Adding intervention visualizations...")
            
            # Harvesting Ponds (Blue Cylinders)
            for i, pond in enumerate(base_plan.get('harvesting_ponds', [])):
                radius_key, depth_key = f'pond_{i}_radius', f'pond_{i}_depth'
                if radius_key in params_dict and depth_key in params_dict:
                    center_x_local, center_y_local = pond['x'] - np.min(X), pond['y'] - np.min(Y)
                    radius, depth = params_dict[radius_key], params_dict[depth_key]
                    pond_cylinder = trimesh.primitives.Cylinder(radius=radius, height=max(0.5, depth * 5), sections=16)
                    pond_cylinder.apply_translation([center_x_local, center_y_local, np.max(Z) + 1])
                    pond_cylinder.visual.vertex_colors = [0, 0, 255, 180] # Blue
                    meshes.append(pond_cylinder)
                    print(f"      - Added pond {i}: r={radius:.1f}m, d={depth:.1f}m")

            # Recharge Structures (Green Walls)
            for i, structure in enumerate(base_plan.get('recharge_structures', [])):
                height_key = f'structure_{i}_height'
                if height_key in params_dict:
                    height = params_dict[height_key]
                    x1, y1 = structure['x_start'], structure['y_start']
                    x2, y2 = structure['x_end'], structure['y_end']
                    if not all(np.isfinite([x1, y1, x2, y2, height])): continue
                    x1_local, y1_local = x1 - np.min(X), y1 - np.min(Y)
                    x2_local, y2_local = x2 - np.min(X), y2 - np.min(Y)
                    length = np.sqrt((x2_local - x1_local)**2 + (y2_local - y1_local)**2)
                    if not (np.isfinite(length) and length > 1e-6): continue

                    try:
                        structure_box = trimesh.primitives.Box(extents=[length, 2.0, height * 3])
                        center_x, center_y = (x1_local + x2_local) / 2, (y1_local + y2_local) / 2
                        angle = np.arctan2(y2_local - y1_local, x2_local - x1_local)
                        translation = trimesh.transformations.translation_matrix([center_x, center_y, np.max(Z) + height * 1.5])
                        rotation = trimesh.transformations.rotation_matrix(angle, [0, 0, 1])
                        structure_box.apply_transform(trimesh.transformations.concatenate_matrices(translation, rotation))
                        structure_box.visual.vertex_colors = [0, 255, 0, 200] # Green
                        meshes.append(structure_box)
                        print(f"      - Added recharge structure {i}: h={height:.1f}m, len={length:.1f}m")
                    except Exception as e_trimesh:
                        print(f"      - FAILED to create trimesh object for structure {i}: {e_trimesh}")

            # NbS Swales (Brown Strips)
            for i, swale in enumerate(base_plan.get('nbs_swales', [])):
                x1, y1 = swale['x_start'], swale['y_start']
                x2, y2 = swale['x_end'], swale['y_end']
                if not all(np.isfinite([x1, y1, x2, y2])): continue
                x1_local, y1_local = x1 - np.min(X), y1 - np.min(Y)
                x2_local, y2_local = x2 - np.min(X), y2 - np.min(Y)
                length = np.sqrt((x2_local - x1_local)**2 + (y2_local - y1_local)**2)
                if not (np.isfinite(length) and length > 1e-6): continue

                try:
                    swale_box = trimesh.primitives.Box(extents=[length, 3.0, 0.5])
                    center_x, center_y = (x1_local + x2_local) / 2, (y1_local + y2_local) / 2
                    angle = np.arctan2(y2_local - y1_local, x2_local - x1_local)
                    translation = trimesh.transformations.translation_matrix([center_x, center_y, np.max(Z) + 0.25])
                    rotation = trimesh.transformations.rotation_matrix(angle, [0, 0, 1])
                    swale_box.apply_transform(trimesh.transformations.concatenate_matrices(translation, rotation))
                    swale_box.visual.vertex_colors = [139, 69, 19, 180] # Brown
                    meshes.append(swale_box)
                    print(f"      - Added NbS swale {i}: len={length:.1f}m")
                except Exception as e_trimesh:
                    print(f"      - FAILED to create trimesh object for swale {i}: {e_trimesh}")

            # Solar Pumps (Orange Markers)
            for i, pump in enumerate(base_plan.get('solar_pumps', [])):
                x_local, y_local = pump['x'] - np.min(X), pump['y'] - np.min(Y)
                pump_marker = trimesh.primitives.Box(extents=[2.0, 2.0, 2.0]) # Make a cube
                pump_marker.apply_translation([x_local, y_local, np.max(Z) + 1.0])
                pump_marker.visual.vertex_colors = [255, 165, 0, 220] # Orange
                meshes.append(pump_marker)
                print(f"      - Added solar pump {i}")
        
        combined_mesh = trimesh.util.concatenate(meshes) if len(meshes) > 1 else meshes[0]
        scene = trimesh.Scene(combined_mesh)
        scene.export(filename)
        print(f"✅ 3D model with {len(meshes)} components saved to: {filename}")
    except Exception as e:
        print(f"❌ ERROR exporting 3D model: {e}")
        import traceback
        traceback.print_exc()

class Tee:
    def __init__(self, *files): self.files = files
    def write(self, obj):
        for f in self.files: f.write(obj); f.flush()
    def flush(self):
        for f in self.files: f.flush()

if __name__ == "__main__":
    # <<< ADAPTED >>> Updated all titles, file paths, and logic
    print("="*80); print("🌊 LAUNCHING STAGE 3: DETAILED WATER ENGINEERING (v1.0 - HRF Engine)"); print("="*80)
    output_dir = os.environ.get('GORAKHPUR_OUTPUT_DIR', f"Outputs/Water_Run_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    os.makedirs(output_dir, exist_ok=True); print(f"📁 Using output directory: {output_dir}")
    log_file = open(f"{output_dir}/stage3_engineer.log", 'w'); sys.stdout = Tee(sys.stdout, log_file); sys.stderr = Tee(sys.stderr, log_file)

    try:
        if len(sys.argv) <= 2: print("❌ ERROR: Script requires diagnostics_report.json and water_management_plan.json"); sys.exit(1)
        diagnostics_file, plan_file = sys.argv[1], sys.argv[2]
        print(f"🌉 Received diagnostics report from: '{diagnostics_file}'")
        print(f"🌉 Received optimal water plan from: '{plan_file}'")
        
        with open(plan_file, 'r') as f:
            full_plan_data = json.load(f)
            base_plan = full_plan_data.get('optimal_plan', full_plan_data)
            
        with open(diagnostics_file, 'r') as f: diagnostics_report = json.load(f)

        # Get the cropped raster paths from the Stage 2 output directory
        output_base_dir = os.path.dirname(diagnostics_file)
        
        # <<< ADAPTED >>> Find the *specific* cropped files for the best zone
        best_zone_id = full_plan_data.get('optimization_summary', {}).get('best_zone', 1)
        print(f"    -> Optimizing for best zone: {best_zone_id}")
        dem_path = f"{output_base_dir}/cropped_dem_zone_{best_zone_id}.tif"
        pop_demand_path = f"{output_base_dir}/cropped_pop_demand_zone_{best_zone_id}.tif"
        water_stress_path = f"{output_base_dir}/cropped_water_stress_zone_{best_zone_id}.tif"
        
        if not os.path.exists(dem_path):
             print(f"    ⚠️ Cropped DEM not found, falling back to zone 1...")
             dem_path = f"{output_base_dir}/cropped_dem_zone_1.tif"
             pop_demand_path = f"{output_base_dir}/cropped_pop_demand_zone_1.tif"
             water_stress_path = f"{output_base_dir}/cropped_water_stress_zone_1.tif"
             if not os.path.exists(dem_path):
                 print(f"    ❌ CRITICAL: No cropped DEM found. Aborting.")
                 sys.exit(1)
        
        print(f"  -> Loading initial terrain from '{dem_path}'...")
        with rasterio.open(dem_path) as dem_src:
            initial_bed = dem_src.read(1)
            grid = hrf.Grid(nx=dem_src.width, ny=dem_src.height,
                          Lx=dem_src.width * dem_src.transform.a,
                          Ly=dem_src.height * abs(dem_src.transform.e))
            dem_profile = dem_src.profile
            print(f"    -> Using grid dimensions: {dem_src.height}×{dem_src.width} pixels")
        
        print(f"  -> Loading and aligning water demand map from '{pop_demand_path}'...")
        with rasterio.open(pop_demand_path) as pop_src:
            demand_map_aligned = np.zeros((dem_src.height, dem_src.width), dtype=pop_src.dtypes[0])
            reproject(source=rasterio.band(pop_src, 1), destination=demand_map_aligned,
                     src_transform=pop_src.transform, src_crs=pop_src.crs,
                     dst_transform=dem_profile['transform'], dst_crs=dem_profile['crs'],
                     resampling=Resampling.nearest)
        
        print(f"  -> Loading and aligning initial runoff supply from '{water_stress_path}'...")
        with rasterio.open(water_stress_path) as stress_src:
            runoff_map_aligned = np.zeros((dem_src.height, dem_src.width), dtype=stress_src.dtypes[0])
            reproject(source=rasterio.band(stress_src, 1), destination=runoff_map_aligned,
                     src_transform=stress_src.transform, src_crs=stress_src.crs,
                     dst_transform=dem_profile['transform'], dst_crs=dem_profile['crs'],
                     resampling=Resampling.nearest)
        
        # --- Calculate Total Demand ---
        SIMULATION_DURATION_DAYS = 30.0
        DEMAND_PER_PERSON_M3_DAY = 0.1
        total_demand_units = np.sum(demand_map_aligned)
        total_demand_volume = (total_demand_units * DEMAND_PER_PERSON_M3_DAY * SIMULATION_DURATION_DAYS)
        print(f"    -> Total Demand for Optimization: {total_demand_volume:,.0f} m³")

        # --- Build Optimization Space ---
        param_space = []
        for i, p in enumerate(base_plan.get('harvesting_ponds', [])):
            param_space.extend([Real(20, 120, name=f'pond_{i}_radius'), Real(0.5, 8.0, name=f'pond_{i}_depth')])
        for i, l in enumerate(base_plan.get('recharge_structures', [])):
            param_space.append(Real(0.2, 3.0, name=f'structure_{i}_height')) # Check dams are lower
        # <<< ADAPTED >>> Add pump capacity to the optimization
        for i, pump in enumerate(base_plan.get('solar_pumps', [])):
            param_space.append(Real(50.0, 500.0, name=f'pump_{i}_capacity')) # Optimize m³/day
        
        if not param_space: print("✅ No parameters to optimize in plan. Skipping Stage 3."); sys.exit(0)
        print(f"\n  -> Dynamically created a {len(param_space)}-dimensional search space.")
        
        n_calls = int(os.environ.get('HRF_OPTIMIZATION_RUNS', '10'))
        if len(sys.argv) > 3:
            try: n_calls = int(sys.argv[3])
            except ValueError: pass

        obj_func_with_data = lambda p: objective_function(p, param_space, base_plan, initial_bed, grid, dem_profile['transform'],
                                                         runoff_map_aligned, total_demand_volume, SIMULATION_DURATION_DAYS)

        if n_calls >= 10:
            print(f"\n🔬 Starting Bayesian Optimization with {n_calls} simulation runs...")
            opt_start = time.time()
            result = gp_minimize(func=obj_func_with_data, dimensions=param_space, n_calls=n_calls, random_state=123)
        else:
            # ... (Random search fallback - logic is unchanged) ...
            print(f"\n🔬 Starting Random Search with {n_calls} simulation runs...")
            opt_start = time.time()
            best_score = float('inf'); best_params = None
            for i in range(n_calls):
                random_params = [param.rvs(random_state=123 + i)[0] if hasattr(param, 'rvs') else param.low + (param.high - param.low) * np.random.rand() for param in param_space]
                score = obj_func_with_data(random_params)
                if score < best_score:
                    best_score = score; best_params = random_params
            class MockResult:
                def __init__(self, fun, x): self.fun = fun; self.x = x
            result = MockResult(best_score, best_params)
        
        print(f"  - ✅ Optimization complete in {time.time() - opt_start:.2f} seconds.")
        best_params_dict = {p.name: v for p, v in zip(param_space, result.x)}

        print("\n" + "="*60 + "\n--- FINAL OPTIMIZED WATER PLAN REPORT ---\n" + "="*60)
        print(f"  - Best Water Deficit Score: {result.fun:.4f} ({(1 - result.fun) * 100:.1f}% of demand met)")
        print("\n--- Optimal Engineering Parameters ---"); [print(f"  - {name}: {val:.2f}") for name, val in best_params_dict.items()]; print("="*60 + "\n")
        
        final_engineered_bed = generate_excavated_terrain(grid, base_plan, best_params_dict, initial_bed)
        # <<< ADAPTED >>> New output file name
        export_to_3d_cad_format(f"{output_dir}/water_engineered_solution.glb", grid, final_engineered_bed,
                               base_plan=base_plan, params_dict=best_params_dict, initial_bed=initial_bed)

    finally:
        sys.stdout = sys.stdout.files[0] if isinstance(sys.stdout, Tee) else sys.stdout
        sys.stderr = sys.stderr.files[0] if isinstance(sys.stderr, Tee) else sys.stderr
        if 'log_file' in locals() and not log_file.closed: log_file.close()