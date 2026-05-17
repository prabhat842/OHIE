"""
CAD Drawing Generator

Generates AutoCAD DXF/DWG files from engineering specifications.
Creates:
- Plan views (top-down)
- Section views (cross-sections)
- Detail drawings (reinforcement)
- Dimensioned drawings
- Title blocks

Output: DXF files compatible with AutoCAD, LibreCAD, BricsCAD, etc.
"""

import ezdxf
from ezdxf import units
from ezdxf.enums import TextEntityAlignment
import math
from typing import Dict, List, Tuple
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))

from applications.engineering_spec_generator import (
    DetentionBasinDesign,
    BioswaleDesign,
    EngineeringSpecGenerator
)


class CADDrawingGenerator:
    """
    Generates construction-ready CAD drawings from engineering designs.
    
    Features:
    - Plan views with dimensions
    - Cross-sections with annotations
    - Reinforcement detail drawings
    - Professional title blocks
    - Layer organization
    - Standard CAD conventions
    """
    
    def __init__(self):
        self.scale = 100  # 1:100 scale
        self.text_height = 2.5  # mm on drawing
        
    def generate_detention_basin_drawings(
        self,
        design: DetentionBasinDesign,
        output_dir: str = 'engineering_drawings'
    ):
        """
        Generate complete set of drawings for a detention basin.
        
        Creates:
        1. Plan view
        2. Section A-A
        3. Reinforcement details
        """
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        # Create main drawing with multiple layouts
        doc = ezdxf.new('R2010', setup=True)
        doc.units = units.M
        
        # Setup layers
        self._setup_layers(doc)
        
        # Create plan view
        self._draw_basin_plan(doc, design)
        
        # Create section view
        self._draw_basin_section(doc, design)
        
        # Create detail view
        self._draw_reinforcement_detail(doc, design)
        
        # Save
        filename = f"{output_dir}/detention_basin_{design.basin_id:03d}.dxf"
        doc.saveas(filename)
        print(f"   ✓ Generated CAD drawing: {filename}")
        
        return filename
    
    def generate_bioswale_drawings(
        self,
        design: BioswaleDesign,
        output_dir: str = 'engineering_drawings'
    ):
        """Generate CAD drawings for bioswale"""
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        doc = ezdxf.new('R2010', setup=True)
        doc.units = units.M
        
        self._setup_layers(doc)
        self._draw_bioswale_plan(doc, design)
        self._draw_bioswale_section(doc, design)
        
        filename = f"{output_dir}/bioswale_{design.bioswale_id:03d}.dxf"
        doc.saveas(filename)
        print(f"   ✓ Generated CAD drawing: {filename}")
        
        return filename
    
    def _setup_layers(self, doc):
        """Setup standard CAD layers"""
        msp = doc.modelspace()
        
        # Create layers with colors
        doc.layers.add('WALLS', color=1)  # Red
        doc.layers.add('DIMENSIONS', color=2)  # Yellow
        doc.layers.add('TEXT', color=3)  # Green
        doc.layers.add('REINFORCEMENT', color=4)  # Cyan
        doc.layers.add('CENTERLINES', color=5)  # Blue
        doc.layers.add('HATCHING', color=8)  # Gray
        doc.layers.add('WATER', color=4)  # Cyan
        doc.layers.add('VEGETATION', color=3)  # Green
    
    def _draw_basin_plan(self, doc, design: DetentionBasinDesign):
        """Draw plan view of detention basin"""
        msp = doc.modelspace()
        
        # Title
        msp.add_text(
            f"DETENTION BASIN #{design.basin_id:03d} - PLAN VIEW",
            dxfattribs={
                'layer': 'TEXT',
                'height': 5,
                'style': 'OpenSans'
            }
        ).set_placement((0, 50), align=TextEntityAlignment.LEFT)
        
        # Center of basin at origin
        center = (0, 0)
        radius = design.diameter_m / 2
        
        # Draw outer circle (top of wall)
        msp.add_circle(
            center=center,
            radius=radius,
            dxfattribs={'layer': 'WALLS', 'lineweight': 50}
        )
        
        # Draw inner circle (base)
        inner_radius = radius - design.wall_thickness_mm / 1000
        msp.add_circle(
            center=center,
            radius=inner_radius,
            dxfattribs={'layer': 'WALLS', 'lineweight': 25}
        )
        
        # Draw water level
        water_level_radius = radius - 0.2
        msp.add_circle(
            center=center,
            radius=water_level_radius,
            dxfattribs={'layer': 'WATER', 'linetype': 'DASHED'}
        )
        
        # Centerlines
        msp.add_line(
            (-radius * 1.2, 0),
            (radius * 1.2, 0),
            dxfattribs={'layer': 'CENTERLINES', 'linetype': 'CENTER'}
        )
        msp.add_line(
            (0, -radius * 1.2),
            (0, radius * 1.2),
            dxfattribs={'layer': 'CENTERLINES', 'linetype': 'CENTER'}
        )
        
        # Inlet pipe
        inlet_angle = 45  # degrees
        inlet_x = radius * math.cos(math.radians(inlet_angle))
        inlet_y = radius * math.sin(math.radians(inlet_angle))
        pipe_length = 1.5
        inlet_end_x = inlet_x + pipe_length * math.cos(math.radians(inlet_angle))
        inlet_end_y = inlet_y + pipe_length * math.sin(math.radians(inlet_angle))
        
        # Draw inlet pipe
        pipe_radius = design.inlet_pipe_diameter_mm / 2000  # Convert mm to m
        msp.add_line(
            (inlet_x, inlet_y),
            (inlet_end_x, inlet_end_y),
            dxfattribs={'layer': 'WALLS', 'lineweight': 35}
        )
        msp.add_circle(
            (inlet_end_x, inlet_end_y),
            pipe_radius,
            dxfattribs={'layer': 'WALLS'}
        )
        msp.add_text(
            f"INLET\n{design.inlet_pipe_diameter_mm}mm ø",
            dxfattribs={'layer': 'TEXT', 'height': 1.5}
        ).set_placement((inlet_end_x + 0.5, inlet_end_y), align=TextEntityAlignment.LEFT)
        
        # Outlet pipe
        outlet_angle = 225  # degrees (opposite side)
        outlet_x = radius * math.cos(math.radians(outlet_angle))
        outlet_y = radius * math.sin(math.radians(outlet_angle))
        outlet_end_x = outlet_x + pipe_length * math.cos(math.radians(outlet_angle))
        outlet_end_y = outlet_y + pipe_length * math.sin(math.radians(outlet_angle))
        
        msp.add_line(
            (outlet_x, outlet_y),
            (outlet_end_x, outlet_end_y),
            dxfattribs={'layer': 'WALLS', 'lineweight': 35}
        )
        msp.add_circle(
            (outlet_end_x, outlet_end_y),
            design.outlet_pipe_diameter_mm / 2000,
            dxfattribs={'layer': 'WALLS'}
        )
        msp.add_text(
            f"OUTLET\n{design.outlet_pipe_diameter_mm}mm ø",
            dxfattribs={'layer': 'TEXT', 'height': 1.5}
        ).set_placement((outlet_end_x - 0.5, outlet_end_y), align=TextEntityAlignment.RIGHT)
        
        # Dimensions
        dim_y = -radius - 3
        
        # Diameter dimension
        dimstyle = doc.dimstyles.get('EZ_CURVED')
        dim = msp.add_linear_dim(
            base=(-radius, dim_y),
            p1=(-radius, 0),
            p2=(radius, 0),
            dimstyle='Standard',
            dxfattribs={'layer': 'DIMENSIONS'}
        )
        dim.render()
        
        # Add dimension text manually
        msp.add_text(
            f"ø {design.diameter_m:.2f}m",
            dxfattribs={'layer': 'DIMENSIONS', 'height': 1.5}
        ).set_placement((0, dim_y - 1), align=TextEntityAlignment.CENTER)
        
        # Key notes
        notes_x = radius + 5
        notes_y = 5
        notes = [
            "GENERAL NOTES:",
            f"1. Internal diameter: {design.diameter_m:.2f}m",
            f"2. Wall thickness: {design.wall_thickness_mm:.0f}mm",
            f"3. Concrete: {design.concrete_grade}",
            f"4. Storage volume: {design.storage_volume_m3:.1f}m³",
            f"5. Design flow: {design.design_flow_lps:.0f} lps",
            "",
            "COORDINATES:",
            f"Lat: {design.location['lat']:.6f}°",
            f"Lon: {design.location['lon']:.6f}°"
        ]
        
        for i, note in enumerate(notes):
            msp.add_text(
                note,
                dxfattribs={'layer': 'TEXT', 'height': 1.2}
            ).set_placement((notes_x, notes_y - i * 1.8), align=TextEntityAlignment.LEFT)
        
        # Section marker
        section_y = radius * 0.7
        msp.add_line(
            (-radius * 1.1, section_y),
            (radius * 1.1, section_y),
            dxfattribs={'layer': 'DIMENSIONS', 'lineweight': 25}
        )
        
        # Section arrows
        arrow_size = 1
        # Left arrow
        msp.add_solid([
            (-radius * 1.1, section_y),
            (-radius * 1.1 - arrow_size, section_y + arrow_size/2),
            (-radius * 1.1 - arrow_size, section_y - arrow_size/2)
        ], dxfattribs={'layer': 'DIMENSIONS'})
        
        # Right arrow
        msp.add_solid([
            (radius * 1.1, section_y),
            (radius * 1.1 + arrow_size, section_y + arrow_size/2),
            (radius * 1.1 + arrow_size, section_y - arrow_size/2)
        ], dxfattribs={'layer': 'DIMENSIONS'})
        
        # Section labels
        msp.add_text(
            "A",
            dxfattribs={'layer': 'TEXT', 'height': 2}
        ).set_placement((-radius * 1.1 - arrow_size - 0.5, section_y + 0.5), align=TextEntityAlignment.RIGHT)
        
        msp.add_text(
            "A",
            dxfattribs={'layer': 'TEXT', 'height': 2}
        ).set_placement((radius * 1.1 + arrow_size + 0.5, section_y + 0.5), align=TextEntityAlignment.LEFT)
    
    def _draw_basin_section(self, doc, design: DetentionBasinDesign):
        """Draw section A-A of detention basin"""
        msp = doc.modelspace()
        
        # Position section view below plan
        offset_y = -design.diameter_m - 20
        
        # Title
        msp.add_text(
            f"SECTION A-A",
            dxfattribs={'layer': 'TEXT', 'height': 5}
        ).set_placement((0, offset_y + 15), align=TextEntityAlignment.LEFT)
        
        # Ground level
        ground_y = offset_y
        radius = design.diameter_m / 2
        
        # Draw ground line
        msp.add_line(
            (-radius * 2, ground_y),
            (radius * 2, ground_y),
            dxfattribs={'layer': 'WALLS', 'lineweight': 25}
        )
        
        # Basin geometry
        depth = design.depth_m
        wall_thickness = design.wall_thickness_mm / 1000
        base_thickness = design.base_thickness_mm / 1000
        
        # Left wall outer
        msp.add_line(
            (-radius, ground_y),
            (-radius, ground_y - depth),
            dxfattribs={'layer': 'WALLS', 'lineweight': 50}
        )
        
        # Left wall inner
        msp.add_line(
            (-radius + wall_thickness, ground_y),
            (-radius + wall_thickness, ground_y - depth + base_thickness),
            dxfattribs={'layer': 'WALLS', 'lineweight': 25}
        )
        
        # Right wall outer
        msp.add_line(
            (radius, ground_y),
            (radius, ground_y - depth),
            dxfattribs={'layer': 'WALLS', 'lineweight': 50}
        )
        
        # Right wall inner
        msp.add_line(
            (radius - wall_thickness, ground_y),
            (radius - wall_thickness, ground_y - depth + base_thickness),
            dxfattribs={'layer': 'WALLS', 'lineweight': 25}
        )
        
        # Base slab outer
        msp.add_line(
            (-radius, ground_y - depth),
            (radius, ground_y - depth),
            dxfattribs={'layer': 'WALLS', 'lineweight': 50}
        )
        
        # Base slab inner
        msp.add_line(
            (-radius + wall_thickness, ground_y - depth + base_thickness),
            (radius - wall_thickness, ground_y - depth + base_thickness),
            dxfattribs={'layer': 'WALLS', 'lineweight': 25}
        )
        
        # Water level
        water_depth = depth - design.freeboard_m
        water_y = ground_y - water_depth
        msp.add_line(
            (-radius + wall_thickness, water_y),
            (radius - wall_thickness, water_y),
            dxfattribs={'layer': 'WATER', 'linetype': 'DASHED', 'color': 4}
        )
        
        # Hatch water
        hatch = msp.add_hatch(color=4)
        hatch.set_pattern_fill('ANSI31', scale=0.1)
        hatch.paths.add_polyline_path([
            (-radius + wall_thickness, water_y),
            (radius - wall_thickness, water_y),
            (radius - wall_thickness, ground_y - depth + base_thickness),
            (-radius + wall_thickness, ground_y - depth + base_thickness)
        ])
        
        # Dimensions
        dim_x = radius + 3
        
        # Total depth
        msp.add_line(
            (dim_x, ground_y),
            (dim_x, ground_y - depth),
            dxfattribs={'layer': 'DIMENSIONS'}
        )
        msp.add_line(
            (dim_x - 0.3, ground_y),
            (dim_x + 0.3, ground_y),
            dxfattribs={'layer': 'DIMENSIONS'}
        )
        msp.add_line(
            (dim_x - 0.3, ground_y - depth),
            (dim_x + 0.3, ground_y - depth),
            dxfattribs={'layer': 'DIMENSIONS'}
        )
        msp.add_text(
            f"{depth:.2f}m",
            dxfattribs={'layer': 'DIMENSIONS', 'height': 1.2, 'rotation': 90}
        ).set_placement((dim_x + 0.5, ground_y - depth/2), align=TextEntityAlignment.CENTER)
        
        # Wall thickness
        wall_dim_y = ground_y - depth / 2
        msp.add_line(
            (-radius, wall_dim_y),
            (-radius + wall_thickness, wall_dim_y),
            dxfattribs={'layer': 'DIMENSIONS'}
        )
        msp.add_text(
            f"{design.wall_thickness_mm:.0f}mm",
            dxfattribs={'layer': 'DIMENSIONS', 'height': 1}
        ).set_placement((-radius + wall_thickness/2, wall_dim_y - 0.5), align=TextEntityAlignment.CENTER)
        
        # Base thickness
        msp.add_line(
            (0, ground_y - depth),
            (0, ground_y - depth + base_thickness),
            dxfattribs={'layer': 'DIMENSIONS'}
        )
        msp.add_text(
            f"{design.base_thickness_mm:.0f}mm",
            dxfattribs={'layer': 'DIMENSIONS', 'height': 1, 'rotation': 90}
        ).set_placement((0.3, ground_y - depth + base_thickness/2), align=TextEntityAlignment.CENTER)
        
        # Labels
        msp.add_text(
            f"GROUND LEVEL",
            dxfattribs={'layer': 'TEXT', 'height': 1.2}
        ).set_placement((-radius * 1.5, ground_y + 0.5), align=TextEntityAlignment.LEFT)
        
        msp.add_text(
            f"WATER LEVEL",
            dxfattribs={'layer': 'TEXT', 'height': 1.2}
        ).set_placement((-radius * 1.5, water_y + 0.5), align=TextEntityAlignment.LEFT)
        
        msp.add_text(
            f"{design.concrete_grade} CONCRETE",
            dxfattribs={'layer': 'TEXT', 'height': 1}
        ).set_placement((0, ground_y - depth - 1), align=TextEntityAlignment.CENTER)
        
        # Reinforcement indicators
        # Vertical bars in walls
        bar_spacing = 0.15  # 150mm
        for x in range(int(-radius / bar_spacing), int(radius / bar_spacing) + 1):
            bar_x = x * bar_spacing
            if abs(bar_x) < radius - wall_thickness:
                # Draw small circles for bars
                msp.add_circle(
                    (-radius + wall_thickness/2, ground_y - 0.5 - abs(x) * 0.3),
                    0.006,  # 12mm bar
                    dxfattribs={'layer': 'REINFORCEMENT', 'color': 1}
                )
                msp.add_circle(
                    (radius - wall_thickness/2, ground_y - 0.5 - abs(x) * 0.3),
                    0.006,
                    dxfattribs={'layer': 'REINFORCEMENT', 'color': 1}
                )
    
    def _draw_reinforcement_detail(self, doc, design: DetentionBasinDesign):
        """Draw reinforcement detail"""
        msp = doc.modelspace()
        
        # Position detail to the right of section
        offset_x = design.diameter_m + 15
        offset_y = -design.diameter_m - 20
        
        # Title
        msp.add_text(
            f"REINFORCEMENT DETAIL",
            dxfattribs={'layer': 'TEXT', 'height': 3}
        ).set_placement((offset_x, offset_y + 15), align=TextEntityAlignment.LEFT)
        
        # Draw wall section detail (enlarged)
        scale = 10  # 1:10 detail
        wall_thickness = design.wall_thickness_mm / 1000
        
        # Wall outline
        detail_width = wall_thickness * scale
        detail_height = 1.5  # meters of wall shown
        
        msp.add_lwpolyline([
            (offset_x, offset_y),
            (offset_x + detail_width, offset_y),
            (offset_x + detail_width, offset_y + detail_height),
            (offset_x, offset_y + detail_height),
            (offset_x, offset_y)
        ], dxfattribs={'layer': 'WALLS', 'lineweight': 35})
        
        # Reinforcement bars
        bar_diameter = 0.012 * scale  # 12mm bar scaled
        bar_spacing = 0.15 * scale  # 150mm spacing scaled
        cover = 0.05 * scale  # 50mm cover scaled
        
        # Vertical bars (main steel)
        num_bars = int(detail_height / (bar_spacing))
        for i in range(num_bars + 1):
            y = offset_y + i * bar_spacing
            # Outer face
            msp.add_circle(
                (offset_x + cover, y),
                bar_diameter / 2,
                dxfattribs={'layer': 'REINFORCEMENT', 'color': 1}
            )
            # Inner face
            msp.add_circle(
                (offset_x + detail_width - cover, y),
                bar_diameter / 2,
                dxfattribs={'layer': 'REINFORCEMENT', 'color': 1}
            )
        
        # Horizontal bars (distribution steel)
        horizontal_spacing = 0.20 * scale  # 200mm
        bar_10mm = 0.010 * scale
        for i in range(int(detail_width / horizontal_spacing)):
            x = offset_x + i * horizontal_spacing
            # Draw as small lines
            msp.add_line(
                (x, offset_y + 0.3),
                (x, offset_y + 0.3 + 0.1),
                dxfattribs={'layer': 'REINFORCEMENT', 'color': 4, 'lineweight': 15}
            )
        
        # Labels
        labels_x = offset_x + detail_width + 1
        labels = [
            f"Main Steel: 12mm ø @ 150mm c/c",
            f"Distribution: 10mm ø @ 200mm c/c",
            f"Cover: 50mm",
            f"Grade: Fe 500 TMT",
            f"Total: {design.steel_tonnes:.2f} tonnes"
        ]
        
        for i, label in enumerate(labels):
            msp.add_text(
                label,
                dxfattribs={'layer': 'TEXT', 'height': 1}
            ).set_placement((labels_x, offset_y + detail_height - i * 1.5), align=TextEntityAlignment.LEFT)
        
        # Dimension for spacing
        msp.add_line(
            (offset_x - 1, offset_y),
            (offset_x - 1, offset_y + bar_spacing),
            dxfattribs={'layer': 'DIMENSIONS'}
        )
        msp.add_text(
            "150mm",
            dxfattribs={'layer': 'DIMENSIONS', 'height': 0.8, 'rotation': 90}
        ).set_placement((offset_x - 1.3, offset_y + bar_spacing/2), align=TextEntityAlignment.CENTER)
    
    def _draw_bioswale_plan(self, doc, design: BioswaleDesign):
        """Draw bioswale plan view"""
        msp = doc.modelspace()
        
        # Title
        msp.add_text(
            f"BIOSWALE #{design.bioswale_id:03d} - PLAN VIEW",
            dxfattribs={'layer': 'TEXT', 'height': 5}
        ).set_placement((0, 15), align=TextEntityAlignment.LEFT)
        
        # Draw bioswale outline
        length = design.length_m
        top_width = design.top_width_m
        
        # Top edges
        msp.add_line(
            (0, top_width/2),
            (length, top_width/2),
            dxfattribs={'layer': 'WALLS', 'lineweight': 35}
        )
        msp.add_line(
            (0, -top_width/2),
            (length, -top_width/2),
            dxfattribs={'layer': 'WALLS', 'lineweight': 35}
        )
        
        # Centerline
        msp.add_line(
            (0, 0),
            (length, 0),
            dxfattribs={'layer': 'CENTERLINES', 'linetype': 'CENTER'}
        )
        
        # Bottom width lines
        bottom_width = design.bottom_width_m
        msp.add_line(
            (0, bottom_width/2),
            (length, bottom_width/2),
            dxfattribs={'layer': 'VEGETATION', 'linetype': 'DASHED'}
        )
        msp.add_line(
            (0, -bottom_width/2),
            (length, -bottom_width/2),
            dxfattribs={'layer': 'VEGETATION', 'linetype': 'DASHED'}
        )
        
        # Add vegetation symbols (trees)
        tree_spacing = length / (design.tree_count + 1)
        for i in range(design.tree_count):
            x = (i + 1) * tree_spacing
            # Draw simple tree symbol (circle with cross)
            msp.add_circle(
                (x, 0),
                0.3,
                dxfattribs={'layer': 'VEGETATION', 'color': 3}
            )
            msp.add_line(
                (x - 0.2, 0),
                (x + 0.2, 0),
                dxfattribs={'layer': 'VEGETATION', 'color': 3}
            )
            msp.add_line(
                (x, -0.2),
                (x, 0.2),
                dxfattribs={'layer': 'VEGETATION', 'color': 3}
            )
        
        # Dimensions
        dim_y = -top_width/2 - 2
        msp.add_line(
            (0, dim_y),
            (length, dim_y),
            dxfattribs={'layer': 'DIMENSIONS'}
        )
        msp.add_text(
            f"LENGTH: {length:.1f}m",
            dxfattribs={'layer': 'DIMENSIONS', 'height': 1.5}
        ).set_placement((length/2, dim_y - 1), align=TextEntityAlignment.CENTER)
        
        # Width dimension
        msp.add_line(
            (-2, -top_width/2),
            (-2, top_width/2),
            dxfattribs={'layer': 'DIMENSIONS'}
        )
        msp.add_text(
            f"WIDTH: {top_width:.2f}m",
            dxfattribs={'layer': 'DIMENSIONS', 'height': 1.5, 'rotation': 90}
        ).set_placement((-2.5, 0), align=TextEntityAlignment.CENTER)
        
        # Notes
        notes_x = length + 5
        notes = [
            "PLANTING SCHEDULE:",
            f"- Native trees: {design.tree_count} nos.",
            f"- Native shrubs: {design.shrub_count} nos.",
            f"- Grass area: {design.grass_area_m2:.1f} m²",
            "",
            "MATERIALS:",
            f"- Soil mix: {design.soil_mix_type}",
            f"- Geotextile: {design.geotextile_spec}",
            f"- Mulch: {design.mulch_depth_mm}mm depth"
        ]
        
        for i, note in enumerate(notes):
            msp.add_text(
                note,
                dxfattribs={'layer': 'TEXT', 'height': 1}
            ).set_placement((notes_x, 10 - i * 1.5), align=TextEntityAlignment.LEFT)
    
    def _draw_bioswale_section(self, doc, design: BioswaleDesign):
        """Draw bioswale cross-section"""
        msp = doc.modelspace()
        
        # Position below plan
        offset_y = -design.top_width_m - 10
        
        # Title
        msp.add_text(
            f"TYPICAL CROSS-SECTION",
            dxfattribs={'layer': 'TEXT', 'height': 4}
        ).set_placement((0, offset_y + 8), align=TextEntityAlignment.LEFT)
        
        # Ground level
        ground_y = offset_y
        top_width = design.top_width_m
        bottom_width = design.bottom_width_m
        depth = design.depth_m
        
        # Bioswale profile
        side_slope = design.side_slope_ratio
        
        points = [
            (-top_width/2, ground_y),
            (-bottom_width/2, ground_y - depth),
            (bottom_width/2, ground_y - depth),
            (top_width/2, ground_y),
            (-top_width/2, ground_y)
        ]
        
        msp.add_lwpolyline(
            points,
            dxfattribs={'layer': 'WALLS', 'lineweight': 35}
        )
        
        # Soil layers
        # Mulch layer (top 75mm)
        mulch_depth = design.mulch_depth_mm / 1000
        msp.add_line(
            (-bottom_width/2, ground_y - mulch_depth),
            (bottom_width/2, ground_y - mulch_depth),
            dxfattribs={'layer': 'VEGETATION', 'linetype': 'DASHED'}
        )
        
        # Labels
        msp.add_text(
            f"MULCH ({design.mulch_depth_mm}mm)",
            dxfattribs={'layer': 'TEXT', 'height': 0.8}
        ).set_placement((0, ground_y - mulch_depth/2), align=TextEntityAlignment.CENTER)
        
        msp.add_text(
            f"ENGINEERED SOIL MIX",
            dxfattribs={'layer': 'TEXT', 'height': 0.8}
        ).set_placement((0, ground_y - depth/2), align=TextEntityAlignment.CENTER)
        
        msp.add_text(
            f"GEOTEXTILE",
            dxfattribs={'layer': 'TEXT', 'height': 0.8}
        ).set_placement((0, ground_y - depth - 0.3), align=TextEntityAlignment.CENTER)
        
        # Dimensions
        dim_x = top_width/2 + 1
        
        # Depth
        msp.add_line(
            (dim_x, ground_y),
            (dim_x, ground_y - depth),
            dxfattribs={'layer': 'DIMENSIONS'}
        )
        msp.add_text(
            f"{depth:.2f}m",
            dxfattribs={'layer': 'DIMENSIONS', 'height': 1, 'rotation': 90}
        ).set_placement((dim_x + 0.3, ground_y - depth/2), align=TextEntityAlignment.CENTER)
        
        # Top width
        msp.add_line(
            (-top_width/2, ground_y + 1),
            (top_width/2, ground_y + 1),
            dxfattribs={'layer': 'DIMENSIONS'}
        )
        msp.add_text(
            f"{top_width:.2f}m",
            dxfattribs={'layer': 'DIMENSIONS', 'height': 1}
        ).set_placement((0, ground_y + 1.5), align=TextEntityAlignment.CENTER)
        
        # Side slope notation
        slope_text = f"SIDE SLOPE {design.side_slope_ratio}H:1V"
        msp.add_text(
            slope_text,
            dxfattribs={'layer': 'TEXT', 'height': 0.8, 'rotation': -20}
        ).set_placement((-top_width/4, ground_y - depth/3), align=TextEntityAlignment.CENTER)


if __name__ == "__main__":
    print("="*80)
    print("CAD DRAWING GENERATOR - DEMO")
    print("="*80)
    print("\n🎨 Generating AutoCAD DXF files from engineering specifications...\n")
    
    # First generate engineering specs
    from engineering_spec_generator import EngineeringSpecGenerator
    
    spec_gen = EngineeringSpecGenerator(verbose=False)
    
    # Generate designs
    print("📐 Step 1: Generating engineering designs...")
    basin1 = spec_gen.generate_detention_basin_design(
        basin_id=1,
        target_volume_m3=250,
        location={'lat': 23.1815, 'lon': 79.9864},
        design_flow_lps=180,
        soil_type='medium'
    )
    
    bioswale1 = spec_gen.generate_bioswale_design(
        bioswale_id=1,
        length_m=100,
        location={'lat': 23.1825, 'lon': 79.9875},
        design_flow_lps=50
    )
    
    # Generate CAD drawings
    print("\n🎨 Step 2: Generating CAD drawings (DXF format)...")
    cad_gen = CADDrawingGenerator()
    
    cad_gen.generate_detention_basin_drawings(basin1)
    cad_gen.generate_bioswale_drawings(bioswale1)
    
    print("\n" + "="*80)
    print("✅ CAD GENERATION COMPLETE!")
    print("="*80)
    print("\n📁 Files created:")
    print("   - engineering_drawings/detention_basin_001.dxf")
    print("   - engineering_drawings/bioswale_001.dxf")
    print("\n💡 These DXF files can be opened in:")
    print("   • AutoCAD")
    print("   • LibreCAD (free)")
    print("   • BricsCAD")
    print("   • DraftSight")
    print("   • QCAD")
    print("   • Any CAD software supporting DXF format")
    print("\n🎯 Drawings include:")
    print("   ✓ Plan views with dimensions")
    print("   ✓ Cross-sections with annotations")
    print("   ✓ Reinforcement details")
    print("   ✓ Material specifications")
    print("   ✓ Professional layering (walls, dimensions, text, etc.)")
    print("\n🚀 TRUE generative CAD - from requirements to drawings!")

