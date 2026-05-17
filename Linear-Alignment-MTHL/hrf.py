#!/usr/bin/env python3
"""
HRF-SWE (MVP) — Pseudo‑spectral shallow‑water solver with exponential filtering,
CFL‑controlled RK3 time stepping, basic wetting/drying guards, and simple
hydraulic structures (weir/culvert/bridge as flux couplers across user‑defined
interfaces). Designed as a single-file, reproducible baseline for pilot tiles.

Notes
-----
1) This is a practical, minimal implementation: it evolves fields on a uniform
   grid in physical space but computes spatial derivatives and filtering in the
   spectral domain (FFT). It captures the spirit of the discussed HRF approach
   (spectral representation + exponential filter + parameter parsimony) without
   introducing an external basis manager. You can later swap in your custom
   basis/projection while keeping the same stepping/filter/structure logic.
2) Boundaries are periodic by construction (FFT). A light sponge/relaxation is
   provided to emulate open/tidal boundaries for pilot experiments.
3) Structures are implemented as localized flux exchanges across a polyline of
   grid faces you define. They conserve mass and are applied after each substep.
4) This file includes two demo cases: 1D dam‑break and 2D radial dam‑break. You
   can adapt `make_pilot_tile()` to run a Singapore city tile.

Dependencies: numpy (only). No SciPy required.

Author: PUB-style reproduction scaffold
License: MIT
"""
from __future__ import annotations

import math
import time
import os
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Callable

import numpy as np

# ============================================================
# Backend selection for GPU acceleration (NumPy/PyTorch)
# ============================================================
_xp = np
_device = "cpu"
try:
    import torch
    if torch.backends.mps.is_available():
        _device = "mps"
        _xp = torch
        print("[hrf] Using PyTorch with MPS backend.")
    else:
        print("[hrf] PyTorch found but MPS not available, using NumPy.")
except ImportError:
    print("[hrf] PyTorch not found, using NumPy backend.")

def to_numpy(arr):
    """Convert a tensor to a NumPy array, regardless of backend."""
    if hasattr(arr, 'cpu') and hasattr(arr, 'numpy'):
        return arr.cpu().numpy()
    return np.asarray(arr)

def asarray_backend_agnostic(xp, arr, device="cpu", dtype=None):
    """Create array in backend-agnostic way."""
    if hasattr(xp, 'device'):  # PyTorch
        return xp.asarray(arr, device=device, dtype=dtype)
    else:  # NumPy
        arr_np = np.asarray(arr, dtype=dtype)
        return xp.asarray(arr_np)

def roll_backend_agnostic(xp, arr, shift, axis):
    """Roll array in backend-agnostic way."""
    if hasattr(xp, 'device'):  # PyTorch
        return xp.roll(arr, shift, dims=axis)
    else:  # NumPy
        return xp.roll(arr, shift, axis=axis)

# ============================================================
# Utilities: grid, FFT-based spectral ops, exponential filter
# ============================================================

@dataclass
class Grid:
    nx: int
    ny: int
    Lx: float
    Ly: float
    xp: ... = _xp
    device: str = _device

    def __post_init__(self):
        self.dx = self.Lx / self.nx
        self.dy = self.Ly / max(1, self.ny)
        if hasattr(self.xp, 'device'):  # PyTorch
            x = self.xp.arange(self.nx, device=self.device, dtype=self.xp.float32) * self.dx + (0.5 * self.dx)
            if self.ny > 1:
                y = self.xp.arange(self.ny, device=self.device, dtype=self.xp.float32) * self.dy + (0.5 * self.dy)
            else:
                y = self.xp.array([0.5 * self.dy], device=self.device, dtype=self.xp.float32)
        else:  # NumPy
            x = self.xp.arange(self.nx, dtype=self.xp.float32) * self.dx + (0.5 * self.dx)
            if self.ny > 1:
                y = self.xp.arange(self.ny, dtype=self.xp.float32) * self.dy + (0.5 * self.dy)
            else:
                y = self.xp.array([0.5 * self.dy], dtype=self.xp.float32)
        
        self.X, self.Y = self.xp.meshgrid(x, y, indexing="ij")
        
        # Wavenumbers (periodic domain)
        kx_raw = 2 * np.pi * self.xp.fft.fftfreq(self.nx, d=self.dx)
        if hasattr(kx_raw, 'to'):  # PyTorch tensor
            kx = kx_raw.to(self.device)
        else:  # NumPy array
            kx = self.xp.asarray(kx_raw, dtype=self.xp.float32)

        if self.ny > 1:
            ky_raw = 2 * np.pi * self.xp.fft.fftfreq(self.ny, d=self.dy)
            if hasattr(ky_raw, 'to'):  # PyTorch tensor
                ky = ky_raw.to(self.device)
            else:  # NumPy array
                ky = self.xp.asarray(ky_raw, dtype=self.xp.float32)
        else:
            ky = self.xp.array([0.0], dtype=self.xp.float32)

        self.KX, self.KY = self.xp.meshgrid(kx, ky, indexing="ij")
        self.kx_max = self.xp.max(self.xp.abs(kx)) if self.nx > 1 else 0.0
        self.ky_max = self.xp.max(self.xp.abs(ky)) if self.ny > 1 else 0.0

    # Spectral derivatives
    def ddx(self, f) -> np.ndarray:
        F = self.xp.fft.fft2(f)
        d = self.xp.fft.ifft2(1j * self.KX * F).real
        return d

    def ddy(self, f) -> np.ndarray:
        if self.ny == 1:
            return self.xp.zeros_like(f)
        F = self.xp.fft.fft2(f)
        d = self.xp.fft.ifft2(1j * self.KY * F).real
        return d

@dataclass
class ExponentialFilter:
    alpha: float = 36.0
    p: int = 8

    def mask(self, grid: Grid):
        xp = grid.xp
        # Normalized radius in spectral space η ∈ [0, 1]
        kx_n = xp.abs(grid.KX) / (grid.kx_max + 1e-14)
        ky_n = xp.abs(grid.KY) / (grid.ky_max + 1e-14) if grid.ny > 1 else 0.0
        
        # Backend-agnostic check for tensor type
        is_tensor = xp.is_tensor(ky_n) if hasattr(xp, 'is_tensor') else isinstance(ky_n, np.ndarray)
        
        eta = xp.sqrt(kx_n ** 2 + (ky_n ** 2 if is_tensor else ky_n))
        sigma = xp.exp(-self.alpha * (eta ** self.p))
        return sigma

    def apply(self, grid: Grid, f):
        xp = grid.xp
        F = xp.fft.fft2(f)
        out = xp.fft.ifft2(F * self.mask(grid)).real
        return out

# ==============================================
# Hydraulic structures (mass-conserving couplers)
# ==============================================

@dataclass
class FaceIndex:
    """Represents a face between cell (i,j) and its neighbor.
    dir: 'x' means face between (i,j) and (i+1,j); 'y' means (i,j) and (i,j+1).
    """
    i: int
    j: int
    dir: str  # 'x' or 'y'

@dataclass
class Weir:
    faces: List[FaceIndex]
    Cd: float = 1.6  # discharge coefficient
    crest_elev: float = 0.0  # m (relative to bed)
    width_per_face: Optional[float] = None  # if None, uses grid spacing

@dataclass
class Culvert:
    faces: List[FaceIndex]
    area: float  # m^2
    C0: float = 0.62  # pressurized coefficient
    Cf: float = 0.62  # free-flow coefficient
    invert_up: float = 0.0
    invert_dn: float = 0.0

@dataclass
class Bridge:
    faces: List[FaceIndex]
    area_free: float  # m^2
    area_press: float  # m^2 (for drowned)
    Cd_free: float = 0.7
    Cd_press: float = 0.7
    deck_elev: float = 1.0

# ================================
# Core shallow‑water MVP components
# ================================

@dataclass
class SWEParams:
    g: float = 9.81
    manning_n: float = 0.0  # 0 => frictionless
    h_min: float = 1e-4
    cfl: float = 0.30
    vmax_guard_coef: float = 1.5  # |v|max <= coef * sqrt(g h)
    sponge_width: int = 0  # cells from boundary to relax
    sponge_tau: float = 60.0  # s, relaxation timescale
    dt_max: float = 0.0  # optional hard cap on time step (0 => disabled)
    # SPU controls
    adaptive_truncation: bool = False
    tail_target: float = 1e-3
    mfrac_min: float = 0.20
    mfrac_max: float = 1.00
    filter_type: str = "exp"  # hard | exp
    filter_alpha: float = 8.0
    filter_order: int = 8

@dataclass
class HRFSolver:
    grid: Grid
    prm: SWEParams
    filt: ExponentialFilter
    structures: Dict[str, List] = field(default_factory=lambda: {"weirs": [], "culverts": [], "bridges": []})
    tide_bc: Optional[Dict] = None  # e.g., {"edge": "west", "eta_func": callable(t)->stage}
    # Optional fields for extended physics
    bed = None            # bed elevation z(x,y) in meters
    rain_rate = None      # rainfall rate [m/s], grid-shaped or scalar broadcast
    infil_rate = None     # infiltration rate [m/s], grid-shaped or scalar broadcast
    manning_n_field = None  # spatial roughness map (per-cell Manning n)
    # Optional overflow treatment for canals/drains
    overflow_mask = None     # uint8 mask where bankfull/crest logic applies
    crest_elev = None        # crest elevation (m) per cell
    overflow_Cd: float = 1.6 # broad-crested coefficient
    mode: str = "swe"  # 'swe' (default), 'dw' (spectral DW), 'dw_fv' (finite-volume DW)

    def __post_init__(self):
        self.xp = self.grid.xp
        self.device = self.grid.device
        self.h = None
        self.u = None
        self.v = None
        # SPU state
        self.spu_hard_mask = None
        self.spu_smooth_mask = None
        self.spu_mfrac = self.prm.mfrac_max

    def initialize(self, h0: np.ndarray, u0: np.ndarray, v0: np.ndarray):
        self.h = asarray_backend_agnostic(self.xp, h0, device=self.device, dtype=self.xp.float32)
        self.u = asarray_backend_agnostic(self.xp, u0, device=self.device, dtype=self.xp.float32)
        self.v = asarray_backend_agnostic(self.xp, v0, device=self.device, dtype=self.xp.float32)
        self.time = 0.0
        self.mass0 = self.total_mass()
        self.initialize_spu()

    def initialize_spu(self):
        if not self.prm.adaptive_truncation:
            return
        R = self.xp.sqrt(self.grid.KX**2 + self.grid.KY**2)
        R_cpu = to_numpy(R)
        self.spu_R_sorted = np.sort(R_cpu.ravel())
        self.spu_build_mask_from_fraction(self.spu_mfrac)

    def spu_build_mask_from_fraction(self, frac: float):
        frac = float(min(max(frac, self.prm.mfrac_min), self.prm.mfrac_max))
        kth = int(min(max(1, round(frac * self.spu_R_sorted.size)), self.spu_R_sorted.size - 1))
        r_cut = float(self.spu_R_sorted[kth])
        
        R = self.xp.sqrt(self.grid.KX**2 + self.grid.KY**2)
        if self.prm.filter_type == "hard":
            self.spu_hard_mask = (R <= r_cut)
            self.spu_smooth_mask = None
        else: # exp
            self.spu_hard_mask = None
            self.spu_smooth_mask = self.xp.exp(-self.prm.filter_alpha * (R / max(r_cut, 1e-9)) ** self.prm.filter_order)
        self.spu_mfrac = frac

    def spu_apply_truncation(self, f_hat):
        if not self.prm.adaptive_truncation:
            return f_hat
        if self.prm.filter_type == "hard":
            return self.xp.where(self.spu_hard_mask, f_hat, 0.0)
        else: # exp
            return f_hat * self.spu_smooth_mask

    def spu_update_controller(self, h_hat):
        if not self.prm.adaptive_truncation:
            return
        
        if self.prm.filter_type == "hard":
            tail_energy = float(self.xp.sum(self.xp.abs(h_hat[~self.spu_hard_mask]) ** 2))
            total_energy = float(self.xp.sum(self.xp.abs(h_hat) ** 2)) + 1e-12
        else: # exp
            comp = 1.0 - self.spu_smooth_mask
            tail_energy = float(self.xp.sum(self.xp.abs(h_hat) ** 2 * comp))
            total_energy = float(self.xp.sum(self.xp.abs(h_hat) ** 2)) + 1e-12

        tail_frac = tail_energy / total_energy
        
        # Proportional controller
        if tail_frac > 1.5 * self.prm.tail_target:
            self.spu_mfrac = min(self.prm.mfrac_max, self.spu_mfrac * 1.15)
            self.spu_build_mask_from_fraction(self.spu_mfrac)
        elif tail_frac < 0.5 * self.prm.tail_target:
            self.spu_mfrac = max(self.prm.mfrac_min, self.spu_mfrac * 0.90)
            self.spu_build_mask_from_fraction(self.spu_mfrac)

    def set_forcing(self, bed: Optional[np.ndarray] = None,
                    rain_rate = None,
                    infil_rate = None,
                    roughness_n: Optional[np.ndarray] = None,
                    overflow_mask: Optional[np.ndarray] = None,
                    crest_elev: Optional[np.ndarray] = None,
                    overflow_Cd: Optional[float] = None) -> None:
        """Attach optional bed elevation and hydrologic source/sink fields.
        All arrays must be shaped (nx, ny). Scalars will be broadcast by caller.
        """
        if bed is not None:
            self.bed = asarray_backend_agnostic(self.xp, bed, device=self.device, dtype=self.xp.float32)

        # Helper to check for array types in a backend-agnostic way
        def is_array(x):
            if self.xp is np:
                return isinstance(x, np.ndarray)
            else: # torch
                return self.xp.is_tensor(x)

        if rain_rate is not None:
            if is_array(rain_rate):
                 self.rain_rate = asarray_backend_agnostic(self.xp, rain_rate, device=self.device, dtype=self.xp.float32)
            else:
                 self.rain_rate = self.xp.full((self.grid.nx, self.grid.ny), float(rain_rate), dtype=self.xp.float32)
        if infil_rate is not None:
            if is_array(infil_rate):
                self.infil_rate = asarray_backend_agnostic(self.xp, infil_rate, device=self.device, dtype=self.xp.float32)
            else:
                self.infil_rate = self.xp.full((self.grid.nx, self.grid.ny), float(infil_rate), dtype=self.xp.float32)
        if roughness_n is not None:
            self.manning_n_field = asarray_backend_agnostic(self.xp, roughness_n, device=self.device, dtype=self.xp.float32)
        if overflow_mask is not None:
            # ensure binary mask
            om = asarray_backend_agnostic(self.xp, overflow_mask, device=self.device, dtype=self.xp.float32)
            if hasattr(self.xp, 'where'):
                om = self.xp.where(om > 0, 1.0, 0.0)
            self.overflow_mask = om.astype(self.xp.float32) if hasattr(om, 'astype') else om.to(self.xp.float32)
        if crest_elev is not None:
            self.crest_elev = asarray_backend_agnostic(self.xp, crest_elev, device=self.device, dtype=self.xp.float32)
        if overflow_Cd is not None:
            self.overflow_Cd = float(overflow_Cd)

    # --------------------
    # Diagnostics & guards
    # --------------------
    def total_mass(self) -> float:
        return float(self.xp.sum(self.h) * self.grid.dx * self.grid.dy)

    def apply_guards(self):
        h = self.h
        u = self.u
        v = self.v
        xp = self.xp
        # Positivity
        h[h < self.prm.h_min] = self.prm.h_min
        # Velocity cap
        c = xp.sqrt(self.prm.g * h)
        vcap = self.prm.vmax_guard_coef * c + 1e-9
        spd = xp.sqrt(u*u + v*v)
        mask = spd > vcap
        if xp.any(mask):
            scale = vcap[mask] / spd[mask]
            u[mask] *= scale
            v[mask] *= scale

    # ---------------
    # Sponge / tides
    # ---------------
    def apply_sponge(self, h_target: Optional[np.ndarray] = None, dt: float = 0.0):
        if self.prm.sponge_width <= 0:
            return
        nx, ny = self.grid.nx, self.grid.ny
        w = self.prm.sponge_width
        tau = max(1e-6, self.prm.sponge_tau)
        if h_target is None:
            h_target = self.h
        # Left/right
        lam = dt / tau
        self.h[:w, :] = (1 - lam) * self.h[:w, :] + lam * h_target[:w, :]
        self.h[-w:, :] = (1 - lam) * self.h[-w:, :] + lam * h_target[-w:, :]
        if ny > 1:
            self.h[:, :w] = (1 - lam) * self.h[:, :w] + lam * h_target[:, :w]
            self.h[:, -w:] = (1 - lam) * self.h[:, -w:] + lam * h_target[:, -w:]

    def apply_tide_bc(self, t: float, dt: float):
        if not self.tide_bc:
            return
        edge = self.tide_bc.get("edge", "west")
        eta = float(self.tide_bc["eta_func"](t))
        target = self.h.clone() if hasattr(self.h, 'clone') else self.h.copy()
        if edge == "west":
            target[0, :] = eta
        elif edge == "east":
            target[-1, :] = eta
        elif edge == "south" and self.grid.ny > 1:
            target[:, 0] = eta
        elif edge == "north" and self.grid.ny > 1:
            target[:, -1] = eta
        self.apply_sponge(target, dt)

    # --------------------
    # Physics: RHS builders
    # --------------------
    def rhs(self, h, u, v) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        g = self.prm.g
        grid = self.grid
        xp = self.xp
        
        # --- Create tensor versions of scalar parameters for PyTorch ---
        h_min_tensor = xp.asarray(self.prm.h_min, device=self.device, dtype=xp.float32)
        g_tensor = xp.asarray(g, device=self.device, dtype=xp.float32)
        zero_tensor = xp.asarray(0.0, device=self.device, dtype=xp.float32)
        one_tensor = xp.asarray(1.0, device=self.device, dtype=xp.float32)
        eps_tensor = xp.asarray(1e-12, device=self.device, dtype=xp.float32)

        if self.mode == "dw":
            # Diffusive-wave closure: finite-difference surface gradients with caps
            n = max(1e-9, self.prm.manning_n)
            H = xp.maximum(h, h_min_tensor)
            eta = H + (self.bed if self.bed is not None else 0.0)
            # Centered differences with periodic wrap
            deta_dx = (xp.roll(eta, -1, dims=0) - xp.roll(eta, 1, dims=0)) / (2.0 * grid.dx)
            deta_dy = (xp.roll(eta, -1, dims=1) - xp.roll(eta, 1, dims=1)) / (2.0 * grid.dy)
            slope_mag = xp.sqrt(deta_dx * deta_dx + deta_dy * deta_dy)
            # Cap slopes to avoid unrealistically steep local gradients
            slope_cap = 0.1  # 10%
            slope_mag = xp.minimum(slope_mag, slope_cap)
            eps = 1e-10
            slope_mag = xp.maximum(slope_mag, eps)
            ex = -deta_dx / slope_mag
            ey = -deta_dy / slope_mag
            # Zero directions where slope ~ 0
            mask_flat = slope_mag <= 2*eps
            if xp.any(mask_flat):
                ex[mask_flat] = 0.0
                ey[mask_flat] = 0.0
            # Manning relation with caps on velocity
            Umag = (H ** (2.0 / 3.0)) * xp.sqrt(g_tensor) * xp.sqrt(slope_mag) / n
            vcap = self.prm.vmax_guard_coef * xp.sqrt(g_tensor * H)
            Umag = xp.minimum(Umag, vcap)
            u_d = Umag * ex
            v_d = Umag * ey
            # Fluxes (cap extreme values and avoid NaNs)
            hu = xp.nan_to_num(H * u_d, nan=0.0, posinf=0.0, neginf=0.0)
            hv = xp.nan_to_num(H * v_d, nan=0.0, posinf=0.0, neginf=0.0)
            # Finite-difference divergence to avoid FFT in DW path
            d_hu_dx = (hu - xp.roll(hu, 1, axis=0)) / grid.dx
            d_hv_dy = (hv - xp.roll(hv, 1, axis=1)) / grid.dy
            dhdt = -(d_hu_dx + d_hv_dy)
            if self.rain_rate is not None:
                dhdt = dhdt + self.rain_rate
            if self.infil_rate is not None:
                dhdt = dhdt - self.infil_rate
            # Momentum not prognosed in DW; relax u,v toward diagnostic velocity
            relax = 0.5
            dudt = relax * (u_d - u)
            dvdt = relax * (v_d - v)
            return dhdt, dudt, dvdt
        elif self.mode == "dw_fv":
            # Finite-volume diffusive-wave: monotone donor-cell upwind face fluxes
            # Allow spatial roughness field; fallback to global scalar
            if self.manning_n_field is not None:
                n_cell = xp.maximum(xp.asarray(1e-9, device=self.device), self.manning_n_field)
            else:
                n_cell = xp.full_like(h, max(1e-9, self.prm.manning_n), dtype=xp.float32)
            H = xp.maximum(h, h_min_tensor)
            Z = self.bed if self.bed is not None else 0.0
            eta = H + Z
            dx, dy = self.grid.dx, self.grid.dy
            nx, ny = self.grid.nx, self.grid.ny
            K_cell = xp.sqrt(g_tensor) / n_cell
            s_cap = 0.1
            # East-face slopes s_e >= 0 for flow i->i+1; size (nx,ny) with last column zero
            s_e = xp.zeros_like(H)
            d_eta_e = (eta[0:nx-1, :] - eta[1:nx, :]) / dx
            s_e[0:nx-1, :] = xp.clip(d_eta_e, 0.0, s_cap)
            H_e = xp.zeros_like(H)
            H_e[0:nx-1, :] = xp.minimum(H[0:nx-1, :], H[1:nx, :])
            K_e = xp.zeros_like(H)
            K_e[0:nx-1, :] = 0.5 * (K_cell[0:nx-1, :] + K_cell[1:nx, :])
            q_e = K_e * (H_e ** (5.0/3.0)) * xp.sqrt(s_e)
            # South-face slopes s_s >= 0 for flow j->j+1; size (nx,ny) with last row zero
            s_s = xp.zeros_like(H)
            d_eta_s = (eta[:, 0:ny-1] - eta[:, 1:ny]) / dy
            s_s[:, 0:ny-1] = xp.clip(d_eta_s, 0.0, s_cap)
            H_s = xp.zeros_like(H)
            H_s[:, 0:ny-1] = xp.minimum(H[:, 0:ny-1], H[:, 1:ny])
            K_s = xp.zeros_like(H)
            K_s[:, 0:ny-1] = 0.5 * (K_cell[:, 0:ny-1] + K_cell[:, 1:ny])
            q_s = K_s * (H_s ** (5.0/3.0)) * xp.sqrt(s_s)
            # Optional draining-based limiter
            dt = getattr(self, '_dt', 0.0)
            if dt > 0.0:
                cell_area = dx * dy
                out = q_e * dy + q_s * dx
                avail = xp.maximum(H - h_min_tensor, zero_tensor) * cell_area
                theta = xp.where(out > 0.0, xp.minimum(one_tensor, avail / (out * dt + eps_tensor)), one_tensor)
                q_e[0:nx-1, :] *= theta[0:nx-1, :]
                q_s[:, 0:ny-1] *= theta[:, 0:ny-1]
            # Divergence: east flux out minus west flux in; south out minus north in
            dqx = xp.zeros_like(H)
            dqx[0, :] = q_e[0, :] / dx
            dqx[1:nx-1, :] = (q_e[1:nx-1, :] - q_e[0:nx-2, :]) / dx
            dqx[nx-1, :] = -q_e[nx-2, :] / dx if nx > 1 else 0.0
            dqy = xp.zeros_like(H)
            dqy[:, 0] = q_s[:, 0] / dy
            dqy[:, 1:ny-1] = (q_s[:, 1:ny-1] - q_s[:, 0:ny-2]) / dy
            dqy[:, ny-1] = -q_s[:, ny-2] / dy if ny > 1 else 0.0
            dhdt = -(dqx + dqy)
            if self.rain_rate is not None:
                dhdt = dhdt + self.rain_rate
            if self.infil_rate is not None:
                dhdt = dhdt - self.infil_rate
            # Diagnostic velocities from face fluxes (cell-centered approx)
            invH = 1.0 / xp.maximum(H, h_min_tensor)
            u_d = xp.zeros_like(H); v_d = xp.zeros_like(H)
            u_d[0, :] = 0.5 * q_e[0, :] * invH[0, :]
            u_d[1:nx, :] = 0.5 * (q_e[1:nx, :] + q_e[0:nx-1, :]) * invH[1:nx, :]
            v_d[:, 0] = 0.5 * q_s[:, 0] * invH[:, 0]
            v_d[:, 1:ny] = 0.5 * (q_s[:, 1:ny] + q_s[:, 0:ny-1]) * invH[:, 1:ny]
            relax = 0.5
            dudt = relax * (u_d - u)
            dvdt = relax * (v_d - v)
            return dhdt, dudt, dvdt
        else:
            # Full SWE path (original)
            hu = h * u
            hv = h * v
            dhdt = -(grid.ddx(hu) + grid.ddy(hv))
            if self.rain_rate is not None:
                dhdt = dhdt + self.rain_rate
            if self.infil_rate is not None:
                dhdt = dhdt - self.infil_rate
            u2 = u * u
            v2 = v * v
            uv = u * v
            px = grid.ddx(0.5 * g * h * h)
            py = grid.ddy(0.5 * g * h * h)
            dudt = -(grid.ddx(hu * u) + grid.ddy(hv * u)) - px / (h + eps_tensor)
            dvdt = -(grid.ddx(hu * v) + grid.ddy(hv * v)) - py / (h + eps_tensor)
            if self.bed is not None:
                dzdx = grid.ddx(self.bed)
                dzdy = grid.ddy(self.bed)
                dudt = dudt - g * dzdx
                dvdt = dvdt - g * dzdy
            if self.prm.manning_n > 0.0:
                n2 = self.prm.manning_n ** 2
                spd = xp.sqrt(u2 + v2)
                Sf = n2 * spd / xp.maximum(h, h_min_tensor) ** (4.0 / 3.0)
                dudt -= g_tensor * Sf * u
                dvdt -= g_tensor * Sf * v
            return dhdt, dudt, dvdt

    # --------------------------
    # Structures as flux couplers
    # --------------------------
    def apply_structures(self, dt: float):
        g = self.prm.g
        nx, ny = self.grid.nx, self.grid.ny
        dx, dy = self.grid.dx, self.grid.dy
        cell_area = dx * dy
        # Bankfull overtop (canal/drain overflow): broad-crested weir per cell to neighbors
        if self.overflow_mask is not None and self.crest_elev is not None:
            Cd = float(self.overflow_Cd)
            mask = self.overflow_mask
            # Excess head above crest
            Hx = self.h - self.crest_elev
            zero = self.xp.asarray(0.0, device=self.device, dtype=self.xp.float32)
            Hx = self.xp.maximum(Hx, zero) if hasattr(self.xp, 'maximum') else np.maximum(Hx, 0.0)
            if float(self.xp.max(Hx)) > 0.0:
                # Potential discharge per edge (limit to neighbors outside mask or lower head)
                W_e = dy; W_s = dx
                # East/west
                q_e = Cd * W_e * (Hx ** 1.5) * math.sqrt(2 * g)
                q_w = self.xp.roll(q_e, 1, dims=0)
                # South/north
                q_s = Cd * W_s * (Hx ** 1.5) * math.sqrt(2 * g)
                q_n = self.xp.roll(q_s, 1, dims=1)
                # Only from overflow cells to non-overflow neighbors
                nei_e = 1.0 - self.xp.roll(mask, -1, dims=0)
                nei_w = 1.0 - self.xp.roll(mask,  1, dims=0)
                nei_s = 1.0 - self.xp.roll(mask, -1, dims=1)
                nei_n = 1.0 - self.xp.roll(mask,  1, dims=1)
                q_e = q_e * mask * nei_e
                q_w = q_w * self.xp.roll(mask, -1, dims=0) * nei_w  # from east neighbor into this
                q_s = q_s * mask * nei_s
                q_n = q_n * self.xp.roll(mask, -1, dims=1) * nei_n
                # Net volume change (outflows positive)
                dV = dt * (q_e + q_s) - dt * (q_w + q_n)
                dH = dV / cell_area
                self.h = self.h - dH

        # Helper to pull head (stage) at a face
        def head(i, j):
            return self.h[i, j]

        # Weirs
        for w in self.structures.get("weirs", []):
            Wf = w.width_per_face if w.width_per_face is not None else (dy if w.faces and w.faces[0].dir == 'x' else dx)
            for fc in w.faces:
                i, j, d = fc.i, fc.j, fc.dir
                if d == 'x':
                    iu = i; idn = (i + 1) % nx; ju = j; jdn = j
                else:
                    iu = i; idn = i; ju = j; jdn = (j + 1) % ny
                H_up = max(0.0, head(iu, ju) - w.crest_elev)
                H_dn = max(0.0, head(idn, jdn) - w.crest_elev)
                # Only flow if upstream above crest
                if H_up <= 0.0:
                    continue
                H = H_up
                Q = w.Cd * Wf * (H ** 1.5) * math.sqrt(2 * g)
                # Direction: from higher head to lower
                sgn = 1.0 if head(iu, ju) >= head(idn, jdn) else -1.0
                Q *= sgn
                dV = Q * dt
                # Convert volume to depth change equally in donor/receiver cell
                dH = dV / cell_area
                self.h[iu, ju] -= dH
                self.h[idn, jdn] += dH

        # Culverts
        for c in self.structures.get("culverts", []):
            A = c.area
            for fc in c.faces:
                i, j, d = fc.i, fc.j, fc.dir
                if d == 'x':
                    iu = i; idn = (i + 1) % nx; ju = j; jdn = j
                else:
                    iu = i; idn = i; ju = j; jdn = (j + 1) % ny
                H_up = max(0.0, head(iu, ju) - c.invert_up)
                H_dn = max(0.0, head(idn, jdn) - c.invert_dn)
                if H_up <= 0 and H_dn <= 0:
                    continue
                dH = (head(iu, ju) - head(idn, jdn))
                if dH >= 0:  # flow from up -> down
                    # Determine regime (pressurized vs free)
                    if head(iu, ju) > c.invert_up and head(idn, jdn) > c.invert_dn and head(iu, ju) > head(idn, jdn):
                        Q = c.C0 * A * math.sqrt(max(0.0, 2 * g * (head(iu, ju) - head(idn, jdn))))
                    else:
                        Hf = max(0.0, head(iu, ju) - c.invert_up)
                        Q = c.Cf * A * math.sqrt(2 * g * Hf)
                    sgn = 1.0
                else:  # reverse
                    if head(idn, jdn) > c.invert_dn and head(iu, ju) > c.invert_up and head(idn, jdn) > head(iu, ju):
                        Q = c.C0 * A * math.sqrt(max(0.0, 2 * g * (head(idn, jdn) - head(iu, ju))))
                    else:
                        Hf = max(0.0, head(idn, jdn) - c.invert_dn)
                        Q = c.Cf * A * math.sqrt(2 * g * Hf)
                    sgn = -1.0
                dV = sgn * Q * dt
                dHr = dV / cell_area
                self.h[iu, ju] -= dHr
                self.h[idn, jdn] += dHr

        # Bridges (composite: free + pressurized under deck)
        for b in self.structures.get("bridges", []):
            for fc in b.faces:
                i, j, d = fc.i, fc.j, fc.dir
                if d == 'x':
                    iu = i; idn = (i + 1) % nx; ju = j; jdn = j
                else:
                    iu = i; idn = i; ju = j; jdn = (j + 1) % ny
                eta_u = head(iu, ju)
                eta_d = head(idn, jdn)
                dH = eta_u - eta_d
                if abs(dH) < 1e-12:
                    continue
                if eta_u < b.deck_elev and eta_d < b.deck_elev:
                    A = b.area_free
                    Cd = b.Cd_free
                else:
                    A = b.area_press
                    Cd = b.Cd_press
                Q = Cd * A * math.sqrt(2 * g * abs(dH)) * (1.0 if dH >= 0 else -1.0)
                dV = Q * dt
                dHr = dV / cell_area
                self.h[iu, ju] -= dHr
                self.h[idn, jdn] += dHr

    # ---------------------
    # Time stepping (RK3-CFL)
    # ---------------------
    def max_characteristic_speed(self) -> float:
        xp = self.xp
        c = xp.sqrt(self.prm.g * self.h)
        spd = xp.sqrt(self.u * self.u + self.v * self.v) + c
        return float(xp.max(spd))

    def choose_dt(self) -> float:
        xp = self.xp
        # Special dt control for diffusive-wave modes: local draining cap
        if self.mode in ("dw", "dw_fv"):
            dt = 1e9
            g = self.prm.g
            n = max(1e-9, self.prm.manning_n)
            H = xp.maximum(self.h, xp.asarray(self.prm.h_min, device=self.device))
            Z = self.bed if self.bed is not None else 0.0
            eta = H + Z
            dx, dy = self.grid.dx, self.grid.dy
            cell_area = dx * dy
            # Slopes to neighbors (only downslope outflows considered)
            eta_e = roll_backend_agnostic(xp, eta, -1, 0)
            eta_w = roll_backend_agnostic(xp, eta, 1, 0)
            eta_n = roll_backend_agnostic(xp, eta, 1, 1)
            eta_s = roll_backend_agnostic(xp, eta, -1, 1)
            s_e = xp.clip((eta - eta_e) / dx, 0.0, 0.1)
            s_w = xp.clip((eta - eta_w) / dx, 0.0, 0.1)
            s_n = xp.clip((eta - eta_n) / dy, 0.0, 0.1)
            s_s = xp.clip((eta - eta_s) / dy, 0.0, 0.1)
            H_e = xp.minimum(H, roll_backend_agnostic(xp, H, -1, 0))
            H_w = xp.minimum(H, roll_backend_agnostic(xp, H, 1, 0))
            H_n = xp.minimum(H, roll_backend_agnostic(xp, H, 1, 1))
            H_s = xp.minimum(H, roll_backend_agnostic(xp, H, -1, 1))
            K = xp.sqrt(asarray_backend_agnostic(xp, g, device=self.device)) / n
            q_e = (H_e ** (5.0/3.0)) * K * xp.sqrt(s_e)  # per unit width
            q_w = (H_w ** (5.0/3.0)) * K * xp.sqrt(s_w)
            q_n = (H_n ** (5.0/3.0)) * K * xp.sqrt(s_n)
            q_s = (H_s ** (5.0/3.0)) * K * xp.sqrt(s_s)
            Qout = q_e * dy + q_w * dy + q_n * dx + q_s * dx
            Qout = xp.where(Qout > 0.0, Qout, 1e-12)
            frac = 0.1
            dt_local = frac * H * cell_area / Qout
            # PyTorch doesn't have nanmin, so we emulate it
            dt = float(xp.min(dt_local[~xp.isnan(dt_local)])) if xp.any(~xp.isnan(dt_local)) else 1e9
            if getattr(self.prm, 'dt_max', 0.0) and self.prm.dt_max > 0.0:
                dt = min(dt, self.prm.dt_max)
            return max(1e-6, dt)
        # Default SWE CFL
        vmax = max(1e-8, self.max_characteristic_speed())
        dx_min = min(self.grid.dx, self.grid.dy)
        dt = self.prm.cfl * dx_min / vmax
        if getattr(self.prm, 'dt_max', 0.0) and self.prm.dt_max > 0.0:
            dt = min(dt, self.prm.dt_max)
        return dt

    def rk3_step(self, dt: float):
        # For diffusive-wave FV mode, use single-step conservative update for h
        if self.mode == "dw_fv":
            # Finite-volume diffusive-wave: single-step conservative update for h
            self._dt = dt
            dh, du, dv = self.rhs(self.h, self.u, self.v)
            self.h = self.h + dt * dh
            # Optional SPU filtering (apply spectral truncation to h with mass correction)
            if self.prm.adaptive_truncation:
                # Build/update mask as needed
                h_hat = self.xp.fft.fft2(self.h)
                # Controller can adjust mfrac based on tail energy
                self.spu_update_controller(h_hat)
                h_hat = self.spu_apply_truncation(h_hat)
                h_filtered = self.xp.fft.ifft2(h_hat).real
                # Mass correction to preserve mean depth
                m_before = self.xp.mean(self.h)
                m_after = self.xp.mean(h_filtered)
                self.h = h_filtered + (m_before - m_after)
                # Positivity clamp
                self.h = self.xp.maximum(self.h, self.xp.asarray(self.prm.h_min, device=self.device))
            # Relax velocities toward diagnostic without multi-stage mixing
            self.u = self.u + dt * du
            self.v = self.v + dt * dv
        else:
            # Stage 1
            # expose dt for flux limiters in DW-FV
            self._dt = dt
            dh1, du1, dv1 = self.rhs(self.h, self.u, self.v)
            h1 = self.h + dt * dh1
            u1 = self.u + dt * du1
            v1 = self.v + dt * dv1
            # Filter & guards
            if self.mode == "swe":
                h1_hat = self.xp.fft.fft2(h1)
                h1_hat = self.spu_apply_truncation(h1_hat)
                self.spu_update_controller(h1_hat)
                h1 = self.xp.fft.ifft2(h1_hat).real
                
                u1 = self.filt.apply(self.grid, u1)
                v1 = self.filt.apply(self.grid, v1)
            # Stage 2
            dh2, du2, dv2 = self.rhs(h1, u1, v1)
            h2 = 0.75 * self.h + 0.25 * (h1 + dt * dh2)
            u2 = 0.75 * self.u + 0.25 * (u1 + dt * du2)
            v2 = 0.75 * self.v + 0.25 * (v1 + dt * dv2)
            if self.mode == "swe":
                h2_hat = self.xp.fft.fft2(h2)
                h2_hat = self.spu_apply_truncation(h2_hat)
                h2 = self.xp.fft.ifft2(h2_hat).real

                u2 = self.filt.apply(self.grid, u2)
                v2 = self.filt.apply(self.grid, v2)
            # Stage 3
            dh3, du3, dv3 = self.rhs(h2, u2, v2)
            h3 = (1.0/3.0) * self.h + (2.0/3.0) * (h2 + dt * dh3)
            u3 = (1.0/3.0) * self.u + (2.0/3.0) * (u2 + dt * du3)
            v3 = (1.0/3.0) * self.v + (2.0/3.0) * (v2 + dt * dv3)
            
            h3_hat = self.xp.fft.fft2(h3)
            h3_hat = self.spu_apply_truncation(h3_hat)
            self.h = self.xp.fft.ifft2(h3_hat).real
            self.u, self.v = u3, v3

        # Apply structures & guards
        self.apply_structures(dt)
        self.apply_guards()

    def run(self, t_end: float, output_every: float = 0.0, verbose: bool = True,
            frame_writer: Optional[Callable[[float, "HRFSolver"], None]] = None) -> Dict[str, List[Tuple[float, float]]]:
        t = 0.0
        next_out = 0.0
        logs = {"mass": [], "vmax": [], "dt": []}
        start = time.time()
        while t < t_end:
            dt = min(self.choose_dt(), t_end - t)
            if self.tide_bc:
                self.apply_tide_bc(t, dt)
            self.rk3_step(dt)
            t += dt
            self.time = t
            # Logs
            mass = self.total_mass()
            vmax = self.max_characteristic_speed()
            logs["mass"].append((t, mass))
            logs["vmax"].append((t, vmax))
            logs["dt"].append((t, dt))
            # Output hook (placeholder — users can insert writers here)
            if output_every > 0.0 and t >= next_out:
                if verbose:
                    m_err = 100.0 * (mass - self.mass0) / max(1e-12, self.mass0)
                    # Diagnostics: Froude and slope
                    xp = self.xp
                    c = xp.sqrt(self.prm.g * self.h)
                    spd = xp.sqrt(self.u*self.u + self.v*self.v)
                    fr_max = float(xp.max(spd / xp.maximum(c, asarray_backend_agnostic(xp, 1e-9, device=self.device))))
                    eta = self.h + (self.bed if self.bed is not None else 0.0)
                    deta_dx = (roll_backend_agnostic(xp, eta, -1, 0) - roll_backend_agnostic(xp, eta, 1, 0)) / (2.0 * self.grid.dx)
                    deta_dy = (roll_backend_agnostic(xp, eta, -1, 1) - roll_backend_agnostic(xp, eta, 1, 1)) / (2.0 * self.grid.dy)
                    slope_max = float(xp.max(xp.sqrt(deta_dx*deta_dx + deta_dy*deta_dy)))
                    print(f"t={t:8.2f}s  dt={dt:7.4f}s  vmax={vmax:7.3f}  Fr_max={fr_max:5.3f}  slope_max={slope_max:5.3f}  mass_err={m_err:7.4f}%")
                if frame_writer is not None:
                    try:
                        frame_writer(t, self)
                    except Exception:
                        pass
                next_out += output_every
        if verbose:
            print(f"Run finished in {time.time() - start:.2f}s (simulated {t_end:.2f}s)")
        return logs

# =====================
# Demo / test utilities
# =====================

def dam_break_1d(nx: int = 512, Lx: float = 200.0,
                  hL: float = 2.0, hR: float = 1.0, x0: float = 100.0,
                  t_end: float = 10.0) -> HRFSolver:
    grid = Grid(nx=nx, ny=1, Lx=Lx, Ly=1.0)
    prm = SWEParams(g=9.81, manning_n=0.0, h_min=1e-5, cfl=0.30, vmax_guard_coef=1.5)
    filt = ExponentialFilter(alpha=36.0, p=8)
    solver = HRFSolver(grid, prm, filt)
    h0 = np.where(to_numpy(grid.X[:, 0]) < x0, hL, hR).reshape(nx, 1)
    u0 = np.zeros_like(h0)
    v0 = np.zeros_like(h0)
    solver.initialize(h0, u0, v0)
    return solver


def dam_break_2d(nx: int = 256, ny: int = 256, Lx: float = 200.0, Ly: float = 200.0,
                  h_in: float = 2.0, h_out: float = 1.0, r0: float = 25.0,
                  t_end: float = 10.0) -> HRFSolver:
    grid = Grid(nx=nx, ny=ny, Lx=Lx, Ly=Ly)
    prm = SWEParams(g=9.81, manning_n=0.0, h_min=1e-5, cfl=0.30, vmax_guard_coef=1.5)
    filt = ExponentialFilter(alpha=36.0, p=8)
    solver = HRFSolver(grid, prm, filt)
    cx, cy = 0.5 * Lx, 0.5 * Ly
    R = np.sqrt((to_numpy(grid.X) - cx) ** 2 + (to_numpy(grid.Y) - cy) ** 2)
    h0 = np.where(R <= r0, h_in, h_out)
    u0 = np.zeros_like(h0)
    v0 = np.zeros_like(h0)
    solver.initialize(h0, u0, v0)
    return solver


def dwfv_ramp_1d(nx: int = 200, Lx: float = 2000.0, slope: float = 1e-3,
                 h0_level: float = 0.1) -> HRFSolver:
    # 1D strip as (nx,1) with linear bed slope and shallow initial water
    grid = Grid(nx=nx, ny=1, Lx=Lx, Ly=1.0)
    prm = SWEParams(g=9.81, manning_n=0.04, h_min=1e-3, cfl=0.15, vmax_guard_coef=1.0, dt_max=0.5)
    filt = ExponentialFilter(alpha=36.0, p=8)
    solver = HRFSolver(grid, prm, filt)
    # Bed z = slope * x (decreasing to the right)
    z = (slope * (to_numpy(grid.X[:, 0]) - to_numpy(grid.X[0, 0]))).reshape(nx, 1)
    h0 = np.full((nx, 1), h0_level, dtype=float)
    u0 = np.zeros_like(h0)
    v0 = np.zeros_like(h0)
    solver.initialize(h0, u0, v0)
    solver.set_forcing(bed=z, rain_rate=0.0, infil_rate=0.0)
    solver.mode = "dw_fv"
    return solver

# -----------------------------
# Pilot tile sketch (customize)
# -----------------------------

def make_pilot_tile(nx: int = 400, ny: int = 400,
                    Lx: float = 2000.0, Ly: float = 2000.0,
                    tide_amp: float = 0.3, tide_mean: float = 1.2,
                    tide_T: float = 6 * 3600.0) -> HRFSolver:
    grid = Grid(nx=nx, ny=ny, Lx=Lx, Ly=Ly)
    prm = SWEParams(g=9.81, manning_n=0.025, h_min=5e-4, cfl=0.30,
                    vmax_guard_coef=1.5, sponge_width=8, sponge_tau=120.0)
    filt = ExponentialFilter(alpha=36.0, p=8)
    solver = HRFSolver(grid, prm, filt)

    # Flat initial water surface
    h0 = np.full((nx, ny), tide_mean)
    u0 = np.zeros_like(h0)
    v0 = np.zeros_like(h0)
    solver.initialize(h0, u0, v0)

    # Simple tidal boundary on the west edge
    def eta_func(t: float) -> float:
        return tide_mean + tide_amp * math.sin(2 * math.pi * t / tide_T)
    solver.tide_bc = {"edge": "west", "eta_func": eta_func}

    # Example structures — a weir line through the middle
    faces = [FaceIndex(i=nx//2, j=j, dir='x') for j in range(0, ny, 2)]
    solver.structures["weirs"].append(Weir(faces=faces, Cd=1.6, crest_elev=tide_mean + 0.2,
                                           width_per_face=grid.dy))

    # A culvert row near the south
    faces_c = [FaceIndex(i=i, j=ny//4, dir='y') for i in range(0, nx, 4)]
    solver.structures["culverts"].append(Culvert(faces=faces_c, area=1.0, C0=0.62, Cf=0.62,
                                                  invert_up=tide_mean - 0.1, invert_dn=tide_mean - 0.1))
    return solver

# ========
# __main__
# ========

if __name__ == "__main__":
    # Example: run a quick 1D dam-break sanity
    s = dam_break_1d(nx=512, Lx=200.0, hL=2.0, hR=1.0, x0=100.0, t_end=10.0)
    logs = s.run(t_end=10.0, output_every=0.5, verbose=True)
    # Print simple diagnostics
    mass_err = 100.0 * (s.total_mass() - s.mass0) / max(1e-12, s.mass0)
    print(f"Final mass error: {mass_err:.4f}% ; Max char speed: {s.max_characteristic_speed():.3f} m/s")

    # Export final 1D profile (CSV and optional PNG)
    if s.grid.ny == 1:
        output_dir = os.path.join("runs", "dam_break_1d")
        os.makedirs(output_dir, exist_ok=True)
        x = to_numpy(s.grid.X[:, 0])
        h = to_numpy(s.h[:, 0])
        u = to_numpy(s.u[:, 0])
        csv_path = os.path.join(output_dir, "final_profile.csv")
        np.savetxt(csv_path, np.column_stack([x, h, u]), delimiter=",", header="x,h,u", comments="")
        try:
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(7, 3))
            ax.plot(x, h, label="h (m)")
            ax.set_xlabel("x (m)")
            ax.set_ylabel("Depth (m)")
            ax.set_title("1D Dam-break: Final Profile")
            ax.grid(True, alpha=0.3)
            ax.legend()
            png_path = os.path.join(output_dir, "final_profile.png")
            fig.tight_layout()
            fig.savefig(png_path, dpi=150)
            plt.close(fig)
        except Exception:
            pass

    # 2D radial dam-break (small grid) with NPZ/PNG export
    s2 = dam_break_2d(nx=128, ny=128, t_end=6.0)
    frames_dir = os.path.join("runs", "dam_break_2d", "frames")
    os.makedirs(frames_dir, exist_ok=True)
    def write_frame(t_cur: float, solver: HRFSolver) -> None:
        try:
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(5, 4))
            im = ax.imshow(to_numpy(solver.h).T, origin="lower", cmap="viridis",
                           extent=[0, solver.grid.Lx, 0, solver.grid.Ly], aspect="auto")
            ax.set_title(f"h at t={t_cur:.2f}s")
            ax.set_xlabel("x (m)")
            ax.set_ylabel("y (m)")
            fig.colorbar(im, ax=ax, label="h (m)")
            fig.tight_layout()
            fname = os.path.join(frames_dir, f"frame_{int(round(t_cur*100)):05d}.png")
            fig.savefig(fname, dpi=130)
            plt.close(fig)
        except Exception:
            pass
    s2.run(t_end=6.0, output_every=0.5, verbose=False, frame_writer=write_frame)
    out2d = os.path.join("runs", "dam_break_2d")
    os.makedirs(out2d, exist_ok=True)
    np.savez(os.path.join(out2d, "final_snapshot.npz"),
             X=to_numpy(s2.grid.X), Y=to_numpy(s2.grid.Y), h=to_numpy(s2.h), u=to_numpy(s2.u), v=to_numpy(s2.v))
    try:
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(5, 4))
        im = ax.imshow(to_numpy(s2.h).T, origin="lower", cmap="viridis",
                       extent=[0, s2.grid.Lx, 0, s2.grid.Ly], aspect="auto")
        ax.set_title("2D Dam-break: Final h")
        ax.set_xlabel("x (m)")
        ax.set_ylabel("y (m)")
        fig.colorbar(im, ax=ax, label="h (m)")
        fig.tight_layout()
        plt_path = os.path.join(out2d, "final_h.png")
        fig.savefig(plt_path, dpi=150)
        plt.close(fig)
    except Exception:
        pass
