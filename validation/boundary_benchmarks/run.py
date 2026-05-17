from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ohie.validation.boundary_benchmarks import stage_response_benchmark


def main() -> int:
    result = stage_response_benchmark()
    lines = [
        "# Boundary Benchmark Results",
        "",
        f"## {result.name}",
        "",
        f"Assumptions: {result.assumptions}",
        f"Limitations: {result.limitations}",
        f"Confidence: {result.confidence}",
        "",
        f"Expected behavior: {result.expected_behavior}",
        f"Observed behavior: {result.observed_behavior}",
        "",
        "| Stage (m) | Boundary | Near-river mean depth (m) | Near-river persistence (s) | Mass error |",
        "|---:|---|---:|---:|---:|",
    ]
    for row in result.rows:
        lines.append(
            f"| {row.stage_m:.3f} | {row.boundary_type} | {row.near_river_mean_depth_m:.3f} | {row.near_river_persistence_s:.1f} | {row.mass_error:.6f} |"
        )
    out = Path(__file__).with_name("observed_output.md")
    out.write_text("\n".join(lines) + "\n")
    print(out.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

