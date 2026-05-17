# ==============================================================================
# Project: Chimera-Urbanist - Bioswale Design
# FILE NAME: bioswale_designer.py
# VERSION: 2.2 (Final CAD Export Fix)
# PURPOSE: To design a flood resilience system and export a correct 3D model.
# ==============================================================================

import matplotlib.cm as cm
import matplotlib.colors as colors
import math
import time
import os
from dataclasses import dataclass, field
from typing import List, Dict
import warnings
import numpy as np
from skopt import gp_minimize
from skopt.space import Real
from skopt.utils import use_named_args
import sys
import json
import rasterio
from scipy.ndimage import zoom
import trimesh

from datetime import datetime

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

# --- Backend Setup ---
_xp = np; _device = "cpu"
try:
    import torch
    if torch.cuda.is_available(): _device = "cuda"; _xp = torch; print("✅ [Setup] Using PyTorch with CUDA backend.")
    elif torch.backends.mps.is_available(): _device = "mps"; _xp = torch; print("✅ [Setup] Using PyTorch with MPS backend.")
    else: print("⚠️ [Setup] PyTorch found but no GPU backend available, using NumPy.")
except ImportError: print("⚠️ [Setup] PyTorch not found, using NumPy backend.")
warnings.filterwarnings('ignore', category=UserWarning)

# --- Plotting Setup ---
try:
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d import Axes3D
    plt.style.use('seaborn-v0_8-whitegrid')
except ImportError: print("⚠️ [Setup] Matplotlib or 3D toolkit not found. Plotting will be disabled."); plt = None

# --- Helper Function ---
def to_numpy(arr):
    if hasattr(arr, 'cpu') and hasattr(arr, 'numpy'): return arr.cpu().numpy()
    return np.asarray(arr)

# ==============================================================================
# Part 2: HRF-SWE Flood Solver (Unchanged)
# ==============================================================================
print("Defining Part 2: HRF-SWE Flood Solver...")
@dataclass
class Grid:
    nx: int; ny: int; Lx: float; Ly: float; xp: ... = _xp; device: str = _device
    def __post_init__(self):
        self.dx = self.Lx / self.nx; self.dy = self.Ly / max(1, self.ny); x = self.xp.arange(self.nx, device=self.device, dtype=self.xp.float32) * self.dx + (0.5 * self.dx); y = self.xp.arange(self.ny, device=self.device, dtype=self.xp.float32) * self.dy + (0.5 * self.dy) if self.ny > 1 else self.xp.array([0.5 * self.dy], device=self.device, dtype=self.xp.float32); self.X, self.Y = self.xp.meshgrid(x, y, indexing="ij"); kx = 2 * np.pi * self.xp.fft.fftfreq(self.nx, d=self.dx); kx = kx.to(self.device) if hasattr(kx, 'to') else kx; ky = 2 * np.pi * self.xp.fft.fftfreq(self.ny, d=self.dy) if self.ny > 1 else self.xp.array([0.0], device=self.device); ky = ky.to(self.device) if hasattr(ky, 'to') else ky; self.KX, self.KY = self.xp.meshgrid(kx, ky, indexing="ij")
    def ddx(self, f): return self.xp.fft.ifft2(1j * self.KX * self.xp.fft.fft2(f)).real
    def ddy(self, f): return self.xp.fft.ifft2(1j * self.KY * self.xp.fft.fft2(f)).real if self.ny > 1 else self.xp.zeros_like(f)
@dataclass
class ExponentialFilter:
    alpha: float = 36.0; p: int = 8
    def apply(self, grid: Grid, f):
        xp = grid.xp; kx_max = xp.max(xp.abs(grid.KX)); ky_max = xp.max(xp.abs(grid.KY)); eta = xp.sqrt((grid.KX / (kx_max + 1e-14))**2 + (grid.KY / (ky_max + 1e-14))**2); sigma = xp.exp(-self.alpha * (eta ** self.p)); return xp.fft.ifft2(xp.fft.fft2(f) * sigma).real
@dataclass
class SWEParams:
    g: float = 9.81; manning_n: ... = 0.03; h_min: float = 1e-4; cfl: float = 0.30
@dataclass
class HRFSolver:
    grid: Grid; prm: SWEParams; filt: ExponentialFilter = field(default_factory=ExponentialFilter)
    def __post_init__(self): self.xp = self.grid.xp; self.device = self.grid.device; self.h = self.u = self.v = self.bed = self.rain_rate = None; self.time = 0.0
    def initialize(self, h0, u0, v0): self.h = self.xp.asarray(h0, device=self.device, dtype=self.xp.float32); self.u = self.xp.asarray(u0, device=self.device, dtype=self.xp.float32); self.v = self.xp.asarray(v0, device=self.device, dtype=self.xp.float32)
    def set_forcing(self, bed=None, rain_rate=None):
        if bed is not None: self.bed = self.xp.asarray(bed, device=self.device, dtype=self.xp.float32)
        if rain_rate is not None: self.rain_rate = self.xp.full_like(self.h, float(rain_rate), device=self.device, dtype=self.xp.float32)
        if not hasattr(self.prm.manning_n, 'shape'): self.prm.manning_n = self.xp.full_like(self.h, float(self.prm.manning_n), device=self.device, dtype=self.xp.float32)
        elif isinstance(self.prm.manning_n, np.ndarray): self.prm.manning_n = self.xp.asarray(self.prm.manning_n, device=self.device, dtype=self.xp.float32)
    def rhs(self, h, u, v):
        g = self.prm.g; grid = self.grid; xp = self.xp; h_min_tensor = xp.asarray(self.prm.h_min, device=self.device, dtype=h.dtype); h_eff = xp.maximum(h, h_min_tensor); hu = h_eff * u; hv = h_eff * v; dhdt = -(grid.ddx(hu) + grid.ddy(hv))
        if self.rain_rate is not None: dhdt += self.rain_rate
        dudt_adv = -(u * grid.ddx(u) + v * grid.ddy(u)); dvdt_adv = -(u * grid.ddx(v) + v * grid.ddy(v)); eta = h + (self.bed if self.bed is not None else 0.0); forcing_x = -g * grid.ddx(eta); forcing_y = -g * grid.ddy(eta); friction_x = xp.zeros_like(u); friction_y = xp.zeros_like(v)
        if xp.max(self.prm.manning_n) > 0.0: spd = xp.sqrt(u**2 + v**2); friction_term = (g * self.prm.manning_n**2 * spd) / (h_eff**(4./3.) + 1e-6); friction_x = -friction_term * u; friction_y = -friction_term * v
        dudt = dudt_adv + forcing_x + friction_x; dvdt = dvdt_adv + forcing_y + friction_y; return dhdt, dudt, dvdt
    def rk3_step(self, dt: float):
        dh1, du1, dv1 = self.rhs(self.h, self.u, self.v); h1 = self.h + dt * dh1; u1 = self.u + dt * du1; v1 = self.v + dt * dv1; h1=self.filt.apply(self.grid,h1); u1=self.filt.apply(self.grid,u1); v1=self.filt.apply(self.grid,v1); dh2, du2, dv2 = self.rhs(h1, u1, v1); h2 = 0.75*self.h + 0.25*(h1 + dt*dh2); u2 = 0.75*self.u + 0.25*(u1 + dt*du2); v2 = 0.75*self.v + 0.25*(v1 + dt*dv2); h2=self.filt.apply(self.grid,h2); u2=self.filt.apply(self.grid,u2); v2=self.filt.apply(self.grid,v2); dh3, du3, dv3 = self.rhs(h2, u2, v2); self.h = (1/3)*self.h + (2/3)*(h2 + dt*dh3); self.u = (1/3)*self.u + (2/3)*(u2 + dt*du3); self.v = (1/3)*self.v + (2/3)*(v2 + dt*dv3); self.h=self.filt.apply(self.grid,self.h); self.u=self.filt.apply(self.grid,self.u); self.v=self.filt.apply(self.grid,self.v); h_min_tensor = self.xp.asarray(self.prm.h_min, device=self.device, dtype=self.h.dtype); self.h = self.xp.maximum(self.h, h_min_tensor)
    def run(self, t_end):
        while self.time < t_end:
            h_min_tensor = self.xp.asarray(self.prm.h_min, device=self.device, dtype=self.h.dtype); vmax = self.xp.max(self.xp.sqrt(self.u**2 + self.v**2) + self.xp.sqrt(self.prm.g * self.xp.maximum(self.h, h_min_tensor))); dt = min(self.prm.cfl * self.grid.dx / max(1e-6, float(to_numpy(vmax))), t_end - self.time);
            if dt < 1e-6: break
            self.rk3_step(dt); self.time += dt

# ==============================================================================
# Part 3: Design, Evaluation & Export Functions
# ==============================================================================
print("Defining Part 3: The Drafter and Wrapper...")

def generate_terrain_and_friction_map(grid, params: Dict, initial_bed):
    X_np, Y_np = to_numpy(grid.X), to_numpy(grid.Y); manning_map = np.full_like(X_np, params['manning_n_base'], dtype=np.float32); p1_swale = np.array([params['bioswale_x_start'], params['bioswale_y_start']]); p2_swale = np.array([params['bioswale_x_end'], params['bioswale_y_end']]); l2_swale = np.sum((p1_swale - p2_swale)**2)
    if l2_swale == 0: dist_sq_swale = (X_np - p1_swale[0])**2 + (Y_np - p1_swale[1])**2
    else: t = np.maximum(0, np.minimum(1, ((X_np-p1_swale[0])*(p2_swale[0]-p1_swale[0]) + (Y_np-p1_swale[1])*(p2_swale[1]-p1_swale[1]))/l2_swale)); proj_x=p1_swale[0]+t*(p2_swale[0]-p1_swale[0]); proj_y=p1_swale[1]+t*(p2_swale[1]-p1_swale[1]); dist_sq_swale = (X_np-proj_x)**2+(Y_np-proj_y)**2
    swale_mask = np.exp(-dist_sq_swale / params['bioswale_width']**2) > 0.1; manning_map[swale_mask] = params['bioswale_friction']; bioswale_bed = -params['bioswale_depth'] * np.exp(-dist_sq_swale / params['bioswale_width']**2); dist_sq_pond1=(X_np-params['pond1_x'])**2+(Y_np-params['pond1_y'])**2; pond1_bed=-params['pond1_depth']*np.exp(-dist_sq_pond1/params['pond1_radius']**2); dist_sq_pond2=(X_np-params['pond2_x'])**2+(Y_np-params['pond2_y'])**2; pond2_bed=-params['pond2_depth']*np.exp(-dist_sq_pond2/params['pond2_radius']**2); subtractive_features = np.minimum(np.minimum(pond1_bed, pond2_bed), bioswale_bed); p1_levee=np.array([params['levee_x_start'],params['levee_y_start']]); p2_levee=np.array([params['levee_x_end'],params['levee_y_end']]); l2_levee = np.sum((p1_levee - p2_levee)**2)
    if l2_levee == 0: dist_sq_levee = (X_np - p1_levee[0])**2 + (Y_np - p1_levee[1])**2
    else: t = np.maximum(0, np.minimum(1, ((X_np-p1_levee[0])*(p2_levee[0]-p1_levee[0]) + (Y_np-p1_levee[1])*(p2_levee[1]-p1_levee[1]))/l2_levee)); proj_x=p1_levee[0]+t*(p2_levee[0]-p1_levee[0]); proj_y=p1_levee[1]+t*(p2_levee[1]-p1_levee[1]); dist_sq_levee = (X_np-proj_x)**2+(Y_np-proj_y)**2
    levee_bed = params['levee_height'] * np.exp(-dist_sq_levee / params['levee_width']**2); bed = initial_bed.astype(np.float32) + subtractive_features + levee_bed; return bed, manning_map

memoization_cache = {}
def evaluate_design(params: Dict, initial_bed, runway_specs, terminal_specs) -> Dict:
    param_tuple = tuple(sorted(params.items()));
    if param_tuple in memoization_cache: return memoization_cache[param_tuple]
    grid = Grid(nx=128, ny=128, Lx=3000.0, Ly=800.0); prm = SWEParams(manning_n=None, cfl=0.1); solver = HRFSolver(grid, prm); h0 = _xp.full((grid.nx, grid.ny), 0.01, device=_device, dtype=_xp.float32); u0 = _xp.zeros_like(h0); v0 = _xp.zeros_like(h0); solver.initialize(h0, u0, v0); bed, manning_map = generate_terrain_and_friction_map(grid, params, initial_bed); solver.prm.manning_n = manning_map; rain_intensity = 50 / (3600 * 1000); solver.set_forcing(bed=bed, rain_rate=rain_intensity); solver.run(t_end=900.0); X_m, Y_m = to_numpy(grid.X), to_numpy(grid.Y)
    runway_mask = (X_m >= runway_specs['x_start']) & (X_m <= runway_specs['x_start'] + runway_specs['width']) & (Y_m >= runway_specs['y_start']) & (Y_m <= runway_specs['y_start'] + runway_specs['height'])
    terminal_mask = (X_m >= terminal_specs['x_start']) & (X_m <= terminal_specs['x_start'] + terminal_specs['width']) & (Y_m >= terminal_specs['y_start']) & (Y_m <= terminal_specs['y_start'] + terminal_specs['height'])
    critical_zone_mask = np.logical_or(runway_mask, terminal_mask); critical_zone_mask_xp = _xp.asarray(critical_zone_mask, device=_device); flood_in_critical_zones = solver.h[critical_zone_mask_xp]
    if flood_in_critical_zones.shape[0] > 0: max_flood_depth = float(to_numpy(_xp.max(flood_in_critical_zones)))
    else: max_flood_depth = 999.0
    final_bed_np = to_numpy(bed); initial_bed_np = to_numpy(initial_bed); diff = final_bed_np - initial_bed_np; excavation_volume = -np.sum(diff[diff < 0]) * grid.dx * grid.dy; levee_fill_volume = np.sum(diff[diff > 0]) * grid.dx * grid.dy; total_construction_cost = excavation_volume + levee_fill_volume; grad_y, grad_x = np.gradient(final_bed_np, grid.dy, grid.dx); max_slope_deg = np.rad2deg(np.arctan(np.max(np.sqrt(grad_x**2 + grad_y**2)))); costs = {'flood_depth': max_flood_depth, 'construction_cost': total_construction_cost, 'max_slope': max_slope_deg}; memoization_cache[param_tuple] = costs; return costs

# --- FINAL, CORRECTED CAD EXPORT FUNCTION ---
# --- FINAL, CORRECTED CAD EXPORT FUNCTION ---
# --- FINAL, CORRECTED CAD EXPORT FUNCTION ---
def export_to_3d_cad_format(filename, grid, bed, initial_bed, runway_specs, terminal_specs):
    print(f"📦 Exporting detailed 3D model with elevation colormap to '{filename}'...")
    try:
        # --- Normalize all coordinates to Y-up system for GLB compatibility ---
        base_elevation = initial_bed[0,0]
        relative_bed = bed - base_elevation

        # 1. Create the main terrain mesh using relative elevation
        vertices = np.stack([to_numpy(grid.X).flatten(), relative_bed.flatten(), to_numpy(grid.Y).flatten()], axis=1)
        faces = []
        for y in range(grid.ny - 1):
            for x in range(grid.nx - 1):
                v1 = y * grid.nx + x; v2 = y * grid.nx + (x + 1); v3 = (y + 1) * grid.nx + x; v4 = (y + 1) * grid.nx + (x + 1)
                # Correct counter-clockwise winding order
                faces.append([v1, v2, v3]); faces.append([v2, v4, v3])
        
        terrain_mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)

        # --- NEW: Generate vertex colors based on elevation ---
        # Get the elevation value (the Y coordinate) for each vertex
        elevations = vertices[:, 1]
        
        # Normalize the elevation values to the range [0, 1]
        norm = colors.Normalize(vmin=np.min(elevations), vmax=np.max(elevations))
        
        # Choose a colormap (e.g., 'terrain', 'viridis', 'gist_earth')
        cmap = cm.get_cmap('terrain')
        
        # Apply the colormap to the normalized elevations to get RGBA colors
        # and convert from [0,1] float to [0,255] uint8
        vertex_colors_rgba = (cmap(norm(elevations)) * 255).astype(np.uint8)

        # Apply the calculated colors to the mesh's visual properties
        terrain_mesh.visual.vertex_colors = vertex_colors_rgba


        # 2. Create the runway mesh (using PBR material for a distinct look)
        runway_center_x = runway_specs['x_start'] + runway_specs['width'] / 2
        runway_center_y = runway_specs['y_start'] + runway_specs['height'] / 2
        runway_mesh = trimesh.creation.box(
            extents=[runway_specs['width'], 0.20, runway_specs['height']],
            transform=trimesh.transformations.translation_matrix([runway_center_x, 0.1, runway_center_y])
        )
        runway_material = trimesh.visual.material.PBRMaterial(baseColorFactor=[0.2, 0.2, 0.2, 1.0]) # Dark grey
        runway_mesh.visual = trimesh.visual.texture.TextureVisuals(material=runway_material)


        # 3. Create the terminal mesh (using PBR material)
        terminal_center_x = terminal_specs['x_start'] + terminal_specs['width'] / 2
        terminal_center_y = terminal_specs['y_start'] + terminal_specs['height'] / 2
        terminal_mesh = trimesh.creation.box(
            extents=[terminal_specs['width'], 15.0, terminal_specs['height']],
            transform=trimesh.transformations.translation_matrix([terminal_center_x, 7.5, terminal_center_y])
        )
        terminal_material = trimesh.visual.material.PBRMaterial(baseColorFactor=[1.0, 0.55, 0.0, 1.0]) # Orange
        terminal_mesh.visual = trimesh.visual.texture.TextureVisuals(material=terminal_material)


        # 4. Combine all meshes into a single scene and export
        scene = trimesh.Scene([terrain_mesh, runway_mesh, terminal_mesh])
        scene.export(filename)
        print(f"✅ 3D model with colormap saved successfully.")

    except Exception as e:
        print(f"❌ ERROR: Failed to export 3D model. Is 'trimesh' or 'matplotlib' installed? Error: {e}")


# ==============================================================================
# Part 4: Main Optimization Loop (Unchanged)
# ==============================================================================
print("Defining Part 4: Bayesian Optimization Loop...")
param_space = [Real(0.02, 0.04, name='manning_n_base'), Real(100, 2900, name='pond1_x'), Real(50, 750, name='pond1_y'), Real(50, 200, name='pond1_radius'), Real(2, 8, name='pond1_depth'), Real(100, 2900, name='pond2_x'), Real(50, 750, name='pond2_y'), Real(50, 200, name='pond2_radius'), Real(2, 8, name='pond2_depth'), Real(0, 3000, name='levee_x_start'), Real(0, 800, name='levee_y_start'), Real(0, 3000, name='levee_x_end'), Real(0, 800, name='levee_y_end'), Real(0.5, 2.0, name='levee_height'), Real(10.0, 30.0, name='levee_width'), Real(0, 3000, name='bioswale_x_start'), Real(0, 800, name='bioswale_y_start'), Real(0, 3000, name='bioswale_x_end'), Real(0, 800, name='bioswale_y_end'), Real(0.5, 2.5, name='bioswale_depth'), Real(20.0, 60.0, name='bioswale_width'), Real(0.05, 0.15, name='bioswale_friction'),]

def objective_function(params, initial_bed, runway_specs, terminal_specs):
    params_dict = {param.name: value for param, value in zip(param_space, params)}; raw_costs = evaluate_design(params_dict, initial_bed, runway_specs, terminal_specs); flood_depth = raw_costs['flood_depth']; construction_cost = raw_costs['construction_cost']; max_slope = raw_costs['max_slope']; TARGET_MAX_FLOOD = 0.5; TARGET_MAX_COST = 500000.0; SLOPE_LIMIT_DEG = 15.0
    if np.isnan(flood_depth) or np.isinf(flood_depth) or flood_depth > 100: total_cost = 10.0
    else: norm_flood = flood_depth / TARGET_MAX_FLOOD; norm_cost = min(construction_cost / TARGET_MAX_COST, 1.0); slope_penalty = max(0, (max_slope - SLOPE_LIMIT_DEG) / SLOPE_LIMIT_DEG)**2; w_flood = 0.7; w_cost = 0.2; w_slope = 0.1; total_cost = w_flood * norm_flood + w_cost * norm_cost + w_slope * slope_penalty
    print(f"Testing... Flood: {flood_depth:.4f}m | Cost: {construction_cost/1e3:.1f}k m³ | Slope: {max_slope:.1f}° | Score: {total_cost:.4f}"); return total_cost

def run_bayesian_optimization(num_episodes=75, initial_bed=None, runway_specs=None, terminal_specs=None, output_dir=None):
    print("\n" + "="*80 + f"\n🔬 STARTING BIOSWALE DESIGN AI - ({num_episodes} DESIGN ITERATIONS)\n" + "="*80); print("Goal: Design flood defenses for the selected airport site."); optimization_start_time = time.time()
    obj_func_with_bed = lambda params: objective_function(params, initial_bed=initial_bed, runway_specs=runway_specs, terminal_specs=terminal_specs)
    result = gp_minimize(func=obj_func_with_bed, dimensions=param_space, n_calls=num_episodes, random_state=123, n_initial_points=20)
    print(f"\n✅ Optimization complete. Search took {time.time() - optimization_start_time:.2f}s"); print(f"Best score found: {result.fun:.4f}")
    best_params = {param.name: value for param, value in zip(param_space, result.x)}
    print("\n" + "="*60 + "\n--- FINAL PERFORMANCE REPORT (FLOOD RESILIENCE) ---\n" + "="*60); print("\n🏆 Best Flood Defense Design Found:"); [print(f"- {key}: {val:.2f}") for key, val in best_params.items()]
    final_costs = evaluate_design(best_params, initial_bed=initial_bed, runway_specs=runway_specs, terminal_specs=terminal_specs)
    print(f"  - Performance: {final_costs['flood_depth']:.4f} m flood | {final_costs['construction_cost']:.0f} m³ cost | {final_costs['max_slope']:.1f}° slope")
    grid = Grid(nx=128, ny=128, Lx=3000.0, Ly=800.0); bed, _ = generate_terrain_and_friction_map(grid, best_params, initial_bed=initial_bed)
    if plt and bed is not None:
        fig = plt.figure(figsize=(16, 10)); ax = fig.add_subplot(111, projection='3d'); X_np, Y_np = to_numpy(grid.X), to_numpy(grid.Y); ax.plot_surface(X_np, Y_np, bed, cmap='terrain', rstride=2, cstride=2, alpha=0.8, linewidth=0, antialiased=True); ax.set_title('🏆 Optimal Flood Defense System by Bayesian AI (with Final Layout)', fontsize=18); ax.set_xlabel('Position x (m)'); ax.set_ylabel('Position y (m)'); ax.set_zlabel('Bed Elevation (m)'); ax.view_init(elev=30., azim=-45)
        z_range = bed.max() - bed.min()
        if z_range > 0: ax.set_box_aspect((grid.Lx, grid.Ly, z_range * 2))
        import matplotlib.patches as patches; import mpl_toolkits.mplot3d.art3d as art3d
        runway_rect = patches.Rectangle((runway_specs['x_start'], runway_specs['y_start']), runway_specs['width'], runway_specs['height'], linewidth=1, edgecolor='k', facecolor='black', alpha=0.6); ax.add_patch(runway_rect); art3d.pathpatch_2d_to_3d(runway_rect, z=initial_bed[0,0], zdir="z")
        terminal_rect = patches.Rectangle((terminal_specs['x_start'], terminal_specs['y_start']), terminal_specs['width'], terminal_specs['height'], linewidth=1, edgecolor='#444444', facecolor='darkorange', alpha=0.7); ax.add_patch(terminal_rect); art3d.pathpatch_2d_to_3d(terminal_rect, z=initial_bed[0,0], zdir="z")
        legend_patches = [patches.Patch(facecolor='black', edgecolor='k', alpha=0.6, label='Runway'), patches.Patch(facecolor='darkorange', edgecolor='#444444', alpha=0.7, label='Terminal/Apron')]; ax.legend(handles=legend_patches, loc='upper left', frameon=True, facecolor='white', framealpha=0.8)
        plt.savefig(f"{output_dir}/flood_defense_3d_report_with_layout.png", dpi=200); print(f"✅ Report saved to '{output_dir}/flood_defense_3d_report_with_layout.png'")
        export_to_3d_cad_format(f"{output_dir}/final_airport_design.glb", grid, bed, initial_bed, runway_specs, terminal_specs)

# ==============================================================================
# Part 5: Main Execution Block (Unchanged)
# ==============================================================================
if __name__ == "__main__":
    print("="*80); print("🌊 LAUNCHING STAGE 3: FLOOD DEFENSE ENGINEER"); print("="*80)

    # Get output directory from environment variable or create with timestamp
    output_dir = os.environ.get('AEROGIS_OUTPUT_DIR')
    if not output_dir:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = f"Outputs/Run_{timestamp}"
    os.makedirs(output_dir, exist_ok=True)
    print(f"📁 Using output directory: {output_dir}")

    # Redirect stdout and stderr to log files
    log_file = open(f"{output_dir}/stage3_engineer.log", 'w')
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    sys.stdout = Tee(original_stdout, log_file)
    sys.stderr = Tee(original_stderr, log_file)

    try:
        initial_bed = None; runway_specs = None; terminal_specs = None
        if len(sys.argv) > 2:
            site_details_file = sys.argv[1]; layout_file = sys.argv[2]
            print(f"🌉 Received site details from: '{site_details_file}'"); print(f"🌉 Received optimal layout from: '{layout_file}'")
            try:
                with open(site_details_file, 'r') as f: site_details = json.load(f)
                target_elevation = site_details['target_elevation_m']; grid_nx, grid_ny = 128, 128; initial_bed = np.full((grid_nx, grid_ny), target_elevation, dtype=np.float32); print(f"  - ✅ Created flat initial terrain at {target_elevation:.2f} m.")
                with open(layout_file, 'r') as f: layout = json.load(f)
                runway_data = layout['runways'][0]; terminal_data = layout['terminals'][0]
                runway_specs = {'x_start': runway_data['center_x'] - runway_data['length'] / 2, 'y_start': runway_data['center_y'] - runway_data['width'] / 2, 'width': runway_data['length'], 'height': runway_data['width']}
                terminal_specs = {'x_start': terminal_data['footprint_x'], 'y_start': terminal_data['footprint_y'], 'width': terminal_data['width'], 'height': terminal_data['height']}
                print(f"  - ✅ Loaded critical zone definitions from optimal layout.")
            except Exception as e: print(f"❌ ERROR: Could not process input files. Error: {e}"); sys.exit(1)
        else: print("❌ ERROR: This script requires two input files: site_details.json and optimal_layout.json"); sys.exit(1)
        if initial_bed is not None and runway_specs and terminal_specs:
            run_bayesian_optimization(initial_bed=initial_bed, runway_specs=runway_specs, terminal_specs=terminal_specs, output_dir=output_dir)
    finally:
        # Restore original stdout/stderr and close log file
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        log_file.close()