import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ohie.validation.literature import literature_behavior_table


if __name__ == "__main__":
    for row in literature_behavior_table():
        print(row.benchmark)
        print(f"  literature: {row.literature_behavior}")
        print(f"  ohie: {row.ohie_behavior}")
        print(f"  confidence: {row.confidence}")
        print(f"  limitation: {row.limitation}")
