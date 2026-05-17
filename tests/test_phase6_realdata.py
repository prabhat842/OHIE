from pathlib import Path

import numpy as np

from ohie.validation.literature import literature_behavior_table
from ohie.validation.real_terrain import flat_terrain_case, river_adjacent_case
from ohie.validation.remote_sensing import (
    flooded_area_agreement,
    intersection_over_union,
    observed_overlap,
    proxy_observation_comparison,
)


def test_phase6_data_package_exists():
    root = Path("ohie-data")
    assert (root / "real_terrain" / "flat_terrain_small.npz").exists()
    assert (root / "real_terrain" / "river_adjacent_small.npz").exists()
    assert (root / "remote_sensing" / "observed_water_mask_small.npz").exists()


def test_real_terrain_cases_run_and_disclose_limits():
    flat = flat_terrain_case()
    river = river_adjacent_case()
    assert flat.metrics["mass_error"] < 1.0e-8
    assert river.metrics["mass_error"] < 1.0e-8
    assert flat.metrics["dinfinity_split_fraction"] > 0.0
    assert "not calibrated" in flat.limitations.lower()
    assert "synthetic" in river.limitations.lower()


def test_literature_table_is_conservative():
    rows = literature_behavior_table()
    assert len(rows) >= 5
    confidence = {row.benchmark: row.confidence for row in rows}
    assert confidence["Closed basin conservation"] == "High"
    assert confidence["Storage attenuation"] == "Low"
    assert all(row.limitation for row in rows)


def test_remote_sensing_proxy_metrics():
    simulated = np.array([[True, True], [False, False]])
    observed = np.array([[True, False], [True, False]])
    assert intersection_over_union(simulated, observed) == 1 / 3
    assert observed_overlap(simulated, observed) == 0.5
    assert flooded_area_agreement(simulated, observed) == 1.0
    result = proxy_observation_comparison()
    assert "proxy comparison only" in result.assumptions.lower()
    assert 0.0 <= result.metrics["iou"] <= 1.0
    assert 0.0 <= result.metrics["flooded_area_agreement"] <= 1.0

