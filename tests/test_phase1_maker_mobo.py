import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase1_maker_mobo import analyze, gate, is_taker_fee_match
from whiskas.fees import taker_fee_usdc


def test_taker_fee_match_pm15() -> None:
    size, price = 20.0, 0.40
    fee = taker_fee_usdc(size, price)
    usdc = size * price + fee
    assert is_taker_fee_match(usdc, size, price) is True
    assert is_taker_fee_match(usdc * 1.0 + fee * 0.10, size, price) is True
    assert is_taker_fee_match(size * price, size, price) is False
    assert is_taker_fee_match(size * price + fee * 1.20, size, price) is False


def test_gate_fail_when_maker_thin() -> None:
    rows = [
        {"type": "TRADE", "side": "BUY", "eventSlug": "btc-updown-5m-1", "outcome": "Up", "size": 20, "price": 0.40, "usdcSize": 20 * 0.40 + taker_fee_usdc(20, 0.40)},
        {"type": "TRADE", "side": "BUY", "eventSlug": "btc-updown-5m-1", "outcome": "Down", "size": 20, "price": 0.44, "usdcSize": 20 * 0.44 + taker_fee_usdc(20, 0.44)},
    ]
    stats = analyze("x", "0xabc", rows * 30)
    verdict, _ = gate([stats])
    assert stats["pct_taker"] > 0.9
    assert verdict == "FAIL"
