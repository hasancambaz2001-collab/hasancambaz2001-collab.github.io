#!/usr/bin/env python3
"""BTC A vs A+A2 compare. Does not rewrite A replay or PHASE3_REPLAY.md."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from whiskas.config import load_config, product_from_config
from whiskas.replay_a2 import run_a2_compare

PROC = ROOT / "data" / "processed"
REPORTS = ROOT / "data" / "reports"
FILLS = PROC / "whiskas_fills.parquet"


def _fmt(x: float | None, digits: int = 2) -> str:
    if x is None:
        return "n/a"
    return f"{x:.{digits}f}"


def _pct(x: float | None) -> str:
    if x is None:
        return "n/a"
    return f"{x:.2%}"


def write_report(stats: dict) -> str:
    a = stats["a"]
    x = stats["a2_extra"]
    p = stats["a_plus_a2"]
    gate = "PASS" if stats["passed"] else "FAIL"
    reasons = ", ".join(stats["fail_reasons"]) if stats["fail_reasons"] else "none"
    return f"""# PHASE3 A vs A+A2 (BTC tape only)

A replay is unchanged (`PHASE3_REPLAY.md`). No T6. No pair>1 force. No Diamond.
No live. Inventory is per-window leftover, not cross-asset.

## Policy

- **A:** flat + `ask_u+ask_d≤0.96` + `min_size≥21` → FOK both, clip 21
- **A2 first-leg:** flat + valid pair + one side `<21` + `cheap_ask≤0.45` → FOK cheap `min(21, cheap_size)`
- **A2 complete:** holding one leg + `avg+ask≤0.96` → FOK the other, `min(held, 21, ask_size)`
- Never complete if `avg+ask>0.96`. Never a lone cheap ask.

A+A2 = A windows (existing VWAP complete-set) **plus** sequential A2 on the other BTC windows.

| | windows | pnl @100% | pnl @30% EV | max naked s | worst day @30% EV |
|---|---:|---:|---:|---:|---:|
| A | {a["n_windows"]} | {_fmt(a["pnl_fill1"])} | {_fmt(a["pnl_fill30_ev"])} | {_fmt(a["max_naked_sec"], 1)} | {_pct(a["worst_day_pct_fill30_ev"])} |
| A2 extra | {x["n_windows"]} | {_fmt(x["pnl_fill1"])} | {_fmt(x["pnl_fill30_ev"])} | {_fmt(x["max_naked_sec"], 1)} | — |
| **A+A2** | {p["n_windows"]} | {_fmt(p["pnl_fill1"])} | {_fmt(p["pnl_fill30_ev"])} | {_fmt(p["max_naked_sec"], 1)} | {_pct(p["worst_day_pct_fill30_ev"])} |

A2 extra first-legs={x["n_first"]}, completes={x["n_complete"]}, leftover windows={x["n_residual"]}.
A+A2 30% MC pnl={_fmt(p["pnl_fill30_mc"])}, worst MC day={_pct(p["worst_day_pct_fill30_mc"])}.

## PASS

| gate | need | ok |
|---|---|---|
| A2 pnl ≥ A (30% EV) | {_fmt(p["pnl_fill30_ev"])} ≥ {_fmt(a["pnl_fill30_ev"])} | {stats["pass_a2_ge_a"]} |
| no day −15% | worst={_pct(p["worst_day_pct_fill30_ev"])} | {stats["pass_day"]} |

**{gate}**. Fail reasons: {reasons}.
"""


def main() -> int:
    if not FILLS.is_file():
        print(f"missing {FILLS}", file=sys.stderr)
        return 2
    cfg = product_from_config(load_config(ROOT / "configs" / "whiskas.yaml"))
    fills = pd.read_parquet(FILLS)
    stats = run_a2_compare(
        fills,
        pair_max=cfg["pair_max"],
        pair_max_cap=cfg["pair_max_cap"],
        clip=cfg["clip"],
        fill_prob=cfg["fill_prob_stress"],
        start_equity=cfg["start_equity"],
        day_dd=cfg["day_dd"],
    )
    PROC.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (PROC / "a2_stats.json").write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    (REPORTS / "PHASE3_A2.md").write_text(write_report(stats), encoding="utf-8")
    print(json.dumps({
        "a_n": stats["a"]["n_windows"],
        "a_pnl30": stats["a"]["pnl_fill30_ev"],
        "a2_extra_n": stats["a2_extra"]["n_windows"],
        "a2_extra_pnl30": stats["a2_extra"]["pnl_fill30_ev"],
        "plus_n": stats["a_plus_a2"]["n_windows"],
        "plus_pnl30": stats["a_plus_a2"]["pnl_fill30_ev"],
        "max_naked_sec": stats["a_plus_a2"]["max_naked_sec"],
        "passed": stats["passed"],
        "fail_reasons": stats["fail_reasons"],
    }, indent=2))
    print(f"wrote {REPORTS / 'PHASE3_A2.md'}", flush=True)
    return 0 if stats["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
