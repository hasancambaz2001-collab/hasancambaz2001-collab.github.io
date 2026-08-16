"""BookSource: live CLOB / record jsonl / parquet / tape_synthetic. No live orders.

record = 5m/15m l2_recorder. Does NOT cover 06dc daily/monthly.
06dc truth = tape_06dc dump + paper_06dc + T6.
"""

from __future__ import annotations

import json
from glob import glob
from pathlib import Path
from typing import Any, Iterator

from whiskas.kasa import load_tape, tape_path, two_leg_windows
from whiskas.l2 import BookTick
from whiskas.paper import (
    asset_window_slug,
    best_ask,
    best_bid,
    current_t0,
    discover_tokens,
    fetch_book,
    normalize_tf,
)

ROOT = Path(__file__).resolve().parents[2]
WALLETS = {
    "mo": "mo-money",
    "mo-money": "mo-money",
    "tape_mo": "mo-money",
    "bosona": "bosona",
    "tape_bosona": "bosona",
    "06dc": "06dc",
    "tape_06dc": "06dc",
}


def _t0_from_slug(slug: str) -> int:
    parts = str(slug).rsplit("-", 1)
    try:
        return int(parts[-1])
    except ValueError:
        return 0


def window_to_tick(win: dict[str, Any]) -> BookTick:
    """Synthetic top-of-book from a two-leg tape window (selection tests)."""
    slug = str(win.get("slug") or "")
    t0 = _t0_from_slug(slug)
    pair = float(win["pair"]) if win.get("pair") is not None else None
    maker_pair = win.get("maker_pair")
    taker_pair = win.get("taker_pair")
    use_pair = float(maker_pair) if maker_pair is not None else (float(pair) if pair is not None else 0.0)
    half = use_pair / 2.0
    matched = float(win.get("maker_matched") or win.get("matched") or 0.0)
    tf = str(win.get("tf") or "5m")
    asset = slug.split("-")[0] if slug else ""
    return BookTick(
        t=float(t0 or 0),
        slug=slug,
        asset=asset,
        tf=tf,
        t0=int(t0 or 0),
        bu=half,
        bd=use_pair - half,
        au=half,
        ad=use_pair - half,
        su=matched,
        sd=matched,
        condition_id=None,
    )


def iter_tape_windows(name: str, *, root: Path = ROOT) -> list[dict[str, Any]]:
    key = WALLETS.get(name, name)
    tfs = None if key == "06dc" else ("5m", "15m")
    rows = load_tape(tape_path(root, key))
    wins = two_leg_windows(rows, tfs=tfs)
    for w in wins:
        w["wallet"] = key
    return wins


def iter_record_ticks(pattern: str = "data/l2/*.jsonl", *, root: Path = ROOT) -> Iterator[BookTick]:
    paths = [Path(p) for p in glob(pattern if Path(pattern).is_absolute() else str(root / pattern))]
    for path in sorted(paths):
        if not path.is_file():
            continue
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if not isinstance(rec, dict) or rec.get("error"):
                    continue
                if rec.get("bu") is None and rec.get("bid_up") is None:
                    continue
                yield BookTick.from_record(rec)


def iter_parquet_ticks(path: Path) -> Iterator[BookTick]:
    from scripts.twin_l2 import iter_parquet_ticks as _iter

    markets = path.with_name(path.name.replace("_ticks", "_markets"))
    yield from _iter(path, markets if markets.is_file() else None)


def iter_live_ticks(assets: tuple[str, ...] = ("btc",), tfs: tuple[str, ...] = ("5m",)) -> Iterator[BookTick]:
    """One CLOB snapshot per asset/tf. GET only. Never posts."""
    import time

    now = time.time()
    for asset in assets:
        for tf in tfs:
            tf_key = normalize_tf(tf)
            t0 = current_t0(now, tf=tf_key)
            slug = asset_window_slug(asset, t0, tf_key)
            try:
                tok = discover_tokens(slug)
            except Exception:
                continue
            if "Up" not in tok or "Down" not in tok:
                continue
            try:
                up = fetch_book(tok["Up"], pause=0.0)
                down = fetch_book(tok["Down"], pause=0.0)
            except Exception:
                continue
            bu, su = best_bid(up)
            bd, sd = best_bid(down)
            au, sau = best_ask(up)
            ad, sad = best_ask(down)
            yield BookTick(
                t=now,
                slug=slug,
                asset=asset,
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


class BookSource:
    def __init__(self, kind: str, *, root: Path = ROOT, path: Path | None = None, glob_pat: str = "data/l2/*.jsonl"):
        self.kind = kind
        self.root = root
        self.path = path
        self.glob_pat = glob_pat

    def windows(self) -> list[dict[str, Any]]:
        if self.kind in WALLETS or self.kind.startswith("tape_"):
            return iter_tape_windows(self.kind, root=self.root)
        return []

    def ticks(self) -> Iterator[BookTick]:
        if self.kind == "record":
            yield from iter_record_ticks(self.glob_pat, root=self.root)
        elif self.kind == "parquet":
            p = self.path or (self.root / "data" / "parquet" / "btc_ticks.parquet")
            yield from iter_parquet_ticks(p)
        elif self.kind == "live":
            yield from iter_live_ticks()
        elif self.kind in WALLETS or self.kind.startswith("tape_"):
            for win in self.windows():
                if win.get("pair") is None:
                    continue
                yield window_to_tick(win)
        else:
            raise ValueError(f"unknown BookSource {self.kind}")


def iter_source(name: str, **kwargs: Any) -> BookSource:
    return BookSource(name, **kwargs)
