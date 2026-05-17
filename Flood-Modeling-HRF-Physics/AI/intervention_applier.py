#!/usr/bin/env python3
"""
Dynamic Intervention Application for HRF Solver
================================================
Reads QCIA design JSON and applies interventions to physics simulation.

This is the bridge between AI decisions and physics implementation.
"""

import json
import numpy as np
from pathlib import Path
from typing import Dict, List, Any

from AI.intervention_library import INTERVENTION_CATALOG
from Physics.hrf import FaceIndex, Culvert


class InterventionApplier:
    """
    Applies interventions from QCIA design to HRF solver.
    Maps civil engineering interventions to physics parameters.
    """
    
    def __init__(self, solver, grid, verbose=True):
        """
        Args:
            solver: HRFSolver instance
            grid: Grid instance
            verbose: Print application details
        """
        self.solver = solver
        self.grid = grid
        self.verbose = verbose
        self.applied_interventions = []
        
        # CRITICAL: Ensure structures dict exists on solver
        if not hasattr(self.solver, 'structures') or self.solver.structures is None:
            self.solver.structures = {"weirs": [], "culverts": [], "bridges": []}
        
        # Cache some handy values
        self.cell_area = float(self.grid.dx * self.grid.dy)
        self.nx = int(self.grid.nx)
        self.ny = int(self.grid.ny)
        self._routing_built = False
        self._d8_next = None  # shape (nx, ny, 2) of downstream neighbor indices
        self._outfall = None  # shape (nx, ny, 2) of outfall cell indices
        self._flow_accum = None  # contributing cells count
        # Optional rainfall depth over design storm (provided by runner)
        self._rain_depth_m = float(getattr(self.solver, 'rain_depth_m', 0.0))
        self._design_storm_s = float(getattr(self.solver, 'design_storm_seconds', 0.0))
        
        # ADAPTIVE PHYSICS BOOSTING: Compensate for sub-grid scale effects
        self.dx = float(self.grid.dx)
        self.physics_boost = self._compute_adaptive_boost(self.dx)
        if self.verbose and self.physics_boost > 1.01:
            print(f"   🔧 Adaptive physics boost: {self.physics_boost:.2f}x (dx={self.dx:.0f}m)")
        
        # Ensure a source_rate field exists on solver for conservative routing (pump outfalls)
        if not hasattr(self.solver, 'source_rate') or self.solver.source_rate is None:
            try:
                import numpy as _np
                self.solver.source_rate = _np.zeros_like(self.solver.h, dtype=_np.float32)
            except Exception:
                self.solver.source_rate = np.zeros_like(self.solver.h, dtype=np.float32)
    
    def _compute_adaptive_boost(self, dx: float) -> float:
        """
        Compute physics boost factor based on grid resolution.
        
        Rationale:
        - At 10m resolution: interventions are properly resolved → no boost (1.0x)
        - At 50m resolution: sub-grid effects begin → modest boost (1.5x)
        - At 100m resolution: significant homogenization → strong boost (3.0x)
        - At 500m resolution: severe averaging → maximum boost (10x cap)
        
        Formula: boost = (dx / dx_ref)^1.0, capped at [1.0, 10.0]
        Exponent 1.0 gives linear scaling (stronger, needed for coarse grids).
        
        Examples:
        - dx=10m  → boost=1.00x (no adjustment)
        - dx=25m  → boost=2.50x
        - dx=50m  → boost=5.00x
        - dx=100m → boost=10.0x (capped)
        - dx=200m → boost=10.0x (capped)
        - dx=500m → boost=10.0x (capped)
        """
        dx_ref = 10.0  # Reference resolution for urban drainage (culverts, roads well-resolved)
        boost = (dx / dx_ref) ** 1.0  # Linear scaling
        return min(10.0, max(1.0, boost))

    # ------------------------------
    # Internal helpers
    # ------------------------------
    def _ensure_infil_array(self):
        """Ensure solver.infil_rate exists as a writable numpy array."""
        if getattr(self.solver, 'infil_rate', None) is None:
            # Create zero infiltration (will behave as no sink by default)
            self.solver.infil_rate = np.zeros_like(self.solver.h, dtype=np.float32)
        else:
            # Make sure it is a numpy array (HRF uses numpy by default on CPU)
            try:
                # If it's a cupy/torch array, bring to host numpy for safe in-place edits
                self.solver.infil_rate = np.asarray(self.solver.infil_rate)
            except Exception:
                pass

    def _apply_sink_patch(self, i: int, j: int, rate_mps: float, radius_cells: int) -> float:
        """
        Add a uniform sink patch centered at (i,j).
        Returns the total m³/s removal represented by this patch.
        """
        self._ensure_infil_array()
        nx, ny = self.solver.infil_rate.shape
        ii0 = max(0, i - radius_cells)
        ii1 = min(nx, i + radius_cells + 1)
        jj0 = max(0, j - radius_cells)
        jj1 = min(ny, j + radius_cells + 1)
        # Apply
        self.solver.infil_rate[ii0:ii1, jj0:jj1] = (
            self.solver.infil_rate[ii0:ii1, jj0:jj1] + float(rate_mps)
        )
        patch_cells = (ii1 - ii0) * (jj1 - jj0)
        total_m3s = float(rate_mps) * self.cell_area * patch_cells
        return total_m3s

    def _apply_source_patch(self, i: int, j: int, rate_mps: float, radius_cells: int) -> float:
        """
        Add a uniform source patch centered at (i,j) into solver.source_rate (m/s).
        Returns total m³/s injected.
        """
        # Ensure array exists and is NumPy for safe in-place
        try:
            self.solver.source_rate = np.asarray(self.solver.source_rate)
        except Exception:
            pass
        nx, ny = self.solver.source_rate.shape
        ii0 = max(0, i - radius_cells)
        ii1 = min(nx, i + radius_cells + 1)
        jj0 = max(0, j - radius_cells)
        jj1 = min(ny, j + radius_cells + 1)
        self.solver.source_rate[ii0:ii1, jj0:jj1] = (
            self.solver.source_rate[ii0:ii1, jj0:jj1] + float(rate_mps)
        )
        patch_cells = (ii1 - ii0) * (jj1 - jj0)
        total_m3s = float(rate_mps) * self.cell_area * patch_cells
        return total_m3s
    
    def apply_design(self, design_path: Path):
        """
        Read QCIA design JSON and apply all interventions.
        
        Args:
            design_path: Path to qcia_design.json
        
        Returns:
            List of applied interventions with details
        """
        with open(design_path) as f:
            design = json.load(f)
        
        if self.verbose:
            print(f"\n🏗️  Applying QCIA Design:")
            print(f"   Budget: ₹{design['total_cost_cr']:.2f} Crores")
            print(f"   Interventions: {design['num_interventions']}")
            print()
        
        for intervention in design['interventions']:
            # Build routing on first use
            if not self._routing_built:
                self._build_flow_routing()
            self._apply_single(intervention)
        
        return self.applied_interventions
    
    def _apply_single(self, intervention: Dict[str, Any]):
        """Apply a single intervention to the solver."""
        itype = intervention['type']
        location = tuple(intervention['location'])
        i, j = location
        
        # Get specification from catalog
        if itype not in INTERVENTION_CATALOG:
            if self.verbose:
                print(f"   ⚠️  Unknown intervention type: {itype}, skipping")
            return
        
        spec = INTERVENTION_CATALOG[itype]
        
        # Dispatch to appropriate handler based on intervention name/type
        if 'pond' in itype.lower() or 'basin' in itype.lower() or 'retention' in itype.lower() or 'detention' in itype.lower():
            # Use physics-based Gaussian-smoothed detention basin
            result = self._apply_detention_basin_physics(i, j, spec, intervention)
        elif 'pump' in itype.lower():
            result = self._apply_pump(i, j, spec, intervention)
        elif 'culvert' in itype.lower():
            result = self._apply_culvert(i, j, spec, intervention)
        elif 'drain' in itype.lower() or 'channel' in itype.lower():
            result = self._apply_drain(i, j, spec, intervention)
        elif 'permeable' in itype.lower() or 'paver' in itype.lower():
            result = self._apply_permeable(i, j, spec, intervention)
        elif 'wall' in itype.lower() or 'levee' in itype.lower() or 'floodgate' in itype.lower():
            result = self._apply_barrier(i, j, spec, intervention)
        elif 'bioswale' in itype.lower() or 'rain_garden' in itype.lower() or 'green_roof' in itype.lower():
            result = self._apply_green(i, j, spec, intervention)
        elif 'infiltration_trench' in itype.lower():
            result = self._apply_infiltration_trench(i, j, spec, intervention)
        elif 'smart_valve' in itype.lower():
            result = self._apply_smart_valve(i, j, spec, intervention)
        elif 'underground_tank' in itype.lower():
            result = self._apply_underground_tank(i, j, spec, intervention)
        else:
            if self.verbose:
                print(f"   ⚠️  Unimplemented intervention type: {itype}")
            return
        
        if result:
            self.applied_interventions.append(result)
            if self.verbose:
                print(f"   ✅ Applied {itype} at ({i}, {j})")
        else:
            if self.verbose:
                print(f"   ⚠️  Skipped {itype} at ({i}, {j}) (failed constraints)")

    # ------------------------------
    # Watershed-aware routing helpers
    # ------------------------------
    def _build_flow_routing(self):
        """Build simple D8 routing on bed elevation and compute per-cell outfalls and flow accumulation.
        - Downstream neighbor = steepest descent among 8 neighbors (tie-break by lowest bed).
        - Outfall = first river_mask cell along path; if none, first boundary cell reached.
        - Flow accumulation via bed-sorted propagation (upslope -> downslope).
        """
        bed = getattr(self.solver, 'bed', None)
        if bed is None:
            # Fallback: flat bed → route to nearest domain edge
            self._d8_next = np.zeros((self.nx, self.ny, 2), dtype=np.int32)
            self._outfall = np.zeros((self.nx, self.ny, 2), dtype=np.int32)
            self._flow_accum = np.ones((self.nx, self.ny), dtype=np.float32)
            for i in range(self.nx):
                for j in range(self.ny):
                    oi = 0 if i < (self.nx - 1 - i) else (self.nx - 1)
                    oj = j
                    self._outfall[i, j, 0] = oi
                    self._outfall[i, j, 1] = oj
            self._routing_built = True
            return
        bed = np.asarray(bed, dtype=np.float64)
        river_mask = np.asarray(getattr(self.solver, 'river_mask', np.zeros_like(bed)), dtype=np.uint8)
        # D8 neighbor offsets
        nbrs = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
        self._d8_next = np.zeros((self.nx, self.ny, 2), dtype=np.int32)
        for i in range(self.nx):
            for j in range(self.ny):
                best_di, best_dj = 0, 0
                best_drop = 0.0
                z0 = bed[i, j]
                for di, dj in nbrs:
                    ii = i + di
                    jj = j + dj
                    if 0 <= ii < self.nx and 0 <= jj < self.ny:
                        dz = z0 - bed[ii, jj]
                        if dz > best_drop + 1e-12 or (abs(dz - best_drop) <= 1e-12 and bed[ii, jj] < (z0 - best_drop)):
                            best_drop = dz
                            best_di, best_dj = di, dj
                self._d8_next[i, j, 0] = i + best_di
                self._d8_next[i, j, 1] = j + best_dj
        # Compute outfalls by walking paths
        self._outfall = np.zeros((self.nx, self.ny, 2), dtype=np.int32)
        for i in range(self.nx):
            for j in range(self.ny):
                vi, vj = i, j
                visited = 0
                while visited < (self.nx + self.ny):
                    if river_mask[vi, vj] > 0:
                        break
                    ni, nj = int(self._d8_next[vi, vj, 0]), int(self._d8_next[vi, vj, 1])
                    if ni == vi and nj == vj:
                        break
                    vi, vj = ni, nj
                    visited += 1
                    if vi == 0 or vj == 0 or vi == self.nx - 1 or vj == self.ny - 1:
                        break
                self._outfall[i, j, 0] = vi
                self._outfall[i, j, 1] = vj
        # Flow accumulation: sort cells by bed ascending and push counts to downstream neighbor
        self._flow_accum = np.ones((self.nx, self.ny), dtype=np.float64)
        order = np.argsort(bed, axis=None)
        for flat_idx in order:
            i = flat_idx // self.ny
            j = flat_idx % self.ny
            ni, nj = int(self._d8_next[i, j, 0]), int(self._d8_next[i, j, 1])
            if (ni != i or nj != j) and 0 <= ni < self.nx and 0 <= nj < self.ny:
                self._flow_accum[ni, nj] += self._flow_accum[i, j]
        self._routing_built = True

    def _find_outfall(self, i: int, j: int) -> tuple:
        if not self._routing_built:
            self._build_flow_routing()
        return int(self._outfall[i, j, 0]), int(self._outfall[i, j, 1])

    def _contributing_area_m2(self, i: int, j: int) -> float:
        if not self._routing_built:
            self._build_flow_routing()
        return float(self._flow_accum[i, j]) * self.cell_area

    # ------------------------------
    # Structural coupler helpers
    # ------------------------------
    def _orient_face_by_bed(self, i: int, j: int) -> str:
        """Choose face orientation ('x' or 'y') based on local bed gradient magnitude.
        If bed is missing, default to 'x'.
        """
        bed = getattr(self.solver, 'bed', None)
        if bed is None or not isinstance(bed, np.ndarray):
            return 'x'
        nx, ny = bed.shape
        sx = 0.0; sy = 0.0
        if 0 < i < nx - 1:
            sx = abs((float(bed[i+1, j]) - float(bed[i-1, j])) / max(1e-9, 2 * self.grid.dx))
        if 0 < j < ny - 1:
            sy = abs((float(bed[i, j+1]) - float(bed[i, j-1])) / max(1e-9, 2 * self.grid.dy))
        return 'x' if sx >= sy else 'y'

    def _add_local_culvert_structure(self, i: int, j: int, area_m2: float, invert_up: float = 0.0, invert_dn: float = 0.0) -> bool:
        """Create a one-face culvert at cell (i,j) aligned with local gradient.
        Returns True if appended.
        STRENGTHENED: More robust, always succeeds unless critical failure.
        """
        try:
            # Always try to add structural culvert, default to 'x' direction if gradient unclear
            dir_sel = self._orient_face_by_bed(i, j) if hasattr(self, '_orient_face_by_bed') else 'x'
            faces = [FaceIndex(i=int(i), j=int(j), dir=str(dir_sel))]
            # STRENGTHENED: Use higher discharge coefficients (0.8 instead of default 0.62)
            # to ensure culverts are effective at grid scale
            culv = Culvert(faces=faces, area=float(area_m2), C0=0.8, Cf=0.8)
            culv.invert_up = float(invert_up)
            culv.invert_dn = float(invert_dn)
            if 'culverts' not in self.solver.structures:
                self.solver.structures['culverts'] = []
            self.solver.structures['culverts'].append(culv)
            if self.verbose:
                print(f"      ✓ Added structural culvert at ({i},{j}), area={area_m2:.1f}m², Cd=0.8, dir={dir_sel}")
            return True
        except Exception as e:
            if self.verbose:
                print(f"      ⚠️  Structural culvert failed at ({i},{j}): {e}, using sink/source fallback")
            return False
    
    def _apply_detention_basin_physics(self, i: int, j: int, spec, intervention: Dict) -> Dict:
        """
        Apply detention basin with PROPER ENGINEERING HYDRAULICS and Gaussian smoothing.
        
        This implements the reference system's physics-based approach:
        1. Gentle bed depression with Gaussian smoothing (prevents numerical shocks)
        2. Enhanced infiltration modeling  
        3. Realistic storage volume calculation
        4. Conservative 1:4 side slopes (civil engineering standard)
        
        This creates REAL terrain modification that the physics can respond to correctly.
        """
        itype = intervention.get('type', '')
        
        # Determine pond size from type
        if 'xlarge' in itype.lower():
            capacity_base = 100000.0  # 100k m³
            radius_m = 80.0           # ~80m radius
            depth_m = 2.5             # 2.5m depth
        elif 'large' in itype.lower():
            capacity_base = 50000.0   # 50k m³
            radius_m = 60.0           # ~60m radius  
            depth_m = 2.0             # 2m depth
        elif 'medium' in itype.lower():
            capacity_base = 25000.0   # 25k m³
            radius_m = 45.0           # ~45m radius
            depth_m = 1.5             # 1.5m depth
        else:
            capacity_base = 10000.0   # Default 10k m³
            radius_m = 30.0           # ~30m radius
            depth_m = 1.0             # 1m depth
        
        # Convert radius to cells
        radius_cells = int(np.ceil(radius_m / self.dx))
        
        # Create arrays for modifications
        nx, ny = self.nx, self.ny
        bed_change = np.zeros((nx, ny), dtype=np.float32)
        infil_enhancement = np.zeros((nx, ny), dtype=np.float32)
        
        # Engineering parameters
        side_slope_ratio = 4.0  # 1:4 (H:V) - gentle slope for stability
        transition_factor = 1.5  # Extended transition zone
        
        effective_radius_cells = radius_cells + int(depth_m * side_slope_ratio / self.dx)
        
        modified_cells = 0
        
        # Build the basin profile
        for di in range(-effective_radius_cells - 3, effective_radius_cells + 4):
            for dj in range(-effective_radius_cells - 3, effective_radius_cells + 4):
                ii = i + di
                jj = j + dj
                
                if 0 <= ii < nx and 0 <= jj < ny:
                    # Distance from center
                    dist = np.sqrt((di * self.dx)**2 + (dj * self.dx)**2)
                    
                    # Build gentle depression profile
                    if dist <= radius_m:
                        # Inside basin: cubic profile for smooth bottom
                        depth_factor = 1.0 - (dist / radius_m)**3
                        depression = depth_m * depth_factor
                        infil_factor = 1.0 - (dist / radius_m)**2
                    elif dist <= radius_m + (depth_m * side_slope_ratio):
                        # Transition zone: gentle 1:4 slopes
                        slope_dist = dist - radius_m
                        slope_fraction = 1.0 - (slope_dist / (depth_m * side_slope_ratio))
                        depression = depth_m * slope_fraction
                        infil_factor = slope_fraction * 0.5
                    elif dist <= radius_m * transition_factor + (depth_m * side_slope_ratio):
                        # Extended transition: fade to zero
                        extra_dist = dist - (radius_m + depth_m * side_slope_ratio)
                        max_extra = radius_m * (transition_factor - 1.0)
                        fade = 1.0 - (extra_dist / max(1.0, max_extra))
                        depression = depth_m * 0.1 * fade
                        infil_factor = 0.1 * fade
                    else:
                        continue
                    
                    # Apply (negative = lower bed)
                    bed_change[ii, jj] = -depression
                    
                    # Enhanced infiltration (100 mm/hr design rate)
                    infiltration_rate_mps = 100.0 / (1000.0 * 3600.0) * infil_factor
                    infil_enhancement[ii, jj] = infiltration_rate_mps
                    
                    modified_cells += 1
        
        # CRITICAL: Apply Gaussian smoothing to prevent numerical shocks
        from scipy.ndimage import gaussian_filter
        bed_change_smooth = gaussian_filter(bed_change, sigma=3.0)
        infil_smooth = gaussian_filter(infil_enhancement, sigma=2.0)
        
        # Apply to solver
        if hasattr(self.solver, 'bed') and self.solver.bed is not None:
            self.solver.bed += bed_change_smooth
        
        # Apply infiltration enhancement
        self._ensure_infil_array()
        self.solver.infil_rate = np.maximum(self.solver.infil_rate, infil_smooth)
        
        # Calculate actual volume from bed modification
        volume_created = np.sum(np.abs(bed_change_smooth[bed_change_smooth < 0])) * self.cell_area
        
        if self.verbose:
            max_depression = np.min(bed_change_smooth)
            print(f"   ✅ Physics-based detention basin: {itype}")
            print(f"      Location: ({i}, {j})")
            print(f"      Design: radius={radius_m:.0f}m, depth={depth_m:.1f}m")
            print(f"      Volume: {volume_created:.0f} m³ (target: {capacity_base:.0f} m³)")
            print(f"      Modified: {modified_cells} cells, max depression={abs(max_depression):.2f}m")
            print(f"      Gaussian smoothing: sigma=3.0 (prevents numerical shocks)")
        
        return {
            'type': 'detention_basin_physics',
            'subtype': itype,
            'location': (i, j),
            'capacity_m3': volume_created,
            'radius_m': radius_m,
            'depth_m': depth_m,
            'modified_cells': modified_cells,
            'max_depression_m': abs(float(np.min(bed_change_smooth))),
            'implementation': 'gaussian_smoothed_physics_v1'
        }
    
    def _apply_storage(self, i: int, j: int, spec, intervention: Dict) -> Dict:
        """
        OLD METHOD: Apply storage as a sink (kept for non-pond interventions).
        STRENGTHENED: 3x larger capacities, faster drawdown (more aggressive removal).
        CONSERVATIVE ROUTING: Transfer withdrawn water to a river/edge outfall (source).
        """
        itype = intervention.get('type', '')
        
        # Base capacity (realistic dimensions) - will be boosted adaptively
        if 'large' in str(itype).lower():
            capacity_base = 10000.0    # pond_large: 10k m³ (realistic)
            radius_cells = 6           # 13×13 patch
            drawdown_hours = 4.0       # Faster drawdown
        elif 'basin_dry' in str(itype).lower() or 'detention' in str(itype).lower():
            capacity_base = 50000.0    # Large basin: 50k m³ (realistic)
            radius_cells = 7           # 15×15 patch
            drawdown_hours = 8.0       # Slow natural drainage
        elif 'underground_tank' in str(itype).lower():
            capacity_base = 5000.0     # Underground: 5k m³ (realistic)
            radius_cells = 4           # 9×9 patch (concentrated)
            drawdown_hours = 6.0       # Mechanical pumping
        elif 'medium' in str(itype).lower():
            capacity_base = 5000.0     # pond_medium: 5k m³ (realistic)
            radius_cells = 4           # 9×9 patch
            drawdown_hours = 3.0       # Moderate drawdown
        elif 'retention' in str(itype).lower():
            capacity_base = 10000.0    # Retention pond: 10k m³ (realistic)
            radius_cells = 5           # 11×11 patch
            drawdown_hours = 12.0      # Permanent water, slow drainage
        else:
            # Fallback for unrecognized types
            capacity_base = float(getattr(spec, 'capacity_m3', 10000.0)) if hasattr(spec, 'capacity_m3') else 10000.0
            radius_cells = int(intervention.get('radius_cells', 4))
            drawdown_hours = 4.0
        
        # Apply adaptive boost for coarse grids
        capacity = capacity_base * self.physics_boost
        
        # Demand-based sizing: scale capacity with contributing area and design storm depth
        try:
            A = self._contributing_area_m2(i, j)
            depth = self._rain_depth_m if self._rain_depth_m > 0.0 else 0.06 * 3600.0 * 1.5  # m; fallback ~1.5h at 60mm/h
            runoff_coeff = 0.6  # proxy; can be refined from LULC
            demand_vol = runoff_coeff * depth * A
            # Target to capture a significant fraction of local runoff
            target_frac = 0.25 if 'retention' in str(itype).lower() else 0.35
            capacity = max(capacity, target_frac * demand_vol)
        except Exception:
            pass
        # Allow override
        capacity = float(intervention.get('capacity_m3', capacity))
        radius_cells = int(intervention.get('radius_cells', radius_cells))
        drawdown_time_s = float(intervention.get('drawdown_hours', drawdown_hours)) * 3600.0
        
        # Calculate base sink rate (target drawdown)
        total_Q_m3s = capacity / max(1.0, drawdown_time_s)
        patch_cells = (2 * radius_cells + 1) ** 2
        sink_mps = total_Q_m3s / (self.cell_area * patch_cells)
        total_applied_m3s = self._apply_sink_patch(i, j, sink_mps, radius_cells)
        # Also record a per-cell storage uptake map on solver for mass ledger
        try:
            self.solver.pond_storage_rate = np.asarray(self.solver.pond_storage_rate)
        except Exception:
            pass
        nx, ny = self.solver.h.shape
        ii0 = max(0, i - radius_cells)
        ii1 = min(nx, i + radius_cells + 1)
        jj0 = max(0, j - radius_cells)
        jj1 = min(ny, j + radius_cells + 1)
        self.solver.pond_storage_rate[ii0:ii1, jj0:jj1] = (
            self.solver.pond_storage_rate[ii0:ii1, jj0:jj1] + float(sink_mps)
        )
        # Log pond storage ledger on solver
        try:
            self.solver.pond_storage_total += float(total_applied_m3s) * float(drawdown_time_s)
        except Exception:
            pass
        # Route to outfall (river preferred)
        oi, oj = self._find_outfall(i, j)
        out_radius = max(1, radius_cells - 1)
        # Rated outlet (orifice/weir proxy): Q_out = min(Q_sink, C*A*sqrt(2g*H)) using local head above a crest
        g = 9.81
        try:
            bed = float(self.solver.bed[i, j]) if getattr(self.solver, 'bed', None) is not None else 0.0
        except Exception:
            bed = 0.0
        crest = bed + 0.5  # m above bed
        eta = float(self.solver.h[i, j]) + bed
        H = max(0.0, eta - crest)
        CdA = 0.2  # m^2 equivalent
        rated_Q = CdA * (2.0 * g * H) ** 0.5
        release_Q = min(total_Q_m3s, rated_Q)
        release_frac = release_Q / max(1e-9, total_Q_m3s)
        source_mps = sink_mps * release_frac
        total_injected_m3s = self._apply_source_patch(oi, oj, source_mps, out_radius)
        
        return {
            'type': 'storage',
            'subtype': itype,
            'location': (i, j),
            'capacity_m3': capacity,
            'drawdown_hours': drawdown_time_s / 3600.0,
            'patch_radius_cells': radius_cells,
            'patch_size': f'{2*radius_cells+1}×{2*radius_cells+1}',
            'sink_per_cell_mps': float(sink_mps),
            'total_patch_Q_m3s': float(total_applied_m3s),
            'outfall': (oi, oj),
            'outfall_radius_cells': out_radius,
            'source_per_cell_mps': float(source_mps),
            'total_injected_Q_m3s': float(total_injected_m3s),
            'implementation': 'rated_storage_routing_v1',
            'rated_Q_m3s': float(rated_Q),
            'release_Q_m3s': float(release_Q)
        }
    
    def _apply_pump(self, i: int, j: int, spec, intervention: Dict) -> Dict:
        """
        Apply pump as active removal distributed over a larger patch.
        STRENGTHENED: 10x stronger - larger patches (5×5 → 9×9), higher effective flow rates.
        """
        # Get base capacity from spec (realistic dimensions)
        base_capacity_base = float(getattr(spec, 'capacity_m3_s', 1.5))
        
        # Determine pump sizing and patch radius based on capacity
        if base_capacity_base >= 5.0:  # pump_station_large
            actual_capacity_base = 5.0  # Strong large pump (realistic)
            radius_cells = 4               # 9×9 patch for wide coverage
        elif base_capacity_base >= 3.0:  # pump_medium
            actual_capacity_base = 3.0  # Moderate pump (realistic)
            radius_cells = 3               # 7×7 patch
        else:  # pump_small
            actual_capacity_base = 1.5  # Small pump (realistic)
            radius_cells = 2               # 5×5 patch
        
        # Apply adaptive boost for coarse grids
        actual_capacity = actual_capacity_base * self.physics_boost
        
        # Allow override from intervention
        rate_m3s_nom = float(intervention.get('rate_m3s', actual_capacity))
        radius_cells = int(intervention.get('radius_cells', radius_cells))

        # Rated pump curve Q(H): Q = Qmax * max(0, 1 - H/H_shut)
        oi, oj = self._find_outfall(i, j)
        try:
            bed_d = float(self.solver.bed[i, j]) if getattr(self.solver, 'bed', None) is not None else 0.0
            bed_o = float(self.solver.bed[oi, oj]) if getattr(self.solver, 'bed', None) is not None else 0.0
        except Exception:
            bed_d, bed_o = 0.0, 0.0
        eta_d = bed_d + float(self.solver.h[i, j])
        eta_o = bed_o + float(self.solver.h[oi, oj])
        H_static = max(0.0, eta_d - eta_o)
        H_shut = 3.0  # m; shutoff head
        head_factor = max(0.0, 1.0 - (H_static / H_shut))
        rate_m3s = max(0.0, rate_m3s_nom * head_factor)

        patch_cells = (2 * radius_cells + 1) ** 2
        sink_mps = rate_m3s / (self.cell_area * patch_cells)
        total_applied_m3s = self._apply_sink_patch(i, j, sink_mps, radius_cells)
        # Conservative routing: inject at outfall
        out_radius = max(1, radius_cells - 1)
        source_mps = sink_mps
        total_injected_m3s = self._apply_source_patch(oi, oj, source_mps, out_radius)
        
        return {
            'type': 'pump',
            'location': (i, j),
            'rate_m3s_nom': rate_m3s_nom,
            'rate_m3s': rate_m3s,
            'head_static_m': H_static,
            'head_factor': head_factor,
            'patch_radius_cells': radius_cells,
            'patch_size': f'{2*radius_cells+1}×{2*radius_cells+1}',
            'sink_per_cell_mps': float(sink_mps),
            'total_patch_Q_m3s': float(total_applied_m3s),
            'outfall': (oi, oj),
            'outfall_radius_cells': out_radius,
            'source_per_cell_mps': float(source_mps),
            'total_injected_Q_m3s': float(total_injected_m3s),
            'implementation': 'rated_pump_routing_v1'
        }
    
    def _apply_culvert(self, i: int, j: int, spec, intervention: Dict) -> Dict:
        """
        Apply culvert as hydraulic structure with proper flow physics.
        STRENGTHENED: Using simplified Orifice equation Q = C × A × √(2gh)
        CONSERVATIVE ROUTING: Convert sink to routed source at outfall (river/edge).
        """
        itype = intervention.get('type', '')
        
        # Determine culvert size and flow capacity (ADAPTIVE BOOST based on resolution)
        if '3x3' in str(itype).lower() or 'large' in str(spec.name).lower():
            area_m2_base = 9.0       # 3m × 3m box culvert (realistic dimension)
            radius_cells = 2         # 5×5 patch
            discharge_coef = 0.8     # Good box culvert
        elif '2x2' in str(itype).lower() or 'box' in str(spec.name).lower():
            area_m2_base = 4.0       # 2m × 2m box culvert (realistic dimension)
            radius_cells = 1         # 3×3 patch
            discharge_coef = 0.75    # Standard box culvert
        else:  # pipe culvert
            area_m2_base = 2.0       # ~1.6m diameter pipe (realistic dimension)
            radius_cells = 1         # 3×3 patch
            discharge_coef = 0.6     # Pipe culvert (entrance loss)
        
        # Apply adaptive boost for coarse grids
        area_m2 = area_m2_base * self.physics_boost
        
        # Demand-based sizing target flow using rational method Q = C i A
        try:
            A = self._contributing_area_m2(i, j)
            i_mps = float(np.nanmean(self.solver.rain_rate)) if getattr(self.solver, 'rain_rate', None) is not None else 0.0
            runoff_coeff = 0.6
            target_Q = max(1.0, runoff_coeff * i_mps * A)  # m3/s
        except Exception:
            target_Q = None
        # STRENGTHENED: Hydraulic calculation; Q = C × A × √(2gh)
        g = 9.81  # m/s²
        assumed_head = 0.75  # m (typical for road crossings)
        flow_m3s = discharge_coef * area_m2 * np.sqrt(2 * g * assumed_head)
        if target_Q is not None:
            flow_m3s = max(flow_m3s, 0.6 * target_Q)
        
        # Prefer structural coupler at site (road–drain crossing). If not feasible, fallback to sink+source routing.
        added_struct = self._add_local_culvert_structure(i, j, area_m2=area_m2)
        if added_struct:
            return {
                'type': 'culvert',
                'subtype': itype,
                'location': (i, j),
                'area_m2': area_m2,
                'discharge_coef': discharge_coef,
                'flow_capacity_m3s': float(flow_m3s),
                'implementation': 'structural_culvert_face_v1'
            }
        else:
            # Fallback conservative routing
            patch_cells = (2 * radius_cells + 1) ** 2
            sink_mps = flow_m3s / (self.cell_area * patch_cells)
            total_applied_m3s = self._apply_sink_patch(i, j, sink_mps, radius_cells=radius_cells)
            oi, oj = self._find_outfall(i, j)
            out_radius = max(1, radius_cells - 1)
            self._apply_source_patch(oi, oj, sink_mps, out_radius)
            return {
                'type': 'culvert',
                'subtype': itype,
                'location': (i, j),
                'area_m2': area_m2,
                'discharge_coef': discharge_coef,
                'flow_capacity_m3s': float(flow_m3s),
                'patch_radius_cells': radius_cells,
                'patch_size': f'{2*radius_cells+1}×{2*radius_cells+1}',
                'sink_per_cell_mps': float(sink_mps),
                'total_patch_Q_m3s': float(total_applied_m3s),
                'outfall': (oi, oj),
                'outfall_radius_cells': out_radius,
                'implementation': 'conservative_culvert_routing_v1'
            }
    
    def _apply_drain(self, i: int, j: int, spec, intervention: Dict) -> Dict:
        """
        Apply drain/channel upgrades.
        For 'channel' types: carve a corridor along D8 path to outfall and set canal roughness.
        For 'drain' types: apply localized sink+source routing (fallback).
        """
        itype = intervention.get('type', '').lower()
        # CHANNEL/CORRIDOR UPGRADE PATH
        if ('channel' in itype) or ('drain' in itype and intervention.get('corridor', False)):
            if not self._routing_built:
                self._build_flow_routing()
            # Walk D8 path from (i,j) to outfall with a step cap
            max_steps = int(intervention.get('max_steps', 150))
            carve_depth_m = float(intervention.get('carve_depth_m', 0.5)) * self.physics_boost
            canal_n = float(intervention.get('canal_manning_n', 0.030))
            half_width_cells = int(intervention.get('half_width_cells', 1))  # corridor half-width
            vi, vj = int(i), int(j)
            path = []
            steps = 0
            nx, ny = self.nx, self.ny
            while steps < max_steps:
                path.append((vi, vj))
                ni, nj = int(self._d8_next[vi, vj, 0]), int(self._d8_next[vi, vj, 1])
                if (ni == vi and nj == vj) or ni < 0 or nj < 0 or ni >= nx or nj >= ny:
                    break
                vi, vj = ni, nj
                steps += 1
                # Stop if reached boundary (likely outfall)
                if vi == 0 or vj == 0 or vi == nx - 1 or vj == ny - 1:
                    path.append((vi, vj))
                    break
            # Ensure manning_n_field exists
            try:
                if getattr(self.solver, 'manning_n_field', None) is None:
                    base_n = float(getattr(self.solver.prm, 'manning_n', 0.06))
                    self.solver.manning_n_field = np.full_like(self.solver.h, base_n, dtype=np.float32)
            except Exception:
                pass
            # Carve and set canal roughness along path
            carved = 0
            for (ci, cj) in path:
                ii0 = max(0, ci - half_width_cells)
                ii1 = min(nx, ci + half_width_cells + 1)
                jj0 = max(0, cj - half_width_cells)
                jj1 = min(ny, cj + half_width_cells + 1)
                # Lower bed to create preferential corridor
                try:
                    if hasattr(self.solver, 'bed') and isinstance(self.solver.bed, np.ndarray):
                        self.solver.bed[ii0:ii1, jj0:jj1] -= carve_depth_m
                except Exception:
                    pass
                # Reduce roughness to canal value
                try:
                    self.solver.manning_n_field[ii0:ii1, jj0:jj1] = np.minimum(
                        self.solver.manning_n_field[ii0:ii1, jj0:jj1], np.float32(canal_n)
                    )
                except Exception:
                    pass
                carved += 1
            return {
                'type': 'channel_upgrade',
                'location': (i, j),
                'path_len_cells': carved,
                'carve_depth_m': carve_depth_m,
                'canal_manning_n': canal_n,
                'half_width_cells': half_width_cells,
                'implementation': 'corridor_carve_and_canal_roughness_v1'
            }
        # LOCAL DRAIN (SINK+SOURCE)
        # Scale drain boost by contributing area, rainfall, and adaptive physics
        try:
            A = self._contributing_area_m2(i, j)
            i_mps = float(np.nanmean(self.solver.rain_rate)) if getattr(self.solver, 'rain_rate', None) is not None else 0.0
            runoff_coeff = 0.5
            Q_base = runoff_coeff * i_mps * A
            Q = Q_base * self.physics_boost
            patch_area = (2 * 1 + 1) ** 2 * self.cell_area
            boost_rate = max(5e-8, Q / patch_area)  # m/s
        except Exception:
            boost_rate = 2e-7 * self.physics_boost
        self._apply_sink_patch(i, j, boost_rate, radius_cells=1)
        oi, oj = self._find_outfall(i, j)
        out_radius = 1
        self._apply_source_patch(oi, oj, boost_rate, out_radius)
        return {
            'type': 'drain',
            'location': (i, j),
            'effective_sink_mps': boost_rate,
            'outfall': (oi, oj),
            'outfall_radius_cells': out_radius,
            'implementation': 'conservative_surface_drainage_v1'
        }
    
    def _apply_permeable(self, i: int, j: int, spec, intervention: Dict) -> Dict:
        """
        Apply permeable pavement/pavers as infiltration improvement.
        STRENGTHENED: 5x stronger infiltration (2e-6 → 1e-5 m/s), larger patch.
        """
        patch_size = 3  # 7x7 cell patch
        infil_boost_base = 2e-6  # Realistic infiltration boost (m/s)
        # Apply adaptive boost
        infil_boost = infil_boost_base * self.physics_boost
        self._apply_sink_patch(i, j, infil_boost, radius_cells=patch_size)
        
        return {
            'type': 'permeable',
            'location': (i, j),
            'patch_radius_cells': patch_size,
            'patch_size': f'{2*patch_size+1}×{2*patch_size+1}',
            'infil_boost_mps': infil_boost,
            'implementation': 'infiltration_patch_strengthened_v2'
        }
    
    # ------------------------------
    # New intervention types (Phase 2)
    # ------------------------------
    
    def _apply_barrier(self, i: int, j: int, spec, intervention: Dict) -> Dict:
        """
        Apply flood barrier (wall/levee/floodgate).
        Barriers block flow by setting bed elevation high or zeroing depth.
        """
        itype = intervention.get('type', '')
        
        # For walls/levees: raise bed locally to block flow
        if hasattr(self.solver, 'bed') and isinstance(self.solver.bed, np.ndarray):
            # Raise bed by wall height (2-6m typical)
            if 'wall' in str(itype).lower():
                height = 4.0  # 4m concrete wall
                radius = 0  # Single cell barrier
            elif 'levee' in str(itype).lower():
                height = 5.0  # 5m earthen levee
                radius = 1  # 3x3 footprint
            else:  # floodgate
                height = 3.0
                radius = 1
            
            nx, ny = self.solver.bed.shape
            ii0 = max(0, i - radius)
            ii1 = min(nx, i + radius + 1)
            jj0 = max(0, j - radius)
            jj1 = min(ny, j + radius + 1)
            self.solver.bed[ii0:ii1, jj0:jj1] += height
            # Mark these cells as overtoppable by setting crest elevations and overflow mask
            try:
                # Ensure overflow fields exist
                if getattr(self.solver, 'overflow_mask', None) is None:
                    self.solver.overflow_mask = np.zeros_like(self.solver.bed, dtype=np.float32)
                if getattr(self.solver, 'crest_elev', None) is None:
                    self.solver.crest_elev = np.full_like(self.solver.bed, 1.0e9, dtype=np.float32)
                # Water surface (eta) crest equals raised bed locally
                self.solver.overflow_mask[ii0:ii1, jj0:jj1] = 1.0
                self.solver.crest_elev[ii0:ii1, jj0:jj1] = self.solver.bed[ii0:ii1, jj0:jj1].astype(np.float32)
            except Exception:
                pass
        
        return {
            'type': 'barrier',
            'subtype': itype,
            'location': (i, j),
            'height_m': height if 'height' in locals() else 4.0,
            'implementation': 'bed_raise_with_overtopping'
        }
    
    def _apply_green(self, i: int, j: int, spec, intervention: Dict) -> Dict:
        """
        Apply green infrastructure (bioswale/rain garden/green roof).
        STRENGTHENED: 10x stronger infiltration, larger coverage areas.
        """
        itype = intervention.get('type', '')
        
        if 'bioswale' in str(itype).lower():
            # STRENGTHENED: 10x stronger + larger
            infil_boost = 5e-6  # was 5e-7
            radius = 3          # was 2 (5x5 → 7x7)
        elif 'rain_garden' in str(itype).lower():
            # STRENGTHENED: 10x stronger + larger
            infil_boost = 1e-5  # was 1e-6
            radius = 2          # was 1 (3x3 → 5x5)
        else:  # green_roof
            # STRENGTHENED: 10x stronger + larger
            infil_boost = 3e-6  # was 3e-7
            radius = 1          # was 0 (1x1 → 3x3)
        
        self._apply_sink_patch(i, j, infil_boost, radius_cells=radius)
        
        return {
            'type': 'green',
            'subtype': itype,
            'location': (i, j),
            'infil_boost_mps': infil_boost,
            'radius_cells': radius,
            'patch_size': f'{2*radius+1}×{2*radius+1}',
            'implementation': 'infiltration_boost_strengthened_v2'
        }
    
    def _apply_infiltration_trench(self, i: int, j: int, spec, intervention: Dict) -> Dict:
        """
        Apply infiltration trench - linear feature for groundwater recharge.
        """
        # Strong localized infiltration
        infil_boost = 1.5e-6
        radius = 1  # 3x3 patch
        self._apply_sink_patch(i, j, infil_boost, radius_cells=radius)
        
        return {
            'type': 'infiltration_trench',
            'location': (i, j),
            'infil_boost_mps': infil_boost,
            'implementation': 'trench_infiltration'
        }
    
    def _apply_smart_valve(self, i: int, j: int, spec, intervention: Dict) -> Dict:
        """
        Apply smart valve network - doesn't add capacity, but improves
        drainage efficiency. Model as modest infiltration boost.
        """
        # Valves don't remove water, they optimize existing drainage
        # Model as slight efficiency improvement
        efficiency_boost = 1e-7
        radius = 3  # 7x7 network coverage
        self._apply_sink_patch(i, j, efficiency_boost, radius_cells=radius)
        
        return {
            'type': 'smart_valve',
            'location': (i, j),
            'efficiency_boost_mps': efficiency_boost,
            'coverage_radius': radius,
            'implementation': 'drainage_efficiency'
        }
    
    def _apply_underground_tank(self, i: int, j: int, spec, intervention: Dict) -> Dict:
        """
        Apply underground storage tank - similar to pond but smaller footprint.
        """
        # Smaller capacity but concentrated
        capacity = 5000.0  # m³
        drawdown_time_s = 4.0 * 3600.0  # 4 hour drawdown
        total_Q_m3s = capacity / drawdown_time_s
        radius_cells = 2  # 5x5 footprint
        
        patch_cells = (2 * radius_cells + 1) ** 2
        sink_mps = total_Q_m3s / (self.cell_area * patch_cells)
        total_applied_m3s = self._apply_sink_patch(i, j, sink_mps, radius_cells)
        
        return {
            'type': 'underground_tank',
            'location': (i, j),
            'capacity_m3': capacity,
            'drawdown_hours': 4.0,
            'patch_radius_cells': radius_cells,
            'sink_per_cell_mps': float(sink_mps),
            'total_patch_Q_m3s': float(total_applied_m3s),
            'implementation': 'buried_storage'
        }


def apply_qcia_design_to_solver(solver, grid, design_path: Path, verbose=True) -> List[Dict]:
    """
    Convenience function to apply QCIA design to solver.
    
    Args:
        solver: HRFSolver instance
        grid: Grid instance  
        design_path: Path to qcia_design.json
        verbose: Print details
    
    Returns:
        List of applied interventions
    """
    applier = InterventionApplier(solver, grid, verbose=verbose)
    return applier.apply_design(design_path)

