"""FULL KASA helpers. Their tape only. No live. pair_gt_1_trade=false."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from scripts.phase1_maker_mobo import _leg, classify_tf, is_taker_fee_match
from whiskas.fees import taker_fee_usdc
from whiskas.http import get_json

DATA_API = "https://data-api.polymarket.com"
LIMIT = 500
DUMP_MAX = 4000
PAIR_S1 = 0.90
PAIR_S3 = 0.96
PAIR_HARD = 1.0
CLIP_NOW = 10.0

WALLETS = (
    ("mo-money", "0x32ed2e546b187ca15e2841edc82b22c713cf8ec3", ("5m", "15m")),
    ("bosona", "0xc2ad03f79ca3f3c17d8c7de2612ce0c89b7d40ed", ("5m", "15m")),
    ("06dc", "0x06dc51826bc524d9a83770e7de9dd7e005b04524", None),
)

FORBIDDEN_TAPE = (
    Path("data/paper_maker/intended.jsonl"),
    Path("data/paper/intended.jsonl"),
    Path("data/paper06dc/intended.jsonl"),
)


def tape_path(root: Path, name: str) -> Path:
    return root / "data" / "raw" / f"mobo_{name}_activity.jsonl"


def quantile(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    if len(s) == 1:
        return s[0]
    pos = q * (len(s) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    frac = pos - lo
    return s[lo] * (1.0 - frac) + s[hi] * frac


def fetch_activity(user: str, *, max_rows: int = DUMP_MAX) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    offset = 0
    while len(out) < max_rows and offset <= max_rows - LIMIT:
        rows = get_json(
            f"{DATA_API}/activity",
            {
                "user": user,
                "limit": LIMIT,
                "offset": offset,
                "sortBy": "TIMESTAMP",
                "sortDirection": "DESC",
            },
            timeout=30,
            retries=4,
            pause=0.10,
        )
        if not isinstance(rows, list) or not rows:
            break
        for row in rows:
            out.append(row)
            if len(out) >= max_rows:
                return out
        if len(rows) < LIMIT:
            break
        offset += LIMIT
    return out


def dump_if_needed(root: Path, *, max_rows: int = DUMP_MAX) -> dict[str, int]:
    counts: dict[str, int] = {}
    raw = root / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    for name, wallet, _tfs in WALLETS:
        path = tape_path(root, name)
        need = (not path.is_file()) or sum(1 for _ in path.open() if _.strip()) < max_rows
        if not need:
            counts[name] = sum(1 for _ in path.open() if _.strip())
            continue
        rows = fetch_activity(wallet, max_rows=max_rows)
        with path.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, separators=(",", ":")) + "\n")
        counts[name] = len(rows)
    return counts


def load_tape(path: Path) -> list[dict[str, Any]]:
    resolved = path.resolve()
    if resolved in {p.resolve() for p in FORBIDDEN_TAPE}:
        raise ValueError("refusing paper intends as tape")
    if not path.is_file():
        raise FileNotFoundError(f"missing tape {path}")
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if isinstance(rec, dict):
                rows.append(rec)
    return rows


def _vwap(fills: list[tuple[float, float, bool]]) -> tuple[float, float] | None:
    if not fills:
        return None
    q = sum(s for s, _, _ in fills)
    if q <= 0:
        return None
    return q, sum(s * p for s, p, _ in fills) / q


def two_leg_windows(rows: list[dict[str, Any]], *, tfs: tuple[str, ...] | None) -> list[dict[str, Any]]:
    legs: dict[str, dict[str, list[tuple[float, float, bool]]]] = defaultdict(lambda: {"Up": [], "Down": []})
    meta: dict[str, str] = {}
    for row in rows:
        if str(row.get("type") or "") != "TRADE":
            continue
        if str(row.get("side") or "").upper() != "BUY":
            continue
        tf = classify_tf(row.get("eventSlug"), row.get("slug"))
        if tfs is not None and tf not in tfs:
            continue
        # Market slug, not eventSlug: 06dc ladders share an event across strikes.
        slug = str(row.get("slug") or row.get("eventSlug") or "")
        if not slug:
            continue
        leg = _leg(row)
        if leg not in {"Up", "Down"}:
            continue
        size = float(row.get("size") or 0.0)
        price = float(row.get("price") or 0.0)
        usdc = float(row.get("usdcSize") or row.get("usdc") or 0.0)
        if size <= 0 or price <= 0:
            continue
        taker = is_taker_fee_match(usdc, size, price)
        legs[slug][leg].append((size, price, taker))
        meta[slug] = tf
    out: list[dict[str, Any]] = []
    for slug, book in legs.items():
        if not book["Up"] or not book["Down"]:
            continue
        all_up = _vwap(book["Up"])
        all_dn = _vwap(book["Down"])
        mk_up = _vwap([x for x in book["Up"] if not x[2]])
        mk_dn = _vwap([x for x in book["Down"] if not x[2]])
        tk_up = _vwap([x for x in book["Up"] if x[2]])
        tk_dn = _vwap([x for x in book["Down"] if x[2]])
        rec: dict[str, Any] = {"slug": slug, "tf": meta[slug]}
        if all_up and all_dn:
            rec["pair"] = all_up[1] + all_dn[1]
            rec["matched"] = min(all_up[0], all_dn[0])
        if mk_up and mk_dn:
            rec["maker_pair"] = mk_up[1] + mk_dn[1]
            rec["maker_matched"] = min(mk_up[0], mk_dn[0])
        if tk_up and tk_dn:
            rec["taker_pair"] = tk_up[1] + tk_dn[1]
            rec["taker_matched"] = min(tk_up[0], tk_dn[0])
            rec["taker_fee"] = taker_fee_usdc(rec["taker_matched"], tk_up[1]) + taker_fee_usdc(
                rec["taker_matched"], tk_dn[1]
            )
        out.append(rec)
    return out


def is_s1(win: dict[str, Any]) -> bool:
    pair = win.get("maker_pair")
    if pair is None:
        return False
    if float(pair) + 1e-12 >= PAIR_HARD:
        return False
    return float(pair) < PAIR_S1


def is_s3(win: dict[str, Any]) -> bool:
    pair = win.get("taker_pair")
    if pair is None:
        return False
    if float(pair) + 1e-12 >= PAIR_HARD:
        return False
    return float(pair) <= PAIR_S3 + 1e-12


def s1_pnl(win: dict[str, Any], *, clip: float | None = None) -> float:
    """Winner-independent maker complete-set. No taker fee. pair_gt_1_trade=false."""
    if not is_s1(win):
        return 0.0
    size = float(clip) if clip is not None else float(win["maker_matched"])
    return size * (1.0 - float(win["maker_pair"]))


def s3_pnl(win: dict[str, Any], *, clip: float | None = None) -> float:
    """Winner-independent taker complete-set minus official fee. Not primary."""
    if not is_s3(win):
        return 0.0
    size = float(clip) if clip is not None else float(win["taker_matched"])
    pair = float(win["taker_pair"])
    # scale fee with clip if we override size
    fee = float(win.get("taker_fee") or 0.0)
    if clip is not None and float(win["taker_matched"]) > 0:
        fee = fee * (size / float(win["taker_matched"]))
    return size * (1.0 - pair) - fee


def load_all_windows(root: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name, _wallet, tfs in WALLETS:
        rows = load_tape(tape_path(root, name))
        for win in two_leg_windows(rows, tfs=tfs):
            win["wallet"] = name
            out.append(win)
    return out
