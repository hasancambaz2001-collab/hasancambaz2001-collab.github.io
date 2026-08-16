"""Paper logger: intended BUY FOKs against the live CLOB. Never posts an order."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from whiskas.constants import CLIP, CLOB_API, GAMMA_API, PAIR_MAX, PAIR_MAX_CAP, REPEAT_CLIP_MAX, WINDOW_SECONDS
from whiskas.http import get_json
from whiskas.policy import BookInventory, PolicyDecision, decide_a, decide_a2, decide_repeat

PAPER_ASSETS = ("btc", "eth", "sol", "xrp")
PAPER_TFS = ("5m", "15m", "4h")
PAPER_BUCKETS = (0.90, 0.96)
TF_SECONDS = {"5m": 300, "15m": 900, "4h": 14400}
CONFIRM_DELAY_SEC = 0.25


def normalize_tf(tf: str | None) -> str:
    key = str(tf or "5m").strip().lower()
    return key if key in TF_SECONDS else "5m"


def is_poll_only_tf(tf: str | None) -> bool:
    """4h is measure-only: poll the book, never A/A2/repeat."""
    return normalize_tf(tf) == "4h"


def current_t0(now: float | None = None, tf: str = "5m") -> int:
    ts = time.time() if now is None else float(now)
    sec = TF_SECONDS.get(normalize_tf(tf), WINDOW_SECONDS)
    return int(ts // sec) * sec


def asset_window_slug(asset: str, t0: int, tf: str = "5m") -> str:
    return f"{str(asset).strip().lower()}-updown-{normalize_tf(tf)}-{int(t0)}"


def book_key(asset: str, tf: str = "5m") -> str:
    return f"{str(asset).strip().lower()}:{normalize_tf(tf)}"


def _set_buckets(rec: dict[str, Any]) -> None:
    try:
        s = float(rec["ask_sum"]) if rec.get("ask_sum") is not None else None
    except (TypeError, ValueError):
        s = None
    rec["bucket_le_090"] = s is not None and s <= 0.90 + 1e-12
    rec["bucket_le_096"] = s is not None and s <= 0.96 + 1e-12


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
    orders = (
        {"outcome": "Up", "price": ask_up, "size": clip},
        {"outcome": "Down", "price": ask_down, "size": clip},
    )
    return bool(confirm_orders(tokens, orders, books=books))


def confirm_orders(
    tokens: dict[str, str],
    orders: Iterable[Any],
    *,
    books: dict[str, dict[str, Any]] | None = None,
) -> bool:
    """True if each intended BUY still has size at that price or better."""
    try:
        if books is not None:
            book_up = books.get("Up") or {}
            book_down = books.get("Down") or {}
        else:
            book_up = fetch_book(tokens["Up"], pause=0.0)
            book_down = fetch_book(tokens["Down"], pause=0.0)
    except Exception:
        return False
    ok = False
    for order in orders:
        if hasattr(order, "outcome"):
            outcome, price, size = order.outcome, float(order.price), float(order.size)
        else:
            outcome = str(order.get("outcome"))
            price = float(order.get("price"))
            size = float(order.get("size"))
        book = book_up if outcome == "Up" else book_down
        if size_at_or_better(book, price) + 1e-12 < size:
            return False
        ok = True
    return ok


def snapshot_window(
    *,
    now: float | None = None,
    pair_max: float = PAIR_MAX,
    pair_max_cap: float = PAIR_MAX_CAP,
    clip: float = CLIP,
    tokens: dict[str, str] | None = None,
    books: dict[str, dict[str, Any]] | None = None,
    asset: str = "btc",
    tf: str = "5m",
    inventory: BookInventory | None = None,
    filled_this_window: bool = False,
    clips_this_window: int = 0,
    max_clips: int = REPEAT_CLIP_MAX,
    poll_only: bool | None = None,
) -> dict[str, Any]:
    tf_key = normalize_tf(tf)
    measure_only = is_poll_only_tf(tf_key) if poll_only is None else bool(poll_only)
    t0 = current_t0(now, tf=tf_key)
    asset_key = str(asset).strip().lower()
    slug = asset_window_slug(asset_key, t0, tf_key)
    ts = datetime.now(timezone.utc).isoformat()
    rec: dict[str, Any] = {
        "ts": ts,
        "t0": t0,
        "asset": asset_key,
        "tf": tf_key,
        "slug": slug,
        "market": f"{asset_key}-updown-{tf_key}",
        "clip": float(clip),
        "pair_max": float(pair_max),
        "live_order": False,
        "maker_bid": False,
        "poll_only": measure_only,
        "still_there_250ms": None,
        "a_intend": False,
        "a2_intend": False,
        "repeat_intend": False,
        "clips_this_window": int(clips_this_window),
        "held_leg": None,
        "held_qty": 0.0,
        "bucket_le_090": False,
        "bucket_le_096": False,
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
    inv = inventory if inventory is not None else BookInventory()
    rec["held_leg"] = inv.residual_leg()
    rec["held_qty"] = inv.residual_qty()
    rec["avg_up"] = inv.avg("Up")
    rec["avg_down"] = inv.avg("Down")
    if measure_only:
        rec["ask_sum"] = (
            float(ask_up) + float(ask_down) if ask_up is not None and ask_down is not None else None
        )
        _set_buckets(rec)
        rec["intend"] = False
        rec["a_intend"] = False
        rec["a2_intend"] = False
        rec["repeat_intend"] = False
        rec["reason"] = "poll_only"
        rec["a_reason"] = "poll_only"
        rec["a2_reason"] = "poll_only"
        rec["repeat_reason"] = "poll_only"
        rec["a_orders"] = []
        rec["a2_orders"] = []
        rec["repeat_orders"] = []
        rec["orders"] = []
        rec["filled_this_window"] = bool(filled_this_window)
        rec["clips_this_window"] = int(clips_this_window)
        return rec
    a = decide_a(ask_up, ask_down, depth_up, depth_down, pair_max=pair_max, pair_max_cap=pair_max_cap, clip=clip)
    if filled_this_window and a.intend:
        a = PolicyDecision(False, "a_already_filled", a.ask_up, a.ask_down, a.ask_sum, a.clip)
    a2 = decide_a2(
        ask_up,
        ask_down,
        depth_up,
        depth_down,
        inv,
        pair_max=pair_max,
        pair_max_cap=pair_max_cap,
        clip=clip,
    )
    rec["ask_sum"] = a.ask_sum if a.ask_sum is not None else a2.ask_sum
    _set_buckets(rec)
    rec["a_intend"] = bool(a.intend)
    rec["a2_intend"] = bool(a2.intend)
    rec["a_reason"] = a.reason
    rec["a2_reason"] = a2.reason
    rec["a_orders"] = [o.to_dict() for o in a.orders]
    rec["a2_orders"] = [o.to_dict() for o in a2.orders]
    rec["intend"] = rec["a_intend"]
    rec["reason"] = a.reason if a.intend else (a2.reason if a2.intend else a.reason)
    rec["orders"] = rec["a_orders"] if a.intend else rec["a2_orders"]
    rec["depth_short"] = a.reason == "depth_short"
    clips = int(clips_this_window)
    filled = bool(filled_this_window)
    if rec["a_intend"] or rec["a2_intend"]:
        filled = True
        if clips < int(max_clips):
            clips += 1
        rec["repeat_intend"] = False
        rec["repeat_reason"] = "repeat_not_same_poll"
        rec["repeat_orders"] = []
    else:
        rpt = decide_repeat(
            ask_up,
            ask_down,
            depth_up,
            depth_down,
            inv,
            filled_this_window=filled,
            clips_this_window=clips,
            pair_max=pair_max,
            clip=clip,
            max_clips=max_clips,
        )
        rec["repeat_intend"] = bool(rpt.intend)
        rec["repeat_reason"] = rpt.reason
        rec["repeat_orders"] = [o.to_dict() for o in rpt.orders]
        if rpt.intend:
            clips += 1
    rec["clips_this_window"] = clips
    rec["filled_this_window"] = filled
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
        "n_a_hits": 0,
        "n_a2_hits": 0,
        "n_repeat_hits": 0,
        "max_clips_on_hit": 0,
        "n_le_096_depth_ge_clip": 0,
        "n_still_there_250ms": 0,
        "n_err": 0,
    }


def _empty_bucket_cell() -> dict[str, int]:
    return {"polls": 0, "A_hits": 0, "A2_hits": 0, "repeat_hits": 0, "depth_ok": 0, "still250": 0}


def _row_depth_ok(rec: dict[str, Any], clip: float) -> bool:
    if rec.get("depth_ok") is True:
        return True
    if rec.get("depth_ok") is False:
        return False
    depth_up = float(rec.get("depth_up") or 0.0)
    depth_down = float(rec.get("depth_down") or 0.0)
    return min(depth_up, depth_down) + 1e-12 >= float(clip)


def summarize_paper(
    rows: list[dict[str, Any]],
    *,
    since: datetime | None = None,
    pair_max: float = PAIR_MAX,
    clip: float = CLIP,
    assets: Iterable[str] = PAPER_ASSETS,
    tfs: Iterable[str] = PAPER_TFS,
) -> dict[str, Any]:
    """asset × tf × bucket: polls, A/A2/repeat hits, depth≥21, still@250ms."""
    wanted = [str(a).strip().lower() for a in assets]
    wanted_tfs = [normalize_tf(t) for t in tfs]
    polls: dict[tuple[str, str], int] = {(a, t): 0 for a in wanted for t in wanted_tfs}
    cells: dict[tuple[str, str, float], dict[str, int]] = {
        (a, t, b): _empty_bucket_cell() for a in wanted for t in wanted_tfs for b in PAPER_BUCKETS
    }
    by_asset = {a: _empty_asset_stats() for a in wanted}
    first_ts = None
    last_ts = None
    for rec in rows:
        ts = _parse_ts(rec.get("ts"))
        if since is not None and ts is not None and ts < since:
            continue
        asset = str(rec.get("asset") or "btc").strip().lower()
        tf = normalize_tf(rec.get("tf"))
        if (asset, tf) not in polls:
            polls[(asset, tf)] = 0
            for b in PAPER_BUCKETS:
                cells[(asset, tf, b)] = _empty_bucket_cell()
        if asset not in by_asset:
            by_asset[asset] = _empty_asset_stats()
        polls[(asset, tf)] += 1
        bucket = by_asset[asset]
        bucket["n_poll"] += 1
        if first_ts is None or (ts is not None and ts < first_ts):
            first_ts = ts
        if last_ts is None or (ts is not None and ts > last_ts):
            last_ts = ts
        if rec.get("error") or rec.get("reason") in {"gamma_error", "clob_error", "poll_error"}:
            bucket["n_err"] += 1
        try:
            s = float(rec["ask_sum"]) if rec.get("ask_sum") is not None else None
        except (TypeError, ValueError):
            s = None
        if rec.get("a_intend") or rec.get("intend"):
            bucket["n_a_hits"] += 1
        if rec.get("a2_intend"):
            bucket["n_a2_hits"] += 1
        if rec.get("repeat_intend"):
            bucket["n_repeat_hits"] += 1
        if rec.get("a_intend") or rec.get("a2_intend") or rec.get("repeat_intend"):
            clips = int(rec.get("clips_this_window") or 0)
            if clips > bucket["max_clips_on_hit"]:
                bucket["max_clips_on_hit"] = clips
        if rec.get("still_there_250ms") is True:
            bucket["n_still_there_250ms"] += 1
        depth_ok = _row_depth_ok(rec, clip)
        for thresh in PAPER_BUCKETS:
            if s is None or s > float(thresh) + 1e-12:
                continue
            cell = cells[(asset, tf, thresh)]
            if rec.get("a_intend"):
                cell["A_hits"] += 1
            if rec.get("a2_intend"):
                cell["A2_hits"] += 1
            if rec.get("repeat_intend"):
                cell["repeat_hits"] += 1
            if depth_ok:
                cell["depth_ok"] += 1
            if rec.get("still_there_250ms") is True:
                cell["still250"] += 1
        if s is None or s > float(pair_max) + 1e-12:
            continue
        bucket["n_le_096"] += 1
        if depth_ok:
            bucket["n_le_096_depth_ge_clip"] += 1
    assets_out = list(wanted)
    for asset, tf in polls:
        if asset not in assets_out:
            assets_out.append(asset)
    tfs_out = list(wanted_tfs)
    for asset, tf in polls:
        if tf not in tfs_out:
            tfs_out.append(tf)
    table: list[dict[str, Any]] = []
    for asset in assets_out:
        for tf in tfs_out:
            n_poll = int(polls.get((asset, tf), 0))
            for thresh in PAPER_BUCKETS:
                cell = cells.get((asset, tf, thresh)) or _empty_bucket_cell()
                table.append(
                    {
                        "asset": asset,
                        "tf": tf,
                        "bucket": f"{thresh:.2f}",
                        "polls": n_poll,
                        "A_hits": cell["A_hits"],
                        "A2_hits": cell["A2_hits"],
                        "repeat_hits": cell["repeat_hits"],
                        "depth_ok": cell["depth_ok"],
                        "still250": cell["still250"],
                    }
                )
    totals = _empty_asset_stats()
    for bucket in by_asset.values():
        for key in totals:
            if key == "max_clips_on_hit":
                totals[key] = max(totals[key], bucket[key])
            else:
                totals[key] += bucket[key]
    return {
        "n_poll": totals["n_poll"],
        "n_le_096": totals["n_le_096"],
        "n_a_hits": totals["n_a_hits"],
        "n_a2_hits": totals["n_a2_hits"],
        "n_repeat_hits": totals["n_repeat_hits"],
        "max_clips_on_hit": totals["max_clips_on_hit"],
        "n_le_096_depth_ge_clip": totals["n_le_096_depth_ge_clip"],
        "n_still_there_250ms": totals["n_still_there_250ms"],
        "n_err": totals["n_err"],
        "pair_max": float(pair_max),
        "clip": float(clip),
        "first_ts": first_ts.isoformat() if first_ts else None,
        "last_ts": last_ts.isoformat() if last_ts else None,
        "table": table,
        "assets": by_asset,
        "paper_pass_if_zero_edge": totals["n_le_096"] == 0,
        "note": (
            "0 prints with ask_sum≤0.96 is a paper PASS: live book did not show the pair."
            if totals["n_le_096"] == 0
            else "Live book printed ask_sum≤0.96 at least once. Still no orders. 4h is poll-only."
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
    tfs: Iterable[str] = PAPER_TFS,
    confirm_delay: float = CONFIRM_DELAY_SEC,
) -> list[dict[str, Any]]:
    """Poll live books per asset×tf. 4h is poll-only. Never send orders."""
    asset_list = [str(a).strip().lower() for a in assets]
    tf_list = [normalize_tf(t) for t in tfs]
    keys = [book_key(a, t) for a in asset_list for t in tf_list]
    forever = (not once) and float(seconds) <= 0
    deadline = None if forever else time.time() + max(0.0, float(seconds))
    rows: list[dict[str, Any]] = []
    token_cache: dict[str, dict[str, str]] = {}
    inventories: dict[str, BookInventory] = {k: BookInventory() for k in keys}
    clip_state: dict[str, dict[str, Any]] = {k: {"t0": None, "clips": 0, "filled": False} for k in keys}
    n_lines = 0
    n_cycles = 0
    next_tick = time.time()
    while True:
        cycle_sums: dict[str, Any] = {}
        for asset in asset_list:
            for tf in tf_list:
                t0 = current_t0(tf=tf)
                key = book_key(asset, tf)
                inv = inventories.get(key) or BookInventory()
                st = clip_state.get(key) or {"t0": None, "clips": 0, "filled": False}
                if inv.t0 != t0:
                    inventories[key] = BookInventory(t0=t0)
                    inv = inventories[key]
                if st.get("t0") != t0:
                    st = {"t0": t0, "clips": 0, "filled": False}
                    clip_state[key] = st
                slug = asset_window_slug(asset, t0, tf)
                tokens = token_cache.get(slug)
                if tokens is None:
                    try:
                        tokens = discover_tokens(slug)
                    except Exception:
                        tokens = {}
                    if tokens:
                        stale = [k for k in token_cache if k.startswith(f"{asset}-updown-{tf}-") and k != slug]
                        for old in stale:
                            token_cache.pop(old, None)
                        token_cache[slug] = tokens
                try:
                    rec = snapshot_window(
                        pair_max=pair_max,
                        clip=clip,
                        tokens=tokens or None,
                        asset=asset,
                        tf=tf,
                        inventory=inv,
                        filled_this_window=bool(st["filled"]),
                        clips_this_window=int(st["clips"]),
                    )
                except Exception as exc:
                    rec = {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "t0": t0,
                        "asset": asset,
                        "tf": tf,
                        "slug": slug,
                        "market": f"{asset}-updown-{tf}",
                        "clip": float(clip),
                        "pair_max": float(pair_max),
                        "live_order": False,
                        "maker_bid": False,
                        "poll_only": is_poll_only_tf(tf),
                        "intend": False,
                        "a_intend": False,
                        "a2_intend": False,
                        "repeat_intend": False,
                        "clips_this_window": int(st["clips"]),
                        "reason": "poll_error",
                        "error": str(exc),
                        "orders": [],
                        "still_there_250ms": None,
                        "bucket_le_090": False,
                        "bucket_le_096": False,
                    }
                poll_only = bool(rec.get("poll_only") or is_poll_only_tf(tf))
                confirm_list = rec.get("a2_orders") or rec.get("a_orders") or rec.get("repeat_orders") or rec.get("orders") or []
                if (
                    (not poll_only)
                    and (rec.get("a_intend") or rec.get("a2_intend") or rec.get("repeat_intend"))
                    and tokens
                    and confirm_list
                ):
                    time.sleep(max(0.0, float(confirm_delay)))
                    rec["still_there_250ms"] = confirm_orders(tokens, confirm_list)
                    rec["ts_250ms"] = datetime.now(timezone.utc).isoformat()
                elif (
                    poll_only
                    and tokens
                    and rec.get("bucket_le_096")
                    and rec.get("depth_ok")
                    and rec.get("ask_up") is not None
                    and rec.get("ask_down") is not None
                ):
                    time.sleep(max(0.0, float(confirm_delay)))
                    rec["still_there_250ms"] = confirm_ask_exists(
                        tokens,
                        float(rec["ask_up"]),
                        float(rec["ask_down"]),
                        float(clip),
                    )
                    rec["ts_250ms"] = datetime.now(timezone.utc).isoformat()
                else:
                    rec["still_there_250ms"] = None
                if (not poll_only) and rec.get("a2_intend") and rec.get("a2_orders"):
                    for order in rec["a2_orders"]:
                        inv.apply_buy(str(order["outcome"]), float(order["size"]), float(order["price"]))
                st["clips"] = int(rec.get("clips_this_window") or st["clips"])
                st["filled"] = bool(rec.get("filled_this_window") or st["filled"])
                clip_state[key] = st
                rec["live_order"] = False
                append_jsonl(out_path, rec)
                n_lines += 1
                cycle_sums[key] = rec.get("ask_sum")
                if collect:
                    rows.append(rec)
        n_cycles += 1
        if heartbeat_every and n_cycles % int(heartbeat_every) == 0:
            print(
                json.dumps(
                    {
                        "heartbeat_cycles": n_cycles,
                        "lines": n_lines,
                        "t0": {tf: current_t0(tf=tf) for tf in tf_list},
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
