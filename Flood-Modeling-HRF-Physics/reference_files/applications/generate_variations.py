"""
Generate Multiple Design Variations

Shows how QCIA creates unique designs for different requirements.
Each design is optimized individually - NO templates!
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from applications.engineering_spec_generator import EngineeringSpecGenerator
from applications.model_3d_generator import Model3DGenerator
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def generate_variations():
    """Generate multiple basin designs with different requirements"""
    
    print("="*80)
    print("GENERATIVE DESIGN VARIATIONS")
    print("="*80)
    print("\n🎨 Generating 3 different basins to show unique AI-optimized geometry...\n")
    
    spec_gen = EngineeringSpecGenerator(verbose=False)
    model_gen = Model3DGenerator()
    
    # Define 3 different requirements
    requirements = [
        {'id': 1, 'volume': 150, 'flow': 120, 'name': 'SMALL'},
        {'id': 2, 'volume': 300, 'flow': 220, 'name': 'MEDIUM'},
        {'id': 3, 'volume': 500, 'flow': 350, 'name': 'LARGE'}
    ]
    
    designs = []
    
    for req in requirements:
        print(f"🏗️  Optimizing {req['name']} basin (target: {req['volume']}m³, {req['flow']} lps)...")
        
        # QCIA optimizes each one individually
        design = spec_gen.generate_detention_basin_design(
            basin_id=req['id'],
            target_volume_m3=req['volume'],
            location={'lat': 23.18 + req['id']*0.01, 'lon': 79.98 + req['id']*0.01},
            design_flow_lps=req['flow'],
            soil_type='medium'
        )
        
        print(f"   ✓ Optimized: {design.diameter_m:.2f}m dia × {design.depth_m:.2f}m deep")
        print(f"   ✓ Storage: {design.storage_volume_m3:.1f}m³")
        print(f"   ✓ Cost: ₹{design.total_cost:,.0f}\n")
        
        designs.append(design)
    
    # Generate 3D models
    print("📐 Generating 3D models...")
    for design in designs:
        model_gen.generate_detention_basin_3d(design, output_dir='engineering_3d_models/variations')
    
    # Create comparison visualization
    print("\n📊 Creating comparison visualization...")
    create_comparison_view(designs)
    
    return designs


def create_comparison_view(designs):
    """Create side-by-side comparison of the 3 designs"""
    
    fig = make_subplots(
        rows=1, cols=3,
        subplot_titles=[f"DESIGN {d.basin_id}: {d.diameter_m:.2f}m × {d.depth_m:.2f}m"
                       for d in designs],
        specs=[[{'type': 'scatter3d'}, {'type': 'scatter3d'}, {'type': 'scatter3d'}]]
    )
    
    for idx, design in enumerate(designs):
        col = idx + 1
        radius = design.diameter_m / 2
        depth = design.depth_m
        wall_thickness = design.wall_thickness_mm / 1000
        
        # Create simplified visualization
        theta = [i * 2 * 3.14159 / 32 for i in range(33)]
        
        # Outer wall circle
        x_outer = [radius * __import__('math').cos(t) for t in theta]
        y_outer = [radius * __import__('math').sin(t) for t in theta]
        z_top = [0] * len(theta)
        z_bottom = [-depth] * len(theta)
        
        # Add outer wall
        for i in range(len(theta) - 1):
            fig.add_trace(go.Scatter3d(
                x=[x_outer[i], x_outer[i+1], x_outer[i+1], x_outer[i], x_outer[i]],
                y=[y_outer[i], y_outer[i+1], y_outer[i+1], y_outer[i], y_outer[i]],
                z=[z_top[i], z_top[i+1], z_bottom[i+1], z_bottom[i], z_top[i]],
                mode='lines',
                line=dict(color='gray', width=2),
                showlegend=False
            ), row=1, col=col)
        
        # Add base circle
        fig.add_trace(go.Scatter3d(
            x=x_outer + [x_outer[0]],
            y=y_outer + [y_outer[0]],
            z=[-depth] * (len(x_outer) + 1),
            mode='lines',
            line=dict(color='darkgray', width=4),
            showlegend=False
        ), row=1, col=col)
        
        # Add water level
        water_depth = depth - design.freeboard_m
        fig.add_trace(go.Scatter3d(
            x=x_outer + [x_outer[0]],
            y=y_outer + [y_outer[0]],
            z=[-water_depth] * (len(x_outer) + 1),
            mode='lines',
            line=dict(color='cyan', width=3, dash='dash'),
            name='Water' if col == 1 else None,
            showlegend=(col == 1)
        ), row=1, col=col)
        
        # Add specs annotation
        specs_text = (f"Volume: {design.storage_volume_m3:.1f}m³<br>"
                     f"Wall: {design.wall_thickness_mm:.0f}mm<br>"
                     f"Cost: ₹{design.total_cost/100000:.1f}L")
        
        fig.add_annotation(
            text=specs_text,
            xref=f"x{col}", yref=f"y{col}",
            x=0, y=radius * 1.5,
            showarrow=False,
            font=dict(size=10),
            bgcolor="rgba(255,255,255,0.8)"
        )
    
    fig.update_layout(
        title_text="<b>GENERATIVE DESIGN COMPARISON</b><br>Each basin uniquely optimized by QCIA",
        title_x=0.5,
        height=600,
        showlegend=True
    )
    
    # Update all 3D scenes
    for i in range(1, 4):
        fig.update_scenes(
            aspectmode='data',
            camera=dict(eye=dict(x=1.5, y=1.5, z=1)),
            **{f'scene{i}': dict()}
        )
    
    output_path = 'engineering_3d_models/variations/comparison.html'
    fig.write_html(output_path)
    print(f"   ✓ Comparison saved: {output_path}")


if __name__ == "__main__":
    designs = generate_variations()
    
    print("\n" + "="*80)
    print("✅ VARIATION GENERATION COMPLETE!")
    print("="*80)
    print("\n💡 Key Points:")
    print("   • Each design is UNIQUE - optimized for its specific requirements")
    print("   • NO templates - dimensions calculated from physics & optimization")
    print("   • Different volumes → completely different geometries")
    print("   • Cost optimized for each individually")
    print("\n📂 Files created:")
    print("   - engineering_3d_models/variations/detention_basin_001_3d.html (150m³)")
    print("   - engineering_3d_models/variations/detention_basin_002_3d.html (300m³)")
    print("   - engineering_3d_models/variations/detention_basin_003_3d.html (500m³)")
    print("   - engineering_3d_models/variations/comparison.html (side-by-side)")
    print("\n🔬 Notice how:")
    print("   • Larger volumes = bigger diameter BUT also optimized depth")
    print("   • Wall thickness varies based on structural needs")
    print("   • Each one has different cost-effectiveness")
    print("\n🚀 This is TRUE generative design - not scaling, not templating!")

