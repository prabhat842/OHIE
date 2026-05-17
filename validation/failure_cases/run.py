from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ohie.validation.failure_cases import run_all_failure_cases


def main() -> int:
    results = run_all_failure_cases()
    lines = [
        "# Failure Case Suite",
        "",
        "| Case | Failure Mode | Why Not Trust | Observed | Confidence Limit |",
        "|---|---|---|---|---|",
    ]
    for item in results:
        lines.append(
            f"| {item.case} | {item.failure_mode} | {item.why_not_trust} | {item.observed} | {item.confidence_limit} |"
        )
    out = Path(__file__).with_name("observed_output.md")
    out.write_text("\n".join(lines) + "\n")
    print(out.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

