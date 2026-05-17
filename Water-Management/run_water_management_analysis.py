# ==============================================================================
# Project: [IWMI] Water Resource Management AI
# FILE NAME: run_water_management_analysis.py
# VERSION: 1.0 (IWMI Adaptation)
# PURPOSE: To run the full multi-stage water resource diagnostics and
#          intervention planning process.
# ==============================================================================

import subprocess
import os
import sys
from datetime import datetime

# --- UPDATED Configuration ---
# <<< ADAPTED >>> Point to our new IWMI-adapted scripts.
STAGE1_DIAGNOSTICS_SCRIPT = "water_resource_diagnostics.py"
STAGE15_PRIORITY_ZONES_SCRIPT = "water_opportunity_extractor.py"
STAGE2_PLANNER_SCRIPT = "water_intervention_planner.py"
STAGE3_ENGINEER_SCRIPT = "detailed_water_engineer.py"

# --- UPDATED Bridge Files ---
# <<< ADAPTED >>> Point to the new config and plan file names.
BRIDGE_DIAGNOSTICS_REPORT = "diagnostics_report.json"     # Output of S1, Input for S1.5 & S3
BRIDGE_PRIORITY_ZONES = "opportunity_zones_config.json"   # Output of S1.5, Input for S2
BRIDGE_INTERVENTION_PLAN = "water_management_plan.json"   # Output of S2, Input for S3

def main():
    """Main orchestrator function for the multi-stage water management pipeline."""
    # <<< ADAPTED >>> Updated print statements
    print("="*80)
    print("🚀 LAUNCHING [IWMI] WATER RESOURCE MANAGEMENT AI - MULTI-STAGE ANALYSIS")
    print("="*80 + "\n")

    # <<< ADAPTED >>> Updated default directory name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = f"Outputs/Water_Run_{timestamp}"
    os.makedirs(output_dir, exist_ok=True)
    print(f"📁 Created shared output directory for this run: {output_dir}")

    # --- UPDATED Command Structure ---
    # <<< ADAPTED >>> Commands now call our new scripts and pass the new bridge files.
    scripts = {
        "Stage 1 (Water Diagnostics Engine)": [sys.executable, STAGE1_DIAGNOSTICS_SCRIPT],
        "Stage 1.5 (Opportunity Zone Extraction)": [sys.executable, STAGE15_PRIORITY_ZONES_SCRIPT],
        "Stage 2 (Water Intervention Planner)": [sys.executable, STAGE2_PLANNER_SCRIPT, f"{output_dir}/{BRIDGE_PRIORITY_ZONES}"],
        "Stage 3 (Detailed Water Engineer)": [sys.executable, STAGE3_ENGINEER_SCRIPT, f"{output_dir}/{BRIDGE_DIAGNOSTICS_REPORT}", f"{output_dir}/{BRIDGE_INTERVENTION_PLAN}"]
    }

    # Set an environment variable so each script knows where to save its output.
    # <<< ADAPTED >>> The environment variable name is kept the same for compatibility.
    os.environ['GORAKHPUR_OUTPUT_DIR'] = output_dir

    for stage_name, command in scripts.items():
        # Check if the required input files from the previous stage exist before proceeding.
        if stage_name == "Stage 1.5 (Opportunity Zone Extraction)":
            required_file = f"{output_dir}/{BRIDGE_DIAGNOSTICS_REPORT}"
            if not os.path.exists(required_file):
                print(f"❌ FATAL ERROR: Required input file '{required_file}' for {stage_name} not found. Aborting.")
                return
        elif stage_name == "Stage 2 (Water Intervention Planner)":
            required_file = f"{output_dir}/{BRIDGE_PRIORITY_ZONES}"
            if not os.path.exists(required_file):
                print(f"❌ FATAL ERROR: Required input file '{required_file}' for {stage_name} not found. Aborting.")
                return
        elif stage_name == "Stage 3 (Detailed Water Engineer)":
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
    print("🏆 WATER MANAGEMENT ANALYSIS - FULL PROCESS FINISHED!")
    print(f"All outputs have been saved to: {output_dir}")
    print(f"├── stage1_diagnostics.log - Water resource atlas generation logs")
    print(f"├── opportunity_zones_config.json - Priority zone identification")
    print(f"├── stage2_planner.log - Genetic algorithm optimization logs")
    print(f"├── stage3_engineer.log - Detailed engineering logs (HRF solver)")
    print(f"├── harvesting_pond_suitability.tif - Intervention suitability maps")
    print(f"├── recharge_structure_suitability.tif - (and NbS, pump maps)")
    print(f"├── water_management_plan.kml - KEY OUTPUT: Optimized water infrastructure")
    print(f"├── water_management_plan.json - Complete intervention specifications")
    print(f"├── water_engineered_solution.glb - KEY OUTPUT: 3D model for engineering")
    print(f"├── diagnostics_report.json - Stage 1 analysis metadata")
    print(f"└── opportunity_zone_*.json - Individual zone configurations")
    print("="*80)

if __name__ == "__main__":
    main()