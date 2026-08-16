from infra.book.source import BookSource, window_to_tick
from infra.match.fill_model import apply_fill
from infra.size.ladder import load_ladder
from infra.strategies.s1_maker import S1Maker
from infra.strategies.whiskas_full import WhiskasFullMeasure
from whiskas.kasa import is_s1


def test_s1_window_and_no_pair_gt1_trade() -> None:
    win = {
        "maker_pair": 0.88,
        "maker_matched": 20.0,
        "pair": 0.88,
        "matched": 20.0,
        "slug": "btc-updown-5m-1",
    }
    assert is_s1(win)
    d = S1Maker().on_window(win)
    assert d.intend
    assert d.trade
    assert abs(d.edge - 20 * 0.12) < 1e-9
    dear = {"maker_pair": 1.02, "maker_matched": 20.0, "slug": "x"}
    assert S1Maker().on_window(dear).intend is False


def test_whiskas_full_pair_gt1_is_measure_only() -> None:
    d = WhiskasFullMeasure().on_window({"taker_pair": 1.05, "taker_matched": 10.0, "taker_fee": 0.0, "pair": 1.05})
    assert d.trade is False
    assert d.intend is False
    assert d.reason == "pair_gt_1_attr"
    assert d.measure_edge < 0
    assert d.edge == 0.0


def test_parity_tape_is_upper_bound() -> None:
    assert apply_fill(model="parity_tape", intended_edge=100) == 100
    assert apply_fill(model="none", intended_edge=100) == 0
    ladder = load_ladder()
    assert ladder["size_ok"] is False
    assert ladder["paper_clip"] == 10


def test_tape_source_windows() -> None:
    src = BookSource("tape_bosona")
    wins = src.windows()
    assert wins
    tick = window_to_tick(wins[0])
    assert tick.slug
