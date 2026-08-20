from scripts.replay_full import compare_parity, usd_ratio


def test_usd_ratio_is_computed_not_hardcoded() -> None:
    assert usd_ratio(80.0, 800.0) == 0.1
    assert usd_ratio(797.6, 14110.75) == 797.6 / 14110.75
    assert usd_ratio(10.0, 0.0) is None


def test_compare_same_n_is_size_gap() -> None:
    cmp = compare_parity(their_usd=14110.75, clip_usd=797.60, n_their=209, n_clip=209)
    assert cmp["same_n"] is True
    assert cmp["kind"] == "size_gap"
    assert cmp["clip10_lt_their"] is True
    assert cmp["usd_ratio"] == 797.60 / 14110.75
    assert "0.07" not in cmp["note"]
    assert "7%" not in cmp["note"]
