from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ohie.validation.analytical import run_all_analytical_validations


def main() -> int:
    results = run_all_analytical_validations()
    lines = [
        "# Analytical Validation Results",
        "",
        "| Test | Expected | Observed | Pass/Fail |",
        "|---|---|---|---|",
    ]
    for item in results:
        status = "PASS" if item.passed else "FAIL"
        lines.append(f"| {item.test} | {item.expected} | {item.observed} | {status} |")
    out = Path(__file__).with_name("observed_output.md")
    out.write_text("\n".join(lines) + "\n")
    print(out.read_text())
    return 0 if all(item.passed for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

