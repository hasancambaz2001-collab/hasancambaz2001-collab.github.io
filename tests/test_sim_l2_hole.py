from scripts.sim_l2_hole import hole_mask, run_lengths
import numpy as np


def test_hole_mask_matches_live_gates() -> None:
    ok = hole_mask(
        np.array([0.52]),
        np.array([0.84]),
        np.array([0.17]),
        np.array([0.18]),
        np.array([52.0]),
        np.array([52.0]),
    )
    assert bool(ok[0]) is True
    rich = hole_mask(
        np.array([0.51]),
        np.array([0.52]),
        np.array([0.46]),
        np.array([0.47]),
        np.array([12.0]),
        np.array([12.0]),
    )
    assert bool(rich[0]) is False


def test_run_lengths_break_on_gap_or_new_market() -> None:
    cid = np.array(["a", "a", "a", "a", "b"])
    t = np.array([10, 11, 12, 14, 20])
    hole = np.array([True, True, True, True, True])
    runs = run_lengths(cid, t, hole)
    assert sorted(runs.tolist()) == [1, 1, 3]
