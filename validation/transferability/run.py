from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ohie.validation.transferability import run_transferability_study


def main() -> int:
    result = run_transferability_study()
    lines = [
        "# Transferability Results",
        "",
        f"## {result.name}",
        "",
        f"Assumptions: {result.assumptions}",
        f"Limitations: {result.limitations}",
        f"Confidence: {result.confidence}",
        "",
        f"Best default: {result.best_default}",
        "",
        "| Terrain | Coefficient | Grid | Cell size (m) | Mean depth (m) | Persistence (s) | Boundary volume (m3) | Mass error | Flooded cells | Qualitative realism |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in result.rows:
        lines.append(
            f"| {row.terrain} | {row.coefficient:.1e} | {row.grid_shape[0]}x{row.grid_shape[1]} | {row.cell_size_m:.1f} | "
            f"{row.near_river_mean_depth_m:.3f} | {row.near_river_persistence_s:.1f} | {row.boundary_volume_m3:.1f} | "
            f"{row.mass_error:.6f} | {row.flooded_area_cells} | {row.qualitative_realism} |"
        )
    out = Path(__file__).with_name("observed_output.md")
    out.write_text("\n".join(lines) + "\n")
    print(out.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

