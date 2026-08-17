"""CLI: python -m polyedge scan|farm"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .farm import FarmConfig, QuoteParams, build_plan, render_farm_markdown
from .report import render_markdown
from .scanners import run_scan


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="polyedge",
        description="Polymarket protocol-yield scanners and paper farm planner.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    scan = sub.add_parser("scan", help="Run live Gamma + CLOB paper scan")
    scan.add_argument("--max-markets", type=int, default=1200)
    scan.add_argument("--max-events", type=int, default=40)
    scan.add_argument("--max-books", type=int, default=350)
    scan.add_argument("--min-edge", type=float, default=0.004, help="Min net edge after fees")
    scan.add_argument("--json-out", type=Path, default=None)
    scan.add_argument("--md-out", type=Path, default=None)

    farm = sub.add_parser("farm", help="Build the maker/LP + holding paper farm plan")
    farm.add_argument("--bankroll", type=float, default=2000.0)
    farm.add_argument("--holding-frac", type=float, default=0.15)
    farm.add_argument("--max-markets", type=int, default=6)
    farm.add_argument("--min-daily", type=float, default=15.0)
    farm.add_argument("--include-short-crypto", action="store_true")
    farm.add_argument("--include-same-day", action="store_true")
    farm.add_argument("--include-mentions", action="store_true")
    farm.add_argument("--min-liquidity", type=float, default=2500.0)
    farm.add_argument("--kalshi", action="store_true", help="Cross-check titles on Kalshi/pmxt")
    farm.add_argument("--reward-limit", type=int, default=2000)
    farm.add_argument("--json-out", type=Path, default=None)
    farm.add_argument("--md-out", type=Path, default=None)
    return p


def _write_outputs(md: str, payload: dict, md_out: Path | None, json_out: Path | None) -> None:
    sys.stdout.write(md)
    if md_out:
        md_out.parent.mkdir(parents=True, exist_ok=True)
        md_out.write_text(md, encoding="utf-8")
    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "scan":
        result = run_scan(
            max_markets=args.max_markets,
            max_events=args.max_events,
            max_books=args.max_books,
            min_arb_edge=args.min_edge,
        )
        _write_outputs(render_markdown(result), result.as_dict(), args.md_out, args.json_out)
        return 0
    if args.cmd == "farm":
        cfg = FarmConfig(
            bankroll_usdc=args.bankroll,
            holding_frac=args.holding_frac,
            max_markets=args.max_markets,
            min_daily_rate=args.min_daily,
            include_short_crypto=args.include_short_crypto,
            include_same_day=args.include_same_day,
            include_mentions=args.include_mentions,
            min_liquidity=args.min_liquidity,
            cross_check_kalshi=args.kalshi,
            reward_limit=args.reward_limit,
            quote=QuoteParams(),
        )
        plan = build_plan(cfg)
        _write_outputs(render_farm_markdown(plan), plan.as_dict(), args.md_out, args.json_out)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
