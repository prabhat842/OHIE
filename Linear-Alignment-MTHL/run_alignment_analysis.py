# ==============================================================================
# Project: Culturiq AI-Driven Infrastructure
# FILE NAME: run_alignment_analysis.py
# VERSION: 1.0 (Adapted from run_gorakhpur_analysis.py)
# PURPOSE: To run the full three-stage alignment optimization pipeline for
#          linear infrastructure (roads, rail, pipelines) in complex terrain.
# ==============================================================================

import subprocess
import os
import sys
from datetime import datetime

# --- UPDATED Configuration ---
# <<< ADAPTED >>> Renamed scripts for the alignment task.
STAGE1_ATLAS_SCRIPT = "alignment_diagnostics.py"
# <<< REMOVED >>> Stage 1.5 (Priority Zone Extraction) is not needed for this pipeline.
STAGE2_PLANNER_SCRIPT = "alignment_planner.py"
STAGE3_VALIDATOR_SCRIPT = "alignment_validator.py"

# --- UPDATED Bridge Files ---
# <<< ADAPTED >>> Renamed bridge files for clarity.
BRIDGE_COST_ATLAS = "cost_atlas_report.json"      # Output of S1, Input for S2 & S3
BRIDGE_ALIGNMENT_PLAN = "alignment_plan.json"       # Output of S2, Input for S3

def main():
    """Main orchestrator function for the three-stage alignment pipeline."""
    # <<< ADAPTED >>> Updated print title
    print("="*80)
    print("🚀 LAUNCHING AI-DRIVEN ALIGNMENT GENERATOR - THREE-STAGE ANALYSIS")
    print("="*80 + "\n")

    # Create a shared, timestamped output directory for this specific run.
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = f"Outputs/Alignment_Run_{timestamp}"
    os.makedirs(output_dir, exist_ok=True)
    print(f"📁 Created shared output directory for this run: {output_dir}")

    # --- UPDATED Command Structure ---
    # <<< ADAPTED >>> Removed Stage 1.5, updated S2 and S3 command arguments.
    scripts = {
        "Stage 1 (Cost Atlas Generator)": [sys.executable, STAGE1_ATLAS_SCRIPT],
        "Stage 2 (Alignment Planner)": [sys.executable, STAGE2_PLANNER_SCRIPT, f"{output_dir}/{BRIDGE_COST_ATLAS}"],
        "Stage 3 (Alignment Validator)": [sys.executable, STAGE3_VALIDATOR_SCRIPT, f"{output_dir}/{BRIDGE_COST_ATLAS}", f"{output_dir}/{BRIDGE_ALIGNMENT_PLAN}"]
    }

    # Set an environment variable so each script knows where to save its output.
    # <<< ADAPTED >>> Renamed environment variable
    os.environ['PIPELINE_OUTPUT_DIR'] = output_dir

    for stage_name, command in scripts.items():
        # Check if the required input files from the previous stage exist before proceeding.
        if stage_name == "Stage 2 (Alignment Planner)":
            required_file = f"{output_dir}/{BRIDGE_COST_ATLAS}"
            if not os.path.exists(required_file):
                print(f"❌ FATAL ERROR: Required input file '{required_file}' for {stage_name} not found. Aborting.")
                return
        elif stage_name == "Stage 3 (Alignment Validator)":
            required_files = [f"{output_dir}/{BRIDGE_COST_ATLAS}", f"{output_dir}/{BRIDGE_ALIGNMENT_PLAN}"]
            for file in required_files:
                if not os.path.exists(file):
                    print(f"❌ FATAL ERROR: Required input file '{file}' for {stage_name} not found. Aborting.")
                    return

        print("\n" + "-"*30 + f"\n▶️ EXECUTING {stage_name}\n" + "-"*30)
        try:
            # Execute the script as a subprocess.
            process = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                encoding='utf-8'
            )
            print(process.stdout)
            if process.stderr:
                print(f"--- {stage_name} WARNINGS/ERRORS ---")
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

    # <<< ADAPTED >>> Updated final report
    print("="*80)
    print("🏆 ALIGNMENT ANALYSIS - FULL PROCESS FINISHED!")
    print(f"All outputs have been saved to: {output_dir}")
    print(f"├── stage1_diagnostics.log - Cost atlas generation logs")
    print(f"├── stage2_planner.log - Genetic algorithm (GA) alignment logs")
    print(f"├── stage3_validator.log - Physics-based validation logs (HRF solver)")
    print(f"├── earthworks_cost_atlas.tif - Cost/Risk Atlas maps")
    print(f"├── vegetation_cost_atlas.tif - (and hydrology, exclusion maps)")
    print(f"├── alignment_visualization.png - KEY OUTPUT: Visual alignment map")
    print(f"├── alignment_plan.kml - Top 5 optimized alignments (Google Earth)")
    print(f"├── alignment_plan.shp - Top 5 optimized alignments (ArcGIS/QGIS)")
    print(f"├── alignment_plan.json - Complete alignment specifications")
    print(f"├── alignment_validation.kml - Validated alignments (Google Earth)")
    print(f"├── alignment_validation.shp - Validated alignments (ArcGIS/QGIS)")
    print(f"├── alignment_validation.glb - KEY OUTPUT: 3D model for engineering")
    print(f"└── cost_atlas_report.json - Stage 1 analysis metadata")
    print("="*80)

if __name__ == "__main__":
    main()