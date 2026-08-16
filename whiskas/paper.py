"""Paper logger: intended BUY FOKs against the live CLOB. Never posts an order."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from whiskas.constants import CLIP, CLOB_API, GAMMA_API, PAIR_MAX, PAIR_MAX_CAP, WINDOW_SECONDS
from whiskas.http import get_json
from whiskas.policy import decide

PAPER_ASSETS = ("btc", "eth", "sol", "xrp")
CONFIRM_DELAY_SEC = 0.25


def current_t0(now: float | None = None) -> int:
    ts = time.time() if now is None else float(now)
    return int(ts // WINDOW_SECONDS) * WINDOW_SECONDS


def asset_window_slug(asset: str, t0: int) -> str:
    return f"{str(asset).strip().lower()}-updown-5m-{int(t0)}"


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


def size_at_or_better(book: dict[str, Any] | None, limit_price: float) -> float:
    """BUY FOK at limit_price: sum ask size with price ≤ limit."""
    if not book or limit_price <= 0:
        return 0.0
    total = 0.0
    for level in book.get("asks") or []:
        try:
            price = float(level.get("price"))
            size = float(level.get("size") or 0.0)
        except (TypeError, ValueError):
            continue
        if price <= 0 or size <= 0:
            continue
        if price <= float(limit_price) + 1e-12:
            total += size
    return total


def fetch_book(token_id: str, *, pause: float = 0.08) -> dict[str, Any]:
    return get_json(f"{CLOB_API}/book", {"token_id": token_id}, timeout=20, retries=3, pause=pause)


def confirm_ask_exists(
    tokens: dict[str, str],
    ask_up: float,
    ask_down: float,
    clip: float,
    *,
    books: dict[str, dict[str, Any]] | None = None,
) -> bool:
    """True if both intended asks still have ≥ clip size at that price or better."""
    try:
        if books is not None:
            book_up = books.get("Up") or {}
            book_down = books.get("Down") or {}
        else:
            book_up = fetch_book(tokens["Up"], pause=0.0)
            book_down = fetch_book(tokens["Down"], pause=0.0)
    except Exception:
        return False
    return (
        size_at_or_better(book_up, ask_up) + 1e-12 >= float(clip)
        and size_at_or_better(book_down, ask_down) + 1e-12 >= float(clip)
    )


def snapshot_window(
    *,
    now: float | None = None,
    pair_max: float = PAIR_MAX,
    pair_max_cap: float = PAIR_MAX_CAP,
    clip: float = CLIP,
    tokens: dict[str, str] | None = None,
    books: dict[str, dict[str, Any]] | None = None,
    asset: str = "btc",
) -> dict[str, Any]:
    t0 = current_t0(now)
    asset_key = str(asset).strip().lower()
    slug = asset_window_slug(asset_key, t0)
    ts = datetime.now(timezone.utc).isoformat()
    rec: dict[str, Any] = {
        "ts": ts,
        "t0": t0,
        "asset": asset_key,
        "slug": slug,
        "market": f"{asset_key}-updown-5m",
        "clip": float(clip),
        "pair_max": float(pair_max),
        "live_order": False,
        "maker_bid": False,
        "still_there_250ms": None,
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
    rec["min_ask_size"] = min(depth_up, depth_down) if ask_up is not None and ask_down is not None else 0.0
    rec["depth_ok"] = (
        ask_up is not None
        and ask_down is not None
        and rec["min_ask_size"] + 1e-12 >= float(clip)
    )
    decision = decide(ask_up, ask_down, pair_max=pair_max, pair_max_cap=pair_max_cap, clip=clip)
    rec["ask_sum"] = decision.ask_sum
    if decision.intend and rec["depth_ok"]:
        rec["intend"] = True
        rec["reason"] = "complete_set_fok"
        rec["orders"] = [o.to_dict() for o in decision.orders]
        rec["depth_short"] = False
    else:
        rec["intend"] = False
        rec["reason"] = decision.reason if not decision.intend else "depth_short"
        rec["orders"] = []
        rec["depth_short"] = bool(decision.intend and not rec["depth_ok"])
    return rec


def append_jsonl(path: Path, rec: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, separators=(",", ":")) + "\n")


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict):
                rows.append(rec)
    return rows


def _empty_asset_stats() -> dict[str, Any]:
    return {
        "n_poll": 0,
        "n_le_096": 0,
        "n_le_096_depth_ge_clip": 0,
        "n_still_there_250ms": 0,
        "n_err": 0,
    }


def summarize_paper(
    rows: list[dict[str, Any]],
    *,
    since: datetime | None = None,
    pair_max: float = PAIR_MAX,
    clip: float = CLIP,
    assets: Iterable[str] = PAPER_ASSETS,
) -> dict[str, Any]:
    """Per-asset: polls, ask_sum≤0.96, depth≥21, still-there@250ms."""
    wanted = [str(a).strip().lower() for a in assets]
    by_asset = {a: _empty_asset_stats() for a in wanted}
    first_ts = None
    last_ts = None
    for rec in rows:
        ts = _parse_ts(rec.get("ts"))
        if since is not None and ts is not None and ts < since:
            continue
        asset = str(rec.get("asset") or "btc").strip().lower()
        if asset not in by_asset:
            by_asset[asset] = _empty_asset_stats()
        bucket = by_asset[asset]
        bucket["n_poll"] += 1
        if first_ts is None or (ts is not None and ts < first_ts):
            first_ts = ts
        if last_ts is None or (ts is not None and ts > last_ts):
            last_ts = ts
        if rec.get("error") or rec.get("reason") in {"gamma_error", "clob_error", "poll_error"}:
            bucket["n_err"] += 1
        ask_sum = rec.get("ask_sum")
        try:
            s = float(ask_sum) if ask_sum is not None else None
        except (TypeError, ValueError):
            s = None
        if s is None or s > float(pair_max) + 1e-12:
            continue
        bucket["n_le_096"] += 1
        depth_up = float(rec.get("depth_up") or 0.0)
        depth_down = float(rec.get("depth_down") or 0.0)
        if min(depth_up, depth_down) + 1e-12 >= float(clip):
            bucket["n_le_096_depth_ge_clip"] += 1
        if rec.get("still_there_250ms") is True:
            bucket["n_still_there_250ms"] += 1
    totals = _empty_asset_stats()
    for bucket in by_asset.values():
        for key in totals:
            totals[key] += bucket[key]
    return {
        "n_poll": totals["n_poll"],
        "n_le_096": totals["n_le_096"],
        "n_le_096_depth_ge_clip": totals["n_le_096_depth_ge_clip"],
        "n_still_there_250ms": totals["n_still_there_250ms"],
        "n_err": totals["n_err"],
        "pair_max": float(pair_max),
        "clip": float(clip),
        "first_ts": first_ts.isoformat() if first_ts else None,
        "last_ts": last_ts.isoformat() if last_ts else None,
        "assets": by_asset,
        "paper_pass_if_zero_edge": totals["n_le_096"] == 0,
        "note": (
            "0 prints with ask_sum≤0.96 is a paper PASS: live book did not show the pair."
            if totals["n_le_096"] == 0
            else "Live book printed ask_sum≤0.96 at least once. Still no orders."
        ),
    }


def run_paper(
    *,
    out_path: Path,
    once: bool = True,
    seconds: float = 0.0,
    interval: float = 5.0,
    pair_max: float = PAIR_MAX,
    clip: float = CLIP,
    collect: bool = True,
    heartbeat_every: int = 60,
    assets: Iterable[str] = PAPER_ASSETS,
    confirm_delay: float = CONFIRM_DELAY_SEC,
) -> list[dict[str, Any]]:
    """Poll live books for each asset. One jsonl line per asset per poll. Never send orders."""
    asset_list = [str(a).strip().lower() for a in assets]
    forever = (not once) and float(seconds) <= 0
    deadline = None if forever else time.time() + max(0.0, float(seconds))
    rows: list[dict[str, Any]] = []
    token_cache: dict[str, dict[str, str]] = {}
    n_lines = 0
    n_cycles = 0
    next_tick = time.time()
    while True:
        t0 = current_t0()
        cycle_sums: dict[str, Any] = {}
        for asset in asset_list:
            slug = asset_window_slug(asset, t0)
            tokens = token_cache.get(slug)
            if tokens is None:
                try:
                    tokens = discover_tokens(slug)
                except Exception:
                    tokens = {}
                if tokens:
                    stale = [k for k in token_cache if k.startswith(f"{asset}-updown-5m-") and k != slug]
                    for key in stale:
                        token_cache.pop(key, None)
                    token_cache[slug] = tokens
            try:
                rec = snapshot_window(
                    pair_max=pair_max,
                    clip=clip,
                    tokens=tokens or None,
                    asset=asset,
                )
            except Exception as exc:
                rec = {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "t0": t0,
                    "asset": asset,
                    "slug": slug,
                    "clip": float(clip),
                    "pair_max": float(pair_max),
                    "live_order": False,
                    "maker_bid": False,
                    "intend": False,
                    "reason": "poll_error",
                    "error": str(exc),
                    "orders": [],
                    "still_there_250ms": None,
                }
            if rec.get("intend") and tokens and rec.get("ask_up") is not None and rec.get("ask_down") is not None:
                time.sleep(max(0.0, float(confirm_delay)))
                rec["still_there_250ms"] = confirm_ask_exists(
                    tokens,
                    float(rec["ask_up"]),
                    float(rec["ask_down"]),
                    clip,
                )
                rec["ts_250ms"] = datetime.now(timezone.utc).isoformat()
            else:
                rec["still_there_250ms"] = None
            rec["live_order"] = False
            append_jsonl(out_path, rec)
            n_lines += 1
            cycle_sums[asset] = rec.get("ask_sum")
            if collect:
                rows.append(rec)
        n_cycles += 1
        if heartbeat_every and n_cycles % int(heartbeat_every) == 0:
            print(
                json.dumps(
                    {
                        "heartbeat_cycles": n_cycles,
                        "lines": n_lines,
                        "t0": t0,
                        "ask_sum": cycle_sums,
                        "live_order": False,
                    }
                ),
                flush=True,
            )
        if once or (deadline is not None and time.time() >= deadline):
            break
        next_tick += max(0.2, float(interval))
        sleep_for = next_tick - time.time()
        if sleep_for < 0:
            next_tick = time.time()
            sleep_for = 0.2
        time.sleep(sleep_for)
    return rows
