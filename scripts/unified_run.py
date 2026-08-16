#!/usr/bin/env python3
"""Leader dump replay for the live-config pipeline. No live. No pair>1.

python3 scripts/unified_run.py --dump data/dumps/bosona_activity.json --leader bosona
python3 scripts/unified_run.py --dump data/dumps/mo-money_activity.json --leader mo-money
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.phase1_maker_mobo import WALLETS
from scripts.replay_mobo import COVER_MIN, replay_wallet
from whiskas.config import load_config
from whiskas.live_config import dump_jsonl_to_json, ensure_pmdata_env_file, load_activity, load_pmdata_env

PROC = ROOT / "data" / "processed"
REPORTS = ROOT / "data" / "reports"
DUMPS = ROOT / "data" / "dumps"
RAW = ROOT / "data" / "raw"
WALLETS_MAP = {name: addr for name, addr in WALLETS}


def resolve_dump(path: Path, leader: str) -> Path:
    if path.is_file():
        return path
    raw = RAW / f"mobo_{leader}_activity.jsonl"
    if raw.is_file():
        return dump_jsonl_to_json(raw, path)
    raise FileNotFoundError(f"missing dump {path} and raw {raw}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Unified leader replay. No live.")
    parser.add_argument("--dump", type=Path, required=True)
    parser.add_argument("--leader", required=True, choices=sorted(WALLETS_MAP))
    args = parser.parse_args()
    ensure_pmdata_env_file(ROOT / "configs" / ".env.pmdata")
    load_pmdata_env(ROOT / "configs" / ".env.pmdata")
    cfg = load_config(ROOT / "configs" / "unified.yaml")
    dump_path = resolve_dump(args.dump if args.dump.is_absolute() else ROOT / args.dump, args.leader)
    rows = load_activity(dump_path)
    wallet = WALLETS_MAP[args.leader]
    stats = replay_wallet(
        args.leader,
        wallet,
        rows,
        pair_max=float((cfg.get("paper") or {}).get("pair_max", 0.90)),
        clip=float((cfg.get("paper") or {}).get("clip", 10)),
        maker_only=True,
    )
    stats["dump"] = str(dump_path)
    stats["pair_gt_1_trade"] = False
    stats["live"] = False
    stats["generated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    PROC.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (PROC / f"unified_{args.leader}.json").write_text(json.dumps(stats, indent=2) + "\n")
    md = REPORTS / "UNIFIED.md"
    line = (
        f"- {args.leader} cover={stats['cover']:.4f} "
        f"({stats['n_cover']}/{stats['n_cheap']}) "
        f"{'PASS' if stats['passed'] else 'FAIL'} min={COVER_MIN} dump={dump_path.name}"
    )
    prev = md.read_text(encoding="utf-8") if md.is_file() else (
        "# UNIFIED\n\nTheir tape. No live. pair_gt_1_trade=false.\n\n"
    )
    key = f"- {args.leader} cover="
    lines = prev.splitlines()
    out = [ln for ln in lines if not ln.startswith(key)]
    out.append(line)
    md.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    print(json.dumps({
        "leader": args.leader,
        "cover": round(stats["cover"], 4),
        "n_cover": stats["n_cover"],
        "n_cheap": stats["n_cheap"],
        "passed": stats["passed"],
        "pair_gt_1_trade": False,
        "live": False,
        "dump": str(dump_path),
    }))
    return 0 if stats["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
