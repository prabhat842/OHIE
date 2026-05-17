from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ohie.validation.sensitivity import run_all_sensitivity


def _row(item):
    if hasattr(item, "__dataclass_fields__"):
        return asdict(item)
    return dict(item)


def main() -> int:
    results = run_all_sensitivity()
    lines = ["# Sensitivity Results", ""]
    all_stable = True
    for group, values in results.items():
        lines.extend([f"## {group}", "", "| Parameter | Value | Max Depth | Flooded Cells / Area Reduction | Volume | Mass Error | Stable |", "|---|---:|---:|---:|---:|---:|---|"])
        for item in values:
            d = _row(item)
            stable = bool(d.get("stable", d.get("mass_error", 0.0) < 0.05))
            all_stable = all_stable and stable
            lines.append(
                f"| {d.get('parameter')} | {d.get('value')} | {d.get('max_depth_m', 0.0):.4f} | "
                f"{d.get('flooded_cells', d.get('flooded_area_reduction_m2', 0.0))} | "
                f"{d.get('volume_m3', d.get('volume_reduction_m3', 0.0)):.3f} | "
                f"{d.get('mass_error', 0.0):.4g} | {'PASS' if stable else 'CHECK'} |"
            )
        lines.append("")
    out = Path(__file__).with_name("observed_output.md")
    out.write_text("\n".join(lines) + "\n")
    print(out.read_text())
    return 0 if all_stable else 1


if __name__ == "__main__":
    raise SystemExit(main())

