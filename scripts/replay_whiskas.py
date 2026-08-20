#!/usr/bin/env python3
"""Replay taker complete-set (ask_sum ≤ 0.96). No live. Does not reopen T6–T9 / tie-out."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from whiskas.config import load_config, product_from_config
from whiskas.constants import REPLAY_SEED
from whiskas.replay import result_to_dict, run_replay

PROC = ROOT / "data" / "processed"
REPORTS = ROOT / "data" / "reports"
FILLS = PROC / "whiskas_fills.parquet"


def _fmt(x: float | None, digits: int = 4) -> str:
    if x is None:
        return "n/a"
    return f"{x:.{digits}f}"


def _pct(x: float | None) -> str:
    if x is None:
        return "n/a"
    return f"{x:.2%}"


def _md_days(days: list[dict], limit: int = 8) -> str:
    if not days:
        return "_no trading days_"
    worst = min(days, key=lambda d: d["day_pct"])
    best = max(days, key=lambda d: d["day_pct"])
    last = days[-1]
    lines = [
        f"- days traded: {len(days)}",
        f"- worst day: {worst['day']} pnl={worst['pnl']:.4f} ({worst['day_pct']:.2%}) halt={worst['halt']}",
        f"- best day: {best['day']} pnl={best['pnl']:.4f} ({best['day_pct']:.2%})",
        f"- last day equity: {last['end_equity']:.2f} ({last['day']})",
    ]
    head = days[:limit]
    if head:
        lines.append("")
        lines.append("| day | n | pnl | day % | equity end | halt |")
        lines.append("|---|---:|---:|---:|---:|---|")
        for d in head:
            lines.append(
                f"| {d['day']} | {d['n']} | {d['pnl']:.4f} | {d['day_pct']:.2%} | {d['end_equity']:.2f} | {d['halt']} |"
            )
        if len(days) > limit:
            lines.append(f"| … | {len(days) - limit} more days | | | | |")
    return "\n".join(lines)


def write_report(stats: dict) -> str:
    gate = "PASS" if stats["passed"] else "FAIL"
    reasons = ", ".join(stats["fail_reasons"]) if stats["fail_reasons"] else "none"
    return f"""# PHASE3 replay — taker complete-set

Context locked. This file does **not** reopen T6–T9 or the official tie-out.
Maker / Diamond rebate is **their** edge, not ours. We assume we are **not** Diamond
(no 29% taker rebate).

## Product

| field | value |
|---|---|
| book | BUY both asks FOK |
| SELL | none |
| residual | none (both-or-nothing) |
| signal | none (no spot / TWAP) |
| redeem | after resolve (winner-independent) |
| pair_max | **0.96** (inclusive) |
| pair_max_cap | 0.97 (not traded) |
| clip | **21** |
| fee | `0.07 * p * (1 − p)` on **our** taker fills |
| Diamond | no |
| maker bids | no |
| live | no |

`pair_max=0.9513` is forbidden (broken PHASE1 p25).

## Ask proxy

Eligible window = both Up and Down have at least one **taker BUY** fill on the
Whiskas tape. Ask = size-weighted VWAP of those CLOB `price` fields
(`Σ size×price / Σ size`). That is what they paid lifting the ask — conservative
versus a maker bid.

Replay size is always `clip=21`, not their size. Our fee is the official curve
on that clip at the proxy asks. Their embedded fee / rebate is not reused.

Windows with only one taker leg, or `ask_sum > 0.96`, are skipped.
`(0.96, 0.97]` is reported as excluded-cap only (after-fee can flip negative
near 0.50/0.47).

## Universe

| | n |
|---|---:|
| tape windows (unique slug on fills) | {stats["n_windows"]} |
| both taker legs | {stats["n_both_legs"]} |
| **eligible `ask_sum ≤ 0.96`** | **{stats["n_eligible"]}** |
| excluded `(0.96, 0.97]` | {stats["n_excluded_cap"]} |

Median pair on eligible: **{_fmt(stats["median_pair"], 4)}**
(p10={_fmt(stats["pair_p10"], 4)}, p90={_fmt(stats["pair_p90"], 4)}).

## PnL (after fee, no rebate)

Complete-set: `21 × (1 − ask_sum) − fee(21, ask_up) − fee(21, ask_down)`.
Winner does not matter. Residual is always 0.

Fill 1.00 = every eligible window FOKs. Fill 0.30 = P(pair FOK succeeds) = 0.30
(both-or-nothing; independent per-leg 30% would leave residual and is rejected).
EV = `0.30 × fill1`. MC = seeded Bernoulli per window (seed={stats["seed"]}).

Start equity for day %: **$1000**. Day halt if `day_pnl / equity_at_open ≤ −15%`.
Old kill-switch default (−8%) is unchanged and unused here.

| fill | windows filled | pnl after fee | worst day % |
|---|---:|---:|---:|
| 1.00 | {stats["n_eligible"]} | {_fmt(stats["pnl_fill1"], 2)} | {_pct(stats["worst_day_pct_fill1"])} |
| 0.30 EV | {stats["n_eligible"]} (EV) | {_fmt(stats["pnl_fill30_ev"], 2)} | {_pct(stats["worst_day_pct_fill30_ev"])} |
| 0.30 MC | {stats["n_fill30_mc"]} | {_fmt(stats["pnl_fill30_mc"], 2)} | {_pct(stats["worst_day_pct_fill30_mc"])} |

Fees at fill 1.00 (both legs): ${_fmt(stats["fees_fill1"], 2)}.

### Daily path — fill 1.00

{_md_days(stats["days_fill1"])}

### Daily path — fill 0.30 EV

{_md_days(stats["days_fill30_ev"])}

### Daily path — fill 0.30 MC (seed {stats["seed"]})

{_md_days(stats["days_fill30_mc"])}

## PASS

| gate | need | got | ok |
|---|---|---|---|
| windows | > 400 | {stats["n_eligible"]} | {stats["pass_n"]} |
| pnl after fee @ 30% fill | > 0 | {_fmt(stats["pnl_fill30_ev"], 2)} | {stats["pass_pnl30"]} |
| median pair | ≤ 0.96 | {_fmt(stats["median_pair"], 4)} | {stats["pass_median"]} |
| no day −15% | fill1 + 0.30 EV + 0.30 MC | worst={_pct(stats["worst_day_pct_fill30_ev"])} / MC {_pct(stats["worst_day_pct_fill30_mc"])} | {stats["pass_day"]} |

**{gate}**. Fail reasons: {reasons}.

## Paper (no orders)

`scripts/paper_whiskas.py` polls the public CLOB for the current `btc-updown-5m-{{t0}}`
window and appends *intended* BUY FOKs to `data/paper/intended.jsonl` when
`ask_up + ask_down ≤ 0.96`. GET only. No maker bids. No live.

```bash
python3 scripts/paper_whiskas.py --once
python3 scripts/paper_whiskas.py --seconds 60 --interval 5
```

## Replay command

```bash
python3 scripts/replay_whiskas.py
```

Writes `data/processed/replay_stats.json`, `data/processed/replay_eligible.parquet`,
and this file.
"""


def main() -> int:
    fills_path = FILLS
    if not fills_path.is_file():
        print(f"missing {fills_path} — run dump + build_windows first", file=sys.stderr)
        return 2
    cfg = product_from_config(load_config(ROOT / "configs" / "whiskas.yaml"))
    if cfg["assume_diamond"]:
        raise SystemExit("assume_diamond must be false")
    fills = pd.read_parquet(fills_path)
    result, elig, _asks = run_replay(
        fills,
        pair_max=cfg["pair_max"],
        pair_max_cap=cfg["pair_max_cap"],
        clip=cfg["clip"],
        fill_prob=cfg["fill_prob_stress"],
        start_equity=cfg["start_equity"],
        day_dd=cfg["day_dd"],
        seed=REPLAY_SEED,
    )
    stats = result_to_dict(result)
    stats["pair_max"] = cfg["pair_max"]
    stats["pair_max_cap"] = cfg["pair_max_cap"]
    stats["clip"] = cfg["clip"]
    stats["fill_prob_stress"] = cfg["fill_prob_stress"]
    stats["start_equity"] = cfg["start_equity"]
    stats["day_dd"] = cfg["day_dd"]
    PROC.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (PROC / "replay_stats.json").write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    if not elig.empty:
        elig.to_parquet(PROC / "replay_eligible.parquet", index=False)
    report = write_report(stats)
    (REPORTS / "PHASE3_REPLAY.md").write_text(report, encoding="utf-8")
    print(json.dumps({k: stats[k] for k in (
        "n_eligible", "median_pair", "pnl_fill1", "pnl_fill30_ev", "pnl_fill30_mc",
        "worst_day_pct_fill1", "worst_day_pct_fill30_ev", "worst_day_pct_fill30_mc",
        "passed", "fail_reasons",
    )}, indent=2))
    print(f"wrote {REPORTS / 'PHASE3_REPLAY.md'}", flush=True)
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
