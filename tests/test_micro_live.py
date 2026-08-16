from pathlib import Path

import subprocess
import sys

from scripts.micro_live import _guard_rest, clip_cap, probe, send_rest_both


def test_probe_auth_absent_null_real_fill() -> None:
    payload = probe()
    assert payload["auth_available"] is False
    assert payload["auth_reason"] == "AUTH_ABSENT"
    assert payload["sent"] is False
    assert payload["real_fill"] is None
    assert payload["real_fill_rate"] is None
    assert payload["live_ready_exists"] is False
    assert payload["pair_gt_1_trade"] is False
    assert payload.get("block") in {"AUTH_ABSENT", "MICRO yaml missing"}


def test_guard_refuses_pair_gt_1_and_rich() -> None:
    assert _guard_rest({"reason": "rest", "bid_sum": 1.02, "min_bid_size": 20}, clip=5) == "pair_gt_1_refused"
    assert _guard_rest({"reason": "rest", "bid_sum": 0.91, "min_bid_size": 20}, clip=5) == "bid_sum_gt_pair_max"
    assert _guard_rest({"reason": "rest", "bid_sum": 0.88, "min_bid_size": 4}, clip=5) == "thin_bid"
    assert _guard_rest({"reason": "rest", "bid_sum": 0.88, "min_bid_size": 10}, clip=5) is None


def test_send_without_client_does_not_invent_fill() -> None:
    rec = {
        "reason": "rest",
        "bid_sum": 0.88,
        "bid_up": 0.40,
        "bid_down": 0.48,
        "min_bid_size": 20,
        "clip": 5,
        "pair_max": 0.90,
        "slug": "btc-updown-5m-1",
        "asset": "btc",
        "tf": "5m",
    }
    out = send_rest_both(None, rec, {"Up": "u", "Down": "d"}, clip=5)
    assert out["live_order"] is False
    assert out["real_fill"] is None
    assert out["real_fill_rate"] is None
    assert out.get("send_blocked") == "AUTH_ABSENT"


def test_send_alone_is_refused() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/micro_live.py", "--send"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    assert "not enough" in proc.stdout
    assert "sent" in proc.stdout


def test_clip_cap_without_g5() -> None:
    assert clip_cap(g5=False, yaml_clip=10) == 5
    assert clip_cap(g5=True, yaml_clip=10) == 10
    src = Path("scripts/micro_live.py").read_text()
    assert "--send-live-orders-now" in src
    assert "Default: measurement + yaml only" in src
    assert "AUTH_ABSENT" in src
    assert "create_order" in src or "create_gtc_buy" in src
