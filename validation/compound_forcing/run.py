from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ohie.validation.compound_forcing import compare_overwrite_vs_flux_coupling


def main() -> int:
    result = compare_overwrite_vs_flux_coupling()
    lines = [
        "# Compound Forcing Comparison",
        "",
        f"## {result.name}",
        "",
        f"Assumptions: {result.assumptions}",
        f"Limitations: {result.limitations}",
        f"Confidence: {result.confidence}",
        "",
        "| Mode | Observed |",
        "|---|---|",
        f"| overwrite-style boundary | {result.overwrite_observed} |",
        f"| flux-coupled boundary | {result.flux_observed} |",
        "",
        "| Comparison | Value |",
        "|---|---:|",
    ]
    for key, value in result.comparison.items():
        lines.append(f"| {key} | {value:.6g} |")
    out = Path(__file__).with_name("observed_output.md")
    out.write_text("\n".join(lines) + "\n")
    print(out.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

