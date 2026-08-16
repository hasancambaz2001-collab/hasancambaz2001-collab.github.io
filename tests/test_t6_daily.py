from scripts.t6_daily_06dc import HIT_MIN, N_MIN, analyze


def test_t6_unclear_when_n_low() -> None:
    rows = [
        {"type": "TRADE", "side": "BUY", "eventSlug": "bitcoin-up-or-down-on-august-14-2026", "outcome": "Up", "size": 10, "price": 0.6, "usdcSize": 6},
        {"type": "TRADE", "side": "BUY", "eventSlug": "bitcoin-up-or-down-on-august-14-2026", "outcome": "Down", "size": 1, "price": 0.4, "usdcSize": 0.4},
        {"type": "REDEEM", "eventSlug": "bitcoin-up-or-down-on-august-14-2026", "outcome": "Up"},
    ]
    stats = analyze(rows)
    assert stats["n_directional_resolved"] < N_MIN
    assert stats["gate"] == "UNCLEAR"
    assert stats["r7_daily_t6"] is False
    assert HIT_MIN == 0.58
