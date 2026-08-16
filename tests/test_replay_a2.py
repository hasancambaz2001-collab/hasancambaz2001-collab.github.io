from whiskas.policy import complete_set_pnl
from whiskas.replay import run_replay, synthetic_taker_fills
from whiskas.replay_a2 import run_a2_compare, simulate_a2_window


def test_a2_first_leg_then_complete() -> None:
    slug = "btc-updown-5m-1786886400"
    t0 = 1786886400
    fills = synthetic_taker_fills(
        [
            {"slug": slug, "leg": "Up", "size": 10, "price": 0.40, "timestamp": t0 + 10, "winner": "Up"},
            {"slug": slug, "leg": "Down", "size": 40, "price": 0.55, "timestamp": t0 + 20, "winner": "Up"},
            {"slug": slug, "leg": "Down", "size": 21, "price": 0.55, "timestamp": t0 + 30, "winner": "Up"},
        ]
    )
    sim = simulate_a2_window(fills)
    assert sim["n_first"] == 1
    assert sim["n_complete"] == 1
    assert sim["residual"] == 0
    expect = complete_set_pnl(0.40, 0.55, 10.0)
    assert abs(sim["pnl_fill1"] - expect) < 1e-6


def test_a2_never_completes_above_pair_max() -> None:
    slug = "btc-updown-5m-1786886400"
    t0 = 1786886400
    fills = synthetic_taker_fills(
        [
            {"slug": slug, "leg": "Up", "size": 10, "price": 0.40, "timestamp": t0 + 10, "winner": "Down"},
            {"slug": slug, "leg": "Down", "size": 40, "price": 0.55, "timestamp": t0 + 20, "winner": "Down"},
            {"slug": slug, "leg": "Down", "size": 21, "price": 0.70, "timestamp": t0 + 40, "winner": "Down"},
        ]
    )
    sim = simulate_a2_window(fills)
    assert sim["n_first"] == 1
    assert sim["n_complete"] == 0
    assert sim["residual_leg"] == "Up"
    assert sim["max_naked_sec"] > 0


def test_a_plus_a2_does_not_replace_a() -> None:
    a_slug = "btc-updown-5m-1786886400"
    extra = "btc-updown-5m-1786886700"
    t0 = 1786886400
    t1 = 1786886700
    fills = synthetic_taker_fills(
        [
            {"slug": a_slug, "leg": "Up", "size": 21, "price": 0.40, "timestamp": t0 + 10, "winner": "Up"},
            {"slug": a_slug, "leg": "Down", "size": 21, "price": 0.50, "timestamp": t0 + 12, "winner": "Up"},
            {"slug": extra, "leg": "Up", "size": 100, "price": 0.90, "timestamp": t1 + 5, "winner": "Up"},
            {"slug": extra, "leg": "Down", "size": 100, "price": 0.90, "timestamp": t1 + 6, "winner": "Up"},
            {"slug": extra, "leg": "Up", "size": 10, "price": 0.40, "timestamp": t1 + 20, "winner": "Up"},
            {"slug": extra, "leg": "Down", "size": 40, "price": 0.50, "timestamp": t1 + 21, "winner": "Up"},
            {"slug": extra, "leg": "Down", "size": 21, "price": 0.50, "timestamp": t1 + 40, "winner": "Up"},
        ]
    )
    a_only, elig, _ = run_replay(fills)
    cmp_ = run_a2_compare(fills)
    assert a_only.n_eligible == 1
    assert list(elig["slug"]) == [a_slug]
    assert cmp_["a"]["n_windows"] == 1
    assert abs(cmp_["a"]["pnl_fill1"] - a_only.pnl_fill1) < 1e-9
    assert cmp_["a2_extra"]["n_windows"] == 1
    assert cmp_["a_plus_a2"]["n_windows"] == 2
    assert cmp_["a_plus_a2"]["pnl_fill30_ev"] + 1e-9 >= cmp_["a"]["pnl_fill30_ev"]
    assert cmp_["passed"]
