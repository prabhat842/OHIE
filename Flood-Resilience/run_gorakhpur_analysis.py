# ==============================================================================
# Project: Gorakhpur Urban Resilience AI
# FILE NAME: run_gorakhpur_analysis.py
# VERSION: 1.0
# PURPOSE: To run the full three-stage urban diagnostics and intervention
#          planning process for the city of Gorakhpur.
# ==============================================================================

import subprocess
import os
import sys
from datetime import datetime

# --- UPDATED Configuration ---
# These now point to our repurposed scripts for urban analysis.
STAGE1_DIAGNOSTICS_SCRIPT = "urban_diagnostics.py"
STAGE15_PRIORITY_ZONES_SCRIPT = "priority_zone_extractor.py"
STAGE2_PLANNER_SCRIPT = "intervention_planner.py"
STAGE3_ENGINEER_SCRIPT = "detailed_engineer.py"

# --- UPDATED Bridge Files ---
# These files now pass urban analysis data between stages, not airport designs.
BRIDGE_DIAGNOSTICS_REPORT = "diagnostics_report.json"     # Output of S1, Input for S1.5 & S3
BRIDGE_PRIORITY_ZONES = "priority_zones_config.json"      # Output of S1.5, Input for S2
BRIDGE_INTERVENTION_PLAN = "intervention_plan.json"      # Output of S2, Input for S3

def main():
    """Main orchestrator function for the three-stage urban analysis pipeline."""
    print("="*80)
    print("🚀 LAUNCHING GORAKHPUR URBAN RESILIENCE AI - THREE-STAGE ANALYSIS")
    print("="*80 + "\n")

    # Create a shared, timestamped output directory for this specific run.
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = f"Outputs/Gorakhpur_Run_{timestamp}"
    os.makedirs(output_dir, exist_ok=True)
    print(f"📁 Created shared output directory for this run: {output_dir}")

    # --- UPDATED Command Structure ---
    # The commands now call our new scripts and pass the correct bridge files.
    scripts = {
        "Stage 1 (Diagnostics Engine)": [sys.executable, STAGE1_DIAGNOSTICS_SCRIPT],
        "Stage 1.5 (Priority Zone Extraction)": [sys.executable, STAGE15_PRIORITY_ZONES_SCRIPT],
        "Stage 2 (Intervention Planner)": [sys.executable, STAGE2_PLANNER_SCRIPT, f"{output_dir}/{BRIDGE_PRIORITY_ZONES}"],
        "Stage 3 (Detailed Engineer)": [sys.executable, STAGE3_ENGINEER_SCRIPT, f"{output_dir}/{BRIDGE_DIAGNOSTICS_REPORT}", f"{output_dir}/{BRIDGE_INTERVENTION_PLAN}"]
    }

    # Set an environment variable so each script knows where to save its output.
    os.environ['GORAKHPUR_OUTPUT_DIR'] = output_dir

    for stage_name, command in scripts.items():
        # Check if the required input files from the previous stage exist before proceeding.
        if stage_name == "Stage 1.5 (Priority Zone Extraction)":
            required_file = f"{output_dir}/{BRIDGE_DIAGNOSTICS_REPORT}"
            if not os.path.exists(required_file):
                print(f"❌ FATAL ERROR: Required input file '{required_file}' for {stage_name} not found. Aborting.")
                return
        elif stage_name == "Stage 2 (Intervention Planner)":
            required_file = f"{output_dir}/{BRIDGE_PRIORITY_ZONES}"
            if not os.path.exists(required_file):
                print(f"❌ FATAL ERROR: Required input file '{required_file}' for {stage_name} not found. Aborting.")
                return
        elif stage_name == "Stage 3 (Detailed Engineer)":
            required_files = [f"{output_dir}/{BRIDGE_DIAGNOSTICS_REPORT}", f"{output_dir}/{BRIDGE_INTERVENTION_PLAN}"]
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
                encoding='utf-8' # Added for better compatibility
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

    print("="*80)
    print("🏆 GORAKHPUR ANALYSIS - FULL PROCESS FINISHED!")
    print(f"All outputs have been saved to: {output_dir}")
    print(f"├── stage1_diagnostics.log - Full district vulnerability analysis")
    print(f"├── priority_zones_config.json - Priority zone identification")
    print(f"├── stage2_planner.log - Genetic algorithm optimization logs")
    print(f"├── stage3_engineer.log - Detailed engineering logs")
    print(f"├── pond_suitability_map.tif - Intervention suitability maps")
    print(f"├── levee_suitability_map.tif - (and bioswale, culvert maps)")
    print(f"├── intervention_plan.kml - KEY OUTPUT: Optimized flood defenses")
    print(f"├── intervention_plan.json - Complete intervention specifications")
    print(f"├── diagnostics_report.json - Stage 1 analysis metadata")
    print(f"└── priority_zone_*.json - Individual zone configurations")
    print("="*80)

if __name__ == "__main__":
    main()