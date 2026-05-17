"""
CAD Drawing Viewer

Renders DXF files to PNG images for visualization.
Shows what the generated CAD drawings look like.
"""

import ezdxf
from ezdxf.addons.drawing import RenderContext, Frontend
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
import matplotlib.pyplot as plt
from pathlib import Path
import sys


def render_dxf_to_image(dxf_path: str, output_path: str = None, dpi: int = 300):
    """
    Render a DXF file to PNG image.
    
    Args:
        dxf_path: Path to DXF file
        output_path: Output PNG path (if None, auto-generated)
        dpi: Resolution (higher = better quality)
    """
    # Load DXF
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    
    # Auto-generate output path if not provided
    if output_path is None:
        output_path = str(Path(dxf_path).with_suffix('.png'))
    
    # Setup rendering
    fig = plt.figure(figsize=(20, 14))
    ax = fig.add_axes([0, 0, 1, 1])
    ctx = RenderContext(doc)
    out = MatplotlibBackend(ax)
    
    # Render
    Frontend(ctx, out).draw_layout(msp, finalize=True)
    
    # Save
    fig.savefig(output_path, dpi=dpi, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    
    print(f"   ✓ Rendered: {output_path}")
    return output_path


def view_all_drawings(drawings_dir: str = 'engineering_drawings'):
    """Render all DXF files in directory to PNG"""
    drawings_path = Path(drawings_dir)
    
    if not drawings_path.exists():
        print(f"❌ Directory not found: {drawings_dir}")
        return
    
    dxf_files = list(drawings_path.glob('*.dxf'))
    
    if not dxf_files:
        print(f"❌ No DXF files found in {drawings_dir}")
        return
    
    print(f"\n🎨 Rendering {len(dxf_files)} CAD drawings...\n")
    
    rendered_files = []
    for dxf_file in sorted(dxf_files):
        print(f"📐 Rendering {dxf_file.name}...")
        try:
            output_path = render_dxf_to_image(str(dxf_file))
            rendered_files.append(output_path)
        except Exception as e:
            print(f"   ⚠️  Error: {e}")
    
    return rendered_files


if __name__ == "__main__":
    print("="*80)
    print("CAD DRAWING VIEWER")
    print("="*80)
    
    rendered = view_all_drawings('engineering_drawings')
    
    if rendered:
        print("\n" + "="*80)
        print("✅ RENDERING COMPLETE!")
        print("="*80)
        print(f"\n📁 Rendered {len(rendered)} drawings to PNG:")
        for img in rendered:
            print(f"   - {img}")
        print("\n💡 You can now open these PNG files to see the CAD drawings!")
        print("   The images show exactly what contractors would see in AutoCAD.")
    else:
        print("\n❌ No drawings were rendered.")

