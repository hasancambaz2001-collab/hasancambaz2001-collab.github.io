from pathlib import Path

import subprocess
import sys

from scripts.micro_live import (
    _best_bid_join_prices,
    _buy_off_touch,
    _guard_rest,
    after_send_manage,
    clip_cap,
    inventory_flat,
    manage_open,
    probe,
    residual_of,
    send_rest_both,
    trial_clip,
)
from whiskas.measure_layers import apply_still250_send_gate, guard_still250_send
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


def test_still250_false_blocks_send() -> None:
    rec = {
        "reason": "rest",
        "bid_sum": 0.88,
        "bid_up": 0.40,
        "bid_down": 0.48,
        "min_bid_size": 20,
        "clip": 5,
        "still_there_250ms": False,
        "bid_sum_250": 0.99,
        "bid_up_250": 0.63,
        "bid_down_250": 0.36,
    }
    out = send_rest_both(None, rec, {"Up": "u", "Down": "d"}, clip=5)
    assert out["live_order"] is False
    assert out["real_fill"] is None
    assert out.get("send_blocked") == "still250_false"
    rec2 = {**rec, "still_there_250ms": True, "bid_sum_250": 0.91}
    assert guard_still250_send(rec2) == "bid_sum_250_gt_pair_max"
    out2 = send_rest_both(None, rec2, {"Up": "u", "Down": "d"}, clip=5)
    assert out2.get("send_blocked") == "bid_sum_250_gt_pair_max"


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
        "still_there_250ms": True,
        "bid_sum_250": 0.88,
        "bid_up_250": 0.40,
        "bid_down_250": 0.48,
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
    assert "create_gtc_buy_pair" in src
    assert "create_fok_buy" in src
    assert "MICRO_LIVE_24H" in src or "write_24h" in src
    assert "still250_false" in src
    assert "off_touch" in src
    assert "inventory_flat" in src
    clob = Path("whiskas/clob_orders.py").read_text()
    assert "post_orders" in clob
    assert "trader_side" in clob


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


def test_join_best_bid_and_inventory_flat() -> None:
    assert _best_bid_join_prices({"bid_up_250": 0.37, "bid_down_250": 0.51}) == (0.37, 0.51)
    assert _best_bid_join_prices({"bid_up_250": 0.56, "bid_down_250": 0.40}) is None
    assert inventory_flat({"Up": 0.0, "Down": 0.0}) is True
    assert inventory_flat({"Up": 5.0, "Down": 5.0}) is True
    assert inventory_flat({"Up": 0.0, "Down": 5.0}) is False
    assert residual_of(
        [
            {"outcome": "Up", "rested_size": 5, "filled_size": 0},
            {"outcome": "Down", "rested_size": 5, "filled_size": 5},
        ],
        clip=5,
    ) == {"Up": 5.0, "Down": 0.0}
    assert _buy_off_touch(0.37, 0.63) is True
    assert _buy_off_touch(0.37, 0.37) is False


def test_adverse_runs_before_rich_cancel(monkeypatch) -> None:
    cancelled: list[str] = []
    foks: list[float] = []

    def fake_fetch(_client, oid: str):
        table = {
            "up": {"order_id": "up", "status": "open", "filled_size": 0.0, "rested_size": 5.0, "price": 0.37, "raw_status": "LIVE"},
            "dn": {"order_id": "dn", "status": "filled", "filled_size": 5.0, "rested_size": 5.0, "price": 0.51, "raw_status": "MATCHED", "trade_price": 0.51},
        }
        return {**table[oid], "outcome": "Up" if oid == "up" else "Down"}

    def fake_cancel(_client, oid: str):
        cancelled.append(oid)
        return {"order_id": oid, "status": "cancelled"}

    def fake_fok(_client, token_id: str, price: float, size: float):
        foks.append(price)
        return {"order_id": "fok", "status": "filled", "filled_size": 5.0, "rested_size": 5.0, "price": price, "type": "FOK"}

    monkeypatch.setattr("scripts.micro_live.fetch_order", fake_fetch)
    monkeypatch.setattr("scripts.micro_live.cancel_order", fake_cancel)
    monkeypatch.setattr("scripts.micro_live.create_fok_buy", fake_fok)
    monkeypatch.setattr("scripts.micro_live.stamp_trader_side", lambda _c, o: o)

    rec = {
        "bid_sum": 0.99,
        "ask_up": 0.38,
        "token_up": "tok-up",
        "token_down": "tok-dn",
    }
    orders = [
        {"order_id": "up", "outcome": "Up", "status": "open", "filled_size": 0.0, "rested_size": 5.0, "price": 0.37},
        {"order_id": "dn", "outcome": "Down", "status": "filled", "filled_size": 5.0, "rested_size": 5.0, "price": 0.51, "trade_price": 0.51},
    ]
    book = {"ask_up": 0.38, "ask_down": 0.52, "bid_up": 0.63, "bid_down": 0.36, "bid_sum": 0.99}
    out, why = manage_open(None, rec, orders, clip=5, book_now=book)
    assert why == "complete"
    assert rec["adverse_action"] == "complete"
    assert foks == [0.38]
    assert "up" in cancelled
    assert rec.get("pair_gt_1_trade") is False

    rec2 = {"bid_sum": 0.99, "token_up": "tok-up"}
    book2 = {"ask_up": 0.64, "ask_down": 0.37, "bid_up": 0.63, "bid_down": 0.36, "bid_sum": 0.99}
    _out2, why2 = manage_open(None, rec2, orders, clip=5, book_now=book2)
    assert why2 == "pair_gt_1_refused"
    assert rec2["adverse_action"] == "pair_gt_1_refused"


def test_off_touch_cancels_both_when_unfilled(monkeypatch) -> None:
    cancelled: list[str] = []

    def fake_fetch(_client, oid: str):
        return {
            "order_id": oid,
            "status": "open",
            "filled_size": 0.0,
            "rested_size": 5.0,
            "price": 0.37 if oid == "up" else 0.51,
            "outcome": "Up" if oid == "up" else "Down",
        }

    def fake_cancel(_client, oid: str):
        cancelled.append(oid)
        return {"order_id": oid, "status": "cancelled"}

    monkeypatch.setattr("scripts.micro_live.fetch_order", fake_fetch)
    monkeypatch.setattr("scripts.micro_live.cancel_order", fake_cancel)
    rec = {"bid_sum": 0.88}
    orders = [
        {"order_id": "up", "outcome": "Up", "price": 0.37, "filled_size": 0.0, "rested_size": 5.0},
        {"order_id": "dn", "outcome": "Down", "price": 0.51, "filled_size": 0.0, "rested_size": 5.0},
    ]
    book = {"bid_up": 0.63, "bid_down": 0.36, "ask_up": 0.64, "ask_down": 0.37, "bid_sum": 0.99}
    _out, why = manage_open(None, rec, orders, clip=5, book_now=book)
    assert why == "off_touch"
    assert set(cancelled) == {"up", "dn"}


def test_paper_still250_gate_shared() -> None:
    rec = {"reason": "rest", "still_there_250ms": False, "bid_sum_250": 0.99}
    apply_still250_send_gate(rec)
    assert rec["send_blocked"] == "still250_false"
    assert rec["would_send"] is False
    rec_ok = {"reason": "rest", "still_there_250ms": True, "bid_sum_250": 0.88}
    apply_still250_send_gate(rec_ok)
    assert rec_ok["send_blocked"] is None
    assert rec_ok["would_send"] is True
    src = Path("scripts/micro_live.py").read_text()
    idx_adv = src.find("len(filled) == 1 and leftover")
    idx_rich = src.find('reason="rich_cancel"')
    assert 0 < idx_adv < idx_rich
    assert after_send_manage is not None
