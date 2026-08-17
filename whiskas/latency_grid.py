"""MICRO latency-grid helpers. No clip/pair/still250-gate changes.

v1 = token cache + parallel REST books (current).
v2 = still250 from WS book age ≤250ms; else sleep+GET fallback.
v3 = Rust sketch only if post_ack_ms p50 > 500 after v1/v2.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
VARIANT_FILE = ROOT / "data" / "ops" / "LATENCY_VARIANT"
V1 = "v1_cache_parallel"
V2 = "v2_ws_age"
VARIANTS = (V1, V2)
WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
STILL_AGE_SEC = 0.25


def current_variant() -> str:
    env = (os.environ.get("LATENCY_VARIANT") or "").strip()
    if env in {V1, V2, "v1", "v2"}:
        return V1 if env in {V1, "v1"} else V2
    if VARIANT_FILE.is_file():
        text = VARIANT_FILE.read_text(encoding="utf-8").strip().splitlines()[0].strip()
        if text in {V1, V2, "v1", "v2"}:
            return V1 if text in {V1, "v1"} else V2
    return V1


def write_variant(name: str) -> None:
    if name not in VARIANTS:
        raise ValueError(name)
    VARIANT_FILE.parent.mkdir(parents=True, exist_ok=True)
    VARIANT_FILE.write_text(name + "\n", encoding="utf-8")


def percentile(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    ordered = sorted(float(x) for x in xs)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (float(p) / 100.0)
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    frac = rank - lo
    return ordered[lo] + (ordered[hi] - ordered[lo]) * frac


def summarize_ms(xs: list[float]) -> dict[str, float | int | None]:
    return {
        "n": len(xs),
        "p50": percentile(xs, 50),
        "p95": percentile(xs, 95),
        "min": min(xs) if xs else None,
        "max": max(xs) if xs else None,
    }


class BookAgeCache:
    """In-process CLOB market WS. GET fallback lives in still250 probe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._books: dict[str, dict[str, Any]] = {}
        self._recv_ts: dict[str, float] = {}
        self._want: set[str] = set()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._ws_ok = False
        self._ws: Any = None
        self._recv_n = 0
        self._last_error = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="clob-book-ws", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        ws = self._ws
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass

    def set_tokens(self, token_up: str, token_down: str) -> None:
        with self._lock:
            before = len(self._want)
            self._want.add(str(token_up))
            self._want.add(str(token_down))
            grew = len(self._want) > before
        if grew or self._ws is not None:
            self._subscribe()

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "ws_ok": bool(self._ws_ok),
                "ws_n_books": len(self._books),
                "ws_recv_n": int(self._recv_n),
                "ws_n_want": len(self._want),
                "ws_error": self._last_error,
            }

    def _subscribe(self, ws: Any | None = None) -> None:
        sock = ws if ws is not None else self._ws
        if sock is None:
            return
        with self._lock:
            ids = list(self._want)
        if not ids:
            return
        try:
            sock.send(json.dumps({"type": "market", "assets_ids": ids, "custom_feature_enabled": True}))
        except Exception as exc:
            self._last_error = type(exc).__name__

    def age_ms(self, token_id: str) -> float | None:
        with self._lock:
            ts = self._recv_ts.get(str(token_id))
        if ts is None:
            return None
        return (time.time() - ts) * 1000.0

    def fresh_books(self, token_up: str, token_down: str, *, max_age_sec: float = STILL_AGE_SEC) -> dict[str, Any] | None:
        now = time.time()
        with self._lock:
            up = self._books.get(str(token_up))
            down = self._books.get(str(token_down))
            tu = self._recv_ts.get(str(token_up))
            td = self._recv_ts.get(str(token_down))
        if not up or not down or tu is None or td is None:
            return None
        if (now - tu) > float(max_age_sec) + 1e-12 or (now - td) > float(max_age_sec) + 1e-12:
            return None
        return {
            "Up": up,
            "Down": down,
            "age_up_ms": (now - tu) * 1000.0,
            "age_down_ms": (now - td) * 1000.0,
        }

    def _apply_book(self, token_id: str, book: dict[str, Any]) -> None:
        if not token_id or not isinstance(book, dict):
            return
        with self._lock:
            self._books[str(token_id)] = book
            self._recv_ts[str(token_id)] = time.time()
            self._recv_n += 1

    def _handle(self, payload: Any) -> None:
        rows = payload if isinstance(payload, list) else [payload]
        for msg in rows:
            if not isinstance(msg, dict):
                continue
            kind = str(msg.get("event_type") or msg.get("type") or "")
            if kind == "book" or (msg.get("bids") is not None and msg.get("asks") is not None):
                token = str(msg.get("asset_id") or msg.get("asset") or "")
                self._apply_book(token, {"bids": msg.get("bids") or [], "asks": msg.get("asks") or []})
                continue
            if kind == "price_change":
                for ch in msg.get("price_changes") or []:
                    if not isinstance(ch, dict):
                        continue
                    token = str(ch.get("asset_id") or "")
                    if not token:
                        continue
                    with self._lock:
                        book = dict(self._books.get(token) or {"bids": [], "asks": []})
                        side = str(ch.get("side") or "").upper()
                        key = "bids" if side in {"BID", "BUY"} else "asks"
                        levels = list(book.get(key) or [])
                        px = str(ch.get("price") or "")
                        sz = str(ch.get("size") or "0")
                        levels = [lv for lv in levels if str((lv or {}).get("price")) != px]
                        try:
                            if float(sz) > 0:
                                levels.append({"price": px, "size": sz})
                        except (TypeError, ValueError):
                            pass
                        book[key] = levels
                        self._books[token] = book
                        self._recv_ts[token] = time.time()

    def _run(self) -> None:
        try:
            from websocket import WebSocketApp
        except ImportError:
            self._ws_ok = False
            self._last_error = "ImportError"
            return
        while not self._stop.is_set():
            try:
                self._loop_ws(WebSocketApp)
            except Exception as exc:
                self._last_error = type(exc).__name__
                time.sleep(1.0)

    def _loop_ws(self, WebSocketApp: Any) -> None:
        def on_open(ws: Any) -> None:
            self._ws = ws
            self._ws_ok = True
            self._subscribe(ws)

        def on_message(_ws: Any, message: str) -> None:
            if not message or message == "PONG":
                return
            try:
                self._handle(json.loads(message))
            except Exception:
                return

        def on_error(_ws: Any, err: Any) -> None:
            self._last_error = str(err)[:160]
            self._ws_ok = False

        def on_close(_ws: Any, *_a: Any) -> None:
            self._ws_ok = False

        ws = WebSocketApp(
            WS_URL,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )
        self._ws = ws
        ping = threading.Thread(target=self._ping_loop, name="clob-book-ping", daemon=True)
        ping.start()
        try:
            ws.run_forever(ping_interval=20, ping_timeout=10)
        finally:
            self._ws = None
            self._ws_ok = False

    def _ping_loop(self) -> None:
        while not self._stop.is_set():
            sock = self._ws
            if sock is not None and self._ws_ok:
                try:
                    sock.send("PING")
                except Exception:
                    pass
            if self._stop.wait(10.0):
                break


def infer_variant(rec: dict[str, Any]) -> str | None:
    raw = rec.get("latency_variant")
    if raw in {V1, V2, "v1", "v2"}:
        return V1 if raw in {V1, "v1"} else V2
    if rec.get("token_cache_hit") is not None or rec.get("book_get_ms") is not None:
        return V1
    return None


def is_intent(rec: dict[str, Any]) -> bool:
    return rec.get("intent") is True or str(rec.get("reason") or "") == "rest"


def _floats(rows: list[dict[str, Any]], key: str) -> list[float]:
    out: list[float] = []
    for rec in rows:
        val = rec.get(key)
        if val is None:
            continue
        try:
            out.append(float(val))
        except (TypeError, ValueError):
            continue
    return out


def variant_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    intents = [r for r in rows if is_intent(r)]
    sent = [
        r
        for r in intents
        if r.get("live_order") and r.get("post_ack_ms") is not None
    ]
    sources: dict[str, int] = {}
    for rec in intents:
        src = str(rec.get("still250_source") or "unknown")
        sources[src] = sources.get(src, 0) + 1
    ws_age = [r for r in intents if r.get("still250_source") == "ws_age"]
    return {
        "n_intent": len(intents),
        "n_sent": len(sent),
        "n_would_send": sum(1 for r in intents if r.get("would_send") is True),
        "n_still250_true": sum(1 for r in intents if r.get("still_there_250ms") is True),
        "n_ws_age": len(ws_age),
        "still_ms_ws_age": summarize_ms(_floats(ws_age, "still_ms")),
        "still250_source": sources,
        "still_ms": summarize_ms(_floats(intents, "still_ms")),
        "book_get_ms": summarize_ms(_floats(intents, "book_get_ms")),
        "sign_ms": summarize_ms(_floats(sent, "sign_ms")),
        "post_ack_ms": summarize_ms(_floats(sent, "post_ack_ms")),
        "lag_ms": summarize_ms(_floats(sent, "lag_ms")),
    }


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
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


def group_by_variant(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {V1: [], V2: []}
    for rec in rows:
        name = infer_variant(rec)
        if name in grouped:
            grouped[name].append(rec)
    return grouped


def rank_variants(rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouped = group_by_variant(rows)
    variants = []
    for name in VARIANTS:
        metrics = variant_metrics(grouped[name])
        post = metrics["post_ack_ms"]
        variants.append(
            {
                "variant": name,
                **metrics,
                "rank_key": (
                    post["p50"] if post["p50"] is not None else float("inf"),
                    post["p95"] if post["p95"] is not None else float("inf"),
                    metrics["still_ms"]["p50"] if metrics["still_ms"]["p50"] is not None else float("inf"),
                ),
            }
        )
    ranked = sorted(variants, key=lambda v: v["rank_key"])
    for i, row in enumerate(ranked, start=1):
        row["rank"] = i
        row.pop("rank_key", None)
    best = ranked[0] if ranked else None
    best_p50 = None if best is None else (best.get("post_ack_ms") or {}).get("p50")
    rust = bool(best_p50 is not None and float(best_p50) > 500.0)
    return {
        "variants": ranked,
        "enough": {name: variant_metrics(grouped[name])["n_intent"] >= 20 for name in VARIANTS},
        "rust_sketch": rust,
        "rust_reason": (
            f"best post_ack_ms p50={best_p50:.1f} > 500"
            if rust and best_p50 is not None
            else "skip: post_ack_ms p50 missing or ≤500; no full Rust migrate"
        ),
    }


def render_grid_md(result: dict[str, Any], *, path: str = "") -> str:
    lines = [
        "# MICRO latency grid",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}",
        "Gates fixed. No clip/pair/still250-false-send changes. Max 3 variants, sequential.",
        "",
        "## Rank (post_ack_ms p50, then p95)",
        "",
        "| rank | variant | n_intent | n_sent | n_ws_age | post_ack p50 | post_ack p95 | still_ms p50 | still_ms p95 | still_ms ws_age p50 | still250_source |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in result.get("variants") or []:
        post = row["post_ack_ms"]
        still = row["still_ms"]
        src = ",".join(f"{k}:{v}" for k, v in sorted((row.get("still250_source") or {}).items()))
        lines.append(
            "| {rank} | {variant} | {n_intent} | {n_sent} | {n_ws} | {p50} | {p95} | {s50} | {s95} | {w50} | {src} |".format(
                rank=row.get("rank"),
                variant=row.get("variant"),
                n_intent=row.get("n_intent"),
                n_sent=row.get("n_sent"),
                n_ws=row.get("n_ws_age"),
                p50=_fmt(post.get("p50")),
                p95=_fmt(post.get("p95")),
                s50=_fmt(still.get("p50")),
                s95=_fmt(still.get("p95")),
                w50=_fmt((row.get("still_ms_ws_age") or {}).get("p50")),
                src=src or "—",
            )
        )
    lines.extend(
        [
            "",
            f"Enough (≥20 intents): `{result.get('enough')}`",
            f"V3 Rust sketch: {result.get('rust_reason')}",
            "",
            "## Notes",
            "",
            "- V1 = token cache + parallel book GETs. V2 = V1 + still250 from WS book age ≤250ms (no extra 250 sleep if age ok).",
            "- `post_ack_ms` is sign+HTTP on SEND only. V2 mainly cuts `still_ms`. Do not invent fills.",
            "- still250 false or bid_sum_250>0.90 → SEND YOK. Clip 5. pair_max 0.90.",
            f"- Tape: `{path or 'data/micro_live/intended.jsonl'}`",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def _fmt(val: float | None) -> str:
    if val is None:
        return "—"
    return f"{float(val):.1f}"


RUST_SKETCH = """# MICRO Rust hot-path sketch (V3)

Do **not** implement a full migrate. Sketch only: `post_ack_ms` p50 stayed >500 after V1/V2.

## Why this slice

`post_ack_ms` = L2 sign + one `post_orders` HTTP. Token cache and parallel book GETs do not sit on that clock. still250 WS age cuts `still_ms`, not ack.

## Keep in Python

- Gamma token cache, snapshot decide, still250 gate, adverse/rich_cancel, inventory, jsonl, reports.
- No clip/pair/still250-false-send change. No new strategy.

## Rust (only this)

1. One crate: EIP-712 / CLOB L2 HMAC sign for the existing GTC pair body.
2. One HTTP/2 client: `POST /orders` (same `post_orders` batch, both legs).
3. Thin FFI or stdin JSON: `{token_up, px_up, token_down, px_down, size, api_creds}` → `{order_ids, sign_ms, post_ack_ms}`.
4. Time `sign_ms` and `post_ack_ms` inside Rust; Python still owns `t_intent` and `lag_ms = ack - t_intent`.

## Do not

- Port the maker policy, WS book, or cancel/adverse loop.
- Add `nautilus_trader` / rewrite the sender.
- Send when still250 is not true.

Measure one signed pair post before any wider rewrite.
"""


def maybe_write_rust_sketch(result: dict[str, Any], dest: Path) -> bool:
    if not result.get("rust_sketch"):
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(RUST_SKETCH, encoding="utf-8")
    return True


def write_grid_report(result: dict[str, Any], dest: Path, *, tape: str = "") -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render_grid_md(result, path=tape), encoding="utf-8")
    return dest
