import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ohie.validation.remote_sensing import proxy_observation_comparison


if __name__ == "__main__":
    result = proxy_observation_comparison()
    print(result.name)
    print(result.observed)
    for key, value in result.metrics.items():
        print(f"{key}: {value}")
