from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ohie.benchmarks import compare_d8_dinfinity, run_flat_bowl_benchmark


def main() -> None:
    print(run_flat_bowl_benchmark())
    print(compare_d8_dinfinity())


if __name__ == "__main__":
    main()

