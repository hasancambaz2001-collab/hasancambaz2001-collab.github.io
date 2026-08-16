from pathlib import Path

from scripts.micro_live_bundle import CLIP_NO_G5, CLIP_WITH_G5, micro_payload


def test_micro_clip_caps_and_not_live_ready() -> None:
    no_g5 = micro_payload(clip=CLIP_NO_G5, g5=False, g6=True)
    assert no_g5["clip"] == 5
    assert no_g5["assets"] == ["btc"]
    assert no_g5["tfs"] == ["5m"]
    assert no_g5["max_daily_loss_usd"] == 25
    assert no_g5["kill_switch"] is True
    assert no_g5["max_open_windows"] == 2
    assert no_g5["pair_gt_1_trade"] is False
    assert no_g5["full_live_ready"] is False
    assert no_g5["bundle_placed_orders"] is False
    assert no_g5["executor"]["pair_gt_1_trade"] is False
    assert no_g5["executor"]["stop_if_daily_loss_usd"] == 25
    assert no_g5["executor"]["bundle_sends_orders"] is False
    with_g5 = micro_payload(clip=CLIP_WITH_G5, g5=True, g6=True)
    assert with_g5["clip"] == 10
    src = Path("scripts/micro_live_bundle.py").read_text(encoding="utf-8")
    assert "create_order" not in src
    assert "LIVE_READY" in src
    assert "--allow-without-g5" in src
