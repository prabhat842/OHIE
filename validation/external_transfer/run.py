from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ohie.validation.external_transfer import run_external_transfer_case


def main() -> int:
    result = run_external_transfer_case()
    lines = [
        "# External Transfer Results",
        "",
        f"## {result.name}",
        "",
        f"Site: {result.site}",
        f"Study window: {result.study_window}",
        f"Dataset: {result.dataset}",
        "",
        f"Assumptions: {result.assumptions}",
        f"Limitations: {result.limitations}",
        f"Confidence: {result.confidence}",
        f"Classification: {result.classification}",
        "",
        "## Baseline",
        f"- boundary_volume_m3: {result.baseline_row['boundary_volume_m3']:.3f}",
        f"- mass_error: {result.baseline_row['mass_error']:.6f}",
        f"- near_edge_mean_depth_m: {result.baseline_row['near_edge_mean_depth_m']:.3f}",
        f"- near_edge_persistence_s: {result.baseline_row['near_edge_persistence_s']:.1f}",
        f"- flooded_area_cells: {int(result.baseline_row['flooded_area_cells'])}",
        "",
        "## Default coefficient (1e-6)",
        f"- boundary_volume_m3: {result.default_row['boundary_volume_m3']:.3f}",
        f"- mass_error: {result.default_row['mass_error']:.6f}",
        f"- near_edge_mean_depth_m: {result.default_row['near_edge_mean_depth_m']:.3f}",
        f"- near_edge_persistence_s: {result.default_row['near_edge_persistence_s']:.1f}",
        f"- flooded_area_cells: {int(result.default_row['flooded_area_cells'])}",
        "",
    ]
    if result.sensitivity_rows:
        lines.extend(
            [
                "## Minimal sensitivity sweep",
                "| Coefficient | Boundary volume (m3) | Mass error | Mean edge depth (m) | Persistence (s) | Flooded cells |",
                "|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for row in result.sensitivity_rows:
            lines.append(
                f"| {row.coefficient:.1e} | {row.boundary_volume_m3:.3f} | {row.mass_error:.6f} | "
                f"{row.near_edge_mean_depth_m:.3f} | {row.near_edge_persistence_s:.1f} | {row.flooded_area_cells} |"
            )
    out = Path(__file__).with_name("observed_output.md")
    out.write_text("\n".join(lines) + "\n")
    print(out.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
