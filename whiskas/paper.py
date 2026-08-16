"""Paper logger: intended BUY FOKs against the live CLOB. Never posts an order."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from whiskas.constants import (
    BTC_5M_PREFIX,
    CLIP,
    CLOB_API,
    GAMMA_API,
    PAIR_MAX,
    PAIR_MAX_CAP,
    WINDOW_SECONDS,
)
from whiskas.http import get_json
from whiskas.policy import decide
from whiskas.slug import window_slug


def current_t0(now: float | None = None) -> int:
    ts = time.time() if now is None else float(now)
    return int(ts // WINDOW_SECONDS) * WINDOW_SECONDS


def _as_list(payload: Any) -> list[Any]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if "markets" in payload and isinstance(payload["markets"], list):
            return [payload]
        return [payload]
    return []


def _parse_json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def tokens_from_market(market: dict[str, Any]) -> dict[str, str]:
    outcomes = [str(x) for x in _parse_json_list(market.get("outcomes"))]
    token_ids = [str(x) for x in _parse_json_list(market.get("clobTokenIds"))]
    out: dict[str, str] = {}
    for outcome, token_id in zip(outcomes, token_ids):
        key = outcome.strip().lower()
        if key in {"up", "down"} and token_id:
            out[key.capitalize()] = token_id
    return out


def discover_tokens(slug: str) -> dict[str, str]:
    """Gamma public market → Up/Down CLOB token ids. GET only."""
    events = get_json(f"{GAMMA_API}/events", {"slug": slug}, timeout=20, retries=3, pause=0.08)
    for event in _as_list(events):
        markets = event.get("markets") if isinstance(event, dict) else None
        if not markets:
            continue
        for market in markets:
            tokens = tokens_from_market(market)
            if "Up" in tokens and "Down" in tokens:
                return tokens
    markets = get_json(f"{GAMMA_API}/markets", {"slug": slug}, timeout=20, retries=3, pause=0.08)
    for market in _as_list(markets):
        if not isinstance(market, dict):
            continue
        tokens = tokens_from_market(market)
        if "Up" in tokens and "Down" in tokens:
            return tokens
    return {}


def best_ask(book: dict[str, Any] | None) -> tuple[float | None, float]:
    """Min ask price. Docs disagree on sort; never trust first row. Size is at that price only."""
    if not book:
        return None, 0.0
    asks = book.get("asks") or []
    best_p: float | None = None
    best_sz = 0.0
    for level in asks:
        try:
            price = float(level.get("price"))
            size = float(level.get("size") or 0.0)
        except (TypeError, ValueError):
            continue
        if price <= 0 or size < 0:
            continue
        if best_p is None or price < best_p:
            best_p = price
            best_sz = size
        elif price == best_p:
            best_sz += size
    return best_p, best_sz


def fetch_book(token_id: str) -> dict[str, Any]:
    return get_json(f"{CLOB_API}/book", {"token_id": token_id}, timeout=20, retries=3, pause=0.08)


def snapshot_window(
    *,
    now: float | None = None,
    pair_max: float = PAIR_MAX,
    pair_max_cap: float = PAIR_MAX_CAP,
    clip: float = CLIP,
    tokens: dict[str, str] | None = None,
    books: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    t0 = current_t0(now)
    slug = window_slug(t0)
    ts = datetime.now(timezone.utc).isoformat()
    rec: dict[str, Any] = {
        "ts": ts,
        "t0": t0,
        "slug": slug,
        "market": f"{BTC_5M_PREFIX.rstrip('-')}",
        "clip": float(clip),
        "pair_max": float(pair_max),
        "live_order": False,
        "maker_bid": False,
    }
    try:
        tok = tokens if tokens is not None else discover_tokens(slug)
    except Exception as exc:
        rec["error"] = f"gamma:{exc}"
        rec["intend"] = False
        rec["reason"] = "gamma_error"
        rec["orders"] = []
        return rec
    if "Up" not in tok or "Down" not in tok:
        rec["error"] = "missing_tokens"
        rec["intend"] = False
        rec["reason"] = "missing_tokens"
        rec["orders"] = []
        return rec
    rec["token_up"] = tok["Up"]
    rec["token_down"] = tok["Down"]
    try:
        if books is not None:
            book_up = books.get("Up") or {}
            book_down = books.get("Down") or {}
        else:
            book_up = fetch_book(tok["Up"])
            book_down = fetch_book(tok["Down"])
    except Exception as exc:
        rec["error"] = f"clob:{exc}"
        rec["intend"] = False
        rec["reason"] = "clob_error"
        rec["orders"] = []
        return rec
    ask_up, depth_up = best_ask(book_up)
    ask_down, depth_down = best_ask(book_down)
    rec["ask_up"] = ask_up
    rec["ask_down"] = ask_down
    rec["depth_up"] = depth_up
    rec["depth_down"] = depth_down
    rec["depth_ok"] = (
        ask_up is not None
        and ask_down is not None
        and depth_up + 1e-12 >= clip
        and depth_down + 1e-12 >= clip
    )
    decision = decide(ask_up, ask_down, pair_max=pair_max, pair_max_cap=pair_max_cap, clip=clip)
    rec.update(decision.to_dict())
    rec["depth_short"] = bool(decision.intend and not rec["depth_ok"])
    return rec


def append_jsonl(path: Path, rec: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, separators=(",", ":")) + "\n")


def run_paper(
    *,
    out_path: Path,
    once: bool = True,
    seconds: float = 0.0,
    interval: float = 5.0,
    pair_max: float = PAIR_MAX,
    clip: float = CLIP,
) -> list[dict[str, Any]]:
    """Poll live books. Log intended FOKs. Never send orders."""
    deadline = time.time() + max(0.0, float(seconds))
    rows: list[dict[str, Any]] = []
    while True:
        rec = snapshot_window(pair_max=pair_max, clip=clip)
        append_jsonl(out_path, rec)
        rows.append(rec)
        if once or time.time() >= deadline:
            break
        time.sleep(max(0.2, float(interval)))
    return rows
