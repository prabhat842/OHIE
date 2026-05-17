import numpy as np

from ohie.terrain import build_d8_network, find_blue_spots


def test_d8_accumulation_routes_to_low_corner():
    bed = np.array(
        [
            [4.0, 3.0, 2.0],
            [3.0, 2.0, 1.0],
            [2.0, 1.0, 0.0],
        ]
    )
    network = build_d8_network(bed)
    assert network.outfall(0, 0) == (2, 2)
    assert network.flow_accumulation[2, 2] == 9.0


def test_blue_spot_detection_finds_local_depression():
    bed = np.array(
        [
            [1.0, 1.0, 1.0],
            [1.0, 0.2, 1.0],
            [1.0, 1.0, 1.0],
        ]
    )
    spots = find_blue_spots(bed, min_depth_m=0.5)
    assert len(spots) == 1
    assert spots[0].row == 1
    assert spots[0].col == 1

