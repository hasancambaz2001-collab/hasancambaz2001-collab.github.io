#!/usr/bin/env python3
"""Twin PolicyMaker on recorded L2 or pre-regime parquet. No live. No pair>1.

parquet = REGIME=pre_2026_08_14_DEBUG (kachoio Mar–May). Not live parity.
record  = REGIME=post_2026_08_14 (data/l2 + activity since 2026-08-14).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from glob import glob
from pathlib import Path
from typing import Any, Iterable, Iterator
from urllib.request import urlretrieve

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from whiskas.kasa import load_tape, tape_path, two_leg_windows
from whiskas.l2 import (
    CLIP,
    REGIME_CUTOFF,
    REGIME_POST,
    REGIME_PRE,
    BookTick,
    PolicyMaker,
    action_bucket,
    regime_for_ts,
)

HF_REPO = "kachoio/polymarket-5-minute-crypto-up-down-markets"
HF_BASE = f"https://huggingface.co/datasets/{HF_REPO}/resolve/main"
PARQUET_DIR = ROOT / "data" / "parquet"
L2_DIR = ROOT / "data" / "l2"
REPORTS = ROOT / "data" / "reports"
PROC = ROOT / "data" / "processed"
PMDATA_KEYS = ("PMDATA_API_KEY", "PM_DATA_API_KEY", "PMDATA_KEY")


def _parse_trade_ts(row: dict[str, Any]) -> datetime | None:
    raw = row.get("timestamp") or row.get("matchTime") or row.get("createdAt")
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        ts = float(raw)
        if ts > 1e12:
            ts /= 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    text = str(raw).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def download_hf(name: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    url = f"{HF_BASE}/{name}"
    tmp = dest.with_suffix(dest.suffix + ".part")
    print(json.dumps({"download": name, "url": url}), flush=True)
    urlretrieve(url, tmp)
    tmp.replace(dest)
    return dest


def ensure_btc_parquet(path: Path) -> tuple[Path, Path]:
    ticks = path
    if ticks.name != "btc_ticks.parquet":
        ticks = path if path.suffix == ".parquet" else PARQUET_DIR / "btc_ticks.parquet"
    markets = ticks.with_name("btc_markets.parquet")
    if not ticks.is_file() or ticks.stat().st_size <= 0:
        download_hf("btc_ticks.parquet", ticks)
    if not markets.is_file() or markets.stat().st_size <= 0:
        download_hf("btc_markets.parquet", markets)
    return ticks, markets


def load_slug_map(markets_path: Path) -> dict[str, str]:
    if not markets_path.is_file():
        return {}
    import pyarrow.parquet as pq

    table = pq.read_table(markets_path, columns=["condition_id", "slug"])
    out: dict[str, str] = {}
    for cid, slug in zip(table.column("condition_id").to_pylist(), table.column("slug").to_pylist()):
        if cid and slug:
            out[str(cid)] = str(slug)
    return out


def iter_parquet_ticks(ticks_path: Path, markets_path: Path | None = None) -> Iterator[BookTick]:
    import pyarrow.parquet as pq

    asset = ticks_path.name.split("_")[0].lower()
    slug_by_cid = load_slug_map(markets_path) if markets_path else {}
    pf = pq.ParquetFile(ticks_path)
    cols = ["condition_id", "t", "bu", "bd", "au", "ad", "su", "sd", "sau", "sad"]
    for batch in pf.iter_batches(batch_size=16384, columns=cols):
        data = batch.to_pydict()
        n = batch.num_rows
        for i in range(n):
            cid = data["condition_id"][i]
            t = data["t"][i]
            slug = slug_by_cid.get(str(cid) if cid is not None else "")
            if not slug:
                t0 = int(float(t) // 300) * 300
                slug = f"{asset}-updown-5m-{t0}"
            yield BookTick.from_parquet_row(
                t=t,
                bu=data["bu"][i],
                bd=data["bd"][i],
                au=data["au"][i],
                ad=data["ad"][i],
                su=data["su"][i],
                sd=data["sd"][i],
                sau=data["sau"][i],
                sad=data["sad"][i],
                condition_id=cid,
                slug=slug,
                asset=asset,
                tf="5m",
            )


def iter_record_ticks(paths: Iterable[Path]) -> Iterator[BookTick]:
    for path in sorted(paths):
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


def run_twin(
    ticks: Iterable[BookTick],
    *,
    clip: float,
    fill: str,
    regime: str,
) -> dict[str, Any]:
    policy = PolicyMaker(pair_max=0.90, cancel_above=0.92, clip=float(clip), fill=fill)
    states: dict[str, dict[str, Any] | None] = {}
    hist: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    n = 0
    n_cheap = 0
    n_rest_opp = 0
    first_t = None
    last_t = None
    slugs: set[str] = set()
    rest_slugs: set[str] = set()
    for tick in ticks:
        n += 1
        slugs.add(tick.slug)
        if first_t is None or tick.t < first_t:
            first_t = tick.t
        if last_t is None or tick.t > last_t:
            last_t = tick.t
        if tick.bid_sum is not None and float(tick.bid_sum) <= 0.90 + 1e-12:
            n_cheap += 1
        rec, states[tick.slug] = policy.step(tick, states.get(tick.slug))
        reasons[str(rec.get("reason") or "watch")] += 1
        hist[action_bucket(str(rec.get("reason") or ""), cancel=bool(rec.get("cancel")))] += 1
        if rec.get("reason") == "rest":
            n_rest_opp += 1
            rest_slugs.add(tick.slug)
    pct = (100.0 * n_cheap / n) if n else 0.0
    return {
        "regime": regime,
        "fill": fill,
        "clip": float(clip),
        "pair_max": 0.90,
        "cancel_above": 0.92,
        "live_order": False,
        "pair_gt_1": False,
        "size_ok": False,
        "n_ticks": n,
        "n_slugs": len(slugs),
        "n_rest_slugs": len(rest_slugs),
        "pct_bid_sum_le_090": round(pct, 4),
        "n_bid_sum_le_090": n_cheap,
        "n_rest": int(hist.get("rest", 0)),
        "n_replace": int(hist.get("replace", 0)),
        "n_cancel": int(hist.get("cancel", 0)),
        "n_rich": int(hist.get("rich", 0)),
        "histogram": dict(hist),
        "reasons": dict(reasons),
        "first_t": first_t,
        "last_t": last_t,
        "first_ts": datetime.fromtimestamp(first_t, tz=timezone.utc).isoformat() if first_t else None,
        "last_ts": datetime.fromtimestamp(last_t, tz=timezone.utc).isoformat() if last_t else None,
        "note": (
            "pre-08-14 parquet is DEBUG only; live parity needs post-08-14 L2"
            if regime == REGIME_PRE
            else "post-08-14 record twin. S1 maker complete-set. Not residual/TWAP directional."
        ),
    }


def cheap_mobo_slugs_since_cutoff() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name, tfs in (("mo-money", ("5m", "15m")), ("bosona", ("5m", "15m"))):
        path = tape_path(ROOT, name)
        if not path.is_file():
            continue
        rows = []
        for row in load_tape(path):
            ts = _parse_trade_ts(row)
            if ts is None or ts < REGIME_CUTOFF:
                continue
            rows.append(row)
        for win in two_leg_windows(rows, tfs=tfs):
            pair = win.get("pair")
            if pair is None or float(pair) >= 0.90:
                continue
            out.append(
                {
                    "wallet": name,
                    "slug": win["slug"],
                    "tf": win.get("tf"),
                    "pair": float(pair),
                    "matched": win.get("matched"),
                }
            )
    return out


def cross_check(record_ticks: list[BookTick], cheap: list[dict[str, Any]]) -> dict[str, Any]:
    by_slug: dict[str, list[BookTick]] = {}
    for tick in record_ticks:
        by_slug.setdefault(tick.slug, []).append(tick)
    n_with_l2 = 0
    n_rest = 0
    examples: list[dict[str, Any]] = []
    for win in cheap:
        ticks = by_slug.get(str(win["slug"])) or []
        if not ticks:
            continue
        n_with_l2 += 1
        cheap_ticks = [t for t in ticks if t.bid_sum is not None and float(t.bid_sum) <= 0.90 + 1e-12]
        if cheap_ticks:
            n_rest += 1
            if len(examples) < 8:
                examples.append(
                    {
                        "wallet": win["wallet"],
                        "slug": win["slug"],
                        "their_pair": win["pair"],
                        "l2_n": len(ticks),
                        "l2_cheap_n": len(cheap_ticks),
                        "l2_min_bid_sum": min(float(t.bid_sum) for t in cheap_ticks if t.bid_sum is not None),
                    }
                )
    return {
        "cheap_windows_since_08_14": len(cheap),
        "slugs_with_l2": n_with_l2,
        "slugs_with_rest_opportunity": n_rest,
        "examples": examples,
        "note": "Rest opportunity = same slug has a recorded tick with bid_sum<=0.90.",
    }


def pmdata_optional() -> dict[str, Any]:
    key = None
    for name in PMDATA_KEYS:
        val = os.environ.get(name)
        if val:
            key = name
            break
    if not key:
        return {
            "skipped": True,
            "reason": "no PMDATA_API_KEY (or PM_DATA_API_KEY). HF parquet covers pre-08-14 DEBUG. No paid Mar–May pull.",
        }
    return {
        "skipped": True,
        "reason": f"{key} present but post-08-14 L2 recorder is the truth source; no bulk Mar–May PMData download.",
        "had_key": True,
    }


def write_report(payloads: list[dict[str, Any]], *, recorder: dict[str, Any], cross: dict[str, Any], pmdata: dict[str, Any]) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    PROC.mkdir(parents=True, exist_ok=True)
    lines = [
        "# TWIN_L2",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "S1 maker complete-set (bid_sum≤0.90). Not residual/TWAP directional. No live. No pair>1. size_ok=false.",
        "",
        "**pre-08-14 parquet is DEBUG only; live parity needs post-08-14 L2**",
        "",
        "## Recorder",
        "",
        f"- PID: **{recorder.get('pid')}**",
        f"- start: {recorder.get('start')}",
        f"- hours of L2: **{recorder.get('hours')}**",
        f"- ticks: {recorder.get('n_ticks')} files={recorder.get('n_files')}",
        "",
        "## Twins",
        "",
        "| regime | n_ticks | % bid_sum≤0.90 | rest | replace | cancel | rich | fill |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for p in payloads:
        lines.append(
            f"| {p['regime']} | {p['n_ticks']} | {p['pct_bid_sum_le_090']:.4f} | "
            f"{p['n_rest']} | {p['n_replace']} | {p['n_cancel']} | {p['n_rich']} | {p['fill']} |"
        )
    lines.extend(
        [
            "",
            "## Cross-check (mo/bosona pair<0.90 since 2026-08-14 vs recorded L2)",
            "",
            f"- cheap windows since 08-14: **{cross.get('cheap_windows_since_08_14')}**",
            f"- those slugs with L2: **{cross.get('slugs_with_l2')}**",
            f"- rest opportunity on same slug: **{cross.get('slugs_with_rest_opportunity')}**",
            "",
            "## PMData",
            "",
            f"- {pmdata.get('reason')}",
            "",
            "pre-08-14 parquet is DEBUG only; live parity needs post-08-14 L2",
            "",
        ]
    )
    path = REPORTS / "TWIN_L2.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def recorder_status(out_dir: Path) -> dict[str, Any]:
    pid_path = out_dir / "recorder.pid"
    start_path = out_dir / "recorder_start.txt"
    pid = None
    start = None
    if pid_path.is_file():
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
        except ValueError:
            pid = None
    if start_path.is_file():
        start = start_path.read_text(encoding="utf-8").strip()
    files = sorted(out_dir.glob("*.jsonl"))
    n_ticks = 0
    first = None
    last = None
    for path in files:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                n_ticks += 1
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = rec.get("t")
                if t is None:
                    continue
                t = float(t)
                if first is None or t < first:
                    first = t
                if last is None or t > last:
                    last = t
    hours = 0.0
    if first is not None and last is not None and last >= first:
        hours = (last - first) / 3600.0
    elif start:
        try:
            dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            hours = max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 3600.0)
        except ValueError:
            hours = 0.0
    alive = False
    if pid:
        try:
            os.kill(pid, 0)
            alive = True
        except OSError:
            alive = False
    return {
        "pid": pid,
        "alive": alive,
        "start": start,
        "hours": round(hours, 4),
        "n_ticks": n_ticks,
        "n_files": len(files),
        "first_t": first,
        "last_t": last,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Twin PolicyMaker on L2. No live.")
    parser.add_argument("--source", choices=("parquet", "record", "pmdata"), required=True)
    parser.add_argument("--path", type=Path, default=PARQUET_DIR / "btc_ticks.parquet")
    parser.add_argument("--glob", type=str, default="data/l2/*.jsonl")
    parser.add_argument("--clip", type=float, default=CLIP)
    parser.add_argument("--fill", choices=("none", "residual"), default="none")
    parser.add_argument("--report", action="store_true", help="rewrite TWIN_L2.md from this run plus prior json")
    args = parser.parse_args()

    if args.source == "pmdata":
        payload = {"regime": REGIME_POST, "source": "pmdata", **pmdata_optional(), "n_ticks": 0, "size_ok": False}
        print(json.dumps(payload, indent=2))
        return 0

    if args.source == "parquet":
        ticks_path, markets_path = ensure_btc_parquet(args.path)
        ticks = iter_parquet_ticks(ticks_path, markets_path)
        payload = run_twin(ticks, clip=float(args.clip), fill=args.fill, regime=REGIME_PRE)
        payload["source"] = "parquet"
        payload["path"] = str(ticks_path)
        payload["dataset"] = HF_REPO
        payload["label"] = f"REGIME={REGIME_PRE}"
    else:
        paths = [Path(p) for p in glob(args.glob)]
        record_list = list(iter_record_ticks(paths))
        payload = run_twin(record_list, clip=float(args.clip), fill=args.fill, regime=REGIME_POST)
        payload["source"] = "record"
        payload["glob"] = args.glob
        payload["n_files"] = len(paths)
        payload["label"] = f"REGIME={REGIME_POST}"
        cheap = cheap_mobo_slugs_since_cutoff()
        payload["cross_check"] = cross_check(record_list, cheap)

    PROC.mkdir(parents=True, exist_ok=True)
    out_json = PROC / f"twin_l2_{payload['regime']}.json"
    out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: payload[k] for k in payload if k not in {"reasons", "histogram"} or True}, indent=2))

    recorder = recorder_status(L2_DIR)
    payloads = []
    for name in (REGIME_PRE, REGIME_POST):
        p = PROC / f"twin_l2_{name}.json"
        if p.is_file():
            payloads.append(json.loads(p.read_text(encoding="utf-8")))
        elif payload.get("regime") == name:
            payloads.append(payload)
    if payload not in payloads and payload.get("regime"):
        payloads.append(payload)
    cross = payload.get("cross_check") or {
        "cheap_windows_since_08_14": None,
        "slugs_with_l2": None,
        "slugs_with_rest_opportunity": None,
    }
    write_report(payloads, recorder=recorder, cross=cross, pmdata=pmdata_optional())
    print("pre-08-14 parquet is DEBUG only; live parity needs post-08-14 L2", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
