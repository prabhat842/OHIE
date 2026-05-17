"""
Generate 3D Models for Novel Infrastructure

Creates interactive 3D visualizations of innovative designs:
- Bio-integrated detention with living terraces
- Stepped cascade systems
- Underground modular storage
"""

import numpy as np
import trimesh
import plotly.graph_objects as go
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))

from applications.novel_infrastructure_generator import (
    NovelInfrastructureGenerator,
    BioIntegratedDetention,
    SteppedCascadeBasin,
    UndergroundModular
)


class NovelInfrastructure3DGenerator:
    """Generate 3D models for novel infrastructure designs"""
    
    def generate_bio_integrated_3d(self, design: BioIntegratedDetention, output_dir: str = 'engineering_3d_models/novel'):
        """Generate 3D model of bio-integrated detention with living terraces"""
        
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        print(f"\n🌿 Generating 3D model: BIO-INTEGRATED DETENTION #{design.basin_id:03d}...")
        
        radius = design.diameter_m / 2
        depth = design.depth_m
        terraces = design.terrace_count
        terrace_width = design.terrace_width_m
        
        fig = go.Figure()
        
        # 1. MAIN BASIN WALLS (outer cylinder)
        theta = np.linspace(0, 2*np.pi, 64)
        z_levels = np.linspace(0, -depth, 50)
        
        # Outer wall
        x_outer = radius * np.cos(theta)
        y_outer = radius * np.sin(theta)
        
        for i in range(len(z_levels) - 1):
            fig.add_trace(go.Mesh3d(
                x=np.concatenate([x_outer, x_outer]),
                y=np.concatenate([y_outer, y_outer]),
                z=np.concatenate([np.full(len(x_outer), z_levels[i]), 
                                 np.full(len(x_outer), z_levels[i+1])]),
                alphahull=0,
                opacity=0.3,
                color='lightgray',
                showlegend=(i == 0),
                name='Basin Wall'
            ))
        
        # 2. LIVING TERRACES (stepped platforms)
        terrace_colors = ['green', 'darkgreen', 'forestgreen', 'limegreen', 'olivedrab', 'seagreen', 'mediumseagreen', 'springgreen']
        
        for t in range(terraces):
            terrace_z = -depth * (t + 1) / (terraces + 1)
            terrace_outer = radius - terrace_width * 0.3  # Slightly inset
            terrace_inner = terrace_outer - terrace_width
            
            # Create terrace ring
            x_terrace_outer = terrace_outer * np.cos(theta)
            y_terrace_outer = terrace_outer * np.sin(theta)
            x_terrace_inner = terrace_inner * np.cos(theta)
            y_terrace_inner = terrace_inner * np.sin(theta)
            
            # Terrace platform
            n = len(theta)
            vertices = []
            for i in range(n):
                vertices.extend([
                    [x_terrace_outer[i], y_terrace_outer[i], terrace_z],
                    [x_terrace_inner[i], y_terrace_inner[i], terrace_z]
                ])
            
            vertices_arr = np.array(vertices)
            
            fig.add_trace(go.Scatter3d(
                x=np.concatenate([x_terrace_outer, x_terrace_outer[:1]]),
                y=np.concatenate([y_terrace_outer, y_terrace_outer[:1]]),
                z=np.full(len(x_terrace_outer) + 1, terrace_z),
                mode='lines',
                line=dict(color=terrace_colors[t % len(terrace_colors)], width=8),
                name=f'Terrace {t+1}',
                showlegend=(t < 3)
            ))
            
            # Add plant symbols on terrace
            num_plants = int(2 * np.pi * terrace_outer / 0.5)  # Every 0.5m
            plant_theta = np.linspace(0, 2*np.pi, num_plants, endpoint=False)
            plant_r = (terrace_outer + terrace_inner) / 2
            
            if t < 3:  # Only show plants on first 3 terraces to avoid clutter
                fig.add_trace(go.Scatter3d(
                    x=plant_r * np.cos(plant_theta),
                    y=plant_r * np.sin(plant_theta),
                    z=np.full(num_plants, terrace_z + 0.2),
                    mode='markers',
                    marker=dict(size=4, color='darkgreen', symbol='diamond'),
                    name='Vegetation' if t == 0 else None,
                    showlegend=(t == 0)
                ))
        
        # 3. WATER LEVEL (translucent blue)
        water_z = -depth * 0.7
        water_r = radius - terrace_width * 1.5
        x_water = water_r * np.cos(theta)
        y_water = water_r * np.sin(theta)
        
        # Create water surface mesh
        water_triangles = []
        center_idx = len(theta)
        for i in range(len(theta)):
            next_i = (i + 1) % len(theta)
            water_triangles.append([i, next_i, center_idx])
        
        water_verts = np.vstack([
            np.column_stack([x_water, y_water, np.full(len(theta), water_z)]),
            [[0, 0, water_z]]
        ])
        
        fig.add_trace(go.Mesh3d(
            x=water_verts[:, 0],
            y=water_verts[:, 1],
            z=water_verts[:, 2],
            i=[t[0] for t in water_triangles],
            j=[t[1] for t in water_triangles],
            k=[t[2] for t in water_triangles],
            color='cyan',
            opacity=0.5,
            name='Water Level'
        ))
        
        # 4. BASE
        x_base = radius * np.cos(theta)
        y_base = radius * np.sin(theta)
        
        fig.add_trace(go.Scatter3d(
            x=np.concatenate([x_base, x_base[:1]]),
            y=np.concatenate([y_base, y_base[:1]]),
            z=np.full(len(x_base) + 1, -depth),
            mode='lines',
            line=dict(color='gray', width=10),
            name='Base'
        ))
        
        # Layout
        fig.update_layout(
            title=dict(
                text=f"<b>BIO-INTEGRATED DETENTION #{design.basin_id:03d}</b><br>" +
                     f"{design.diameter_m:.1f}m × {design.depth_m:.1f}m | {design.terrace_count} Living Terraces<br>" +
                     f"{design.living_wall_area_m2:.0f}m² Green Walls | ~{int(design.living_wall_area_m2 * design.vegetation_density)} Plants",
                x=0.5,
                xanchor='center',
                font=dict(size=16)
            ),
            scene=dict(
                xaxis=dict(title='X (m)', backgroundcolor="rgb(230, 245, 230)"),
                yaxis=dict(title='Y (m)', backgroundcolor="rgb(230, 245, 230)"),
                zaxis=dict(title='Z (m)', backgroundcolor="rgb(230, 245, 230)"),
                aspectmode='data',
                camera=dict(eye=dict(x=1.5, y=1.5, z=1.0))
            ),
            showlegend=True,
            legend=dict(x=0.02, y=0.02, bgcolor="rgba(255,255,255,0.9)"),
            width=1400,
            height=900,
            paper_bgcolor='rgb(245,255,245)'
        )
        
        html_path = f"{output_dir}/bio_integrated_{design.basin_id:03d}_3d.html"
        fig.write_html(html_path)
        print(f"   ✓ Interactive 3D: {html_path}")
        
        return html_path
    
    def generate_cascade_3d(self, design: SteppedCascadeBasin, output_dir: str = 'engineering_3d_models/novel'):
        """Generate 3D model of stepped cascade system"""
        
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        print(f"\n💧 Generating 3D model: STEPPED CASCADE #{design.basin_id:03d}...")
        
        fig = go.Figure()
        
        length = design.total_length_m
        width = design.step_width_m
        steps = design.step_count
        step_height = design.step_height_m
        
        # Generate each step
        colors = ['royalblue', 'dodgerblue', 'lightskyblue', 'steelblue', 'cornflowerblue',
                 'deepskyblue', 'skyblue', 'lightblue', 'powderblue', 'lightsteelblue']
        
        step_length = length / steps
        
        for s in range(steps):
            z_top = -(s * step_height)
            z_bottom = -((s + 1) * step_height)
            x_start = s * step_length
            x_end = (s + 1) * step_length
            
            # Step pool (rectangular)
            corners = [
                [x_start, -width/2, z_bottom],
                [x_end, -width/2, z_bottom],
                [x_end, width/2, z_bottom],
                [x_start, width/2, z_bottom],
                [x_start, -width/2, z_top],
                [x_end, -width/2, z_top],
                [x_end, width/2, z_top],
                [x_start, width/2, z_top]
            ]
            
            # Bottom face
            fig.add_trace(go.Mesh3d(
                x=[corners[0][0], corners[1][0], corners[2][0], corners[3][0]],
                y=[corners[0][1], corners[1][1], corners[2][1], corners[3][1]],
                z=[corners[0][2], corners[1][2], corners[2][2], corners[3][2]],
                color='saddlebrown',
                opacity=0.8,
                name=f'Step {s+1}' if s < 3 else None,
                showlegend=(s < 3)
            ))
            
            # Water in pool (partial fill - 60%)
            water_z = z_bottom + step_height * 0.6
            fig.add_trace(go.Mesh3d(
                x=[x_start, x_end, x_end, x_start],
                y=[-width/2, -width/2, width/2, width/2],
                z=[water_z, water_z, water_z, water_z],
                color=colors[s % len(colors)],
                opacity=0.6,
                name='Water' if s == 0 else None,
                showlegend=(s == 0)
            ))
            
            # Cascade/waterfall between steps (if not first)
            if s > 0:
                cascade_x = x_start
                cascade_points = 20
                cascade_y = np.linspace(-width/2, width/2, cascade_points)
                cascade_z_top = -((s - 1) * step_height) + step_height * 0.6
                cascade_z_bottom = z_top
                
                # Create waterfall effect
                for i in range(cascade_points - 1):
                    fig.add_trace(go.Scatter3d(
                        x=[cascade_x, cascade_x],
                        y=[cascade_y[i], cascade_y[i]],
                        z=[cascade_z_top, cascade_z_bottom],
                        mode='lines',
                        line=dict(color='lightblue', width=2),
                        showlegend=False
                    ))
        
        # Add vegetation along sides
        for s in range(0, steps, 2):
            x = s * step_length + step_length / 2
            z = -(s * step_height)
            
            # Trees on sides
            for side in [-1, 1]:
                y = side * (width/2 + 1)
                fig.add_trace(go.Scatter3d(
                    x=[x],
                    y=[y],
                    z=[z + 1],
                    mode='markers+text',
                    marker=dict(size=12, color='green', symbol='diamond'),
                    text=['🌳'],
                    textfont=dict(size=20),
                    showlegend=(s == 0 and side == -1),
                    name='Trees' if (s == 0 and side == -1) else None
                ))
        
        # Layout
        fig.update_layout(
            title=dict(
                text=f"<b>STEPPED CASCADE SYSTEM #{design.basin_id:03d}</b><br>" +
                     f"{steps} Cascading Steps over {length:.1f}m<br>" +
                     f"Total Storage: {design.total_storage_m3:.0f}m³ | {design.aeration_benefit}x Water Quality Boost",
                x=0.5,
                xanchor='center',
                font=dict(size=16)
            ),
            scene=dict(
                xaxis=dict(title='Length (m)', backgroundcolor="rgb(230, 245, 255)"),
                yaxis=dict(title='Width (m)', backgroundcolor="rgb(230, 245, 255)"),
                zaxis=dict(title='Height (m)', backgroundcolor="rgb(230, 245, 255)"),
                aspectmode='data',
                camera=dict(eye=dict(x=2.0, y=1.5, z=0.8))
            ),
            showlegend=True,
            width=1400,
            height=900,
            paper_bgcolor='rgb(240,250,255)'
        )
        
        html_path = f"{output_dir}/stepped_cascade_{design.basin_id:03d}_3d.html"
        fig.write_html(html_path)
        print(f"   ✓ Interactive 3D: {html_path}")
        
        return html_path
    
    def generate_underground_3d(self, design: UndergroundModular, output_dir: str = 'engineering_3d_models/novel'):
        """Generate 3D model of underground modular storage"""
        
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        print(f"\n🏗️  Generating 3D model: UNDERGROUND MODULAR #{design.module_id:03d}...")
        
        fig = go.Figure()
        
        length, width, depth = design.unit_dimensions
        count = design.module_count
        
        # Arrange modules in grid
        grid_cols = int(np.ceil(np.sqrt(count)))
        grid_rows = int(np.ceil(count / grid_cols))
        
        spacing = 2  # meters between modules
        
        module_idx = 0
        for row in range(grid_rows):
            for col in range(grid_cols):
                if module_idx >= count:
                    break
                
                # Module position
                x_offset = col * (length + spacing)
                y_offset = row * (width + spacing)
                
                # Underground module (box)
                corners_x = [x_offset, x_offset + length, x_offset + length, x_offset,
                            x_offset, x_offset + length, x_offset + length, x_offset]
                corners_y = [y_offset, y_offset, y_offset + width, y_offset + width,
                            y_offset, y_offset, y_offset + width, y_offset + width]
                corners_z = [-depth, -depth, -depth, -depth, 0, 0, 0, 0]
                
                # Draw module walls
                # Bottom
                fig.add_trace(go.Mesh3d(
                    x=[corners_x[0], corners_x[1], corners_x[2], corners_x[3]],
                    y=[corners_y[0], corners_y[1], corners_y[2], corners_y[3]],
                    z=[corners_z[0], corners_z[1], corners_z[2], corners_z[3]],
                    color='darkgray',
                    opacity=0.7,
                    name=f'Module {module_idx+1}' if module_idx < 3 else None,
                    showlegend=(module_idx < 3)
                ))
                
                # Sides (wireframe)
                for i in range(4):
                    next_i = (i + 1) % 4
                    fig.add_trace(go.Scatter3d(
                        x=[corners_x[i], corners_x[next_i]],
                        y=[corners_y[i], corners_y[next_i]],
                        z=[corners_z[i], corners_z[next_i]],
                        mode='lines',
                        line=dict(color='gray', width=3),
                        showlegend=False
                    ))
                    # Vertical edges
                    fig.add_trace(go.Scatter3d(
                        x=[corners_x[i], corners_x[i+4]],
                        y=[corners_y[i], corners_y[i+4]],
                        z=[corners_z[i], corners_z[i+4]],
                        mode='lines',
                        line=dict(color='gray', width=3),
                        showlegend=False
                    ))
                
                # Access shaft (cylinder)
                shaft_x = x_offset + length / 2
                shaft_y = y_offset + width / 2
                shaft_r = 0.75  # meters
                theta = np.linspace(0, 2*np.pi, 16)
                
                shaft_x_circle = shaft_x + shaft_r * np.cos(theta)
                shaft_y_circle = shaft_y + shaft_r * np.sin(theta)
                
                # Shaft at surface
                fig.add_trace(go.Scatter3d(
                    x=np.concatenate([shaft_x_circle, shaft_x_circle[:1]]),
                    y=np.concatenate([shaft_y_circle, shaft_y_circle[:1]]),
                    z=np.full(len(shaft_x_circle) + 1, 0),
                    mode='lines',
                    line=dict(color='darkred', width=5),
                    name='Access Shaft' if module_idx == 0 else None,
                    showlegend=(module_idx == 0)
                ))
                
                module_idx += 1
        
        # Surface layer (ground level with park)
        total_x = grid_cols * (length + spacing)
        total_y = grid_rows * (width + spacing)
        
        # Semi-transparent ground
        fig.add_trace(go.Mesh3d(
            x=[0, total_x, total_x, 0],
            y=[0, 0, total_y, total_y],
            z=[0, 0, 0, 0],
            color='lightgreen',
            opacity=0.4,
            name='Surface (Park)'
        ))
        
        # Add trees on surface
        tree_count = min(count * 3, 20)
        tree_x = np.random.uniform(0, total_x, tree_count)
        tree_y = np.random.uniform(0, total_y, tree_count)
        
        fig.add_trace(go.Scatter3d(
            x=tree_x,
            y=tree_y,
            z=np.full(tree_count, 2),
            mode='markers+text',
            marker=dict(size=10, color='darkgreen', symbol='diamond'),
            text=['🌳'] * tree_count,
            textfont=dict(size=16),
            name='Park Trees'
        ))
        
        # Layout
        fig.update_layout(
            title=dict(
                text=f"<b>UNDERGROUND MODULAR STORAGE #{design.module_id:03d}</b><br>" +
                     f"{count} Modules: {length:.1f}m × {width:.1f}m × {depth:.1f}m<br>" +
                     f"Total Capacity: {design.total_volume_m3:.0f}m³ | Surface: {design.surface_use}",
                x=0.5,
                xanchor='center',
                font=dict(size=16)
            ),
            scene=dict(
                xaxis=dict(title='X (m)', backgroundcolor="rgb(245, 240, 230)"),
                yaxis=dict(title='Y (m)', backgroundcolor="rgb(245, 240, 230)"),
                zaxis=dict(title='Z (m)', backgroundcolor="rgb(245, 240, 230)"),
                aspectmode='data',
                camera=dict(eye=dict(x=1.8, y=1.8, z=1.2))
            ),
            showlegend=True,
            width=1400,
            height=900,
            paper_bgcolor='rgb(250,248,240)'
        )
        
        html_path = f"{output_dir}/underground_modular_{design.module_id:03d}_3d.html"
        fig.write_html(html_path)
        print(f"   ✓ Interactive 3D: {html_path}")
        
        return html_path


if __name__ == "__main__":
    print("="*80)
    print("🎨 NOVEL INFRASTRUCTURE 3D VISUALIZATION")
    print("="*80)
    print("\nGenerating interactive 3D models of innovative designs...\n")
    
    # Generate the novel designs
    generator = NovelInfrastructureGenerator()
    
    print("Step 1: Optimizing novel infrastructure designs...")
    bio_design = generator.design_bio_integrated_detention(
        basin_id=1,
        target_volume_m3=300,
        biodiversity_goal='high'
    )
    
    cascade_design = generator.design_stepped_cascade(
        basin_id=2,
        elevation_drop_m=8,
        target_storage_m3=400
    )
    
    underground_design = generator.design_underground_modular(
        module_id=3,
        target_volume_m3=1000,
        surface_use='park'
    )
    
    # Generate 3D models
    print("\n" + "="*80)
    print("Step 2: Creating 3D visualizations...")
    print("="*80)
    
    model_gen = NovelInfrastructure3DGenerator()
    
    bio_3d = model_gen.generate_bio_integrated_3d(bio_design)
    cascade_3d = model_gen.generate_cascade_3d(cascade_design)
    underground_3d = model_gen.generate_underground_3d(underground_design)
    
    print("\n" + "="*80)
    print("✅ 3D VISUALIZATION COMPLETE!")
    print("="*80)
    
    print("\n📁 Generated 3D Models:")
    print(f"   1. {bio_3d}")
    print(f"   2. {cascade_3d}")
    print(f"   3. {underground_3d}")
    
    print("\n🎯 What You'll See:")
    print("   • BIO-INTEGRATED: Terraced living walls spiraling down")
    print("   • CASCADE: Multi-level waterfalls with pools")
    print("   • UNDERGROUND: Hidden modules with park above")
    
    print("\n💡 Interact with the models:")
    print("   • Rotate: Click and drag")
    print("   • Zoom: Scroll wheel")
    print("   • Pan: Right-click and drag")
    print("   • View layers, terraces, modules from all angles")
    
    print("\n🚀 These are NOVEL designs - you won't find these in any handbook!")
    print("   AI-generated, multi-functional, innovative infrastructure!")

