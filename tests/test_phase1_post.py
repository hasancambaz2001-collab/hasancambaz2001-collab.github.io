import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase1_post import classify_market, two_leg_pairs


def test_classify_5m_15m_other() -> None:
    assert classify_market("btc-updown-5m-1786665600", None) == "5m"
    assert classify_market("eth-updown-5m-1786665600", None) == "5m"
    assert classify_market("btc-updown-15m-1786665600", None) == "15m"
    assert classify_market("nhl-car-las-2026-06-09", None) == "other"


def test_two_leg_pair_vwap() -> None:
    rows = [
        {"eventSlug": "btc-updown-5m-1", "outcome": "Up", "side": "BUY", "size": 10, "price": 0.40},
        {"eventSlug": "btc-updown-5m-1", "outcome": "Up", "side": "BUY", "size": 10, "price": 0.50},
        {"eventSlug": "btc-updown-5m-1", "outcome": "Down", "side": "BUY", "size": 20, "price": 0.44},
        {"eventSlug": "solo", "outcome": "Up", "side": "BUY", "size": 21, "price": 0.30},
    ]
    pairs = two_leg_pairs(rows)
    assert len(pairs) == 1
    assert abs(pairs[0] - 0.89) < 1e-9
