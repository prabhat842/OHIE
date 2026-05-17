import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from ohie.validation.real_terrain import river_adjacent_case


if __name__ == "__main__":
    result = river_adjacent_case()
    print(result.name)
    print(result.observed)
    for key, value in result.metrics.items():
        print(f"{key}: {value}")
