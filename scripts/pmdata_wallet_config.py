#!/usr/bin/env python3
"""Infer wallet config from dump + PMData L2/onchain (post-08-14 5m/15m).

NautilusTrader cannot reconstruct historical L2. PMData is the L2 source.
Does NOT invent new alpha. Does NOT cover 06dc daily/monthly.
Whiskas official ledger stays locked. No live. Key from env only.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from whiskas.kasa import is_s1, load_tape, quantile, tape_path, two_leg_windows
from whiskas.pmdata import (
    REGIME_CUTOFF,
    api_key_name,
    bbo_at,
    bbo_timeline,
    download,
    is_pmdata_slug,
    join_best,
    read_parquet,
)

PROC = ROOT / "data" / "processed"
REPORTS = ROOT / "data" / "reports"

WALLETS = {
    "mo-money": "0x32ed2e546b187ca15e2841edc82b22c713cf8ec3",
    "bosona": "0xc2ad03f79ca3f3c17d8c7de2612ce0c89b7d40ed",
    "06dc": "0x06dc51826bc524d9a83770e7de9dd7e005b04524",
    "whiskas": "0x3048d65321be3497164cdfc2996f94f98a2e7537",
}
DUMP_TFS = {
    "mo-money": ("5m", "15m"),
    "bosona": ("5m", "15m"),
    "06dc": None,
}


def _parse_ts(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        ts = float(raw)
        if ts > 1e12:
            ts /= 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def post14_updown_slugs(root: Path, *, before: datetime, max_slugs: int) -> list[str]:
    counts: Counter[str] = Counter()
    for name in ("mo-money", "bosona"):
        path = tape_path(root, name)
        if not path.is_file():
            continue
        for row in load_tape(path):
            if str(row.get("type") or "") != "TRADE":
                continue
            slug = str(row.get("slug") or "")
            if not is_pmdata_slug(slug):
                continue
            dt = _parse_ts(row.get("timestamp") or row.get("matchTime"))
            if dt is None or dt < REGIME_CUTOFF or dt >= before:
                continue
            counts[slug] += 1
    return [s for s, _ in counts.most_common(max_slugs)]


def dump_s1_on_slugs(root: Path, slugs: set[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, _addr, tfs in (
        ("mo-money", WALLETS["mo-money"], ("5m", "15m")),
        ("bosona", WALLETS["bosona"], ("5m", "15m")),
    ):
        path = tape_path(root, name)
        if not path.is_file():
            continue
        wins = [w for w in two_leg_windows(load_tape(path), tfs=tfs) if w.get("slug") in slugs]
        s1 = [w for w in wins if is_s1(w)]
        pairs = [float(w["maker_pair"]) for w in s1 if w.get("maker_pair") is not None]
        sizes = [float(w["maker_matched"]) for w in s1 if w.get("maker_matched") is not None]
        out[name] = {
            "n_windows": len(wins),
            "n_s1": len(s1),
            "maker_pair_p50": quantile(pairs, 0.50),
            "maker_pair_p90": quantile(pairs, 0.90),
            "maker_pair_max": max(pairs) if pairs else None,
            "maker_matched_p50": quantile(sizes, 0.50),
        }
    return out


def analyze_onchain(fills, *, bbo, wallets: dict[str, str]) -> dict[str, dict[str, Any]]:
    by: dict[str, dict[str, Any]] = {}
    for name, addr in wallets.items():
        addr_l = addr.lower()
        cell = {
            "n": 0,
            "as_maker": 0,
            "as_taker": 0,
            "maker_buy": 0,
            "sizes": [],
            "join_yes_n": 0,
            "join_yes_hit": 0,
            "join_no_comp_n": 0,
            "join_no_comp_hit": 0,
        }
        if fills is None or fills.empty:
            by[name] = cell
            continue
        maker_col = fills["maker"].astype(str).str.lower()
        taker_col = fills["taker"].astype(str).str.lower()
        sub = fills[(maker_col == addr_l) | (taker_col == addr_l)]
        cell["n"] = int(len(sub))
        for rec in sub.itertuples(index=False):
            is_maker = str(rec.maker).lower() == addr_l
            if is_maker:
                cell["as_maker"] += 1
                if str(rec.maker_side).upper() == "BUY":
                    cell["maker_buy"] += 1
                cell["sizes"].append(float(rec.token_amount))
                if bbo is not None and not bbo.empty:
                    pair = bbo_at(bbo, rec.timestamp)
                    if pair is not None:
                        flags = join_best(
                            price=float(rec.price),
                            outcome=str(rec.outcome),
                            best_bid=pair[0],
                            best_ask=pair[1],
                        )
                        if flags["yes_leg"]:
                            cell["join_yes_n"] += 1
                            cell["join_yes_hit"] += int(flags["join_best_yes"])
                        else:
                            cell["join_no_comp_n"] += 1
                            cell["join_no_comp_hit"] += int(flags["join_best_no_comp"])
            else:
                cell["as_taker"] += 1
        by[name] = cell
    return by


def _rate(hit: int, n: int) -> float | None:
    if n <= 0:
        return None
    return hit / n


def summarize(cells: list[dict[str, Any]]) -> dict[str, Any]:
    acc: dict[str, Any] = defaultdict(int)
    sizes: list[float] = []
    for c in cells:
        for k in ("n", "as_maker", "as_taker", "maker_buy", "join_yes_n", "join_yes_hit", "join_no_comp_n", "join_no_comp_hit"):
            acc[k] += int(c.get(k) or 0)
        sizes.extend(c.get("sizes") or [])
    n = int(acc["n"])
    return {
        "n_fills": n,
        "as_maker": int(acc["as_maker"]),
        "as_taker": int(acc["as_taker"]),
        "maker_share": (acc["as_maker"] / n) if n else None,
        "maker_buy": int(acc["maker_buy"]),
        "size_p25": quantile(sizes, 0.25),
        "size_p50": quantile(sizes, 0.50),
        "size_p90": quantile(sizes, 0.90),
        "join_best_yes": _rate(acc["join_yes_hit"], acc["join_yes_n"]),
        "join_best_yes_n": int(acc["join_yes_n"]),
        "join_best_no_comp": _rate(acc["join_no_comp_hit"], acc["join_no_comp_n"]),
        "join_best_no_comp_n": int(acc["join_no_comp_n"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="PMData wallet config. Post-08-14 only. No live.")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--max-slugs", type=int, default=10)
    parser.add_argument("--before", default="2026-08-16T12:00:00+00:00", help="exclude too-fresh slugs (hourly lag)")
    args = parser.parse_args()
    if not args.run:
        print(f"SCAFFOLD {Path(__file__).name} (pass --run). Needs PMDATA_API_KEY. No live.", flush=True)
        return 0
    if not api_key_name():
        print(json.dumps({"ok": False, "reason": "no PMDATA_API_KEY"}))
        return 1
    before = datetime.fromisoformat(args.before.replace("Z", "+00:00"))
    if before.tzinfo is None:
        before = before.replace(tzinfo=timezone.utc)
    slugs = post14_updown_slugs(ROOT, before=before, max_slugs=int(args.max_slugs))
    got_fills = 0
    got_l2 = 0
    per_slug: list[dict[str, Any]] = []
    wallet_cells: dict[str, list[dict[str, Any]]] = {k: [] for k in WALLETS}
    for slug in slugs:
        fills_p = download("onchain_fills", slug, dest_dir=ROOT / "data" / "parquet" / "pmdata" / "onchain_fills")
        l2_p = download("l2", slug, dest_dir=ROOT / "data" / "parquet" / "pmdata" / "l2")
        if fills_p:
            got_fills += 1
        if l2_p:
            got_l2 += 1
        fills = read_parquet(fills_p) if fills_p else None
        bbo = bbo_timeline(read_parquet(l2_p)) if l2_p else None
        cells = analyze_onchain(fills, bbo=bbo, wallets=WALLETS)
        for name, cell in cells.items():
            wallet_cells[name].append(cell)
        per_slug.append({"slug": slug, "fills": bool(fills_p), "l2": bool(l2_p)})
    wallets_out = {name: summarize(cells) for name, cells in wallet_cells.items()}
    dump = dump_s1_on_slugs(ROOT, set(slugs))
    payload = {
        "regime": "post_2026_08_14",
        "source": "pmdata + dump",
        "nautilus_historical_l2": False,
        "nautilus_note": "Nautilus Polymarket loader has no historical L2 (orderbook-history decommissioned). PMData parquet is the L2 source.",
        "l2_covers_06dc_daily_monthly": False,
        "pmdata_coverage": "updown 5m/15m/1h only",
        "mar_may_bulk": False,
        "live": False,
        "size_ok": False,
        "pair_gt_1_trade": False,
        "whiskas_official_ledger_locked": True,
        "key_env": api_key_name(),
        "n_slugs_requested": len(slugs),
        "n_onchain_ok": got_fills,
        "n_l2_ok": got_l2,
        "slugs": per_slug,
        "wallets": wallets_out,
        "dump_s1_on_same_slugs": dump,
        "inferred": {
            "pair_max": 0.90,
            "pair_max_source": "dump S1 maker_pair < 0.90 (cover PASS). PMData L2 is Yes-token only — cannot reconstruct bid_sum. Do not override.",
            "cancel_above": 0.92,
            "cancel_above_source": "policy wiring. Cancels not in onchain fills.",
            "paper_clip": 10,
            "join_best": "intended; Yes-leg join% is a fill-band (block time vs L2 µs), not go/no-go",
            "06dc_truth": "dump + paper_06dc + T6",
            "primary": "paper_maker",
        },
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }
    PROC.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (PROC / "pmdata_wallet_config.json").write_text(json.dumps(payload, indent=2) + "\n")
    lines = [
        "# PMDATA_WALLET_CONFIG",
        "",
        f"Generated: {payload['generated']}",
        "Post-08-14 only. No Mar–May bulk. No live. size_ok=false. pair_gt_1_trade=false.",
        "",
        "**Nautilus historical L2 = false** (orderbook-history dead). PMData is the L2 source.",
        "**PMData does NOT cover 06dc daily/monthly.** 06dc truth = dump + paper_06dc + T6.",
        "Whiskas official ledger locked — onchain counts only, no PHASE1 rewrite.",
        "PMData L2 is a single Yes-token book. bid_sum is from the dump, not reconstructed.",
        "",
        f"slugs requested={len(slugs)} onchain_ok={got_fills} l2_ok={got_l2}",
        "",
        "| wallet | n_fills | maker_share | size_p50 | join_best_yes | dump S1 n | dump pair p50 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, cell in wallets_out.items():
        d = dump.get(name) or {}
        lines.append(
            f"| {name} | {cell['n_fills']} | {cell['maker_share']} | {cell['size_p50']} | "
            f"{cell['join_best_yes']} | {d.get('n_s1')} | {d.get('maker_pair_p50')} |"
        )
    lines.extend(
        [
            "",
            "## Inferred vs yaml (no new alpha)",
            "",
            "- pair_max **0.90** from dump S1 (not from PMData bid_sum)",
            "- cancel_above **0.92** (unobserved in fills)",
            "- paper_clip **10** (size gap vs their matched p50 on full tape)",
            "- maker rest both; pair>1 trade=false",
            "- join-best is intended; low join% on short align = calibrate, not kill S1",
            "",
        ]
    )
    (REPORTS / "PMDATA_WALLET_CONFIG.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({
        "ok": True,
        "n_slugs": len(slugs),
        "n_onchain_ok": got_fills,
        "n_l2_ok": got_l2,
        "wallets": {k: {"n": v["n_fills"], "maker_share": v["maker_share"], "size_p50": v["size_p50"], "join_best_yes": v["join_best_yes"]} for k, v in wallets_out.items()},
        "size_ok": False,
        "l2_covers_06dc": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
