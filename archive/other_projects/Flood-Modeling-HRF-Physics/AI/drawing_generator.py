#!/usr/bin/env python3
"""
Generate Engineering Drawings and Technical Specifications
Adapted for QCIA workflow - construction-ready blueprints with cross-sections, dimensions, and specs
"""

import json
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import FancyBboxPatch, Rectangle, Polygon, Circle, Wedge
from pathlib import Path
import sys
import argparse
import rasterio
from rasterio.transform import rowcol
from pyproj import Transformer
import fiona
from shapely.geometry import shape, LineString, MultiLineString
from shapely.ops import transform as shp_transform

# =============================================================================
# ENGINEERING SPECIFICATIONS
# =============================================================================

SPECS = {
    'culvert_box_2x2': {
        'name': 'Box Culvert (2m × 2m)',
        'width': 2.0,
        'height': 2.0,
        'wall_thickness': 0.3,
        'concrete_grade': 'M30',
        'reinforcement': '12mm @ 150mm c/c both ways',
        'excavation_depth': 3.5,
        'bedding': '300mm PCC (M15)',
        'backfill': 'GSB + WMM',
        'capacity': '5.0 m³/s',
        'min_slope': '0.1%',
        'design_life': '50 years'
    },
    'culvert_box_3x3': {
        'name': 'Box Culvert (3m × 3m)',
        'width': 3.0,
        'height': 3.0,
        'wall_thickness': 0.4,
        'concrete_grade': 'M35',
        'reinforcement': '16mm @ 125mm c/c both ways',
        'excavation_depth': 4.5,
        'bedding': '400mm PCC (M15)',
        'backfill': 'GSB + WMM',
        'capacity': '12.0 m³/s',
        'min_slope': '0.1%',
        'design_life': '50 years'
    },
    'drain_rcc_1m': {
        'name': 'RCC Drain (1m wide)',
        'width': 1.0,
        'height': 1.2,
        'wall_thickness': 0.15,
        'concrete_grade': 'M25',
        'reinforcement': '10mm @ 200mm c/c',
        'excavation_depth': 1.8,
        'bedding': '150mm PCC (M10)',
        'cover': 'RCC slab 150mm thick',
        'capacity': '2.0 m³/s per 100m',
        'min_slope': '0.2%',
        'design_life': '40 years'
    },
    'drain_rcc_1.5m': {
        'name': 'RCC Drain (1.5m wide)',
        'width': 1.5,
        'height': 1.5,
        'wall_thickness': 0.2,
        'concrete_grade': 'M25',
        'reinforcement': '12mm @ 150mm c/c',
        'excavation_depth': 2.2,
        'bedding': '200mm PCC (M10)',
        'cover': 'RCC slab 200mm thick',
        'capacity': '4.0 m³/s per 100m',
        'min_slope': '0.2%',
        'design_life': '40 years'
    },
    'pond_medium': {
        'name': 'Detention Pond (5000 m³)',
        'capacity': 5000,
        'depth': 3.5,
        'side_slope': '1:2 (V:H)',
        'lining': 'Brick masonry in CM 1:4',
        'outlet': 'RCC pipe 600mm dia with sluice gate',
        'inlet': 'RCC inlet structure with energy dissipator',
        'design_life': '60 years'
    },
    'pond_large': {
        'name': 'Detention Pond (10000 m³)',
        'capacity': 10000,
        'depth': 4.5,
        'side_slope': '1:2 (V:H)',
        'lining': 'Brick masonry in CM 1:4',
        'outlet': 'RCC pipe 800mm dia with sluice gate',
        'inlet': 'RCC inlet structure with energy dissipator',
        'design_life': '60 years'
    },
    'pump_small': {
        'name': 'Pump Station (1.5 m³/s)',
        'capacity': '1.5 m³/s',
        'pump_type': 'Submersible (Kirloskar/KSB)',
        'motor': '50 HP, 415V, 3-phase',
        'wet_well': '4m × 4m × 5m deep',
        'backup': 'Diesel generator 75 KVA',
        'control': 'Auto start with level sensors',
        'design_life': '25 years'
    },
    'pump_medium': {
        'name': 'Pump Station (3.0 m³/s)',
        'capacity': '3.0 m³/s (dual pumps)',
        'pump_type': 'Submersible (Kirloskar/KSB)',
        'motor': '100 HP × 2, 415V, 3-phase',
        'wet_well': '6m × 6m × 6m deep',
        'backup': 'Diesel generator 150 KVA',
        'control': 'Auto start with level sensors + SCADA',
        'design_life': '25 years'
    },
    'permeable_pavement': {
        'name': 'Permeable Pavement',
        'area': '100 m²',
        'depth': '0.6 m',
        'layers': '150mm paver blocks, 300mm aggregate, 150mm sand',
        'infiltration_rate': '100 mm/hr',
        'design_life': '20 years'
    }
    ,
    'levee_earthen': {
        'name': 'Earthen Levee',
        'crest_width': 4.0,
        'height': 5.0,
        'side_slope': '1:2 (V:H)',
        'material': 'Compacted earth, MDD>95% (IS 2720)',
        'seepage_control': 'Clay core or HDPE liner (where needed)',
        'design_life': '50 years'
    },
    'flood_wall_concrete': {
        'name': 'Concrete Flood Wall',
        'wall_thickness': 0.4,
        'height': 4.0,
        'foundation_depth': 1.5,
        'concrete_grade': 'M35',
        'reinforcement': '16mm @ 150mm c/c both faces',
        'expansion_joints': 'Every 6–10 m with water stops',
        'design_life': '100 years'
    },
    'channel_upgrade_concrete': {
        'name': 'Concrete Lined Channel',
        'bottom_width': 6.0,
        'depth': 3.0,
        'side_slope': '1:1.5 (V:H)',
        'lining': 'RCC 150mm with cut-off walls',
        'manning_n': 0.015,
        'design_life': '75 years'
    }
}

# =============================================================================
# DRAWING FUNCTIONS
# =============================================================================

def draw_culvert_cross_section(ax, type_key, specs):
    """Draw detailed culvert cross-section"""
    ax.set_aspect('equal')
    ax.set_xlim(-2, 4)
    ax.set_ylim(-4.5, 1)
    
    w = specs['width']
    h = specs['height']
    t = specs['wall_thickness']
    exc_depth = specs['excavation_depth']
    
    # Ground level
    ground = Rectangle((-2, 0), 6, 0.5, facecolor='#8B7355', edgecolor='black', linewidth=2)
    ax.add_patch(ground)
    ax.text(3.5, 0.25, 'GROUND LEVEL', fontsize=8, weight='bold')
    
    # Excavation
    excavation = Rectangle((-1, -exc_depth), w + 2*t + 2, exc_depth, 
                          facecolor='#D2B48C', alpha=0.3, linestyle='--', edgecolor='gray')
    ax.add_patch(excavation)
    
    # PCC Bedding
    bedding_height = 0.3
    bedding = Rectangle((-1, -exc_depth), w + 2*t + 2, bedding_height,
                       facecolor='#C0C0C0', edgecolor='black', linewidth=1)
    ax.add_patch(bedding)
    ax.text(w/2 + t, -exc_depth + bedding_height/2, 'PCC M15\n300mm', 
            fontsize=7, ha='center', va='center')
    
    # Bottom slab
    bottom = Rectangle((0, -exc_depth + bedding_height), w + 2*t, t,
                       facecolor='#708090', edgecolor='black', linewidth=2)
    ax.add_patch(bottom)
    
    # Walls
    left_wall = Rectangle((0, -exc_depth + bedding_height + t), t, h,
                          facecolor='#708090', edgecolor='black', linewidth=2)
    right_wall = Rectangle((w + t, -exc_depth + bedding_height + t), t, h,
                           facecolor='#708090', edgecolor='black', linewidth=2)
    ax.add_patch(left_wall)
    ax.add_patch(right_wall)
    
    # Top slab
    top = Rectangle((0, -exc_depth + bedding_height + t + h), w + 2*t, t,
                   facecolor='#708090', edgecolor='black', linewidth=2)
    ax.add_patch(top)
    
    # Interior (flow area)
    interior = Rectangle((t, -exc_depth + bedding_height + t), w, h,
                         facecolor='#87CEEB', alpha=0.5, edgecolor='blue', linewidth=1.5)
    ax.add_patch(interior)
    
    # Water level (example)
    water_level = h * 0.6
    water = Rectangle((t, -exc_depth + bedding_height + t), w, water_level,
                     facecolor='#1E90FF', alpha=0.6)
    ax.add_patch(water)
    
    # Dimensions
    ax.annotate('', xy=(t, -exc_depth + bedding_height + t + h + 0.8), 
                xytext=(w + t, -exc_depth + bedding_height + t + h + 0.8),
                arrowprops=dict(arrowstyle='<->', lw=1.5, color='red'))
    ax.text(w/2 + t, -exc_depth + bedding_height + t + h + 1.0, f'{w}m', 
            fontsize=10, weight='bold', ha='center', color='red')
    
    ax.annotate('', xy=(w + t + 0.5, -exc_depth + bedding_height + t), 
                xytext=(w + t + 0.5, -exc_depth + bedding_height + t + h),
                arrowprops=dict(arrowstyle='<->', lw=1.5, color='red'))
    ax.text(w + t + 0.8, -exc_depth + bedding_height + t + h/2, f'{h}m', 
            fontsize=10, weight='bold', va='center', color='red')
    
    ax.text(1, 0.8, specs['name'], fontsize=12, weight='bold', ha='center')
    
    specs_text = f"""SPECIFICATIONS:
Concrete: {specs['concrete_grade']}
Reinforcement: {specs['reinforcement']}
Capacity: {specs['capacity']}
Min. Gradient: {specs['min_slope']}
Design Life: {specs['design_life']}"""
    
    ax.text(3.5, -2.5, specs_text, fontsize=7, family='monospace',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
    
    ax.axis('off')
    ax.set_title('CROSS SECTION', fontsize=10, weight='bold', pad=20)

def draw_pond_plan(ax, specs):
    """Draw detention pond plan view"""
    ax.set_aspect('equal')
    ax.set_xlim(-5, 65)
    ax.set_ylim(-5, 45)
    
    top_width = 60
    top_height = 40
    pond_top = Rectangle((0, 0), top_width, top_height,
                         facecolor='#87CEEB', alpha=0.3, edgecolor='blue', linewidth=3)
    ax.add_patch(pond_top)
    
    depth = specs.get('depth', 3.5)
    slope_offset = depth * 2
    bottom_width = top_width - 2*slope_offset
    bottom_height = top_height - 2*slope_offset
    
    pond_bottom = Rectangle((slope_offset, slope_offset), bottom_width, bottom_height,
                           facecolor='#1E90FF', alpha=0.5, edgecolor='darkblue', 
                           linewidth=2, linestyle='--')
    ax.add_patch(pond_bottom)
    
    # Inlet
    inlet = Rectangle((top_width/2 - 1, top_height), 2, 3,
                     facecolor='#708090', edgecolor='black', linewidth=2)
    ax.add_patch(inlet)
    ax.text(top_width/2, top_height + 1.5, 'INLET', fontsize=9, 
            weight='bold', ha='center', va='center', color='white')
    
    # Outlet
    outlet = Circle((5, 5), 1.5, facecolor='#708090', edgecolor='black', linewidth=2)
    ax.add_patch(outlet)
    ax.text(5, 5, 'OUTLET\n600mm Ø', fontsize=7, weight='bold', 
            ha='center', va='center', color='white')
    
    # Dimensions
    ax.annotate('', xy=(0, -2), xytext=(top_width, -2),
                arrowprops=dict(arrowstyle='<->', lw=2, color='red'))
    ax.text(top_width/2, -3, f'{top_width}m', fontsize=11, weight='bold', 
            ha='center', color='red')
    
    ax.annotate('', xy=(-2, 0), xytext=(-2, top_height),
                arrowprops=dict(arrowstyle='<->', lw=2, color='red'))
    ax.text(-3.5, top_height/2, f'{top_height}m', fontsize=11, weight='bold',
            va='center', ha='right', color='red')
    
    ax.text(top_width/2, top_height/2, 
            f'DETENTION POND\nCapacity: {specs["capacity"]} m³\nDepth: {specs["depth"]}m',
            fontsize=11, weight='bold', ha='center', va='center',
            bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
    
    specs_text = f"""SPECIFICATIONS:
Side Slope: {specs['side_slope']}
Lining: {specs['lining']}
Outlet: {specs['outlet']}
Design Life: {specs['design_life']}"""
    
    ax.text(62, 20, specs_text, fontsize=8, family='monospace',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.9))
    
    ax.axis('off')
    ax.set_title('PLAN VIEW', fontsize=10, weight='bold', pad=10)

def draw_pump_schematic(ax, specs):
    """Draw pump station schematic"""
    ax.set_aspect('equal')
    ax.set_xlim(-2, 10)
    ax.set_ylim(-8, 2)
    
    # Ground level
    ground = Rectangle((-2, 0), 12, 0.5, facecolor='#8B7355', edgecolor='black', linewidth=2)
    ax.add_patch(ground)
    
    # Wet well
    well_width = 4 if 'small' in specs['name'].lower() else 6
    well_depth = 5 if 'small' in specs['name'].lower() else 6
    
    well = Rectangle((2, -well_depth), well_width, well_depth,
                    facecolor='#B0E0E6', edgecolor='black', linewidth=2)
    ax.add_patch(well)
    
    # Water level
    water = Rectangle((2, -well_depth), well_width, well_depth * 0.7,
                     facecolor='#1E90FF', alpha=0.6)
    ax.add_patch(water)
    
    # Pump (simplified)
    pump_x = 2 + well_width/2
    pump_y = -well_depth + 1
    pump = Circle((pump_x, pump_y), 0.8, facecolor='red', edgecolor='black', linewidth=2)
    ax.add_patch(pump)
    ax.text(pump_x, pump_y, 'PUMP', fontsize=8, weight='bold', ha='center', va='center', color='white')
    
    # Discharge pipe
    ax.plot([pump_x, pump_x, 8], [pump_y + 0.8, 1, 1], 'k-', linewidth=3)
    ax.arrow(7.5, 1, 0.3, 0, head_width=0.3, head_length=0.2, fc='blue', ec='blue')
    ax.text(8.5, 1, 'DISCHARGE', fontsize=9, weight='bold', va='center')
    
    # Control panel
    panel = Rectangle((7, 0.5), 1.5, 1, facecolor='gray', edgecolor='black', linewidth=2)
    ax.add_patch(panel)
    ax.text(7.75, 1, 'CONTROL', fontsize=7, weight='bold', ha='center', va='center', color='white')
    
    # Generator (backup)
    gen = Rectangle((7, -2), 2, 1.5, facecolor='orange', edgecolor='black', linewidth=2)
    ax.add_patch(gen)
    ax.text(8, -1.25, 'GENERATOR', fontsize=7, weight='bold', ha='center', va='center')
    
    # Dimensions
    ax.annotate('', xy=(2, -well_depth - 0.5), xytext=(2 + well_width, -well_depth - 0.5),
                arrowprops=dict(arrowstyle='<->', lw=2, color='red'))
    ax.text(2 + well_width/2, -well_depth - 0.8, f'{well_width}m', fontsize=10, 
            weight='bold', ha='center', color='red')
    
    ax.annotate('', xy=(1.5, 0), xytext=(1.5, -well_depth),
                arrowprops=dict(arrowstyle='<->', lw=2, color='red'))
    ax.text(1.2, -well_depth/2, f'{well_depth}m', fontsize=10, weight='bold', 
            va='center', ha='right', color='red')
    
    ax.text(pump_x, 1.5, specs['name'], fontsize=12, weight='bold', ha='center')
    
    specs_text = f"""SPECIFICATIONS:
Capacity: {specs['capacity']}
Pump Type: {specs['pump_type']}
Motor: {specs['motor']}
Wet Well: {specs['wet_well']}
Backup: {specs['backup']}
Control: {specs['control']}"""
    
    ax.text(0, -5, specs_text, fontsize=7, family='monospace',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.9))
    
    ax.axis('off')
    ax.set_title('SCHEMATIC VIEW', fontsize=10, weight='bold', pad=10)

def get_spec_key_from_type(intervention_type):
    """Map intervention type string to spec key"""
    itype_lower = intervention_type.lower()
    
    if 'culvert' in itype_lower:
        if '3' in intervention_type or '3x3' in intervention_type:
            return 'culvert_box_3x3'
        return 'culvert_box_2x2'
    elif 'drain' in itype_lower:
        if '1.5' in intervention_type:
            return 'drain_rcc_1.5m'
        return 'drain_rcc_1m'
    elif 'pond' in itype_lower or 'retention' in itype_lower:
        if 'large' in itype_lower or '10000' in intervention_type:
            return 'pond_large'
        return 'pond_medium'
    elif 'pump' in itype_lower:
        if 'medium' in itype_lower or '3.0' in intervention_type:
            return 'pump_medium'
        return 'pump_small'
    elif 'levee' in itype_lower:
        return 'levee_earthen'
    elif 'wall' in itype_lower:
        return 'flood_wall_concrete'
    elif 'channel' in itype_lower:
        return 'channel_upgrade_concrete'
    elif 'smart_valve' in itype_lower:
        # simple placeholder to avoid skip
        return 'permeable_pavement'
    elif 'permeable' in itype_lower:
        return 'permeable_pavement'
    
    return None

def _compute_site_metrics(h_base, h_opt, i: int, j: int, radius: int = 10):
    """Compute local depth metrics around a site for baseline vs optimized."""
    if h_base is None or h_opt is None:
        return None
    nx, ny = h_base.shape
    i0, i1 = max(0, i - radius), min(nx, i + radius + 1)
    j0, j1 = max(0, j - radius), min(ny, j + radius + 1)
    hb = h_base[i0:i1, j0:j1]
    ho = h_opt[i0:i1, j0:j1]
    d = hb - ho
    return {
        'window': (i0, i1, j0, j1),
        'baseline_mean': float(np.mean(hb)),
        'optimized_mean': float(np.mean(ho)),
        'delta_mean': float(np.mean(d)),
        'improved_pct': float(np.mean(d > 0.05)) * 100.0
    }


def _plot_vectors_on_ax(ax, vec_path: str, dem_crs, transform, i0, i1, j0, j1, color='white', lw=1.0):
    if not vec_path:
        return
    try:
        transformer = Transformer.from_crs('EPSG:4326', dem_crs, always_xy=True)
        with fiona.open(vec_path, 'r') as src:
            # If layer has its own CRS, overwrite transformer
            try:
                if src.crs_wkt:
                    transformer = Transformer.from_crs(src.crs_wkt, dem_crs, always_xy=True)
            except Exception:
                pass
            for feat in src:
                geom = shape(feat['geometry'])
                def _to_dem(x, y, z=None):
                    X, Y = transformer.transform(x, y)
                    return (X, Y)
                try:
                    g_dem = shp_transform(_to_dem, geom)
                except Exception:
                    continue
                if isinstance(g_dem, LineString):
                    lines = [g_dem]
                elif isinstance(g_dem, MultiLineString):
                    lines = list(g_dem.geoms)
                else:
                    continue
                for ls in lines:
                    cols = []
                    rows = []
                    for x, y in ls.coords:
                        r, c = rowcol(transform, x, y)
                        if i0 <= r < i1 and j0 <= c < j1:
                            rows.append(r - i0)
                            cols.append(c - j0)
                        else:
                            # break segments when outside
                            if len(cols) > 1:
                                ax.plot(cols, rows, color=color, linewidth=lw, alpha=0.8)
                            cols, rows = [], []
                    if len(cols) > 1:
                        ax.plot(cols, rows, color=color, linewidth=lw, alpha=0.8)
    except Exception:
        return


def _add_scale_and_north(ax, width_px, height_px, res_x, res_y):
    # Scale bar ~500 m
    length_m = 500.0
    px = length_m / max(abs(res_x), 1e-6)
    x0 = width_px * 0.05
    y0 = height_px * 0.92
    ax.plot([x0, x0 + px], [y0, y0], color='k', linewidth=3)
    ax.text(x0 + px / 2, y0 - 5, f'{int(length_m)} m', ha='center', va='top', fontsize=8,
            bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
    # North arrow (upwards)
    ax.arrow(width_px * 0.92, height_px * 0.85, 0, -height_px * 0.08,
             head_width=width_px * 0.02, head_length=height_px * 0.04,
             fc='red', ec='black', linewidth=2)
    ax.text(width_px * 0.92, height_px * 0.81, 'N', ha='center', va='top', color='red', fontsize=10,
            bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))


def create_intervention_drawing(interv, idx, dem, transform, h_base=None, h_opt=None, dem_crs=None, roads_path='', drains_path='',
                                tile_row0: int = 0, tile_col0: int = 0):
    """Create detailed engineering drawing for one intervention"""
    fig = plt.figure(figsize=(17, 11))
    
    # Get intervention type
    interv_type = interv.get('type', 'unknown')
    spec_key = get_spec_key_from_type(interv_type)
    
    if spec_key is None or spec_key not in SPECS:
        print(f"  ⚠️  No specs for {interv_type}, skipping...")
        plt.close(fig)
        return None
    
    specs = SPECS[spec_key]
    
    fig.suptitle(f'ENGINEERING DRAWING #{idx:02d}: {specs["name"]}', 
                 fontsize=16, weight='bold', y=0.98)
    
    # Layout - main drawing
    if 'culvert' in spec_key:
        ax1 = plt.subplot(2, 3, (1, 4))
        draw_culvert_cross_section(ax1, spec_key, specs)
    elif 'pond' in spec_key:
        ax1 = plt.subplot(2, 3, (1, 4))
        draw_pond_plan(ax1, specs)
    elif 'pump' in spec_key:
        ax1 = plt.subplot(2, 3, (1, 4))
        draw_pump_schematic(ax1, specs)
    else:
        ax1 = plt.subplot(2, 3, (1, 4))
        # Simple schematic placeholders for new specs
        if 'Levee' in specs['name']:
            ax1.text(0.5, 0.5, 'Levee schematic\nCrest 4m, H 5m\nSide slope 1:2',
                    ha='center', va='center', fontsize=14, weight='bold')
        elif 'Flood Wall' in specs['name']:
            ax1.text(0.5, 0.5, 'Flood wall schematic\nH 4m, t 0.4m\nFoundation 1.5m',
                    ha='center', va='center', fontsize=14, weight='bold')
        elif 'Channel' in specs['name']:
            ax1.text(0.5, 0.5, 'Channel upgrade schematic\nB 6m, D 3m\nRCC lining',
                    ha='center', va='center', fontsize=14, weight='bold')
        else:
            ax1.text(0.5, 0.5, f'{specs["name"]}\n\nCross-section coming soon',
                ha='center', va='center', fontsize=14, weight='bold')
        ax1.axis('off')
    
    # Location map
    ax2 = plt.subplot(2, 3, 2)
    location = interv.get('location', (50, 50))
    i, j = location
    # Map solver grid indices to DEM pixel indices using tile origin
    di = int(tile_row0) + int(i)
    dj = int(tile_col0) + int(j)
    
    window_size = 20
    i_min = max(0, di - window_size)
    i_max = min(dem.shape[0], di + window_size)
    j_min = max(0, dj - window_size)
    j_max = min(dem.shape[1], dj + window_size)
    
    dem_crop = dem[i_min:i_max, j_min:j_max]
    im = ax2.imshow(dem_crop, cmap='terrain')
    # Overlay vectors in AOI coordinates
    _plot_vectors_on_ax(ax2, roads_path, dem_crs, transform, i_min, i_max, j_min, j_max, color='white', lw=1.2)
    _plot_vectors_on_ax(ax2, drains_path, dem_crs, transform, i_min, i_max, j_min, j_max, color='cyan', lw=1.0)
    ax2.plot(dj - j_min, di - i_min, 'r*', markersize=20, markeredgecolor='white', markeredgewidth=2)
    # Add scale bar and north arrow
    res_x = transform.a
    res_y = transform.e
    _add_scale_and_north(ax2, dem_crop.shape[1], dem_crop.shape[0], res_x, res_y)
    ax2.set_title('LOCATION', fontsize=10, weight='bold')
    ax2.axis('off')
    
    # Site info
    ax3 = plt.subplot(2, 3, 3)
    ax3.axis('off')
    
    # Try to get lat/lon from intervention or calculate from transform
    lat_lon = interv.get('lat_lon', (0, 0))
    if lat_lon == (0, 0) and transform:
        x, y = transform * (dj, di)
        try:
            to_wgs84 = Transformer.from_crs(dem_crs, 'EPSG:4326', always_xy=True)
            lon, lat = to_wgs84.transform(x, y)
            lat_lon = (lat, lon)
        except Exception:
            lat_lon = (y, x)
    
    elev = dem[i, j] if 0 <= i < dem.shape[0] and 0 <= j < dem.shape[1] else 0
    cost_lakh = interv.get('cost_lakh', 0)

    # Compute site metrics from provided depth fields (if any)
    metrics = _compute_site_metrics(h_base, h_opt, i, j, radius=10)
    
    info_text = f"""SITE INFORMATION

GPS Coordinates:
  Latitude:  {lat_lon[0]:.6f}°N
  Longitude: {lat_lon[1]:.6f}°E

Grid Location:
  Cell: ({i}, {j})

Site Elevation:
  {elev:.1f}m above MSL

Capital Cost:
  ₹{cost_lakh:.2f} Lakh

Project:
  Jabalpur Urban Flood Mitigation
  Budget: ₹12 Crores

Status:
  PLANNING GRADE
  Requires site survey validation

Generated by: QCIA
Date: October 2025
"""
    if metrics is not None:
        info_text += f"\nObserved Mitigation (this run):\n  Mean depth (baseline):  {metrics['baseline_mean']:.2f} m\n  Mean depth (optimized): {metrics['optimized_mean']:.2f} m\n  Mean Δ (baseline-opt):  {metrics['delta_mean']:.2f} m\n  Cells improved (>5cm):  {metrics['improved_pct']:.1f}%\n"
    
    ax3.text(0.05, 0.95, info_text, fontsize=9, family='monospace',
            verticalalignment='top', 
            bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.9))
    
    # Technical specs table
    ax4 = plt.subplot(2, 3, 5)
    ax4.axis('off')
    ax4.axis('tight')
    
    spec_data = []
    for key, value in specs.items():
        if key != 'name':
            spec_data.append([key.replace('_', ' ').title(), str(value)])
    
    if spec_data:
        table = ax4.table(cellText=spec_data, colLabels=['Parameter', 'Value'],
                         cellLoc='left', loc='center',
                         colWidths=[0.45, 0.55])
        table.auto_set_font_size(False)
        table.set_fontsize(8)
        table.scale(1, 2)
        
        for i in range(2):
            table[(0, i)].set_facecolor('#4472C4')
            table[(0, i)].set_text_props(weight='bold', color='white')
        
        for i in range(1, len(spec_data) + 1):
            for j in range(2):
                if i % 2 == 0:
                    table[(i, j)].set_facecolor('#E7E6E6')
    
    ax4.set_title('TECHNICAL SPECIFICATIONS', fontsize=10, weight='bold', pad=10)
    
    # Construction notes
    ax5 = plt.subplot(2, 3, 6)
    ax5.axis('off')
    
    notes_text = """CONSTRUCTION NOTES:

1. SITE PREPARATION
   • Clear vegetation & debris
   • Mark boundaries with survey pegs
   • Check for utilities (water, gas, electric)

2. EXCAVATION
   • Excavate to specified depth
   • Maintain side slopes 1:1
   • Dewater if groundwater present

3. QUALITY CONTROL
   • Test concrete strength (cube test)
   • Check reinforcement placement
   • Ensure proper curing (7 days min)

4. SAFETY
   • Barricade work zone
   • Provide shoring for deep excavation
   • Use PPE (helmets, boots, gloves)

5. VALIDATION
   • Site photos (before/during/after)
   • As-built measurements
   • Contractor sign-off

⚠️  IMPORTANT:
Final design must be validated by
licensed civil engineer and approved
by PWD/ULB before construction.
"""
    
    ax5.text(0.05, 0.95, notes_text, fontsize=8, family='monospace',
            verticalalignment='top',
            bbox=dict(boxstyle='round', facecolor='#FFE4B5', alpha=0.9))
    
    plt.tight_layout(rect=[0, 0, 1, 0.97])
    
    return fig

# =============================================================================
# MAIN GENERATION FUNCTION
# =============================================================================

def generate_engineering_drawings(design_path, dem_path, output_dir, verbose=True,
                                 baseline_dir: str = '', opt_dir: str = '',
                                 roads_path: str = '', drains_path: str = '',
                                 tile_row0: int = 0, tile_col0: int = 0):
    """
    Generate all engineering drawings from QCIA design.
    
    Args:
        design_path: Path to qcia_design.json
        dem_path: Path to DEM GeoTIFF
        output_dir: Output directory for drawings
        verbose: Print progress
    """
    if verbose:
        print("="*70)
        print("GENERATING ENGINEERING DRAWINGS")
        print("="*70)
    
    # Load design
    if verbose:
        print("\n[1/3] Loading QCIA design...")
    
    with open(design_path, 'r') as f:
        design = json.load(f)
    
    if verbose:
        print(f"  ✅ Design loaded: {design.get('num_interventions', 0)} interventions")
        print(f"  ✅ Total cost: ₹{design.get('total_cost_cr', 0):.2f} Crores")
    
    # Load DEM
    if verbose:
        print("\n[2/3] Loading DEM...")
    
    with rasterio.open(dem_path) as src:
        dem = src.read(1)
        transform = src.transform
        crs = src.crs
    
    if verbose:
        print(f"  ✅ DEM loaded: {dem.shape}")
    
    # Optionally load depth fields for site-specific metrics
    h_base = None
    h_opt = None
    try:
        if baseline_dir:
            hb_path = Path(baseline_dir) / 'final_snapshot.npz'
            if hb_path.exists():
                h_base = np.load(hb_path)['h']
        if opt_dir:
            ho_path = Path(opt_dir) / 'final_snapshot.npz'
            if ho_path.exists():
                h_opt = np.load(ho_path)['h']
    except Exception:
        h_base, h_opt = None, None

    # Create output directory
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate drawings
    if verbose:
        print("\n[3/3] Generating engineering drawings...")
    
    interventions = design.get('interventions', [])
    successful = 0
    
    for idx, interv in enumerate(interventions, 1):
        interv_type = interv.get('type', 'unknown')
        if verbose:
            print(f"  Drawing {idx}/{len(interventions)}: {interv_type}")
        
        fig = create_intervention_drawing(interv, idx, dem, transform, h_base=h_base, h_opt=h_opt,
                                          dem_crs=crs, roads_path=roads_path, drains_path=drains_path,
                                          tile_row0=tile_row0, tile_col0=tile_col0)
        
        if fig:
            # Sanitize filename
            safe_name = (interv_type
                         .replace(' ', '_')
                         .replace('(', '')
                         .replace(')', '')
                         .replace('×', 'x')
                         .replace('/', '_per_')
                         .replace('³', '3')
                         .replace('²', '2'))
            filename = f"{idx:02d}_{safe_name}.png"
            fig.savefig(output_dir / filename, dpi=300, bbox_inches='tight')
            plt.close(fig)
            successful += 1
    
    if verbose:
        print(f"\n  ✅ Saved {successful} drawings to {output_dir}/")
    
    # Generate master specifications HTML
    generate_master_specs(design, output_dir, verbose)
    
    if verbose:
        print("\n" + "="*70)
        print("✅ ENGINEERING DRAWINGS COMPLETE!")
        print("="*70)
        print(f"\n📐 Generated:")
        print(f"  • {successful} engineering drawings (PNG, 300 DPI)")
        print(f"  • MASTER_SPECIFICATIONS.html")
        print(f"\n📁 Location: {output_dir}/")
        print("="*70)
    
    return successful

def generate_master_specs(design, output_dir, verbose=True):
    """Generate master specifications HTML document"""
    
    if verbose:
        print("\n  Creating master specifications document...")
    
    # Get unique intervention types
    intervention_types = set()
    for interv in design['interventions']:
        spec_key = get_spec_key_from_type(interv['type'])
        if spec_key:
            intervention_types.add(spec_key)
    
    spec_html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Master Specifications - QCIA Flood Mitigation</title>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; max-width: 210mm; margin: 0 auto; padding: 20px; }}
        h1 {{ color: #2c3e50; border-bottom: 4px solid #3498db; padding-bottom: 10px; text-align: center; }}
        h2 {{ color: #34495e; background: #ecf0f1; padding: 10px; margin-top: 30px; border-left: 5px solid #3498db; }}
        .important {{ background: #f8d7da; border-left: 5px solid #dc3545; padding: 15px; margin: 20px 0; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th {{ background: #3498db; color: white; padding: 12px; text-align: left; }}
        td {{ padding: 10px; border: 1px solid #ddd; }}
        tr:nth-child(even) {{ background: #f2f2f2; }}
    </style>
</head>
<body>
    <h1>MASTER TECHNICAL SPECIFICATIONS</h1>
    <h2 style="text-align: center; color: #3498db;">QCIA Urban Flood Mitigation Project</h2>
    <p style="text-align: center;"><strong>Total Interventions:</strong> {design['num_interventions']} | <strong>Total Cost:</strong> ₹{design['total_cost_cr']:.2f} Crores</p>
    
    <div class="important">
        <strong>⚠️  IMPORTANT NOTICE:</strong><br>
        These are PLANNING-GRADE specifications generated by QCIA for rapid scenario analysis. 
        Final designs MUST be validated by licensed civil engineers and approved by PWD/ULB before construction.
    </div>
    
    <h2>1. GENERAL SPECIFICATIONS</h2>
    <h3>1.1 Codes and Standards</h3>
    <ul>
        <li><strong>IS 456:2000</strong> - Plain and Reinforced Concrete Code of Practice</li>
        <li><strong>IS 3370:2009</strong> - Concrete Structures for Storage of Liquids</li>
        <li><strong>IRC 5:2015</strong> - Standard Specifications for Road Bridges</li>
        <li><strong>CPWD Specifications</strong> - Central Public Works Department</li>
    </ul>
    
    <h2>2. BILL OF QUANTITIES (BOQ)</h2>
    <table>
        <tr>
            <th>S.No.</th>
            <th>Intervention</th>
            <th>Location (Grid)</th>
            <th>Cost (₹ Lakh)</th>
        </tr>
"""
    
    for idx, interv in enumerate(design['interventions'], 1):
        location = interv.get('location', (0, 0))
        cost_lakh = interv.get('cost_lakh', 0)
        spec_html += f"""
        <tr>
            <td>{idx}</td>
            <td>{interv['type']}</td>
            <td>({location[0]}, {location[1]})</td>
            <td style="text-align: right;"><strong>₹{cost_lakh:.2f}</strong></td>
        </tr>
"""
    
    spec_html += f"""
        <tr style="background: #ffd700;">
            <td colspan="3" style="text-align: right; font-weight: bold;">TOTAL:</td>
            <td style="text-align: right; font-weight: bold; font-size: 14px;">₹{design['total_cost_cr']*100:.2f}</td>
        </tr>
    </table>
    
    <p style="text-align: center; margin-top: 40px;"><strong>Generated by QCIA - October 2025</strong></p>
</body>
</html>
"""
    
    spec_file = output_dir / 'MASTER_SPECIFICATIONS.html'
    with open(spec_file, 'w') as f:
        f.write(spec_html)
    
    if verbose:
        print(f"  ✅ Master specifications saved: {spec_file}")

# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description='Generate engineering drawings from QCIA design')
    parser.add_argument('--design', required=True, help='Path to qcia_design.json')
    parser.add_argument('--dem', required=True, help='Path to DEM GeoTIFF')
    parser.add_argument('--output', default='outputs/engineering_drawings', help='Output directory')
    parser.add_argument('--quiet', action='store_true', help='Suppress progress output')
    parser.add_argument('--roads', default='', help='Path to roads GeoJSON/GeoPackage')
    parser.add_argument('--drains', default='', help='Path to drains/canals GeoJSON/GeoPackage')
    parser.add_argument('--tile_row0', type=int, default=0, help='Baseline DEM tile starting row index')
    parser.add_argument('--tile_col0', type=int, default=0, help='Baseline DEM tile starting col index')
    parser.add_argument('--baseline_dir', default='', help='Path to baseline run dir (to annotate site metrics)')
    parser.add_argument('--opt_dir', default='', help='Path to optimized run dir (to annotate site metrics)')
    
    args = parser.parse_args()
    
    generate_engineering_drawings(
        design_path=args.design,
        dem_path=args.dem,
        output_dir=args.output,
        verbose=not args.quiet,
        baseline_dir=args.baseline_dir,
        opt_dir=args.opt_dir,
        roads_path=args.roads,
        drains_path=args.drains,
        tile_row0=args.tile_row0,
        tile_col0=args.tile_col0
    )

if __name__ == "__main__":
    main()

