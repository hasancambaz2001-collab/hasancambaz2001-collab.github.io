#!/usr/bin/env python3
"""G6-fast: one historical calibration job. No live. No size_ok. No LIVE_READY.

python3 scripts/g6_fast_calibrate.py --download --clip 10 --pair-max 0.90

PASS (all): n_rest >= 50, edge_proxy >= 0, report written.
Writes data/ops/G6_fill_calibrated.flag only on PASS.
Does not set G5. Does not write LIVE_READY. No pair>1 trade.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from infra.match.queue_sim_v2 import run_queue_v2
from scripts.g6_fill_cal import analyze as analyze_paper
from scripts.phase1_maker_mobo import _leg, classify_tf, is_taker_fee_match
from whiskas.fees import taker_fee_usdc
from whiskas.kasa import is_s1, two_leg_windows
from whiskas.l2 import BookTick, PolicyMaker
from whiskas.live_config import (
    G5_FLAG,
    G6_FLAG,
    LIVE_READY,
    ensure_pmdata_env_file,
    load_activity,
    load_pmdata_env,
)
from whiskas.paper import load_jsonl
from whiskas.pmdata import (
    CACHE,
    api_key_name,
    bbo_timeline_full,
    download_day,
    download_slug,
    list_day_members,
    parse_ts,
    parse_updown_slug,
    read_day_member,
    write_parquet,
)

PROC = ROOT / "data" / "processed"
REPORTS = ROOT / "data" / "reports"
DUMPS = ROOT / "data" / "dumps"
L2_DIR = ROOT / "data" / "l2"
BBO_DIR = ROOT / "data" / "pmdata" / "bbo"
DAY_CACHE = CACHE / "day"
SLUG_CACHE = CACHE / "l2"
PAPER_TAPE = ROOT / "data" / "paper_maker" / "intended.jsonl"
NO_UNLOCK_DAYS = frozenset({"2026-08-16"})
FROM_TS_DEFAULT = 1786713600
N_REST_MIN = 50
COVER_MIN = 0.80
WORST_DAY_FLOOR = -0.15
REBATE_FRAC = 0.20
CANCEL_ABOVE = 0.92


def now_aligned_5m() -> int:
    return int(datetime.now(timezone.utc).timestamp()) // 300 * 300


def _ts_unix(value: Any) -> float:
    if value is None:
        return 0.0
    if hasattr(value, "timestamp"):
        try:
            return float(value.timestamp())
        except Exception:
            pass
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        x = float(value)
        if x > 1e12:
            return x / 1000.0
        return x
    text = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).timestamp()


def _vwap(fills: list[tuple[float, float]]) -> tuple[float, float] | None:
    if not fills:
        return None
    qty = sum(s for s, _ in fills)
    if qty <= 0:
        return None
    return qty, sum(s * p for s, p in fills) / qty


def load_leader_state(root: Path = ROOT) -> dict[str, Any]:
    bos_path = root / "data" / "dumps" / "bosona_activity.json"
    mo_path = root / "data" / "dumps" / "mo-money_activity.json"
    bos = load_activity(bos_path) if bos_path.is_file() else []
    mo = load_activity(mo_path) if mo_path.is_file() else []
    bos_s1 = {w["slug"] for w in two_leg_windows(bos, tfs=("5m", "15m")) if is_s1(w)}
    mo_s1 = {w["slug"] for w in two_leg_windows(mo, tfs=("5m", "15m")) if is_s1(w)}
    down: dict[str, dict[str, float]] = {}
    for rows in (bos, mo):
        legs: dict[str, dict[str, list[tuple[float, float]]]] = defaultdict(
            lambda: {"Up": [], "Down": []}
        )
        for row in rows:
            if str(row.get("type") or "") != "TRADE":
                continue
            if str(row.get("side") or "").upper() != "BUY":
                continue
            tf = classify_tf(row.get("eventSlug"), row.get("slug"))
            if tf not in {"5m", "15m"}:
                continue
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
            if is_taker_fee_match(usdc, size, price):
                continue
            legs[slug][leg].append((size, price))
        for slug, book in legs.items():
            mk_up = _vwap(book["Up"])
            mk_dn = _vwap(book["Down"])
            if not mk_dn:
                continue
            rec = down.get(slug) or {}
            rec["down_px"] = float(mk_dn[1])
            rec["down_sz"] = float(mk_dn[0])
            if mk_up:
                rec["up_px"] = float(mk_up[1])
                rec["up_sz"] = float(mk_up[0])
                rec["maker_pair"] = float(mk_up[1] + mk_dn[1])
            down[slug] = rec
    return {
        "bosona_s1": bos_s1,
        "mo_s1": mo_s1,
        "union_s1": bos_s1 | mo_s1,
        "down": down,
    }


def load_recorder_ticks(l2_dir: Path = L2_DIR) -> list[BookTick]:
    ticks: list[BookTick] = []
    if not l2_dir.is_dir():
        return ticks
    for path in sorted(l2_dir.glob("*_*_*.jsonl")):
        for rec in load_jsonl(path):
            if rec.get("bu") is None or rec.get("bd") is None:
                continue
            ticks.append(BookTick.from_record(rec))
    ticks.sort(key=lambda t: (t.slug, t.t))
    return ticks


def ticks_from_joined_bbo(
    slim: pd.DataFrame,
    *,
    slug: str,
    asset: str,
    tf: str,
    t0: int,
    down_px: float,
    down_sz: float,
) -> list[BookTick]:
    """Yes L2 + dump Down maker VWAP. Not two real L2s. Never complement."""
    ticks: list[BookTick] = []
    last_su = 0.0
    for rec in slim.itertuples(index=False):
        bb = getattr(rec, "best_bid", None)
        if bb is None or (isinstance(bb, float) and math.isnan(bb)):
            continue
        su = float(getattr(rec, "bid_size", 0.0) or 0.0)
        if su <= 0:
            su = last_su
        else:
            last_su = su
        ba = getattr(rec, "best_ask", None)
        au = None if ba is None or (isinstance(ba, float) and math.isnan(ba)) else float(ba)
        ticks.append(
            BookTick(
                t=_ts_unix(getattr(rec, "timestamp", None)),
                slug=slug,
                asset=asset,
                tf=tf,
                t0=t0,
                bu=float(bb),
                bd=float(down_px),
                au=au,
                ad=None,
                su=float(su),
                sd=float(down_sz),
            )
        )
    return ticks


def one_leg_stats(slim: pd.DataFrame, slug: str) -> dict[str, Any]:
    if slim is None or slim.empty:
        return {"slug": slug, "n_ticks": 0, "pair_edge": "skipped_one_leg"}
    bids = [float(x) for x in slim["best_bid"].tolist() if x is not None and not pd.isna(x)]
    return {
        "slug": slug,
        "n_ticks": int(len(slim)),
        "yes_bid_min": min(bids) if bids else None,
        "yes_bid_max": max(bids) if bids else None,
        "pair_edge": "skipped_one_leg",
        "note": "PMData L2 is Yes-token only. No complement Down. Pair edge skipped.",
    }


def policy_rests(
    ticks: list[BookTick],
    *,
    clip: float,
    pair_max: float,
) -> list[dict[str, Any]]:
    pm = PolicyMaker(pair_max=pair_max, cancel_above=CANCEL_ABOVE, clip=clip, fill="residual")
    states: dict[str, dict[str, Any] | None] = {}
    rests: list[dict[str, Any]] = []
    for tick in ticks:
        rec, states[tick.slug] = pm.step(tick, states.get(tick.slug))
        rec["pair_gt_1"] = False
        rec["live_order"] = False
        rec["size_ok"] = False
        if rec.get("reason") == "rest":
            rests.append(rec)
    return rests


def edge_proxy(rests: list[dict[str, Any]], *, clip: float) -> dict[str, float]:
    fee0 = 0.0
    rebate = 0.0
    notion = 0.0
    by_day: dict[str, dict[str, float]] = defaultdict(lambda: {"edge": 0.0, "notion": 0.0})
    for rec in rests:
        pair = rec.get("bid_sum")
        if pair is None:
            continue
        pair_f = float(pair)
        if pair_f > 1.0 + 1e-12:
            continue
        e = float(clip) * (1.0 - pair_f)
        n = float(clip) * pair_f
        fee0 += e
        notion += n
        pu = rec.get("bid_up")
        pd = rec.get("bid_down")
        if pu is not None and pd is not None:
            rebate += REBATE_FRAC * (
                taker_fee_usdc(float(clip), float(pu)) + taker_fee_usdc(float(clip), float(pd))
            )
        day = datetime.fromtimestamp(float(rec.get("t") or 0.0), tz=timezone.utc).strftime("%Y-%m-%d")
        by_day[day]["edge"] += e
        by_day[day]["notion"] += n
    worst = None
    for day, rec in sorted(by_day.items()):
        if rec["notion"] <= 0:
            continue
        ratio = rec["edge"] / rec["notion"]
        row = {"day": day, "edge": rec["edge"], "notion": rec["notion"], "edge_over_notion": ratio}
        if worst is None or ratio < worst["edge_over_notion"]:
            worst = row
    return {
        "edge_proxy_fee0": fee0,
        "edge_proxy_rebate": fee0 + rebate,
        "rebate_usd": rebate,
        "notion": notion,
        "worst_day": worst,
    }


def evaluate_pass(stats: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    n_rest = int(stats.get("n_rest") or 0)
    if n_rest < N_REST_MIN:
        reasons.append(f"n_rest={n_rest} < {N_REST_MIN}")
    edge = float(stats.get("edge_proxy_fee0") or 0.0)
    if edge < 0:
        reasons.append(f"edge_proxy_fee0={edge} < 0")
    if not stats.get("report_written"):
        reasons.append("report not written")
    if stats.get("pair_gt_1_trade"):
        reasons.append("pair_gt_1_trade must stay false")
    return (len(reasons) == 0), reasons


def _day_zip(series: str, day: str) -> Path:
    return DAY_CACHE / f"{series}_l2_{day}.zip"


def ensure_day_l2(series: str, day: str, *, download: bool) -> tuple[Path | None, str]:
    if day in NO_UNLOCK_DAYS:
        return None, "skipped_no_unlock"
    cached = _day_zip(series, day)
    if cached.is_file() and cached.stat().st_size > 0:
        return cached, "cached"
    if not download:
        return None, "skipped_no_download"
    try:
        path = download_day(series, "l2", day, dest_dir=DAY_CACHE, timeout=600)
    except FileNotFoundError:
        return None, "404"
    except Exception as exc:
        return None, f"error:{type(exc).__name__}"
    return path, "downloaded"


def extract_day_slim(zip_path: Path, *, from_ts: int, dest_dir: Path) -> list[str]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    slugs: list[str] = []
    names = [n for n in list_day_members(zip_path) if n.endswith(".parquet")]
    for i, name in enumerate(names, 1):
        meta = parse_updown_slug(Path(name).stem)
        if not meta or int(meta["t0"]) < int(from_ts):
            continue
        dest = dest_dir / f"{meta['slug']}.parquet"
        if dest.is_file() and dest.stat().st_size > 0:
            slugs.append(meta["slug"])
            continue
        df = read_day_member(zip_path, name)
        slim = bbo_timeline_full(df)
        if slim.empty:
            continue
        write_parquet(slim, dest)
        slugs.append(meta["slug"])
        if i % 40 == 0:
            print(json.dumps({"extract": zip_path.name, "done": i, "kept": len(slugs)}), flush=True)
    return slugs


def _slug_parquet(slug: str) -> Path | None:
    for folder in (BBO_DIR, SLUG_CACHE, CACHE / "slug" / "l2"):
        path = folder / f"{slug}.parquet"
        if path.is_file() and path.stat().st_size > 0:
            return path
    return None


def download_missing_slugs(slugs: list[str], *, download: bool) -> tuple[list[str], list[str]]:
    have: list[str] = []
    need: list[str] = []
    for slug in slugs:
        if _slug_parquet(slug) is not None:
            have.append(slug)
        else:
            need.append(slug)
    if not download or not need:
        return have, need
    SLUG_CACHE.mkdir(parents=True, exist_ok=True)

    def _one(slug: str) -> tuple[str, bool]:
        path = download_slug("l2", slug, dest_dir=SLUG_CACHE)
        return slug, bool(path and path.is_file() and path.stat().st_size > 0)

    got: list[str] = []
    miss: list[str] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = {pool.submit(_one, s): s for s in need}
        for fut in as_completed(futs):
            slug, ok = fut.result()
            if ok:
                got.append(slug)
            else:
                miss.append(slug)
    return have + got, miss


def load_slim(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    if df.empty:
        return df
    if "bid_size" in df.columns and "best_bid" in df.columns:
        return df
    return bbo_timeline_full(df)


def paper_live_column(tape: Path) -> dict[str, Any]:
    if not tape.is_file():
        return {
            "n_rest": 0,
            "fill_band": "n/a",
            "still250": "n/a",
            "note": "no paper_maker tape",
        }
    rows = load_jsonl(tape)
    stats = analyze_paper(rows)
    rest_rows = [r for r in rows if str(r.get("reason") or "") == "rest"]
    probed = [r for r in rest_rows if "still_there_250ms" in r]
    still_true = sum(1 for r in probed if r.get("still_there_250ms") is True)
    still = "not recorded"
    if probed:
        still = f"{still_true}/{len(probed)}={still_true / len(probed):.4f}"
    fill = "n/a" if stats["fill_pct"] is None else f"{stats['fill_pct']:.4f} residual-sim"
    return {
        "n_rest": int(stats["rests"]),
        "fill_band": fill,
        "still250": still,
        "fill_sim": stats["fill_pct"],
        "n_rows": stats["n_rows"],
        "note": "paper residual-sim only. not hist queue. not live CLOB fill.",
    }


def write_reports(stats: dict[str, Any], *, root: Path = ROOT) -> None:
    proc = root / "data" / "processed"
    reports = root / "data" / "reports"
    proc.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)
    (proc / "g6_fast.json").write_text(json.dumps(stats, indent=2, default=str) + "\n")
    passed = "PASS" if stats.get("g6_pass") else "FAIL"
    flag = "YES" if stats.get("g6_flag_written") else "NO"
    cover = stats.get("cover")
    cover_s = "n/a" if cover is None else f"{cover:.4f} ({stats.get('n_agree')}/{stats.get('n_leader_s1_downloaded')})"
    ra = stats.get("fill_risk_averse") or {}
    pr = stats.get("fill_prob") or {}
    worst = stats.get("worst_day") or {}
    worst_s = "n/a"
    if worst:
        worst_s = (
            f"{worst.get('day')} edge/notion={worst.get('edge_over_notion'):.4f} "
            f"edge={worst.get('edge'):.4f} notion={worst.get('notion'):.4f}"
        )
    paper = stats.get("paper_live") or {}
    lines = [
        "# G6_FAST",
        "",
        f"Generated: {stats.get('generated')}",
        f"Result: **{passed}**",
        "",
        "## Limits",
        "",
        "- G6-fast is historical twin calibration, **not** live fill proof",
        "- Does not set G5 `size_ok`",
        "- Does not write `LIVE_READY`",
        "- Still recommend short live paper smoke after G6-fast before real size",
        "- No pair>1 trade. No clip 67. No full-size.",
        "- Do not unlock PMData day 2026-08-16 (slug API only for that calendar day)",
        "- PMData L2 is Yes-token only. Complement Down is **not** used.",
        "- Joined books are `joined_yes_l2_plus_dump_down` when dump Down exists; else one-leg stats only",
        "",
        "## PASS criteria (this run)",
        "",
        f"- n_rest >= {N_REST_MIN}: **{stats.get('n_rest')}**",
        f"- edge_proxy_fee0 >= 0: **{stats.get('edge_proxy_fee0')}**",
        f"- report written: **yes**",
        "",
        "## Stop table",
        "",
        f"1. n_slugs_downloaded={stats.get('n_slugs_downloaded')} n_rest={stats.get('n_rest')} "
        f"cover_bosona/mo={cover_s}",
        f"2. fill_ratio risk_averse={ra.get('fill_ratio')} vs prob={pr.get('fill_ratio')}",
        f"3. maker edge fee0={stats.get('edge_proxy_fee0')} / with rebate={stats.get('edge_proxy_rebate')}",
        f"4. G6 flag written? **{flag}**",
        f"5. G5 still FAIL (flag exists={stats.get('g5_exists')})",
        f"6. LIVE still BLOCKED (LIVE_READY exists={stats.get('live_ready_exists')})",
        '7. G6-fast replaces week-long wait for calibration evidence; micro live still needed before size',
        "",
        "## Counts",
        "",
        f"- n_slugs_downloaded: {stats.get('n_slugs_downloaded')}",
        f"- n_slugs_one_leg: {stats.get('n_slugs_one_leg')}",
        f"- n_slugs_joined: {stats.get('n_slugs_joined')}",
        f"- n_rest unique (slug,t0): {stats.get('n_rest')} "
        f"(raw recorder={stats.get('n_rest_recorder')} raw joined={stats.get('n_rest_joined')}; "
        f"dense BBO can re-rest after cancel_age)",
        f"- leader S1 union: {stats.get('n_leader_s1')} · downloaded overlap: {stats.get('n_leader_s1_downloaded')}",
        f"- AGREE: {stats.get('n_agree')} · cover: {cover_s}",
        f"- bosona S1 cover on downloaded: {stats.get('cover_bosona')}",
        f"- mo S1 cover on downloaded: {stats.get('cover_mo')}",
        f"- worst synthetic day: {worst_s}",
        f"- pair_gt_1_trade: false",
        f"- days_unlocked_this_run: {stats.get('days_unlocked_this_run')}",
        f"- fail_reasons: {stats.get('fail_reasons')}",
        "",
        "## Fill bands (never mix)",
        "",
        "| band | source | fill_ratio | n_rest | note |",
        "|---|---|---|---|---|",
        f"| (a) residual-sim | paper_maker tape | {paper.get('fill_sim')} | {paper.get('n_rest')} | 2s/1s poll residual |",
        f"| (b) hist queue risk_averse | recorder two-leg + pessimistic | {ra.get('fill_ratio')} | {ra.get('n_rest')} | hidden 1.60 lat 2 |",
        f"| (c) hist queue prob | recorder two-leg + base | {pr.get('fill_ratio')} | {pr.get('n_rest')} | hidden 1.25 lat 1 |",
        f"| paper live CLOB fills | none expected | n/a | n/a | paper does not send |",
        "",
        "G6-fast replaces week-long wait for calibration evidence; micro live still needed before size",
        "",
    ]
    if not stats.get("g6_pass"):
        lines.extend(["## FAIL reason", "", f"{stats.get('fail_reasons')}", ""])
    (reports / "G6_FAST.md").write_text("\n".join(lines), encoding="utf-8")
    # G6_CLOSED.md is owned by scripts/g6_close.py (revised rest-count rule).


def run_g6_fast(
    *,
    clip: float = 10.0,
    pair_max: float = 0.90,
    download: bool = False,
    from_ts: int = FROM_TS_DEFAULT,
    to_ts: int | None = None,
    root: Path = ROOT,
    extra_ticks: list[BookTick] | None = None,
    write_outputs: bool = True,
) -> dict[str, Any]:
    to_ts = int(to_ts or now_aligned_5m())
    leaders = load_leader_state(root)
    down = leaders["down"]
    downloaded: set[str] = set()
    one_leg: list[dict[str, Any]] = []
    joined_ticks: list[BookTick] = []
    day_notes: list[dict[str, Any]] = []

    if extra_ticks is None:
        ensure_pmdata_env_file(root / "configs" / ".env.pmdata")
        load_pmdata_env(root / "configs" / ".env.pmdata")
        BBO_DIR.mkdir(parents=True, exist_ok=True)
        series_days = [
            ("btc-5m", "2026-08-14"),
            ("btc-5m", "2026-08-15"),
            ("eth-5m", "2026-08-14"),
            ("eth-5m", "2026-08-15"),
        ]
        for series, day in series_days:
            path, note = ensure_day_l2(series, day, download=download)
            day_notes.append({"series": series, "day": day, "status": note, "path": None if path is None else str(path)})
            if path is None:
                continue
            slugs = extract_day_slim(path, from_ts=from_ts, dest_dir=BBO_DIR)
            downloaded.update(slugs)
        leader_list = sorted(leaders["union_s1"])
        have, miss = download_missing_slugs(leader_list, download=download)
        downloaded.update(have)
        day_notes.append({"slug_api_have": len(have), "slug_api_miss": len(miss), "no_unlock_days": sorted(NO_UNLOCK_DAYS)})

        for slug in sorted(downloaded):
            meta = parse_updown_slug(slug) or {"slug": slug, "asset": "", "tf": "5m", "t0": 0}
            path = _slug_parquet(slug)
            if path is None:
                continue
            try:
                slim = load_slim(path)
            except Exception:
                continue
            if slim.empty:
                continue
            info = down.get(slug)
            if not info:
                one_leg.append(one_leg_stats(slim, slug))
                continue
            ticks = ticks_from_joined_bbo(
                slim,
                slug=slug,
                asset=str(meta.get("asset") or ""),
                tf=str(meta.get("tf") or "5m"),
                t0=int(meta.get("t0") or 0),
                down_px=float(info["down_px"]),
                down_sz=float(info["down_sz"]),
            )
            if ticks:
                joined_ticks.extend(ticks)
            else:
                one_leg.append(one_leg_stats(slim, slug))

    recorder = [] if extra_ticks is not None else load_recorder_ticks(root / "data" / "l2")
    if extra_ticks is not None:
        recorder = list(extra_ticks)

    rec_rests = policy_rests(recorder, clip=clip, pair_max=pair_max)
    join_rests = policy_rests(joined_ticks, clip=clip, pair_max=pair_max) if extra_ticks is None else []
    seen: set[tuple[str, int]] = set()
    rests: list[dict[str, Any]] = []
    for rec in rec_rests + join_rests:
        key = (str(rec.get("slug") or ""), int(rec.get("t0") or 0))
        if key in seen:
            continue
        seen.add(key)
        rests.append(rec)

    agree: set[str] = set()
    for rec in join_rests:
        slug = str(rec.get("slug") or "")
        if slug in leaders["union_s1"]:
            agree.add(slug)
    downloaded_s1 = (downloaded & leaders["union_s1"]) if extra_ticks is None else set()
    if extra_ticks is not None:
        downloaded_s1 = {str(t.slug) for t in extra_ticks if str(t.slug) in leaders["union_s1"]}
        agree = {str(r.get("slug") or "") for r in rec_rests if str(r.get("slug") or "") in leaders["union_s1"]}
    n_overlap = len(downloaded_s1)
    cover = (len(agree) / n_overlap) if n_overlap else None

    def _cover(side: set[str]) -> float | None:
        ov = downloaded_s1 & side
        if not ov:
            return None
        return len(agree & ov) / len(ov)

    edges = edge_proxy(rests, clip=clip)
    q_ticks = recorder
    fill_ra = run_queue_v2(ticks=q_ticks, clip=clip, scenario="pessimistic") if q_ticks else {
        "fill_ratio": None, "n_rest": 0
    }
    fill_pr = run_queue_v2(ticks=q_ticks, clip=clip, scenario="base") if q_ticks else {
        "fill_ratio": None, "n_rest": 0
    }
    paper = paper_live_column(root / "data" / "paper_maker" / "intended.jsonl")
    worst = edges.get("worst_day")
    worst_ok = True
    if worst and worst.get("edge_over_notion") is not None:
        worst_ok = float(worst["edge_over_notion"]) + 1e-12 >= WORST_DAY_FLOOR

    stats: dict[str, Any] = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "clip": float(clip),
        "pair_max": float(pair_max),
        "from_ts": int(from_ts),
        "to_ts": int(to_ts),
        "download": bool(download),
        "n_slugs_downloaded": len(downloaded) if extra_ticks is None else len({t.slug for t in recorder}),
        "n_slugs_one_leg": len(one_leg),
        "n_slugs_joined": len({t.slug for t in joined_ticks}),
        "n_rest": len(rests),
        "n_rest_recorder": len(rec_rests),
        "n_rest_joined": len(join_rests),
        "n_leader_s1": len(leaders["union_s1"]),
        "n_leader_s1_downloaded": n_overlap,
        "n_agree": len(agree),
        "cover": cover,
        "cover_bosona": _cover(leaders["bosona_s1"]),
        "cover_mo": _cover(leaders["mo_s1"]),
        "cover_min_info": COVER_MIN,
        "edge_proxy_fee0": edges["edge_proxy_fee0"],
        "edge_proxy_rebate": edges["edge_proxy_rebate"],
        "rebate_usd": edges["rebate_usd"],
        "notion": edges["notion"],
        "worst_day": worst,
        "worst_day_ok": worst_ok,
        "fill_risk_averse": {k: fill_ra.get(k) for k in ("fill_ratio", "n_rest", "n_complete_fills", "scenario")},
        "fill_prob": {k: fill_pr.get(k) for k in ("fill_ratio", "n_rest", "n_complete_fills", "scenario")},
        "paper_live": paper,
        "one_leg_sample": one_leg[:8],
        "day_notes": day_notes,
        "days_unlocked_this_run": False,
        "pair_gt_1_trade": False,
        "live_order": False,
        "size_ok": False,
        "g5_exists": (root / G5_FLAG).is_file(),
        "live_ready_exists": (root / LIVE_READY).is_file(),
        "source_joined": "joined_yes_l2_plus_dump_down",
        "key_env": api_key_name() if extra_ticks is None else None,
        "report_written": False,
        "g6_flag_written": False,
        "g6_pass": False,
        "fail_reasons": [],
        "note": (
            "G6-fast historical twin. Not live fill proof. Not G5. Not LIVE_READY. "
            "G6-fast replaces week-long wait for calibration evidence; micro live still needed before size"
        ),
    }
    if write_outputs:
        write_reports(stats, root=root)
        stats["report_written"] = (root / "data" / "reports" / "G6_FAST.md").is_file()
        write_reports(stats, root=root)
    else:
        stats["report_written"] = True
    passed, reasons = evaluate_pass(stats)
    stats["g6_pass"] = passed
    stats["fail_reasons"] = reasons
    flag_path = root / G6_FLAG
    if passed and write_outputs:
        flag_path.parent.mkdir(parents=True, exist_ok=True)
        flag_path.write_text(
            f"g6_fast PASS {stats['generated']}\nn_rest={stats['n_rest']} edge_proxy={stats['edge_proxy_fee0']}\n",
            encoding="utf-8",
        )
        stats["g6_flag_written"] = flag_path.is_file()
    elif write_outputs and flag_path.is_file() and not passed:
        # never leave a stale auto-flag on FAIL
        try:
            flag_path.unlink()
        except OSError:
            pass
        stats["g6_flag_written"] = False
    if write_outputs:
        write_reports(stats, root=root)
        (root / "data" / "processed" / "g6_fast.json").write_text(
            json.dumps(stats, indent=2, default=str) + "\n"
        )
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="G6-fast historical calibration. No live.")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--clip", type=float, default=10.0)
    parser.add_argument("--pair-max", type=float, default=0.90)
    parser.add_argument("--from-ts", default=str(FROM_TS_DEFAULT))
    parser.add_argument("--to-ts", default="")
    args = parser.parse_args()
    from_ts = int(parse_ts(args.from_ts).timestamp()) if not str(args.from_ts).isdigit() else int(args.from_ts)
    to_ts = now_aligned_5m() if not args.to_ts else (
        int(args.to_ts) if str(args.to_ts).isdigit() else int(parse_ts(args.to_ts).timestamp())
    )
    stats = run_g6_fast(
        clip=float(args.clip),
        pair_max=float(args.pair_max),
        download=bool(args.download),
        from_ts=from_ts,
        to_ts=to_ts,
    )
    out = {
        "g6_pass": stats["g6_pass"],
        "n_rest": stats["n_rest"],
        "edge_proxy_fee0": stats["edge_proxy_fee0"],
        "n_slugs_downloaded": stats["n_slugs_downloaded"],
        "cover": stats["cover"],
        "fill_risk_averse": (stats.get("fill_risk_averse") or {}).get("fill_ratio"),
        "fill_prob": (stats.get("fill_prob") or {}).get("fill_ratio"),
        "g6_flag_written": stats["g6_flag_written"],
        "g5_exists": stats["g5_exists"],
        "live_ready_exists": stats["live_ready_exists"],
        "pair_gt_1_trade": False,
        "fail_reasons": stats["fail_reasons"],
        "note": "G6-fast replaces week-long wait for calibration evidence; micro live still needed before size",
    }
    print(json.dumps(out, indent=2))
    if not stats["g6_pass"]:
        print("G6-fast FAIL: " + "; ".join(stats["fail_reasons"] or ["unknown"]), flush=True)
        return 1
    print("G6-fast PASS. flag written. G5 still FAIL. LIVE still BLOCKED.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
