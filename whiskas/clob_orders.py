"""Authenticated CLOB GTC / cancel / status. No fake real_fill.

Uses py-clob-client-v2 when installed. Keys from whiskas.clob_auth only.
If auth is absent, send paths return sent=False and real_fill=None.
"""

from __future__ import annotations

import time
from typing import Any

from whiskas.clob_auth import auth_status, load_secrets
from whiskas.constants import CLOB_API

CHAIN_ID = 137


class AuthAbsent(RuntimeError):
    """No local/env CLOB keys. Do not send. Do not invent real_fill."""


def _import_client():
    try:
        from py_clob_client_v2 import ApiCreds, ClobClient, OrderArgs, OrderType
        from py_clob_client_v2.clob_types import OrderPayload
    except ImportError as exc:
        raise RuntimeError("py-clob-client-v2 not installed") from exc
    return ClobClient, ApiCreds, OrderArgs, OrderType, OrderPayload


def normalize_status(raw: Any) -> str:
    text = str(raw or "").strip().lower()
    if text in {"matched", "filled", "fill"}:
        return "filled"
    if text in {"partially_filled", "partial", "live_partial"}:
        return "partial"
    if text in {"cancelled", "canceled", "cancel"}:
        return "cancelled"
    if text in {"live", "open", "resting", "delayed"}:
        return "open"
    if text in {"rejected", "invalid", "unmatched"}:
        return "cancelled"
    return text or "open"


def parse_order_status(payload: Any) -> dict[str, Any]:
    """Map CLOB get_order / post response to the REAL FILL layer. No invention."""
    if not isinstance(payload, dict):
        return {
            "order_id": None,
            "status": None,
            "filled_size": None,
            "rested_size": None,
            "raw_status": None,
        }
    oid = payload.get("id") or payload.get("orderID") or payload.get("order_id")
    raw_status = payload.get("status") or payload.get("state")
    orig = payload.get("original_size") or payload.get("originalSize") or payload.get("size")
    matched = payload.get("size_matched") or payload.get("sizeMatched") or payload.get("filled_size")
    try:
        rested = float(orig) if orig is not None else None
    except (TypeError, ValueError):
        rested = None
    try:
        filled = float(matched) if matched is not None else 0.0
    except (TypeError, ValueError):
        filled = 0.0
    status = normalize_status(raw_status)
    if rested is not None and filled + 1e-12 >= rested and rested > 0:
        status = "filled"
    elif filled > 1e-12 and rested is not None and filled + 1e-12 < rested:
        status = "partial"
    return {
        "order_id": str(oid) if oid else None,
        "status": status,
        "filled_size": filled,
        "rested_size": rested,
        "raw_status": raw_status,
    }


def real_fill_rate(orders: list[dict[str, Any]]) -> float | None:
    """filled_size/rested_size on sent orders only. None if nothing sent."""
    sent = [o for o in orders if o.get("order_id") and o.get("rested_size")]
    if not sent:
        return None
    filled = sum(float(o.get("filled_size") or 0.0) for o in sent)
    rested = sum(float(o.get("rested_size") or 0.0) for o in sent)
    if rested <= 0:
        return None
    return filled / rested


def connect(*, derive_l2: bool = False) -> Any | None:
    """Build L2 ClobClient or None. Never prints secrets. Does not send orders."""
    status = auth_status()
    if not status["auth_available"] and not (derive_l2 and status["reason"] == "private_key_only_no_l2"):
        return None
    secrets = load_secrets()
    if not secrets or not secrets.get("private_key"):
        return None
    ClobClient, ApiCreds, _OrderArgs, _OrderType, _OrderPayload = _import_client()
    creds = None
    if secrets.get("api_key") and secrets.get("api_secret") and secrets.get("api_passphrase"):
        creds = ApiCreds(
            api_key=str(secrets["api_key"]),
            api_secret=str(secrets["api_secret"]),
            api_passphrase=str(secrets["api_passphrase"]),
        )
    client = ClobClient(
        host=CLOB_API,
        chain_id=CHAIN_ID,
        key=str(secrets["private_key"]),
        creds=creds,
        signature_type=int(secrets.get("signature_type") or 0),
        funder=secrets.get("funder") or None,
    )
    if creds is None and derive_l2:
        derived = client.create_or_derive_api_key()
        client.set_api_creds(derived)
    if client.creds is None:
        return None
    return client


def _post_buy(
    client: Any,
    *,
    token_id: str,
    price: float,
    size: float,
    order_type: str,
) -> dict[str, Any]:
    if client is None:
        raise AuthAbsent("AUTH_ABSENT")
    _ClobClient, _ApiCreds, OrderArgs, OrderType, _OrderPayload = _import_client()
    kind = OrderType.FOK if str(order_type).upper() == "FOK" else OrderType.GTC
    args = OrderArgs(token_id=str(token_id), price=float(price), size=float(size), side="BUY")
    resp = client.create_and_post_order(args, order_type=kind)
    parsed = parse_order_status(resp if isinstance(resp, dict) else {})
    parsed["sent"] = bool(parsed.get("order_id"))
    parsed["side"] = "BUY"
    parsed["type"] = "FOK" if kind == OrderType.FOK else "GTC"
    parsed["price"] = float(price)
    parsed["size"] = float(size)
    parsed["token_id"] = str(token_id)
    return parsed


def create_gtc_buy(
    client: Any,
    *,
    token_id: str,
    price: float,
    size: float,
) -> dict[str, Any]:
    """Post a BUY GTC. Requires a live client. Does not invent fills."""
    return _post_buy(client, token_id=token_id, price=price, size=size, order_type="GTC")


def create_gtc_buy_pair(
    client: Any,
    *,
    token_up: str,
    price_up: float,
    token_down: str,
    price_down: float,
    size: float,
    timings: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Sign both GTCs then post_orders in one HTTP call. Fallback: sequential post."""
    if client is None:
        raise AuthAbsent("AUTH_ABSENT")
    _ClobClient, _ApiCreds, OrderArgs, OrderType, _OrderPayload = _import_client()
    args_up = OrderArgs(token_id=str(token_up), price=float(price_up), size=float(size), side="BUY")
    args_down = OrderArgs(token_id=str(token_down), price=float(price_down), size=float(size), side="BUY")
    posted: list[dict[str, Any]] = []
    t_all = time.time()
    try:
        t_sign = time.time()
        signed_up = client.create_order(args_up)
        signed_down = client.create_order(args_down)
        sign_ms = (time.time() - t_sign) * 1000.0
        from py_clob_client_v2.clob_types import PostOrdersV2Args

        t_http = time.time()
        raw = client.post_orders(
            [
                PostOrdersV2Args(order=signed_up, orderType=OrderType.GTC),
                PostOrdersV2Args(order=signed_down, orderType=OrderType.GTC),
            ]
        )
        rows = raw if isinstance(raw, list) else [raw]
        for row, outcome, px, tok in (
            (rows[0] if rows else {}, "Up", price_up, token_up),
            (rows[1] if len(rows) > 1 else {}, "Down", price_down, token_down),
        ):
            parsed = parse_order_status(row if isinstance(row, dict) else {})
            parsed["sent"] = bool(parsed.get("order_id"))
            parsed["side"] = "BUY"
            parsed["type"] = "GTC"
            parsed["price"] = float(px)
            parsed["size"] = float(size)
            parsed["token_id"] = str(tok)
            parsed["outcome"] = outcome
            parsed["maker_bid"] = True
            posted.append(parsed)
        if len(posted) == 2 and all(p.get("order_id") for p in posted):
            if timings is not None:
                timings["sign_ms"] = sign_ms
                timings["post_http_ms"] = (time.time() - t_http) * 1000.0
                timings["post_ack_ms"] = (time.time() - t_all) * 1000.0
            return posted
        for prev in posted:
            if prev.get("order_id"):
                try:
                    cancel_order(client, str(prev["order_id"]))
                except Exception:
                    pass
        posted = []
    except AuthAbsent:
        raise
    except Exception:
        posted = []
    t_fb = time.time()
    up = create_gtc_buy(client, token_id=token_up, price=price_up, size=size)
    posted = [{**up, "outcome": "Up", "maker_bid": True}]
    try:
        down = create_gtc_buy(client, token_id=token_down, price=price_down, size=size)
        posted.append({**down, "outcome": "Down", "maker_bid": True})
    except Exception:
        if posted and posted[0].get("order_id"):
            try:
                cancel_order(client, str(posted[0]["order_id"]))
            except Exception:
                pass
        raise
    if timings is not None:
        timings["sign_ms"] = None
        timings["post_http_ms"] = None
        timings["post_ack_ms"] = (time.time() - t_fb) * 1000.0
        timings["post_fallback"] = True
    return posted


def create_fok_buy(
    client: Any,
    *,
    token_id: str,
    price: float,
    size: float,
) -> dict[str, Any]:
    """Post a BUY FOK (adverse complete only). Requires a live client. Does not invent fills."""
    return _post_buy(client, token_id=token_id, price=price, size=size, order_type="FOK")


def cancel_order(client: Any, order_id: str) -> dict[str, Any]:
    if client is None:
        raise AuthAbsent("AUTH_ABSENT")
    _ClobClient, _ApiCreds, _OrderArgs, _OrderType, OrderPayload = _import_client()
    resp = client.cancel_order(OrderPayload(orderID=str(order_id)))
    out = parse_order_status(resp if isinstance(resp, dict) else {"orderID": order_id, "status": "cancelled"})
    out["order_id"] = out.get("order_id") or str(order_id)
    out["status"] = out.get("status") or "cancelled"
    out["sent"] = True
    return out


def fetch_order(client: Any, order_id: str) -> dict[str, Any]:
    if client is None:
        raise AuthAbsent("AUTH_ABSENT")
    resp = client.get_order(str(order_id))
    parsed = parse_order_status(resp if isinstance(resp, dict) else {})
    parsed["order_id"] = parsed.get("order_id") or str(order_id)
    parsed["sent"] = True
    if isinstance(resp, dict):
        parsed["associate_trades"] = resp.get("associate_trades") or []
        parsed["created_at"] = resp.get("created_at")
        if resp.get("price") is not None:
            parsed["clob_price"] = resp.get("price")
    return parsed


def stamp_trader_side(client: Any, order: dict[str, Any]) -> dict[str, Any]:
    """CLOB trader_side maker|taker. Separate from S1 edge. No invented fill."""
    oid = order.get("order_id")
    if client is None or not oid:
        return order
    try:
        from py_clob_client_v2.clob_types import TradeParams
    except Exception:
        return order
    trade_ids = list(order.get("associate_trades") or [])
    if not trade_ids:
        try:
            raw = client.get_order(str(oid))
            if isinstance(raw, dict):
                trade_ids = list(raw.get("associate_trades") or [])
                order["associate_trades"] = trade_ids
        except Exception:
            return order
    for tid in trade_ids[:4]:
        try:
            found = client.get_trades(TradeParams(id=str(tid)), only_first_page=True)
        except Exception:
            continue
        rows = found if isinstance(found, list) else []
        if not rows:
            continue
        trade = rows[0] if isinstance(rows[0], dict) else {}
        side = str(trade.get("trader_side") or "").strip().lower()
        if side not in {"maker", "taker"}:
            if str(trade.get("taker_order_id") or "") == str(oid):
                side = "taker"
            else:
                side = "maker"
        order["trader_side"] = side
        order["fill_role"] = side
        try:
            order["trade_price"] = float(trade["price"])
        except (KeyError, TypeError, ValueError):
            pass
        return order
    if float(order.get("filled_size") or 0.0) <= 0:
        order.setdefault("trader_side", None)
        order.setdefault("fill_role", None)
    return order


def refuse_send() -> dict[str, Any]:
    """Canonical no-auth result. real_fill stays null."""
    return {
        "sent": False,
        "auth_available": False,
        "reason": "AUTH_ABSENT",
        "real_fill": None,
        "real_fill_rate": None,
        "live_order": False,
        "pair_gt_1_trade": False,
    }
