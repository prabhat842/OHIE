# ==============================================================================
# Project: Culturiq AI-Driven Infrastructure
# FILE NAME: alignment_validator.py
# VERSION: 1.0 (Adapted from detailed_engineer.py v3.0)
# PURPOSE: To perform a high-fidelity physics-based validation of the
#          top alignment plans from Stage 2 using the advanced HRF solver.
# ==============================================================================
import time
import os
import sys
import json
import rasterio
import numpy as np
import trimesh
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import matplotlib.colors as colors
from datetime import datetime
from rasterio.warp import reproject, Resampling
import simplekml
from pyproj import Transformer

# Import the professional-grade solver engine
import hrf

# --- Helper function copied from alignment_rules.py ---
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

# <<< REMOVED >>> convert_levee_to_faces (not needed for this pipeline)
# <<< REMOVED >>> generate_excavated_terrain (not needed for this pipeline)
# <<< REMOVED >>> objective_function (not needed, we are validating, not optimizing)

# --- New Validation Functions ---

def _score_path_risk(alignment_path, final_flood_map, transform):
    """
    Calculates the total flood risk for a single alignment path
    by sampling the final HRF flood map.
    """
    total_risk_score = 0.0
    pixels_in_path = 0

    if not alignment_path:
        return float('inf')

    # Get the pixel coordinates for the first point
    try:
        r_last, c_last = rasterio.transform.rowcol(transform, alignment_path[0][0], alignment_path[0][1])
    except rasterio.errors.OutOfBoundsError:
        return float('inf') # Path starts outside bounds

    grid_height, grid_width = final_flood_map.shape

    # Iterate through each segment of the path
    for (x, y) in alignment_path[1:]:
        try:
            r_curr, c_curr = rasterio.transform.rowcol(transform, x, y)
        except rasterio.errors.OutOfBoundsError:
            total_risk_score += 1000.0 # Penalize going off-grid
            continue
        
        # Get all pixels on the segment
        pixels_on_segment = bresenham_line(c_last, r_last, c_curr, r_curr)
        
        for (r, c) in pixels_on_segment:
            if 0 <= r < grid_height and 0 <= c < grid_width:
                # Risk score is the sum of water depth along the path
                total_risk_score += final_flood_map[r, c]
                pixels_in_path += 1
            
        r_last, c_last = r_curr, c_curr
    
    # Return the average water depth along the path
    return total_risk_score / max(1, pixels_in_path)


def validate_alignments_with_hrf(base_plan, initial_bed, grid, dem_profile, output_dir):
    """
    Runs a single, high-fidelity HRF simulation (e.g., a storm event) and
    evaluates the flood risk for each of the top alignment plans.
    """
    print("  -> 🌊 Initializing High-Fidelity HRF Storm Simulation...")
    
    # 1. Instantiate and configure the HRF Solver
    # Use robust parameters for complex terrain
    prm = hrf.SWEParams(manning_n=0.04, cfl=0.15, dt_max=0.5, h_min=1e-3)
    filt = hrf.ExponentialFilter(alpha=96.0, p=8)
    solver = hrf.HRFSolver(grid, prm, filt)
    solver.mode = "dw_fv" # Use robust Finite Volume mode
    
    # 2. Set forcing conditions
    # HRF expects bed in (nx, ny) format, but rasterio gives (ny, nx)
    if initial_bed.shape != (grid.nx, grid.ny):
        initial_bed_hrf = initial_bed.T  # Transpose to (nx, ny)
    else:
        initial_bed_hrf = initial_bed
    
    # Simulate a storm surge/tide event instead of pure rainfall
    # No rainfall input - focus on standing water/tidal surge
    rain_rate_ms = 0.0  # No pure rainfall simulation

    # Simulate a 2m surge/tide event
    surge_level_m = 2.0
    h0 = np.full((grid.nx, grid.ny), surge_level_m, dtype=np.float32)

    solver.set_forcing(bed=initial_bed_hrf, rain_rate=rain_rate_ms, infil_rate=0.0)
    solver.initialize(h0, np.zeros_like(h0), np.zeros_like(h0))
    
    t_end_sim = 3600.0 # Simulate for 1 hour
    print(f"  -> ⏱️  Running {t_end_sim / 3600.0:.1f} hour surge simulation...")
    sim_start = time.time()
    solver.run(t_end=t_end_sim, verbose=True, output_every=600.0)
    print(f"  -> ✅ Simulation complete in {time.time() - sim_start:.2f} seconds.")
    
    # 4. Get the final flood map
    final_flood_map = hrf.to_numpy(solver.h) # This is (nx, ny)
    # Transpose to (ny, nx) to match our raster grid
    final_flood_map = final_flood_map.T 
    
    # 5. Score each of the top 5 alignments
    print("\n  -> 📊 Scoring Top 5 Alignments against Flood Map...")
    validation_results = []
    top_5_alignments = base_plan['top_5_alignments']
    
    for i, alignment in enumerate(top_5_alignments):
        # Handle new dictionary format from planner
        if isinstance(alignment, dict) and 'path' in alignment:
            path = alignment['path']
            ga_fitness = alignment['fitness']
        # Handle DEAP Individual objects (legacy)
        elif hasattr(alignment, 'fitness'):
            path = alignment  # The individual itself is the path (list of coordinates)
            ga_fitness = alignment.fitness.values[0]
        else:
            # Fallback for other formats
            path = alignment
            ga_fitness = 0.0

        # Calculate the new, physics-based risk score
        hrf_risk_score = _score_path_risk(path, final_flood_map, dem_profile['transform'])
        
        validation_results.append({
            'rank': i + 1,
            'ga_fitness': ga_fitness,
            'hrf_risk_score': hrf_risk_score,
            'path': path
        })
        print(f"    - Rank {i+1}: GA Fitness={ga_fitness:.4f}  ->  HRF Risk (Avg Depth)={hrf_risk_score:.4f} m")

    # Sort results by the new HRF Risk Score (lowest is best)
    validation_results.sort(key=lambda x: x['hrf_risk_score'])
    
    print("\n  -> ✅ Validation Complete. Final Physical Risk Ranking:")
    for i, res in enumerate(validation_results):
        print(f"    - New Rank {i+1}: (Original Rank {res['rank']}) -> HRF Risk: {res['hrf_risk_score']:.4f} m")
        
    return validation_results, final_flood_map, initial_bed, t_end_sim


# <<< NEW >>> Export validation results to KML and SHP formats
def export_alignment_validation_kml(filename, validation_results, diagnostics_report):
    """Exports the validated alignments from Stage 3 to KML and SHP files."""
    try:
        import geopandas as gpd
        from shapely.geometry import LineString
        print(f"🌍 Exporting validated alignments to KML and SHP...")

        kml = simplekml.Kml(name="Validated Alignments - HRF Flood Risk")

        # Define colors by HRF risk ranking (physics-based)
        # Green (low risk) to Red (high risk)
        risk_colors = [
            simplekml.Style(linestyle=simplekml.LineStyle(color=simplekml.Color.green, width=6)),  # Rank 1 (Best)
            simplekml.Style(linestyle=simplekml.LineStyle(color=simplekml.Color.blue, width=5)),   # Rank 2
            simplekml.Style(linestyle=simplekml.LineStyle(color=simplekml.Color.yellow, width=4)), # Rank 3
            simplekml.Style(linestyle=simplekml.LineStyle(color=simplekml.Color.orange, width=3)), # Rank 4
            simplekml.Style(linestyle=simplekml.LineStyle(color=simplekml.Color.red, width=2))     # Rank 5
        ]

        transformer = Transformer.from_crs(diagnostics_report['raster_profile']['crs'], "EPSG:4326", always_xy=True)

        # Prepare data for shapefile
        gdf_data = []

        for res in validation_results:
            # Get the path coordinates
            path_utm = res['path']
            coords_wgs84 = list(transformer.itransform(path_utm))

            # Create KML linestring with HRF risk info
            hrf_risk = res['hrf_risk_score']
            ga_rank = res['rank']
            ga_fitness = res['ga_fitness']

            line = kml.newlinestring(
                name=f"HRF Rank {ga_rank} (Risk: {hrf_risk:.4f}m, GA: {ga_fitness:.2f})",
                coords=coords_wgs84
            )
            line.style = risk_colors[ga_rank - 1]  # Use HRF ranking for color

            # Prepare data for shapefile
            line_geom = LineString(coords_wgs84)
            gdf_data.append({
                'hrf_rank': ga_rank,
                'ga_fitness': float(ga_fitness),
                'hrf_risk_m': float(hrf_risk),
                'ga_rank': int(res['rank']),
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
        kml = simplekml.Kml(name="Validated Alignments - HRF Flood Risk")

        risk_colors = [
            simplekml.Style(linestyle=simplekml.LineStyle(color=simplekml.Color.green, width=6)),
            simplekml.Style(linestyle=simplekml.LineStyle(color=simplekml.Color.blue, width=5)),
            simplekml.Style(linestyle=simplekml.LineStyle(color=simplekml.Color.yellow, width=4)),
            simplekml.Style(linestyle=simplekml.LineStyle(color=simplekml.Color.orange, width=3)),
            simplekml.Style(linestyle=simplekml.LineStyle(color=simplekml.Color.red, width=2))
        ]

        transformer = Transformer.from_crs(diagnostics_report['raster_profile']['crs'], "EPSG:4326", always_xy=True)

        for res in validation_results:
            path_utm = res['path']
            coords_wgs84 = list(transformer.itransform(path_utm))

            hrf_risk = res['hrf_risk_score']
            ga_rank = res['rank']
            ga_fitness = res['ga_fitness']

            line = kml.newlinestring(
                name=f"HRF Rank {ga_rank} (Risk: {hrf_risk:.4f}m, GA: {ga_fitness:.2f})",
                coords=coords_wgs84
            )
            line.style = risk_colors[ga_rank - 1]

        kml.save(filename)
        print(f"✅ KML file '{filename}' saved successfully (SHP export skipped - GeoPandas not available).")

    except Exception as e:
        print(f"❌ ERROR: Failed to export validation alignments. Error: {e}")


# <<< ADAPTED >>> This function now visualizes the terrain, the flood, and the paths
def export_to_3d_cad_format(filename, grid, bed_elevation_map, final_flood_map, validation_results):
    """
    Exports the terrain, final flood map, and top 5 alignments to a GLB file.
    """
    print(f"📦 Exporting 3D alignment validation model to '{filename}'...")
    try:
        # Load full DEM profile for coordinate conversion (paths are in full UTM coordinates)
        dem_profile = None
        full_dem_path = "Data/UTM43_Data_Mumbai/topobathy_utm43.tif"
        try:
            with rasterio.open(full_dem_path) as dem_src:
                dem_profile = dem_src.profile
            print(f"    -> Using topobathy DEM bounds for path coordinate conversion: {dem_src.bounds}")
        except Exception as e:
            print(f"    -> Could not load topobathy DEM profile: {e}")

        # Get the cropped DEM profile to create UTM coordinate arrays
        cropped_dem_profile = None
        if crop_bounds:
            # If cropped, we need to create UTM coordinate arrays for the cropped area
            try:
                from rasterio.mask import mask
                from shapely.geometry import box
                import geopandas as gpd

                with rasterio.open(dem_path) as src:
                    bbox = box(crop_bounds['left'], crop_bounds['bottom'], crop_bounds['right'], crop_bounds['top'])
                    gdf_bbox = gpd.GeoDataFrame({'geometry': [bbox]}, crs=src.crs)
                    cropped_data, cropped_transform = mask(src, gdf_bbox.geometry, crop=True, nodata=src.nodata)
                    cropped_dem_profile = src.profile.copy()
                    cropped_dem_profile.update({
                        'height': cropped_data.shape[1],  # Note: shape is (1, ny, nx)
                        'width': cropped_data.shape[2],
                        'transform': cropped_transform
                    })

                # Create UTM coordinate arrays for the cropped area
                ny, nx = cropped_dem_profile['height'], cropped_dem_profile['width']
                cols, rows = np.meshgrid(np.arange(nx), np.arange(ny))
                X_utm, Y_utm = rasterio.transform.xy(cropped_dem_profile['transform'], rows, cols)
                X_utm = np.array(X_utm).reshape(ny, nx)
                Y_utm = np.array(Y_utm).reshape(ny, nx)

                print(f"    -> Created UTM coordinate arrays for cropped area:")
                print(f"      X: {np.min(X_utm):.1f} to {np.max(X_utm):.1f}")
                print(f"      Y: {np.min(Y_utm):.1f} to {np.max(Y_utm):.1f}")
                print(f"      Grid shape: {X_utm.shape}")

            except Exception as e:
                print(f"    -> Could not create UTM coordinate arrays: {e}")
                X_utm, Y_utm = None, None
        else:
            X_utm, Y_utm = None, None

        X = hrf.to_numpy(grid.X).T # Transpose back to (ny, nx)
        Y = hrf.to_numpy(grid.Y).T

        print(f"    -> Cropped grid coordinate ranges:")
        print(f"      X: {np.min(X):.1f} to {np.max(X):.1f}")
        print(f"      Y: {np.min(Y):.1f} to {np.max(Y):.1f}")
        print(f"      Grid shape: {X.shape}")

        # 1. Create Base Terrain Mesh
        Z_terrain = bed_elevation_map.copy()

        # Exaggerate terrain for visibility (e.g., 5x vertical exaggeration)
        z_min, z_max = np.min(Z_terrain), np.max(Z_terrain)
        Z_terrain_exaggerated = (Z_terrain - z_min) * 5.0  # Scale elevation to 0-5 range

        # Center coordinates for better 3D viewing
        x_center = np.mean(X)
        y_center = np.mean(Y)
        X_centered = X - x_center
        Y_centered = Y - y_center

        # Use X, Z, Y coordinates (Z=elevation as vertical axis)
        vertices = np.stack([X_centered.flatten(), Z_terrain_exaggerated.flatten(), Y_centered.flatten()], axis=1)
        faces = []
        ny, nx = grid.ny, grid.nx
        for y in range(ny - 1):
            for x in range(nx - 1):
                v1, v2 = y * nx + x, y * nx + (x + 1)
                v3, v4 = (y + 1) * nx + x, (y + 1) * nx + (x + 1)
                faces.append([v1, v3, v2]); faces.append([v2, v3, v4])

        terrain_mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)

        # Color terrain with proper RGBA format
        norm = colors.Normalize(vmin=np.min(Z_terrain_exaggerated), vmax=np.max(Z_terrain_exaggerated))
        try:
            cmap = cm.get_cmap('terrain')
        except:
            cmap = plt.get_cmap('terrain')
        terrain_rgb = (cmap(norm(Z_terrain_exaggerated)) * 255).astype(np.uint8)
        # Add alpha channel
        terrain_colors = np.zeros((terrain_rgb.shape[0], terrain_rgb.shape[1], 4), dtype=np.uint8)
        terrain_colors[:, :, :3] = terrain_rgb[:, :, :3]
        terrain_colors[:, :, 3] = 255  # Fully opaque
        terrain_mesh.visual.vertex_colors = terrain_colors.reshape(-1, 4)

        meshes = [terrain_mesh]

        # 2. Create Flood Water Mesh
        # Water depth (exaggerate this too, and lift slightly)
        water_mask = final_flood_map > 0.01

        if np.any(water_mask):
            # Create water surface only where there's water
            Z_water = Z_terrain_exaggerated + final_flood_map * 50.0 + 0.5 # 50x exaggeration, 0.5m lift

            # Create mesh only for water areas to avoid NaN issues
            water_faces = []
            water_vertices = []
            vertex_map = {}  # Map (y,x) to vertex index

            # First pass: collect valid vertices
            vertex_index = 0
            for y in range(ny):
                for x in range(nx):
                    if water_mask[y, x] and not np.isnan(Z_water[y, x]):
                        water_vertices.append([X_centered[y, x], Z_water[y, x], Y_centered[y, x]])
                        vertex_map[(y, x)] = vertex_index
                        vertex_index += 1

            # Second pass: create faces for valid quads
            for y in range(ny - 1):
                for x in range(nx - 1):
                    # Check if all 4 corners have water and are valid
                    corners = [(y, x), (y, x+1), (y+1, x), (y+1, x+1)]
                    if all(corner in vertex_map for corner in corners):
                        v1 = vertex_map[(y, x)]
                        v2 = vertex_map[(y, x+1)]
                        v3 = vertex_map[(y+1, x)]
                        v4 = vertex_map[(y+1, x+1)]
                        water_faces.append([v1, v3, v2])
                        water_faces.append([v2, v3, v4])

            if water_faces:
                water_vertices = np.array(water_vertices)
                water_mesh = trimesh.Trimesh(vertices=water_vertices, faces=water_faces, process=False)
                # Color water blue with transparency (RGBA)
                water_mesh.visual.vertex_colors = np.array([0, 100, 255, 150])
                meshes.append(water_mesh)
                print(f"    -> Added flood water mesh: {len(water_faces)} faces, {len(water_vertices)} vertices")

        # 3. Add Alignment Paths as 3D tubes
        print("    -> Adding alignment paths...")
        # Define colors by rank: Red→Orange→Yellow→Green→Blue
        rank_colors = {
            1: [255, 0, 0, 255],      # Red
            2: [255, 165, 0, 255],    # Orange
            3: [255, 255, 0, 255],    # Yellow
            4: [0, 255, 0, 255],      # Green
            5: [0, 0, 255, 255]       # Blue
        }
        print(f"    -> Processing {len(validation_results)} alignment paths...")

        for res in validation_results:
            path_utm = res['path']
            risk = res['hrf_risk_score']
            rank = res['rank']

            # Get color by rank
            path_color = rank_colors.get(rank, [128, 128, 128, 255])  # Gray fallback
            
            # Create 3D path vertices
            path_vertices_3d = []
            if X_utm is not None and Y_utm is not None:
                for (x, y) in path_utm:
                    try:
                        # Find closest grid point in UTM coordinates
                        x_distances = np.abs(X_utm - x)
                        y_distances = np.abs(Y_utm - y)
                        total_distances = x_distances + y_distances

                        # Find the minimum distance index
                        min_idx = np.unravel_index(np.argmin(total_distances), total_distances.shape)
                        r, c = min_idx

                        # Check if close enough (within reasonable distance)
                        min_distance = total_distances[r, c]
                        if min_distance < 50:  # Within 50m (reasonable for path matching)
                            # Use centered coordinates and proper Z axis
                            x_centered = X_centered[r, c]
                            y_centered = Y_centered[r, c]
                            z = Z_terrain_exaggerated[r, c] + 1.0  # 1m lift above terrain
                            path_vertices_3d.append([x_centered, z, y_centered])
                    except:
                        continue # Skip points that can't be mapped

            print(f"      - Path Rank {rank}: processing {len(path_utm)} UTM points -> {len(path_vertices_3d)} valid vertices")
            if len(path_vertices_3d) > 1:
                # Create a simple 3D path using cubes instead of spheres for better visibility
                try:
                    path_meshes = []
                    for i, point in enumerate(path_vertices_3d):
                        # Create a cube instead of sphere for better GLB compatibility
                        cube = trimesh.creation.box(extents=[15.0, 15.0, 15.0])  # 15x15x15 cube - even larger
                        cube.apply_translation(point)
                        # Use trimesh's simple color system
                        cube.visual.face_colors = [path_color[0], path_color[1], path_color[2], 255]
                        path_meshes.append(cube)

                    # Combine all cubes for this path into one mesh
                    if path_meshes:
                        path_combined = trimesh.util.concatenate(path_meshes)
                        meshes.append(path_combined)
                        print(f"      - ✅ Added Path Rank {rank} (Risk: {risk:.4f}) - {len(path_vertices_3d)} cubes")
                    else:
                        print(f"      - ❌ No cubes created for Path Rank {rank}")
                except Exception as e:
                    print(f"      - ❌ Failed to create cubes for Path Rank {rank}: {e}")
            else:
                print(f"      - ❌ Path Rank {rank} has insufficient vertices: {len(path_vertices_3d)}")

        # 4. Create scene with all meshes
        scene = trimesh.Scene()
        for mesh in meshes:
            scene.add_geometry(mesh)

        # Export the scene
        scene.export(filename)
        print(f"✅ 3D validation model with {len(meshes)} components saved to: {filename}")

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
    print("="*80); print("🌊 LAUNCHING STAGE 3: ALIGNMENT VALIDATOR (v1.0 - HRF Engine)"); print("="*80)
    
    # <<< ADAPTED >>> Using new environment variable
    output_dir = os.environ.get('PIPELINE_OUTPUT_DIR', f"Outputs/Alignment_Run_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    os.makedirs(output_dir, exist_ok=True); print(f"📁 Using output directory: {output_dir}")
    
    log_file = open(f"{output_dir}/stage3_validator.log", 'w'); sys.stdout = Tee(sys.stdout, log_file); sys.stderr = Tee(sys.stderr, log_file)

    try:
        # <<< ADAPTED >>> New input bridge files
        if len(sys.argv) <= 2: print("❌ ERROR: Script requires cost_atlas_report.json and alignment_plan.json"); sys.exit(1)
        diagnostics_file, plan_file = sys.argv[1], sys.argv[2]
        print(f"🌉 Received cost atlas report from: '{diagnostics_file}'")
        print(f"🌉 Received top alignment plans from: '{plan_file}'")
        
        with open(plan_file, 'r') as f:
            base_plan = json.load(f) # Contains 'top_5_alignments'
            
        with open(diagnostics_file, 'r') as f:
            diagnostics_report = json.load(f)

        # Check if Stage 1 used cropping
        crop_bounds = None
        try:
            # Try to infer crop bounds from the atlas dimensions vs full DEM
            atlas_path = diagnostics_report['atlas_paths']['earthworks_cost_atlas']
            with rasterio.open(atlas_path) as atlas_src:
                atlas_bounds = atlas_src.bounds
                atlas_width = atlas_src.width
                atlas_height = atlas_src.height

            # Get full DEM dimensions
            dem_path = "Data/UTM43_Data_Mumbai/topobathy_utm43.tif"
            with rasterio.open(dem_path) as full_dem_src:
                full_width = full_dem_src.width
                full_height = full_dem_src.height

            # If atlas dimensions are smaller, Stage 1 was cropped
            if atlas_width < full_width or atlas_height < full_height:
                crop_bounds = {
                    'left': atlas_bounds.left,
                    'bottom': atlas_bounds.bottom,
                    'right': atlas_bounds.right,
                    'top': atlas_bounds.top
                }
                print(f"  -> Detected cropped AOI from Stage 1: {crop_bounds}")
        except Exception as e:
            print(f"  -> Could not detect cropping from Stage 1: {e}")

        # Load DEM (cropped or full)
        dem_path = "Data/UTM43_Data_Mumbai/topobathy_utm43.tif"
        if crop_bounds is not None:
            print(f"  -> Using cropped DEM for Stage 3 (AOI mode)...")
            from rasterio.mask import mask
            import geopandas as gpd
            from shapely.geometry import box

            with rasterio.open(dem_path) as dem_src:
                bbox = box(crop_bounds['left'], crop_bounds['bottom'], crop_bounds['right'], crop_bounds['top'])
                gdf_bbox = gpd.GeoDataFrame({'geometry': [bbox]}, crs=dem_src.crs)

                # Crop DEM to match AOI
                cropped_dem, cropped_transform = mask(dem_src, gdf_bbox.geometry, crop=True, nodata=dem_src.nodata)
                initial_bed = cropped_dem[0].astype(np.float32)  # Remove band dimension
                initial_bed = np.nan_to_num(initial_bed, nan=np.nanmean(initial_bed))  # Fill NaNs

                # Create grid that matches the cropped dimensions
                grid = hrf.Grid(nx=initial_bed.shape[1], ny=initial_bed.shape[0],
                              Lx=initial_bed.shape[1] * cropped_transform.a,
                              Ly=initial_bed.shape[0] * abs(cropped_transform.e))
                dem_profile = dem_src.profile.copy()
                dem_profile.update({
                    'height': initial_bed.shape[0],
                    'width': initial_bed.shape[1],
                    'transform': cropped_transform
                })
                print(f"    -> Using cropped grid dimensions: {initial_bed.shape[0]}×{initial_bed.shape[1]} pixels")
        else:
            print(f"  -> Using full DEM for Stage 3 (watershed mode)...")
            with rasterio.open(dem_path) as dem_src:
                initial_bed = dem_src.read(1).astype(np.float32) # (ny, nx)
                if dem_src.nodata is not None:
                    initial_bed[initial_bed == dem_src.nodata] = np.nan
                initial_bed = np.nan_to_num(initial_bed, nan=np.nanmean(initial_bed)) # Fill NaNs

                # Create grid that matches the full raster dimensions
                grid = hrf.Grid(nx=dem_src.width, ny=dem_src.height,
                              Lx=dem_src.width * dem_src.transform.a,
                              Ly=dem_src.height * abs(dem_src.transform.e))
                dem_profile = dem_src.profile
                print(f"    -> Using grid dimensions: {dem_src.height}×{dem_src.width} pixels")
        
        # <<< REMOVED >>> No population map needed
        # <<< REMOVED >>> No optimization parameter space needed

        # <<< ADAPTED >>> Run the new validation function
        validation_results, final_flood_map, initial_bed_map, t_end_sim = validate_alignments_with_hrf(
            base_plan, initial_bed, grid, dem_profile, output_dir
        )
        
        print("\n" + "="*60 + "\n--- FINAL ALIGNMENT VALIDATION REPORT ---\n" + "="*60)
        print("  - Sorted by physical flood risk (Avg. Depth):")
        for i, res in enumerate(validation_results):
            print(f"    - Rank {i+1} (GA Rank {res['rank']}): Fitness={res['ga_fitness']:.4f}  |  HRF Risk={res['hrf_risk_score']:.4f} m")
        print("="*60 + "\n")
        
        # <<< NEW >>> Export validated alignments to KML and SHP
        export_alignment_validation_kml(f"{output_dir}/alignment_validation.kml", validation_results, diagnostics_report)

        # <<< ADAPTED >>> Save new 3D model
        export_to_3d_cad_format(f"{output_dir}/alignment_validation.glb", grid,
                                initial_bed_map, final_flood_map, validation_results)
        
        # Helper function for JSON serialization
        def make_json_serializable(obj):
            if isinstance(obj, np.integer): return int(obj)
            elif isinstance(obj, np.floating): return float(obj)
            elif isinstance(obj, np.ndarray): return obj.tolist()
            elif isinstance(obj, dict): return {key: make_json_serializable(value) for key, value in obj.items()}
            elif isinstance(obj, list): return [make_json_serializable(item) for item in obj]
            else: return obj

        # <<< ADAPTED >>> Save new final report
        final_report = {
            "project_type": "Linear Infrastructure Alignment Validation",
            "hrf_simulation_time_s": t_end_sim,
            "validation_ranking": make_json_serializable(validation_results)
        }
        report_path = f"{output_dir}/alignment_validation_report.json"
        with open(report_path, 'w') as f:
            json.dump(final_report, f, indent=2)
        print(f"  - ✅ Saved final validation report to '{report_path}'")


    finally:
        sys.stdout = sys.stdout.files[0] if isinstance(sys.stdout, Tee) else sys.stdout
        sys.stderr = sys.stderr.files[0] if isinstance(sys.stderr, Tee) else sys.stderr
        if 'log_file' in locals() and not log_file.closed: log_file.close()