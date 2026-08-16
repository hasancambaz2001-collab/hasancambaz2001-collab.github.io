from pathlib import Path

from whiskas.fees import taker_fee_usdc
from whiskas.kasa import is_s1, is_s3, s1_pnl, s3_pnl, two_leg_windows


def _buy(slug: str, outcome: str, size: float, price: float, *, maker: bool, tf: str = "5m") -> dict:
    usdc = size * price if maker else size * price + taker_fee_usdc(size, price)
    return {
        "type": "TRADE",
        "side": "BUY",
        "eventSlug": f"{slug.replace('btc', 'btc')}",
        "slug": f"btc-updown-{tf}-1" if "updown" not in slug else slug,
        "outcome": outcome,
        "size": size,
        "price": price,
        "usdcSize": usdc,
    }


def test_s1_maker_cheap_not_pair_gt_1() -> None:
    rows = [
        _buy("btc-updown-5m-1", "Up", 20, 0.40, maker=True),
        _buy("btc-updown-5m-1", "Down", 20, 0.48, maker=True),
        _buy("btc-updown-5m-2", "Up", 20, 0.51, maker=True),
        _buy("btc-updown-5m-2", "Down", 20, 0.50, maker=True),
    ]
    wins = two_leg_windows(rows, tfs=("5m", "15m"))
    s1 = [w for w in wins if is_s1(w)]
    assert len(s1) == 1
    assert abs(s1_pnl(s1[0]) - 20 * (1 - 0.88)) < 1e-9
    assert abs(s1_pnl(s1[0], clip=10) - 10 * (1 - 0.88)) < 1e-9
    dear = [w for w in wins if w.get("maker_pair") and w["maker_pair"] > 1]
    assert dear
    assert is_s1(dear[0]) is False
    assert s1_pnl(dear[0]) == 0.0


def test_s3_taker_le_096_not_primary_pair_ge_1() -> None:
    rows = [
        _buy("eth-updown-15m-1", "Up", 15, 0.40, maker=False),
        _buy("eth-updown-15m-1", "Down", 15, 0.50, maker=False),
        _buy("eth-updown-15m-2", "Up", 15, 0.52, maker=False),
        _buy("eth-updown-15m-2", "Down", 15, 0.50, maker=False),
    ]
    wins = two_leg_windows(rows, tfs=("5m", "15m"))
    s3 = [w for w in wins if is_s3(w)]
    assert len(s3) == 1
    assert s3[0]["taker_pair"] <= 0.96 + 1e-12
    assert s3_pnl(s3[0]) > 0
    skipped = [w for w in wins if w.get("taker_pair") and w["taker_pair"] > 1]
    assert skipped
    assert is_s3(skipped[0]) is False


def test_two_leg_groups_by_market_slug_not_event() -> None:
    """06dc ladders: Yes+No on one strike is a set; mixed strikes are not."""
    rows = [
        {
            "type": "TRADE",
            "side": "BUY",
            "eventSlug": "what-price-will-ethereum-hit-in-august-2026",
            "slug": "will-ethereum-reach-2200-in-august-2026",
            "outcome": "Yes",
            "size": 100,
            "price": 0.10,
            "usdcSize": 10.0,
        },
        {
            "type": "TRADE",
            "side": "BUY",
            "eventSlug": "what-price-will-ethereum-hit-in-august-2026",
            "slug": "will-ethereum-reach-2200-in-august-2026",
            "outcome": "No",
            "size": 100,
            "price": 0.70,
            "usdcSize": 70.0,
        },
        {
            "type": "TRADE",
            "side": "BUY",
            "eventSlug": "what-price-will-ethereum-hit-in-august-2026",
            "slug": "will-ethereum-reach-3000-in-august-2026",
            "outcome": "No",
            "size": 100,
            "price": 0.90,
            "usdcSize": 90.0,
        },
    ]
    wins = two_leg_windows(rows, tfs=None)
    assert len(wins) == 1
    assert wins[0]["slug"] == "will-ethereum-reach-2200-in-august-2026"
    assert abs(wins[0]["pair"] - 0.80) < 1e-9


def test_size_schedule_stays_disarmed() -> None:
    src = Path("configs/size_schedule.yaml").read_text(encoding="utf-8")
    assert "size_ok: false" in src
    full = Path("configs/mobo_full.yaml").read_text(encoding="utf-8")
    assert "pair_gt_1_trade: false" in full
    assert "ask_fok_primary: false" in full
    assert "primary: paper_maker" in full
    assert "create_order" not in Path("scripts/replay_full.py").read_text()
    assert "create_order" not in Path("scripts/kasa_attribution.py").read_text()
