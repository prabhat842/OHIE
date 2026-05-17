from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ohie.validation.boundary_sensitivity import boundary_coefficient_sweep


def main() -> int:
    rows = boundary_coefficient_sweep()
    lines = [
        "# Boundary Sensitivity Results",
        "",
        "| Coefficient | Near-river mean depth (m) | Near-river persistence (s) | Boundary volume (m3) | Mass error |",
        "|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row.coefficient:.1e} | {row.near_river_mean_depth_m:.3f} | {row.near_river_persistence_s:.1f} | {row.boundary_volume_m3:.1f} | {row.mass_error:.6f} |"
        )
    out = Path(__file__).with_name("observed_output.md")
    out.write_text("\n".join(lines) + "\n")
    print(out.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

