from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from ohie.validation.historical.benchmarks import yamuna_boundary_approximation


def main() -> int:
    result = yamuna_boundary_approximation()
    lines = [
        "# Yamuna Approximate Boundary Benchmark",
        "",
        f"Inputs: {result.inputs}",
        "",
        f"Assumptions: {result.assumptions}",
        "",
        f"Known limitations: {result.limitations}",
        "",
        f"Observed outputs: {result.observed}",
        "",
        "## Metrics",
    ]
    for key, value in result.metrics.items():
        lines.append(f"- {key}: {value}")
    out = Path(__file__).with_name("observed_output.md")
    out.write_text("\n".join(lines) + "\n")
    print(out.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

