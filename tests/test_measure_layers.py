from whiskas.measure_layers import attach_layers, guard_still250_send, still250_ok


def test_still250_is_cheap_and_deep_not_level_eaten() -> None:
    assert still250_ok(0.88, 12, clip=10, pair_max=0.90) is True
    assert still250_ok(0.91, 20, clip=10, pair_max=0.90) is False
    assert still250_ok(0.80, 9, clip=10, pair_max=0.90) is False
    assert still250_ok(None, 20, clip=10) is False


def test_layers_unmixed_on_rest() -> None:
    rec = {
        "reason": "rest",
        "bid_sum": 0.88,
        "min_bid_size": 12,
        "slug": "btc-updown-5m-1",
        "asset": "btc",
        "tf": "5m",
        "ts": "2026-08-16T19:00:00+00:00",
        "clip": 10,
        "pair_max": 0.90,
    }
    attach_layers(
        rec,
        still={"bid_sum_250": 0.87, "min_size_250": 15, "still_there_250ms": True},
        clip=10,
    )
    assert rec["intent"] is True
    assert rec["still250"] is True
    assert rec["bid_sum_0"] == 0.88
    assert rec["bid_sum_250"] == 0.87
    assert rec["real_fill"] is None
    assert rec["real_fill_rate"] is None
    assert rec["pair_gt_1_trade"] is False
    assert rec["sim_fill"] is None
    rec["still_there_250ms"] = True
    rec["bid_sum_250"] = 0.87
    assert guard_still250_send(rec) is None
    rec["still_there_250ms"] = False
    assert guard_still250_send(rec) == "still250_false"


def test_skip_logs_skip_reason_and_null_real_fill() -> None:
    rec = {"reason": "rich_bid_sum", "bid_sum": 0.99, "min_bid_size": 20}
    attach_layers(rec)
    assert rec["intent"] is False
    assert rec["skip_reason"] == "rich_bid_sum"
    assert rec["still250"] is None
    assert rec["real_fill_rate"] is None
