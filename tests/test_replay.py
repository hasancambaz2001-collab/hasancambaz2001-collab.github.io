from whiskas.constants import CLIP, PAIR_MAX
from whiskas.killswitch import day_pnl_halt
from whiskas.policy import complete_set_pnl
from whiskas.replay import eligible_windows, run_replay, simulate_fill30, synthetic_taker_fills, taker_ask_vwap


def test_ask_vwap_uses_taker_price_not_usdc() -> None:
    slug = "btc-updown-5m-1786886400"
    fills = synthetic_taker_fills(
        [
            {"slug": slug, "leg": "Up", "size": 10, "price": 0.40},
            {"slug": slug, "leg": "Up", "size": 10, "price": 0.50},
            {"slug": slug, "leg": "Down", "size": 20, "price": 0.44},
        ]
    )
    asks = taker_ask_vwap(fills)
    row = asks.iloc[0]
    assert abs(row["ask_up"] - 0.45) < 1e-9
    assert abs(row["ask_down"] - 0.44) < 1e-9
    assert abs(row["ask_sum"] - 0.89) < 1e-9


def test_maker_fill_is_not_an_ask_proxy() -> None:
    slug = "btc-updown-5m-1786886400"
    fills = synthetic_taker_fills(
        [
            {"slug": slug, "leg": "Up", "size": 21, "price": 0.40},
            {"slug": slug, "leg": "Down", "size": 21, "price": 0.50},
        ]
    )
    # Overwrite Down as maker: usdc == size*price
    fills.loc[fills["leg"] == "Down", "usdc"] = 21 * 0.50
    asks = taker_ask_vwap(fills)
    row = asks.iloc[0]
    assert row["ask_up"] is not None
    assert row["ask_down"] is None
    assert row["ask_sum"] is None


def test_eligible_only_at_or_below_pair_max() -> None:
    cheap = "btc-updown-5m-1786886400"
    dear = "btc-updown-5m-1786886700"
    fills = synthetic_taker_fills(
        [
            {"slug": cheap, "leg": "Up", "size": 5, "price": 0.40},
            {"slug": cheap, "leg": "Down", "size": 5, "price": 0.50},
            {"slug": dear, "leg": "Up", "size": 5, "price": 0.49},
            {"slug": dear, "leg": "Down", "size": 5, "price": 0.48},
        ]
    )
    asks = taker_ask_vwap(fills)
    elig = eligible_windows(asks)
    assert list(elig["slug"]) == [cheap]
    assert (elig["ask_sum"] <= PAIR_MAX + 1e-12).all()
    assert (elig["residual"] == 0).all()
    assert (elig["clip"] == CLIP).all()


def test_replay_pnl_is_clip_not_their_size() -> None:
    slug = "btc-updown-5m-1786886400"
    fills = synthetic_taker_fills(
        [
            {"slug": slug, "leg": "Up", "size": 5, "price": 0.40},
            {"slug": slug, "leg": "Down", "size": 5, "price": 0.50},
        ]
    )
    result, elig, _ = run_replay(fills)
    expect = complete_set_pnl(0.40, 0.50, 21.0)
    assert abs(float(elig.iloc[0]["pnl_fill1"]) - expect) < 1e-9
    assert abs(result.pnl_fill1 - expect) < 1e-9
    assert abs(result.pnl_fill30_ev - 0.30 * expect) < 1e-9
    assert result.n_eligible == 1


def test_fill30_is_both_or_nothing() -> None:
    slug = "btc-updown-5m-1786886400"
    fills = synthetic_taker_fills(
        [
            {"slug": slug, "leg": "Up", "size": 21, "price": 0.40},
            {"slug": slug, "leg": "Down", "size": 21, "price": 0.50},
        ]
    )
    _result, elig, _ = run_replay(fills, seed=1)
    row = elig.iloc[0]
    assert row["residual"] == 0
    if row["filled"]:
        assert abs(row["pnl_fill30_mc"] - row["pnl_fill1"]) < 1e-9
    else:
        assert row["pnl_fill30_mc"] == 0.0


def test_simulate_fill30_uses_one_bernoulli() -> None:
    import pandas as pd

    elig = pd.DataFrame({"pnl_fill1": [1.0, 2.0, 3.0]})
    out = simulate_fill30(elig, fill_prob=0.0, seed=0)
    assert list(out["pnl_fill30_mc"]) == [0.0, 0.0, 0.0]
    out = simulate_fill30(elig, fill_prob=1.0, seed=0)
    assert list(out["pnl_fill30_mc"]) == [1.0, 2.0, 3.0]


def test_day_dd_product_is_minus_15() -> None:
    assert not day_pnl_halt(-140.0, 1000.0, -0.15)
    assert day_pnl_halt(-150.0, 1000.0, -0.15)
    # default kill-switch stays -8% and is not this product
    from whiskas.killswitch import day_pnl_halt as default_halt

    assert default_halt(-90.0, 1000.0)
    assert not default_halt(-90.0, 1000.0, -0.15)
