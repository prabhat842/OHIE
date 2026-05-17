# ==============================================================================
# Project: Gorakhpur Urban Resilience AI
# FILE NAME: detailed_engineer.py
# VERSION: 3.0 (HRF Solver Integration)
# PURPOSE: To perform high-fidelity physics-based optimization of an
#          intervention plan using the advanced HRF solver engine.
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

# Import the new, professional-grade solver engine
import hrf

# --- Helper function to convert levee geometry to solver-compatible faces ---
def convert_levee_to_faces(levee_geom, grid, dem_profile):
    """
    Translates a levee's line geometry into a list of grid faces
    for the hrf.Weir structure.
    """
    faces = []
    # Get pixel coordinates for start and end points
    start_r, start_c = rasterio.transform.rowcol(dem_profile['transform'], levee_geom['x_start'], levee_geom['y_start'])
    end_r, end_c = rasterio.transform.rowcol(dem_profile['transform'], levee_geom['x_end'], levee_geom['y_end'])

    # Use Bresenham's line algorithm to trace pixels
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
        
        # Determine the face crossed based on movement direction
        if moved_x and not moved_y: # Horizontal move
            face_c = min(last_c, c)
            faces.append(hrf.FaceIndex(i=face_c, j=r, dir='x'))
        elif moved_y and not moved_x: # Vertical move
            face_r = min(last_r, r)
            faces.append(hrf.FaceIndex(i=c, j=face_r, dir='y'))
        # Diagonal moves can be approximated or handled more complexly if needed
        # For now, this simple approach captures the primary barrier effect.

    return faces

def generate_excavated_terrain(grid, base_plan, params, initial_bed):
    """
    Generates a new terrain by ONLY excavating ponds. Levees are now
    handled as separate hydraulic structures.
    """
    # Ensure initial_bed is in the correct shape (ny, nx) for HRF
    if initial_bed.shape != (grid.ny, grid.nx):
        print(f"    -> Reshaping bed from {initial_bed.shape} to ({grid.ny}, {grid.nx})")
        if initial_bed.size == grid.ny * grid.nx:
            initial_bed = initial_bed.reshape((grid.ny, grid.nx))
        else:
            # Handle dimension mismatch
            min_rows = min(initial_bed.shape[0], grid.ny)
            min_cols = min(initial_bed.shape[1], grid.nx)
            reshaped = np.full((grid.ny, grid.nx), np.mean(initial_bed), dtype=initial_bed.dtype)
            reshaped[:min_rows, :min_cols] = initial_bed[:min_rows, :min_cols]
            initial_bed = reshaped

    X, Y = hrf.to_numpy(grid.X), hrf.to_numpy(grid.Y)
    engineered_bed = initial_bed.copy().astype(np.float32)
    
    for i, p in enumerate(base_plan.get('retention_ponds', [])):
        # Check if parameters for this pond exist in the optimization space
        radius_key, depth_key = f'pond_{i}_radius', f'pond_{i}_depth'
        if radius_key in params and depth_key in params:
            r, d = params[radius_key], params[depth_key]
            dist_sq = (X - p['x'])**2 + (Y - p['y'])**2
            excavation = -d * np.exp(-dist_sq / (r**2))
            # Ensure shapes match - excavation should have same shape as engineered_bed
            if excavation.shape != engineered_bed.shape:
                if excavation.size == engineered_bed.size:
                    excavation = excavation.reshape(engineered_bed.shape)
                else:
                    # Skip if shapes are incompatible
                    continue
            engineered_bed += excavation
            
    return engineered_bed

memoization_cache = {}
def objective_function(params, param_space, base_plan, initial_bed, grid, population_map, dem_profile, initial_risk):
    # Create hashable tuple from parameters
    param_tuple = tuple(float(p) if np.isscalar(p) else str(p) for p in params)
    if param_tuple in memoization_cache:
        return memoization_cache[param_tuple]

    params_dict = {p.name: v for p, v in zip(param_space, params)}
    
    # 1. Generate terrain with ponds excavated
    engineered_bed = generate_excavated_terrain(grid, base_plan, params_dict, initial_bed)
    
    # 2. Instantiate and configure the HRF Solver
    prm = hrf.SWEParams(manning_n=0.04, cfl=0.15, dt_max=0.5)
    filt = hrf.ExponentialFilter() # Required, but less critical for dw_fv mode
    solver = hrf.HRFSolver(grid, prm, filt)
    
    # 3. CRITICAL: Set the solver mode to the robust Finite Volume engine
    solver.mode = "dw_fv"
    
    # 4. Set forcing conditions (terrain and rainfall)
    rain_rate_mmhr = 50.0 # 50 mm/hr rainfall
    rain_rate_ms = rain_rate_mmhr / (3600 * 1000)

    # HRF expects bed in (nx, ny) format, but we have (ny, nx) from rasterio
    if engineered_bed.shape != (grid.nx, grid.ny):
        engineered_bed = engineered_bed.T  # Transpose to (nx, ny)

    solver.set_forcing(bed=engineered_bed, rain_rate=rain_rate_ms)
    
    # 5. Translate the plan into realistic hydraulic structures
    weir_structures = []
    for i, levee in enumerate(base_plan.get('levees', [])):
        height_key = f'levee_{i}_height'
        if height_key in params_dict:
            faces = convert_levee_to_faces(levee, grid, dem_profile)
            if not faces: continue
            
            # Estimate crest elevation: ground level + levee height
            # Take average ground elevation along the levee path
            rows, cols = zip(*[(f.j, f.i) for f in faces])
            ground_elev = np.mean(initial_bed[rows, cols])
            crest_elevation = ground_elev + params_dict[height_key]
            
            weir_structures.append(hrf.Weir(faces=faces, crest_elev=crest_elevation, Cd=1.6))
    
    solver.structures["weirs"] = weir_structures
    
    # 6. Initialize and run the high-fidelity simulation
    h0 = np.full((grid.nx, grid.ny), 0.01, dtype=np.float32)  # HRF expects (nx, ny)
    solver.initialize(h0, np.zeros_like(h0), np.zeros_like(h0))
    solver.run(t_end=1800.0, verbose=False) # 30-minute simulation
    
    # 7. Calculate the final score
    final_flood_map = hrf.to_numpy(solver.h)
    # HRF returns in (nx, ny) format, but population_map is (ny, nx) - transpose if needed
    if final_flood_map.shape != population_map.shape:
        final_flood_map = final_flood_map.T
    remaining_at_risk_pop = np.sum(population_map[final_flood_map > 0.5]) # 50cm flood depth threshold
    score = remaining_at_risk_pop / initial_risk if initial_risk > 0 else 0.0
    
    print(f"  -> Testing Design... Remaining Risk Score: {score:.4f}")
    memoization_cache[param_tuple] = score
    return score

def export_to_3d_cad_format(filename, grid, bed, base_plan=None, params_dict=None, initial_bed=None):
    print(f"📦 Exporting comprehensive 3D model with interventions to '{filename}'...")
    try:
        import matplotlib.cm as cm
        import matplotlib.colors as colors

        # Convert to numpy arrays
        X = hrf.to_numpy(grid.X)
        Y = hrf.to_numpy(grid.Y)
        Z = bed.copy()

        # Convert to local coordinates to avoid scale issues
        X_local = X - np.min(X)
        Y_local = Y - np.min(Y)

        # Exaggerate terrain modifications for visibility (10x vertical exaggeration)
        if initial_bed is not None:
            modifications = Z - initial_bed
            Z = initial_bed + modifications * 10  # Exaggerate changes

        print(f"    -> Terrain dimensions: {X_local.shape}, Elevation range: {np.min(Z):.1f}m - {np.max(Z):.1f}m")

        # Create base terrain mesh
        vertices = np.stack([X_local.flatten(), Y_local.flatten(), Z.flatten()], axis=1)
        faces = []
        ny, nx = grid.ny, grid.nx
        for y in range(ny - 1):
            for x in range(nx - 1):
                v1 = y * nx + x
                v2 = y * nx + (x + 1)
                v3 = (y + 1) * nx + x
                v4 = (y + 1) * nx + (x + 1)
                faces.append([v1, v3, v2])
                faces.append([v2, v3, v4])

        # Create terrain mesh with color coding
        terrain_mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)

        # Color terrain based on elevation and modifications
        elevations = vertices[:, 2]
        norm = colors.Normalize(vmin=np.min(elevations), vmax=np.max(elevations))

        # Use terrain colormap
        try:
            cmap = cm.colormaps['terrain']
        except:
            try:
                cmap = plt.colormaps['terrain']
            except:
                # Fallback to a simple colormap
                import matplotlib.pyplot as plt
                cmap = plt.cm.viridis

        terrain_colors = (cmap(norm(elevations)) * 255).astype(np.uint8)
        terrain_mesh.visual.vertex_colors = terrain_colors

        # Collect all meshes (terrain + interventions)
        meshes = [terrain_mesh]

        # Add intervention visualizations
        if base_plan and params_dict:
            print("    -> Adding intervention visualizations...")

            # Ponds: Create cylindrical representations
            for i, pond in enumerate(base_plan.get('retention_ponds', [])):
                radius_key = f'pond_{i}_radius'
                depth_key = f'pond_{i}_depth'

                if radius_key in params_dict and depth_key in params_dict:
                    center_x, center_y = pond['x'], pond['y']
                    radius = params_dict[radius_key]
                    depth = params_dict[depth_key]

                    # Convert to local coordinates
                    center_x_local = center_x - np.min(X)
                    center_y_local = center_y - np.min(Y)

                    # Create pond cylinder (blue)
                    pond_cylinder = trimesh.primitives.Cylinder(
                        radius=radius,
                        height=max(0.5, depth * 5),  # Exaggerate depth for visibility
                        sections=16
                    )
                    pond_cylinder.apply_translation([
                        center_x_local,
                        center_y_local,
                        np.max(Z) + 1  # Place above terrain
                    ])
                    pond_cylinder.visual.vertex_colors = [0, 0, 255, 180]  # Blue with transparency
                    meshes.append(pond_cylinder)
                    print(f"      - Added pond {i}: r={radius:.1f}m, d={depth:.1f}m")

            # Levees: Create wall-like structures
            for i, levee in enumerate(base_plan.get('levees', [])):
                height_key = f'levee_{i}_height'
                if height_key in params_dict:
                    height = params_dict[height_key]

                    # Create levee wall segments
                    x1, y1 = levee['x_start'], levee['y_start']
                    x2, y2 = levee['x_end'], levee['y_end']

                    # --- START OF FIX ---
                    # 1. Validate the input coordinates before doing anything else.
                    if not all(np.isfinite([x1, y1, x2, y2, height])):
                        print(f"      - SKIPPING levee {i} due to invalid (NaN/inf) input coordinates or height.")
                        continue
                    # --- END OF FIX ---

                    # Convert to local coordinates
                    x1_local = x1 - np.min(X)
                    y1_local = y1 - np.min(Y)
                    x2_local = x2 - np.min(X)
                    y2_local = y2 - np.min(Y)

                    # --- START OF FIX ---
                    # Calculate length and validate it is a usable number greater than zero.
                    length = np.sqrt((x2_local - x1_local)**2 + (y2_local - y1_local)**2)
                    if not (np.isfinite(length) and length > 1e-6): # Use a small epsilon for floating point safety
                        print(f"      - SKIPPING levee {i} due to zero or invalid calculated length.")
                        continue
                    # --- END OF FIX ---

                    try:
                        # Create a box for the levee
                        levee_box = trimesh.primitives.Box(extents=[length, 2.0, height * 3])  # Exaggerate height

                        # Position and rotate the box
                        center_x = (x1_local + x2_local) / 2
                        center_y = (y1_local + y2_local) / 2
                        angle = np.arctan2(y2_local - y1_local, x2_local - x1_local)

                        # Create combined transformation matrix (rotation + translation)
                        translation = trimesh.transformations.translation_matrix([center_x, center_y, np.max(Z) + height * 1.5])
                        rotation = trimesh.transformations.rotation_matrix(angle, [0, 0, 1])
                        combined_transform = trimesh.transformations.concatenate_matrices(translation, rotation)

                        levee_box.apply_transform(combined_transform)
                        levee_box.visual.vertex_colors = [255, 0, 0, 200]  # Red with transparency
                        meshes.append(levee_box)
                        print(f"      - Added levee {i}: h={height:.1f}m, len={length:.1f}m")

                    except Exception as e_trimesh:
                        # --- START OF FIX ---
                        # Add a final safety net to catch any other trimesh errors
                        print(f"      - FAILED to create trimesh object for levee {i}: {e_trimesh}")
                        # --- END OF FIX ---

            # Bioswales: Create channel-like depressions (shown as green strips)
            for i, swale in enumerate(base_plan.get('bioswales', [])):
                x1, y1 = swale['x_start'], swale['y_start']
                x2, y2 = swale['x_end'], swale['y_end']

                # --- START OF FIX ---
                # 1. Validate the input coordinates from the plan file.
                if not all(np.isfinite([x1, y1, x2, y2])):
                    print(f"      - SKIPPING bioswale {i} due to invalid (NaN/inf) input coordinates.")
                    continue
                # --- END OF FIX ---

                # Convert to local coordinates
                x1_local = x1 - np.min(X)
                y1_local = y1 - np.min(Y)
                x2_local = x2 - np.min(X)
                y2_local = y2 - np.min(Y)

                # --- START OF FIX ---
                # Calculate length and validate it is a usable number greater than zero.
                length = np.sqrt((x2_local - x1_local)**2 + (y2_local - y1_local)**2)
                if not (np.isfinite(length) and length > 1e-6): # Use a small epsilon for floating point safety
                    print(f"      - SKIPPING bioswale {i} due to zero or invalid calculated length.")
                    continue
                # --- END OF FIX ---

                try:
                    # Create bioswale as a green rectangular strip
                    swale_box = trimesh.primitives.Box(extents=[length, 3.0, 0.5])  # Low profile for channel
                    center_x = (x1_local + x2_local) / 2
                    center_y = (y1_local + y2_local) / 2
                    angle = np.arctan2(y2_local - y1_local, x2_local - x1_local)

                    # Create combined transformation matrix (rotation + translation)
                    translation = trimesh.transformations.translation_matrix([center_x, center_y, np.max(Z) + 0.25])
                    rotation = trimesh.transformations.rotation_matrix(angle, [0, 0, 1])
                    combined_transform = trimesh.transformations.concatenate_matrices(translation, rotation)

                    swale_box.apply_transform(combined_transform)
                    swale_box.visual.vertex_colors = [0, 255, 0, 180]  # Green with transparency
                    meshes.append(swale_box)
                    print(f"      - Added bioswale {i}: len={length:.1f}m")

                except Exception as e_trimesh:
                    # --- START OF FIX ---
                    # Add a final safety net to catch any other trimesh errors.
                    print(f"      - FAILED to create trimesh object for bioswale {i}: {e_trimesh}")
                    # --- END OF FIX ---

            # Culverts: Add as small orange markers
            for i, culvert in enumerate(base_plan.get('culvert_upgrades', [])):
                x, y = culvert['x'], culvert['y']
                x_local = x - np.min(X)
                y_local = y - np.min(Y)

                # Create small culvert marker
                culvert_marker = trimesh.primitives.Box(extents=[2.0, 2.0, 1.0])
                culvert_marker.apply_translation([x_local, y_local, np.max(Z) + 0.5])
                culvert_marker.visual.vertex_colors = [255, 165, 0, 220]  # Orange with transparency
                meshes.append(culvert_marker)
                print(f"      - Added culvert {i}")

        # Combine all meshes and export
        if len(meshes) > 1:
            combined_mesh = trimesh.util.concatenate(meshes)
        else:
            combined_mesh = meshes[0]

        # Export as GLB
        scene = trimesh.Scene(combined_mesh)
        scene.export(filename)

        print(f"✅ 3D model with {len(meshes)} components saved to: {filename}")
        print(f"   - Terrain mesh: {len(terrain_mesh.vertices)} vertices")
        print(f"   - Total components: {len(meshes)}")

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
    print("="*80); print("🌊 LAUNCHING STAGE 3: DETAILED ENGINEERING (v3.0 - HRF Engine)"); print("="*80)
    output_dir = os.environ.get('GORAKHPUR_OUTPUT_DIR', f"Outputs/Run_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    os.makedirs(output_dir, exist_ok=True); print(f"📁 Using output directory: {output_dir}")
    log_file = open(f"{output_dir}/stage3_engineer.log", 'w'); sys.stdout = Tee(sys.stdout, log_file); sys.stderr = Tee(sys.stderr, log_file)

    try:
        if len(sys.argv) <= 2: print("❌ ERROR: Script requires diagnostics_report.json and intervention_plan.json"); sys.exit(1)
        diagnostics_file, plan_file = sys.argv[1], sys.argv[2]
        print(f"🌉 Received diagnostics report from: '{diagnostics_file}'")
        print(f"🌉 Received optimal intervention plan from: '{plan_file}'")
        
        with open(plan_file, 'r') as f:
            # IMPORTANT: The new plan file is comprehensive. We need to extract the best plan.
            full_plan_data = json.load(f)
            base_plan = full_plan_data.get('optimal_plan', full_plan_data) # Handle both old and new formats
            
        with open(diagnostics_file, 'r') as f: diagnostics_report = json.load(f)

        # Use the cropped rasters from Stage 2 instead of full DEM for consistency
        # This ensures the grid dimensions match the intervention plan's spatial extent
        output_base_dir = os.path.dirname(diagnostics_file)
        dem_path = f"{output_base_dir}/cropped_dem_zone_1.tif"
        pop_path = f"{output_base_dir}/cropped_pop_zone_1.tif"

        print(f"    -> Looking for cropped files in: {output_base_dir}")
        print(f"    -> DEM path: {dem_path}")
        print(f"    -> POP path: {pop_path}")
        dem_exists = os.path.exists(dem_path)
        print(f"    -> DEM exists: {dem_exists}")

        if not dem_exists:
            print("    ⚠️ Cropped DEM not found, falling back to full DEM (may cause shape issues)")
            dem_path = "Data/GKP/DEM_GKP_UTM.tif"
        else:
            print(f"    ✅ Using cropped DEM: {dem_path}")

        print(f"  -> Loading initial terrain from '{dem_path}'...")
        with rasterio.open(dem_path) as dem_src:
            initial_bed = dem_src.read(1)
            # Create grid that matches the cropped raster dimensions
            grid = hrf.Grid(nx=dem_src.width, ny=dem_src.height,
                          Lx=dem_src.width * dem_src.transform.a,
                          Ly=dem_src.height * abs(dem_src.transform.e))
            dem_profile = dem_src.profile
            print(f"    -> Using grid dimensions: {dem_src.height}×{dem_src.width} pixels")
        
        print(f"  -> Loading and aligning population map from '{pop_path}'...")
        with rasterio.open(pop_path) as pop_src:
            # Create destination array matching DEM dimensions
            population_map_aligned = np.zeros((dem_src.height, dem_src.width), dtype=pop_src.dtypes[0])
            reproject(source=rasterio.band(pop_src, 1), destination=population_map_aligned,
                     src_transform=pop_src.transform, src_crs=pop_src.crs,
                     dst_transform=dem_profile['transform'], dst_crs=dem_profile['crs'],
                     resampling=Resampling.nearest)
            print(f"    -> Aligned population map to DEM dimensions: {population_map_aligned.shape}")
        
        initial_risk = np.sum(population_map_aligned[initial_bed < 9999]) # Only count population on valid land

        param_space = []
        for i, p in enumerate(base_plan.get('retention_ponds', [])):
            param_space.extend([Real(20, 120, name=f'pond_{i}_radius'), Real(0.5, 8.0, name=f'pond_{i}_depth')])  # Wider depth range
        for i, l in enumerate(base_plan.get('levees', [])):
            param_space.append(Real(0.2, 5.0, name=f'levee_{i}_height'))  # Wider height range
        
        if not param_space: print("✅ No parameters to optimize in plan. Skipping Stage 3."); sys.exit(0)

        print(f"\n  -> Dynamically created a {len(param_space)}-dimensional search space.")

        # Make number of simulations configurable
        n_calls = int(os.environ.get('HRF_OPTIMIZATION_RUNS', '10'))
        if len(sys.argv) > 3:  # Allow command line override
            try:
                n_calls = int(sys.argv[3])
            except ValueError:
                pass

        # Use different optimization strategy based on number of calls
        if n_calls >= 10:
            print(f"\n🔬 Starting Bayesian Optimization with {n_calls} simulation runs...")
            opt_start = time.time()
            obj_func_with_data = lambda p: objective_function(p, param_space, base_plan, initial_bed, grid, population_map_aligned, dem_profile, initial_risk)
            result = gp_minimize(func=obj_func_with_data, dimensions=param_space, n_calls=n_calls, random_state=123)
        else:
            print(f"\n🔬 Starting Random Search with {n_calls} simulation runs (Bayesian requires ≥10)...")
            opt_start = time.time()

            # Simple random search for small numbers of evaluations
            best_score = float('inf')
            best_params = None

            for i in range(n_calls):
                # Random parameter sampling
                random_params = []
                for param in param_space:
                    if hasattr(param, 'low') and hasattr(param, 'high'):
                        val = param.rvs(random_state=123 + i)
                        # Ensure it's a scalar, not a list/array
                        if isinstance(val, (list, np.ndarray)):
                            val = float(val[0] if len(val) > 0 else val)
                        random_params.append(val)
                    else:
                        # Handle other parameter types
                        random_params.append(param.low + (param.high - param.low) * np.random.random())

                # Evaluate
                score = objective_function(random_params, param_space, base_plan, initial_bed, grid, population_map_aligned, dem_profile, initial_risk)

                if score < best_score:
                    best_score = score
                    best_params = random_params.copy()

            # Create mock result object
            class MockResult:
                def __init__(self, fun, x):
                    self.fun = fun
                    self.x = x

            result = MockResult(best_score, best_params)
        print(f"  - ✅ Optimization complete in {time.time() - opt_start:.2f} seconds.")
        best_params_dict = {p.name: v for p, v in zip(param_space, result.x)}

        print("\n" + "="*60 + "\n--- FINAL OPTIMIZED PERFORMANCE REPORT ---\n" + "="*60)
        print(f"  - Best Risk Score: {result.fun:.4f} ({1 - result.fun:.2%} risk reduction)")
        print("\n--- Optimal Engineering Parameters ---"); [print(f"  - {name}: {val:.2f}") for name, val in best_params_dict.items()]; print("="*60 + "\n")
        
        final_engineered_bed = generate_excavated_terrain(grid, base_plan, best_params_dict, initial_bed)
        export_to_3d_cad_format(f"{output_dir}/engineered_solution.glb", grid, final_engineered_bed,
                               base_plan=base_plan, params_dict=best_params_dict, initial_bed=initial_bed)

    finally:
        sys.stdout = sys.stdout.files[0] if isinstance(sys.stdout, Tee) else sys.stdout
        sys.stderr = sys.stderr.files[0] if isinstance(sys.stderr, Tee) else sys.stderr
        if 'log_file' in locals() and not log_file.closed: log_file.close()