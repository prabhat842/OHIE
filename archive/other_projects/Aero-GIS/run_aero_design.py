# ==============================================================================
# Project: AeroGis - Design AI Orchestrator
# FILE NAME: run_aero_design.py
# VERSION: 3.0 (Three-Stage Pipeline)
# PURPOSE: To run the full three-stage airport design process.
# ==============================================================================

import subprocess
import os
import sys

# --- Configuration ---
STAGE1_SELECTOR_SCRIPT = "airport_selector.py"
STAGE2_ARCHITECT_SCRIPT = "genetic_designer.py"
STAGE3_ENGINEER_SCRIPT = "bioswale_designer.py"

# --- Intermediate files used as a bridge between stages ---
BRIDGE_SITE_DETAILS = "site_details.json"       # Output of S1, Input for S2
BRIDGE_OPTIMAL_LAYOUT = "optimal_layout.json"   # Output of S2, Input for S3

# This file is created by S1 but no longer used by the pipeline.
# It is kept for manual inspection/debugging if needed.
BRIDGE_DEM_FILE = "selected_site.tif"

def main():
    """Main orchestrator function for the three-stage pipeline."""
    print("="*80)
    print("🚀 LAUNCHING AeroGis AI THREE-STAGE DESIGN PROCESS")
    print("="*80 + "\n")

    # Create shared output directory for this run
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = f"Outputs/Run_{timestamp}"
    os.makedirs(output_dir, exist_ok=True)
    print(f"📁 Created shared output directory: {output_dir}")

    scripts = {
        "Stage 1 (Selector)": [sys.executable, STAGE1_SELECTOR_SCRIPT],
        "Stage 2 (Architect)": [sys.executable, STAGE2_ARCHITECT_SCRIPT, f"{output_dir}/site_details.json"],
        "Stage 3 (Engineer)": [sys.executable, STAGE3_ENGINEER_SCRIPT, f"{output_dir}/site_details.json", f"{output_dir}/optimal_layout.json"]
    }

    # Set environment variable for output directory so stages know where to save files
    os.environ['AEROGIS_OUTPUT_DIR'] = output_dir

    for stage_name, command in scripts.items():
        # Before running Stage 2/3, check if the required input file from the previous stage exists
        if stage_name == "Stage 2 (Architect)":
            required_file = f"{output_dir}/site_details.json"
            if not os.path.exists(required_file):
                print(f"❌ FATAL ERROR: Required input file '{required_file}' for {stage_name} not found. Aborting.")
                return
        elif stage_name == "Stage 3 (Engineer)":
            required_files = [f"{output_dir}/site_details.json", f"{output_dir}/optimal_layout.json"]
            for required_file in required_files:
                if not os.path.exists(required_file):
                    print(f"❌ FATAL ERROR: Required input file '{required_file}' for {stage_name} not found. Aborting.")
                    return

        print("\n" + "-"*30 + f"\n▶️ EXECUTING {stage_name}\n" + "-"*30)
        try:
            process = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True
            )
            print(process.stdout)
            if process.stderr:
                print(f"--- {stage_name} ERRORS ---")
                print(process.stderr)
            print(f"\n✅ {stage_name} COMPLETED SUCCESSFULLY.\n")

        except FileNotFoundError:
            print(f"❌ FATAL ERROR: The script '{command[1]}' for {stage_name} was not found.")
            return
        except subprocess.CalledProcessError as e:
            print(f"❌ FATAL ERROR: {stage_name} script '{command[1]}' failed with exit code {e.returncode}.")
            print("\n--- STDOUT ---")
            print(e.stdout)
            print("\n--- STDERR ---")
            print(e.stderr)
            return

    print("="*80)
    print("🏆 AeroGis AI Full Design Process Finished!")
    print(f"All outputs saved to: {output_dir}")
    print(f"├── stage1_selector.log - Site selection logs")
    print(f"├── stage2_architect.log - Layout design logs")
    print(f"├── stage3_engineer.log - Flood defense logs")
    print(f"├── stakeholder_report.png - Site selection map")
    print(f"├── 3d_excavation_report.png - Earthworks visualization")
    print(f"├── final_airport_design.kml - Airport layout (Google Earth)")
    print(f"├── flood_defense_3d_report_with_layout.png - Flood defense design")
    print(f"├── final_airport_design.glb - 3D CAD model")
    print(f"├── site_details.json - Site metadata")
    print(f"├── optimal_layout.json - Airport layout configuration")
    print(f"└── selected_site.tif - Selected site DEM")
    print("="*80)

if __name__ == "__main__":
    try:
        main()
    finally:
        # Note: Bridge files are now saved in timestamped output directories
        # and are kept for inspection/debugging
        print("\n✅ Pipeline execution complete. Bridge files preserved in output directories.")