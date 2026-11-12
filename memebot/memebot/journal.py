"""Append-only JSONL journal + performance report."""
from __future__ import annotations

import json
import math
import os
import re
import time
from typing import Iterable


class Journal:
    def __init__(self, path: str | None):
        self.path = path
        self.rows: list[dict] = []
        if path:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            self._fh = open(path, "a", buffering=1)
        else:
            self._fh = None

    def write(self, kind: str, **data):
        row = {"type": kind, "wall_ts": round(time.time(), 3), **data}
        self.rows.append(row)
        if self._fh:
            self._fh.write(json.dumps(row, default=str) + "\n")

    def close(self):
        if self._fh:
            self._fh.close()


def load(path: str) -> list[dict]:
    with open(path) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def summarize(rows: Iterable[dict]) -> dict:
    closes = [r for r in rows if r.get("type") == "close"]
    n = len(closes)
    if not n:
        return {"trades": 0}
    pnls = [r["pnl_sol"] for r in closes]
    cost = sum(r["cost_sol"] for r in closes)
    eq, peak, mdd = 0.0, 0.0, 0.0
    for p in sorted(closes, key=lambda r: r["closed_ts"]):
        eq += p["pnl_sol"]
        peak = max(peak, eq)
        mdd = max(mdd, peak - eq)
    reasons: dict[str, int] = {}
    for r in closes:
        k = re.split(r"[\s@]|_\d", (r.get("exit_reasons") or ["?"])[-1])[0]
        reasons[k] = reasons.get(k, 0) + 1
    mean = sum(pnls) / n
    sd = math.sqrt(sum((p - mean) ** 2 for p in pnls) / (n - 1)) if n > 1 else 0.0
    return {
        "trades": n,
        "win_rate": sum(p > 0 for p in pnls) / n,
        "principal_recovered_rate": sum(bool(r.get("recovered")) for r in closes) / n,
        "total_cost_sol": round(cost, 4),
        "total_pnl_sol": round(sum(pnls), 4),
        "roi_on_deployed": round(sum(pnls) / cost, 4) if cost else 0.0,
        "avg_pnl_sol": round(mean, 4),
        "pnl_t_stat": round(mean / (sd / math.sqrt(n)), 2) if sd > 0 else None,
        "best_multiple": round(max(r["multiple"] for r in closes), 2),
        "worst_multiple": round(min(r["multiple"] for r in closes), 2),
        "max_drawdown_sol": round(mdd, 4),
        "final_exit_reasons": dict(sorted(reasons.items(), key=lambda kv: -kv[1])),
    }


def format_summary(s: dict, sol_usd: float = 0.0) -> str:
    if not s.get("trades"):
        return "Hic kapanmis islem yok."
    usd = (lambda x: f" (${x * sol_usd:,.0f})") if sol_usd else (lambda x: "")
    lines = [
        f"Islem sayisi            : {s['trades']}",
        f"Kazanma orani           : {s['win_rate']:.1%}",
        f"Anapara kurtarma orani  : {s['principal_recovered_rate']:.1%}",
        f"Toplam yatirilan        : {s['total_cost_sol']} SOL{usd(s['total_cost_sol'])}",
        f"Toplam PnL              : {s['total_pnl_sol']:+} SOL{usd(s['total_pnl_sol'])}",
        f"Yatirilana gore getiri  : {s['roi_on_deployed']:+.1%}",
        f"Islem basi ort. PnL     : {s['avg_pnl_sol']:+} SOL  (t-stat {s['pnl_t_stat']})",
        f"En iyi / en kotu carpan : {s['best_multiple']}x / {s['worst_multiple']}x",
        f"Max drawdown            : {s['max_drawdown_sol']} SOL",
        f"Son cikis nedenleri     : {s['final_exit_reasons']}",
    ]
    return "\n".join(lines)
