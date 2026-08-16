import json
from pathlib import Path

import pytest

from scripts.replay_mobo import COVER_MIN, covers, gate, load_tape, replay_wallet, two_leg_windows
from whiskas.fees import taker_fee_usdc


def _buy(slug: str, outcome: str, size: float, price: float, *, maker: bool = True) -> dict:
    usdc = size * price if maker else size * price + taker_fee_usdc(size, price)
    return {
        "type": "TRADE",
        "side": "BUY",
        "eventSlug": slug,
        "slug": slug,
        "outcome": outcome,
        "size": size,
        "price": price,
        "usdcSize": usdc,
    }


def test_cover_rule_maker_clip_pair() -> None:
    cheap_maker = {"pair": 0.88, "min_q": 12.0, "any_maker": True}
    assert covers(cheap_maker) is True
    assert covers({"pair": 0.91, "min_q": 12.0, "any_maker": True}) is False
    assert covers({"pair": 0.88, "min_q": 9.0, "any_maker": True}) is False
    assert covers({"pair": 0.88, "min_q": 12.0, "any_maker": False}) is False


def test_gate_pass_at_80_percent() -> None:
    rows = []
    for i in range(10):
        slug = f"btc-updown-5m-{i}"
        maker = i < 8
        rows.append(_buy(slug, "Up", 12, 0.40, maker=maker))
        rows.append(_buy(slug, "Down", 12, 0.48, maker=maker))
    stats = replay_wallet("x", "0xabc", rows)
    assert stats["n_cheap"] == 10
    assert stats["n_cover"] == 8
    assert abs(stats["cover"] - 0.80) < 1e-12
    assert stats["passed"] is True
    assert stats["pnl_from_paper_maker"] is False
    verdict, _ = gate([stats])
    assert verdict == "PASS"


def test_gate_fail_below_80() -> None:
    rows = []
    for i in range(10):
        slug = f"eth-updown-15m-{i}"
        maker = i < 7
        rows.append(_buy(slug, "Up", 12, 0.40, maker=maker))
        rows.append(_buy(slug, "Down", 12, 0.48, maker=maker))
    stats = replay_wallet("y", "0xdef", rows)
    assert stats["n_cover"] == 7
    assert stats["passed"] is False
    verdict, _ = gate([stats])
    assert verdict == "FAIL"


def test_ignores_4h_and_pair_ge_090() -> None:
    rows = [
        _buy("btc-updown-4h-1", "Up", 20, 0.40),
        _buy("btc-updown-4h-1", "Down", 20, 0.48),
        _buy("sol-updown-5m-1", "Up", 20, 0.50),
        _buy("sol-updown-5m-1", "Down", 20, 0.50),
        _buy("sol-updown-5m-2", "Up", 20, 0.40),
        _buy("sol-updown-5m-2", "Down", 20, 0.48),
    ]
    wins = two_leg_windows(rows)
    assert {w["slug"] for w in wins} == {"sol-updown-5m-1", "sol-updown-5m-2"}
    stats = replay_wallet("z", "0x0", rows)
    assert stats["n_cheap"] == 1
    assert stats["n_cover"] == 1


def test_refuse_paper_maker_tape(tmp_path: Path) -> None:
    fake = Path("data/paper_maker/intended.jsonl")
    if not fake.parent.is_dir():
        pytest.skip("paper_maker dir missing")
    with pytest.raises(ValueError, match="paper intends"):
        load_tape(fake)


def test_script_is_get_only_and_not_pnl() -> None:
    src = Path("scripts/replay_mobo.py").read_text(encoding="utf-8")
    assert "create_order" not in src
    assert "post_order" not in src
    assert "pnl_from_paper_maker" in src
    assert COVER_MIN == 0.80
    cfg = Path("configs/mobo.yaml").read_text(encoding="utf-8")
    assert "pair_max: 0.90" in cfg
    assert "clip: 10" in cfg
    assert "maker_only: true" in cfg
