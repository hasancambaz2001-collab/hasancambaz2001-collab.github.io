from pathlib import Path

import subprocess
import sys

from scripts.micro_live import _guard_rest, clip_cap, probe, send_rest_both, trial_clip
from whiskas.micro_report import adverse_action, fee_estimated_net_pnl, layer_records


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
    assert trial_clip(g5=True, yaml_clip=10) == 5
    assert trial_clip(g5=False, yaml_clip=67) == 5
    src = Path("scripts/micro_live.py").read_text()
    assert "--send-live-orders-now" in src
    assert "Default: measurement + yaml only" in src
    assert "AUTH_ABSENT" in src
    assert "create_order" in src or "create_gtc_buy" in src
    assert "create_fok_buy" in src
    assert "MICRO_LIVE_24H" in src or "write_24h" in src


def test_send_plus_risk_without_keys_is_auth_absent() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/micro_live.py", "--send", "--i-accept-micro-risk", "--seconds", "0"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "AUTH_ABSENT" in proc.stdout
    assert '"sent": false' in proc.stdout.lower() or '"sent": false' in proc.stdout
    assert "real_fill_rate" in proc.stdout


def test_adverse_and_layers_do_not_invent_fill() -> None:
    assert adverse_action(0.40, 0.49) == "complete"
    assert adverse_action(0.40, 0.55) == "rich_complete"
    assert adverse_action(0.40, 0.70) == "pair_gt_1_refused"
    assert adverse_action(0.40, None) == "cancel_missing_opp"
    rec = {
        "ts": "2026-08-16T00:00:00+00:00",
        "reason": "rest",
        "intent": True,
        "asset": "btc",
        "tf": "5m",
        "bid_sum": 0.88,
        "still_there_250ms": True,
        "still250": True,
        "real_fill": None,
        "real_fill_rate": None,
    }
    layers = layer_records(rec)
    assert "INTENT" in layers
    assert "still_there_250ms" in layers
    assert "REAL FILL" not in layers
    assert fee_estimated_net_pnl([]) is None
