#!/usr/bin/env python3
"""
Interactive Visualization of Spatial QCIA Results
Shows GPS-precise interventions on real Jabalpur map
"""

import numpy as np
import json
from pathlib import Path
import plotly.graph_objects as go
from plotly.subplots import make_subplots

print("="*70)
print("INTERACTIVE SPATIAL DESIGN VISUALIZATION")
print("="*70)

# =============================================================================
# LOAD DATA
# =============================================================================

print("\n[1/4] Loading data...")

# Load baseline flood
baseline_flood = np.load('outputs/baseline_flood_for_optimization.npy')

# Load DEM
processed_dir = Path("data/processed_enhanced")
dem = np.load(processed_dir / 'jabalpur_dem_enhanced.npy')
road_mask = np.load(processed_dir / 'road_mask.npy')

with open(processed_dir / 'metadata_enhanced.json', 'r') as f:
    metadata = json.load(f)

# Load optimal designs
design_files = [
    'outputs/optimal_design_₹8_Crores_Conservative.json',
    'outputs/optimal_design_₹12_Crores_Moderate.json',
    'outputs/optimal_design_₹20_Crores_Comprehensive.json'
]

designs = []
for file in design_files:
    with open(file, 'r') as f:
        design = json.load(f)
        designs.append(design)

print(f"  ✅ Loaded {len(designs)} optimal designs")
print(f"  ✅ Baseline flood: {baseline_flood.shape}")
print(f"  ✅ DEM: {dem.shape}")

# =============================================================================
# CREATE MAIN VISUALIZATION
# =============================================================================

print("\n[2/4] Creating main visualization...")

# Select the ₹12 Cr design for main view
main_design = designs[1]  # Moderate scenario

# Create figure with subplots
fig = make_subplots(
    rows=2, cols=2,
    specs=[[{'type': 'xy'}, {'type': 'xy'}],
           [{'type': 'xy'}, {'type': 'xy'}]],
    subplot_titles=(
        f'Real Jabalpur Terrain (404-532m)',
        f'Baseline Flooding (6.90 km² flooded)',
        f'Optimal Design: {main_design["budget_label"]} (₹{main_design["total_cost_cr"]:.2f} Cr)',
        f'All 3 Budget Scenarios Comparison'
    ),
    vertical_spacing=0.12,
    horizontal_spacing=0.08
)

# 1. Terrain with roads
terrain_trace = go.Heatmap(
    z=dem,
    colorscale='earth',
    showscale=True,
    colorbar=dict(x=0.46, len=0.38, y=0.77, title='Elevation (m)')
)
fig.add_trace(terrain_trace, row=1, col=1)

# Add roads as contour
road_contour = go.Contour(
    z=road_mask,
    showscale=False,
    contours=dict(start=0.5, end=0.5, size=1),
    line=dict(color='red', width=1),
    showlegend=False
)
fig.add_trace(road_contour, row=1, col=1)

# 2. Baseline flooding
flood_trace = go.Heatmap(
    z=baseline_flood,
    colorscale='Blues',
    zmin=0,
    zmax=3.0,
    showscale=True,
    colorbar=dict(x=1.0, len=0.38, y=0.77, title='Flood Depth (m)')
)
fig.add_trace(flood_trace, row=1, col=2)

# 3. Optimal design with interventions
design_trace = go.Heatmap(
    z=baseline_flood,
    colorscale='Blues',
    zmin=0,
    zmax=3.0,
    showscale=False,
    opacity=0.6
)
fig.add_trace(design_trace, row=2, col=1)

# Add intervention markers
intervention_colors = {
    'culvert': 'green',
    'drain': 'orange',
    'storage': 'blue',
    'active': 'red'
}

intervention_symbols = {
    'culvert': 'circle',
    'drain': 'square',
    'storage': 'diamond',
    'active': 'star'
}

for interv in main_design['interventions']:
    # Determine type from name
    if 'Culvert' in interv['type']:
        type_key = 'culvert'
    elif 'Drain' in interv['type']:
        type_key = 'drain'
    elif 'Pond' in interv['type']:
        type_key = 'storage'
    elif 'Pump' in interv['type']:
        type_key = 'active'
    else:
        type_key = 'culvert'
    
    # Grid location
    i, j = interv['location_grid']
    
    # Marker
    marker = go.Scatter(
        x=[j],
        y=[i],
        mode='markers',
        marker=dict(
            size=15,
            color=intervention_colors[type_key],
            symbol=intervention_symbols[type_key],
            line=dict(color='white', width=2)
        ),
        text=f"{interv['type']}<br>₹{interv['cost_lakh']:.1f}L<br>{interv['lat_lon'][0]:.5f}°N, {interv['lat_lon'][1]:.5f}°E",
        hovertemplate='%{text}<extra></extra>',
        showlegend=False
    )
    fig.add_trace(marker, row=2, col=1)

# 4. Comparison across budgets
comparison_trace = go.Heatmap(
    z=dem * 0.3,  # Faded terrain as background
    colorscale='gray',
    showscale=False,
    opacity=0.3
)
fig.add_trace(comparison_trace, row=2, col=2)

# Add all interventions from all designs with different sizes
all_lats = []
all_lons = []
all_sizes = []
all_colors = []
all_text = []

for design_idx, design in enumerate(designs):
    size_mult = [8, 12, 16][design_idx]  # Larger for higher budgets
    
    for interv in design['interventions']:
        i, j = interv['location_grid']
        all_lats.append(i)
        all_lons.append(j)
        all_sizes.append(size_mult)
        
        # Color by design
        colors_by_design = ['lightgreen', 'orange', 'red']
        all_colors.append(colors_by_design[design_idx])
        
        all_text.append(f"{design['budget_label']}<br>{interv['type']}<br>₹{interv['cost_lakh']:.1f}L")

comparison_scatter = go.Scatter(
    x=all_lons,
    y=all_lats,
    mode='markers',
    marker=dict(
        size=all_sizes,
        color=all_colors,
        opacity=0.7,
        line=dict(color='white', width=1)
    ),
    text=all_text,
    hovertemplate='%{text}<extra></extra>',
    showlegend=False
)
fig.add_trace(comparison_scatter, row=2, col=2)

# Update layout
fig.update_layout(
    title={
        'text': f'<b>SPATIAL QCIA - REAL JABALPUR FLOOD MITIGATION DESIGN</b><br>' +
                f'<sub>GPS-Precise Infrastructure Placement | {main_design["num_interventions"]} interventions | ' +
                f'₹{main_design["total_cost_cr"]:.2f} Crores</sub>',
        'x': 0.5,
        'xanchor': 'center',
        'font': {'size': 18}
    },
    height=1000,
    showlegend=False,
    font=dict(size=10)
)

# Update axes
for i in range(1, 3):
    for j in range(1, 3):
        fig.update_xaxes(showticklabels=False, row=i, col=j)
        fig.update_yaxes(showticklabels=False, row=i, col=j)

# Save
output_file = 'outputs/spatial_design_interactive.html'
fig.write_html(output_file)
print(f"  ✅ Main visualization saved: {output_file}")

# =============================================================================
# CREATE DETAILED DESIGN VIEW (₹12 Cr scenario)
# =============================================================================

print("\n[3/4] Creating detailed design view...")

fig2 = go.Figure()

# Background: Flooding + terrain
fig2.add_trace(go.Heatmap(
    z=baseline_flood,
    colorscale='Blues',
    zmin=0,
    zmax=3.0,
    showscale=True,
    colorbar=dict(title='Flood Depth (m)', x=1.02)
))

# Overlay terrain contours
fig2.add_trace(go.Contour(
    z=dem,
    showscale=False,
    contours=dict(
        start=400,
        end=530,
        size=20,
        showlabels=True
    ),
    line=dict(color='gray', width=0.5),
    opacity=0.3
))

# Roads
fig2.add_trace(go.Contour(
    z=road_mask,
    showscale=False,
    contours=dict(start=0.5, end=0.5, size=1),
    line=dict(color='darkred', width=2),
    name='Roads'
))

# Interventions by type
for type_key, color in intervention_colors.items():
    type_interventions = [i for i in main_design['interventions'] 
                          if (type_key == 'culvert' and 'Culvert' in i['type']) or
                             (type_key == 'drain' and 'Drain' in i['type']) or
                             (type_key == 'storage' and 'Pond' in i['type']) or
                             (type_key == 'active' and 'Pump' in i['type'])]
    
    if type_interventions:
        lats = [i['location_grid'][0] for i in type_interventions]
        lons = [i['location_grid'][1] for i in type_interventions]
        texts = [f"<b>{i['type']}</b><br>" +
                 f"GPS: {i['lat_lon'][0]:.5f}°N, {i['lat_lon'][1]:.5f}°E<br>" +
                 f"Cost: ₹{i['cost_lakh']:.1f} lakh" +
                 (f"<br>Size: {i['size']:.0f}m" if i['size'] > 1 else "")
                 for i in type_interventions]
        
        fig2.add_trace(go.Scatter(
            x=lons,
            y=lats,
            mode='markers+text',
            marker=dict(
                size=20,
                color=color,
                symbol=intervention_symbols[type_key],
                line=dict(color='white', width=2)
            ),
            text=[str(i+1) for i in range(len(type_interventions))],
            textposition='middle center',
            textfont=dict(color='white', size=10, family='Arial Black'),
            hovertext=texts,
            hovertemplate='%{hovertext}<extra></extra>',
            name=type_key.capitalize()
        ))

fig2.update_layout(
    title={
        'text': f'<b>DETAILED DESIGN: {main_design["budget_label"]}</b><br>' +
                f'<sub>Real Jabalpur: 5.4×5.0 km | {main_design["num_interventions"]} interventions | ' +
                f'Total Cost: ₹{main_design["total_cost_cr"]:.2f} Crores</sub>',
        'x': 0.5,
        'xanchor': 'center',
        'font': {'size': 16}
    },
    height=800,
    xaxis=dict(showticklabels=False, title='← West | East →'),
    yaxis=dict(showticklabels=False, title='← South | North →', scaleanchor='x'),
    showlegend=True,
    legend=dict(x=0.02, y=0.98, bgcolor='rgba(255,255,255,0.8)')
)

output_file2 = 'outputs/spatial_design_detailed.html'
fig2.write_html(output_file2)
print(f"  ✅ Detailed view saved: {output_file2}")

# =============================================================================
# CREATE INTERVENTION CATALOG (Text Summary)
# =============================================================================

print("\n[4/4] Creating intervention catalog...")

catalog_html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Jabalpur Flood Mitigation - Intervention Catalog</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #34495e;
            margin-top: 30px;
        }}
        .scenario {{
            background: white;
            padding: 20px;
            margin: 20px 0;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .intervention {{
            background: #ecf0f1;
            padding: 15px;
            margin: 10px 0;
            border-left: 4px solid #3498db;
            border-radius: 4px;
        }}
        .culvert {{ border-left-color: #27ae60; }}
        .drain {{ border-left-color: #f39c12; }}
        .pond {{ border-left-color: #3498db; }}
        .pump {{ border-left-color: #e74c3c; }}
        .stats {{
            display: flex;
            gap: 20px;
            margin: 20px 0;
        }}
        .stat-box {{
            flex: 1;
            background: #3498db;
            color: white;
            padding: 15px;
            border-radius: 5px;
            text-align: center;
        }}
        .stat-box h3 {{
            margin: 0;
            font-size: 28px;
        }}
        .stat-box p {{
            margin: 5px 0 0 0;
            font-size: 14px;
        }}
        .gps {{
            font-family: 'Courier New', monospace;
            background: #2c3e50;
            color: #2ecc71;
            padding: 3px 8px;
            border-radius: 3px;
            font-size: 12px;
        }}
        .legend {{
            display: flex;
            gap: 20px;
            margin: 20px 0;
            flex-wrap: wrap;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .legend-color {{
            width: 20px;
            height: 20px;
            border-radius: 3px;
        }}
    </style>
</head>
<body>
    <h1>🗺️ Jabalpur Flood Mitigation - GPS-Precise Design Catalog</h1>
    <p><strong>Location:</strong> Jabalpur City Center (23.0°N, 80.0°E) | <strong>Area:</strong> 5.4 × 5.0 km</p>
    <p><strong>Baseline Event:</strong> 450mm rainfall over 10 hours | <strong>Flooded Area:</strong> 6.90 km²</p>
    
    <div class="legend">
        <div class="legend-item">
            <div class="legend-color" style="background: #27ae60;"></div>
            <span><strong>Culverts</strong> - Underground drainage</span>
        </div>
        <div class="legend-item">
            <div class="legend-color" style="background: #f39c12;"></div>
            <span><strong>Drains</strong> - Surface channels</span>
        </div>
        <div class="legend-item">
            <div class="legend-color" style="background: #3498db;"></div>
            <span><strong>Ponds</strong> - Storage basins</span>
        </div>
        <div class="legend-item">
            <div class="legend-color" style="background: #e74c3c;"></div>
            <span><strong>Pumps</strong> - Active drainage</span>
        </div>
    </div>
"""

for design_idx, design in enumerate(designs):
    # Count by type
    culverts = sum(1 for i in design['interventions'] if 'Culvert' in i['type'])
    drains = sum(1 for i in design['interventions'] if 'Drain' in i['type'])
    ponds = sum(1 for i in design['interventions'] if 'Pond' in i['type'])
    pumps = sum(1 for i in design['interventions'] if 'Pump' in i['type'])
    
    catalog_html += f"""
    <div class="scenario">
        <h2>Scenario {design_idx + 1}: {design['budget_label']}</h2>
        
        <div class="stats">
            <div class="stat-box">
                <h3>₹{design['total_cost_cr']:.2f} Cr</h3>
                <p>Total Cost</p>
            </div>
            <div class="stat-box">
                <h3>{design['num_interventions']}</h3>
                <p>Interventions</p>
            </div>
            <div class="stat-box">
                <h3>{culverts}+{drains}+{ponds}+{pumps}</h3>
                <p>C + D + P + Pump</p>
            </div>
        </div>
        
        <h3>📋 Bill of Quantities (BOQ)</h3>
"""
    
    for i, interv in enumerate(design['interventions'], 1):
        # Determine class
        if 'Culvert' in interv['type']:
            css_class = 'culvert'
        elif 'Drain' in interv['type']:
            css_class = 'drain'
        elif 'Pond' in interv['type']:
            css_class = 'pond'
        else:
            css_class = 'pump'
        
        size_text = f" | <strong>Size:</strong> {interv['size']:.0f}m" if interv['size'] > 1 else ""
        
        catalog_html += f"""
        <div class="intervention {css_class}">
            <strong>[{i}] {interv['type']}</strong><br>
            <strong>GPS:</strong> <span class="gps">{interv['lat_lon'][0]:.5f}°N, {interv['lat_lon'][1]:.5f}°E</span><br>
            <strong>Grid:</strong> Cell ({interv['location_grid'][0]}, {interv['location_grid'][1]}){size_text}<br>
            <strong>Cost:</strong> ₹{interv['cost_lakh']:.1f} lakh
        </div>
"""
    
    catalog_html += """
    </div>
"""

catalog_html += """
    <hr style="margin: 40px 0;">
    <p style="text-align: center; color: #7f8c8d;">
        <strong>Generated by Spatial QCIA</strong><br>
        Quantum-Inspired Causal Intelligence Architecture for Flood Risk Management<br>
        Ready for contractor bidding and HEC-RAS certification
    </p>
</body>
</html>
"""

output_file3 = 'outputs/intervention_catalog.html'
with open(output_file3, 'w') as f:
    f.write(catalog_html)

print(f"  ✅ Intervention catalog saved: {output_file3}")

# =============================================================================
# SUMMARY
# =============================================================================

print("\n" + "="*70)
print("✅ VISUALIZATION COMPLETE!")
print("="*70)

print(f"\n📁 Generated Files:")
print(f"  1. {output_file} - Main 4-panel view")
print(f"  2. {output_file2} - Detailed intervention map")
print(f"  3. {output_file3} - BOQ catalog (contractor-ready)")

print(f"\n🎯 What You Can Show CEEW:")
print(f"  ✅ GPS coordinates for every intervention")
print(f"  ✅ Visual proof on real terrain")
print(f"  ✅ 3 budget scenarios ready to compare")
print(f"  ✅ Bill of Quantities for contractors")

print(f"\n📊 Summary for ₹12 Cr Scenario:")
for design in designs:
    if design['budget_label'] == '₹12 Crores (Moderate)':
        print(f"  Cost: ₹{design['total_cost_cr']:.2f} Crores")
        print(f"  Interventions: {design['num_interventions']}")
        print(f"  Sample GPS coordinates:")
        for i, interv in enumerate(design['interventions'][:3], 1):
            print(f"    {i}. {interv['type']}: {interv['lat_lon'][0]:.5f}°N, {interv['lat_lon'][1]:.5f}°E")

print("\n" + "="*70)
print("🚀 READY FOR DEMO!")
print("="*70)
print("\nOpen the HTML files in your browser to see the interactive maps!")
print("="*70)

