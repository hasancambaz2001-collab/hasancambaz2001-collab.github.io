from infra.strategies.s06dc import L2_COVERS_06DC, TRUTH, S06dc
from whiskas.l2 import BookTick


def test_l2_recorder_ticks_are_smoke_not_06dc_truth() -> None:
    assert L2_COVERS_06DC is False
    assert TRUTH == "dump + paper_06dc + T6"
    tick = BookTick(
        t=1,
        slug="bitcoin-up-or-down-on-august-16-2026",
        asset="btc",
        tf="5m",
        t0=1,
        bu=0.48,
        bd=0.50,
        au=0.49,
        ad=0.51,
        su=20,
        sd=20,
    )
    d, _ = S06dc().on_tick(tick, None)
    assert d.intend is False
    assert d.trade is False
    assert d.reason == "smoke_5m_not_daily"
    assert d.measure_edge == 0.0
    assert d.extra["l2_covers_06dc"] is False


def test_dump_daily_window_is_06dc_measure() -> None:
    d = S06dc().on_window(
        {"slug": "bitcoin-up-or-down-on-august-16-2026", "pair": 0.97, "matched": 20.0}
    )
    assert d.reason == "r6_measure"
    assert d.trade is False
    assert d.extra["truth"] == TRUTH
    assert d.extra["l2_covers_06dc"] is False
