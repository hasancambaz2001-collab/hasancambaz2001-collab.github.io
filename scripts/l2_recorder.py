#!/usr/bin/env python3
"""Record top-of-book L2 for 5m/15m updown. GET only. Never posts.

python3 scripts/l2_recorder.py --interval 1 --out-dir data/l2
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from whiskas.l2 import ASSETS, TFS, BookTick
from whiskas.paper import (
    asset_window_slug,
    best_ask,
    best_bid,
    current_t0,
    discover_tokens,
    fetch_book,
    normalize_tf,
)

DEFAULT_OUT = ROOT / "data" / "l2"


def _out_path(out_dir: Path, asset: str, tf: str, now: datetime) -> Path:
    day = now.strftime("%Y%m%d")
    return out_dir / f"{asset}_{tf}_{day}.jsonl"


def snapshot_tick(
    *,
    asset: str,
    tf: str,
    tokens: dict[str, str] | None = None,
    now: float | None = None,
) -> BookTick:
    ts = time.time() if now is None else float(now)
    tf_key = normalize_tf(tf)
    t0 = current_t0(ts, tf=tf_key)
    slug = asset_window_slug(asset, t0, tf_key)
    tok = tokens if tokens is not None else discover_tokens(slug)
    if "Up" not in tok or "Down" not in tok:
        return BookTick(
            t=ts,
            slug=slug,
            asset=str(asset).strip().lower(),
            tf=tf_key,
            t0=t0,
            bu=None,
            bd=None,
            au=None,
            ad=None,
            su=0.0,
            sd=0.0,
        )
    book_up = fetch_book(tok["Up"], pause=0.0)
    book_down = fetch_book(tok["Down"], pause=0.0)
    bu, su = best_bid(book_up)
    bd, sd = best_bid(book_down)
    au, sau = best_ask(book_up)
    ad, sad = best_ask(book_down)
    return BookTick(
        t=ts,
        slug=slug,
        asset=str(asset).strip().lower(),
        tf=tf_key,
        t0=t0,
        bu=bu,
        bd=bd,
        au=au,
        ad=ad,
        su=su,
        sd=sd,
        sau=sau,
        sad=sad,
    )


def run_loop(
    *,
    out_dir: Path,
    interval: float,
    assets: tuple[str, ...],
    tfs: tuple[str, ...],
    once: bool,
    seconds: float,
) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    start = datetime.now(timezone.utc)
    (out_dir / "recorder_start.txt").write_text(start.strftime("%Y-%m-%dT%H:%M:%SZ") + "\n", encoding="utf-8")
    (out_dir / "recorder.pid").write_text(str(os_getpid()) + "\n", encoding="utf-8")
    forever = (not once) and float(seconds) <= 0
    deadline = None if forever else time.time() + max(0.0, float(seconds))
    token_cache: dict[str, dict[str, str]] = {}
    n = 0
    next_tick = time.time()
    while True:
        now_dt = datetime.now(timezone.utc)
        for asset in assets:
            for tf in tfs:
                t0 = current_t0(tf=tf)
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
                    tick = snapshot_tick(asset=asset, tf=tf, tokens=tokens or None)
                except Exception as exc:
                    rec = {
                        "t": time.time(),
                        "asset": asset,
                        "tf": tf,
                        "slug": slug,
                        "error": str(exc)[:200],
                        "live_order": False,
                    }
                    path = _out_path(out_dir, asset, tf, now_dt)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with path.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(rec, separators=(",", ":")) + "\n")
                    n += 1
                    continue
                rec = tick.to_record()
                path = _out_path(out_dir, asset, tf, now_dt)
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec, separators=(",", ":")) + "\n")
                n += 1
        if n % 50 == 0:
            print(json.dumps({"recorder": True, "ticks": n, "live_order": False}), flush=True)
        if once or (deadline is not None and time.time() >= deadline):
            break
        next_tick += max(0.2, float(interval))
        sleep_for = next_tick - time.time()
        if sleep_for < 0:
            next_tick = time.time()
            sleep_for = 0.05
        time.sleep(sleep_for)
    return n


def os_getpid() -> int:
    import os

    return int(os.getpid())


def main() -> int:
    parser = argparse.ArgumentParser(description="L2 top-of-book recorder. GET only. No live.")
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--assets", type=str, default=",".join(ASSETS))
    parser.add_argument("--tfs", type=str, default=",".join(TFS))
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--seconds", type=float, default=0.0)
    args = parser.parse_args()
    assets = tuple(a.strip().lower() for a in args.assets.split(",") if a.strip()) or ASSETS
    tfs = tuple(normalize_tf(t) for t in args.tfs.split(",") if t.strip())
    tfs = tuple(t for t in tfs if t in TFS) or TFS
    n = run_loop(
        out_dir=args.out_dir,
        interval=float(args.interval),
        assets=assets,
        tfs=tfs,
        once=bool(args.once),
        seconds=float(args.seconds),
    )
    print(f"l2_recorder ticks={n} out={args.out_dir} (GET only, no orders)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
