from whiskas.fees import taker_fee_usdc
from whiskas.windows import apply_winners, build_windows, normalize_leg


def test_normalize_leg() -> None:
    assert normalize_leg("Up", None) == "Up"
    assert normalize_leg("down", None) == "Down"
    assert normalize_leg(None, 0) == "Up"
    assert normalize_leg(None, 1) == "Down"


def _trade(ts: int, slug: str, outcome: str, size: float, price: float, side: str = "BUY") -> dict:
    return {
        "type": "TRADE",
        "timestamp": ts,
        "eventSlug": slug,
        "slug": slug,
        "outcome": outcome,
        "outcomeIndex": 0 if outcome == "Up" else 1,
        "side": side,
        "size": size,
        "price": price,
        "usdcSize": size * price,
        "transactionHash": f"0x{ts}{outcome}{size}",
    }


def test_pair_cost_and_residual_sign() -> None:
    slug = "btc-updown-5m-1786886400"
    t0 = 1786886400
    rows = [
        _trade(t0 + 10, slug, "Up", 10, 0.40),
        _trade(t0 + 12, slug, "Down", 10, 0.55),
        _trade(t0 + 20, slug, "Up", 5, 0.40),
    ]
    wins = build_windows(rows)
    w = wins[t0]
    assert abs(w.q_up - 15) < 1e-9
    assert abs(w.q_down - 10) < 1e-9
    assert abs(w.matched - 10) < 1e-9
    assert w.residual_leg == "Up"
    assert w.pair_cost is not None
    assert abs(w.pair_cost - (0.40 + 0.55)) < 1e-9
    apply_winners(wins, {t0: "Up"})
    pair = w.pair_pnl()
    res_up = w.residual_pnl()
    assert pair is not None and pair > 0
    assert res_up is not None and res_up > 0
    apply_winners(wins, {t0: "Down"})
    res_down = w.residual_pnl()
    assert res_down is not None and res_down < 0


def test_taker_fee_matches_official_table() -> None:
    # 100 shares at 0.50, crypto rate 0.07 → $1.75
    assert abs(taker_fee_usdc(100, 0.50) - 1.75) < 1e-9
