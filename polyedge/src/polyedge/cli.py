"""CLI: python -m polyedge scan"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .report import render_markdown
from .scanners import run_scan


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="polyedge",
        description="Paper-only Polymarket scanners for protocol yield and structural arb.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    scan = sub.add_parser("scan", help="Run live Gamma + CLOB paper scan")
    scan.add_argument("--max-markets", type=int, default=1200)
    scan.add_argument("--max-events", type=int, default=40)
    scan.add_argument("--max-books", type=int, default=350)
    scan.add_argument("--min-edge", type=float, default=0.004, help="Min net edge after fees")
    scan.add_argument("--json-out", type=Path, default=None)
    scan.add_argument("--md-out", type=Path, default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "scan":
        result = run_scan(
            max_markets=args.max_markets,
            max_events=args.max_events,
            max_books=args.max_books,
            min_arb_edge=args.min_edge,
        )
        md = render_markdown(result)
        sys.stdout.write(md)
        if args.md_out:
            args.md_out.parent.mkdir(parents=True, exist_ok=True)
            args.md_out.write_text(md, encoding="utf-8")
        if args.json_out:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(
                json.dumps(result.as_dict(), indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
