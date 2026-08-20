#!/usr/bin/env python3
"""PMData Day API + Slug API. Key from env. Never hardcode. No live.

Day (docs):
  GET https://api.pmdata.dev/polymarket/{series}/{type}/{series}_{type}_{date}.zip
  headers={"api_key": <env>}

Slug (docs / curl):
  GET https://api.pmdata.dev/download/{type}/{slug}.parquet
  pandas.read_parquet(..., storage_options={api_key, User-Agent})

--date 2026-08-01 is pre-08-14 DEBUG. Prefer --date 2026-08-14 or later.
Does not cover 06dc daily/monthly. Chainlink/TWAP is not S1.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from whiskas.pmdata import (
    api_key_name,
    day_url,
    download_day,
    download_slug,
    list_day_members,
    read_slug,
    regime_for_date,
    slug_url,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="PMData Day/Slug API. Key from env. No live.")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--mode", choices=("day", "slug"), default="day")
    parser.add_argument("--series", default="btc-5m", help="btc-5m, btc-15m, eth-5m, ...")
    parser.add_argument("--type", dest="data_type", default="onchain_fills", choices=("l2", "trades", "onchain_fills"))
    parser.add_argument("--date", dest="data_date", default="2026-08-15")
    parser.add_argument("--slug", default="")
    args = parser.parse_args()
    if not args.run:
        print(f"SCAFFOLD {Path(__file__).name} (pass --run). Needs PMDATA_API_KEY.", flush=True)
        return 0
    if not api_key_name():
        print(json.dumps({"ok": False, "reason": "no PMDATA_API_KEY"}))
        return 1
    if args.mode == "slug":
        slug = args.slug or "btc-updown-5m-1786869000"
        path = download_slug(args.data_type, slug, dest_dir=ROOT / "data" / "parquet" / "pmdata" / "slug" / args.data_type)
        df = read_slug(args.data_type, slug) if path is None else None
        n = 0 if path is None and df is None else (len(df) if df is not None else "cached")
        print(json.dumps({
            "ok": path is not None or df is not None,
            "mode": "slug",
            "url": slug_url(args.data_type, slug),
            "path": None if path is None else str(path),
            "n": n,
            "key_env": api_key_name(),
        }))
        return 0 if path is not None or df is not None else 1
    regime = regime_for_date(args.data_date)
    dest = ROOT / "data" / "parquet" / "pmdata" / "day"
    path = download_day(args.series, args.data_type, args.data_date, dest_dir=dest)
    names = list_day_members(path)
    print(json.dumps({
        "ok": True,
        "mode": "day",
        "url": day_url(args.series, args.data_type, args.data_date),
        "path": str(path),
        "bytes": path.stat().st_size,
        "n_members": len(names),
        "members_head": names[:8],
        "regime": regime,
        "l2_covers_06dc": False,
        "size_ok": False,
        "key_env": api_key_name(),
        "note": "pre-08-14 dates are DEBUG only. Day usage counts by unlocked calendar day.",
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
