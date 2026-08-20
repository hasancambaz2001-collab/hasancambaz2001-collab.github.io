#!/usr/bin/env python3
"""PMData range client. Key from env only. Never print the key.

python3 scripts/pmdata_client.py --from-ts 2026-08-14 --to-ts 2026-08-15 --asset btc --tf 5m

Writes data/pmdata/ via pyarrow. Reuses already-unlocked Day zips.
Does not unlock new calendar days. Post-08-14 only.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from whiskas.live_config import ensure_pmdata_env_file, load_pmdata_env
from whiskas.pmdata import (
    api_key_name,
    bbo_timeline_full,
    download_day,
    iter_day_parquets,
    parse_ts,
    regime_for_date,
)

OUT = ROOT / "data" / "pmdata"
DAY_CACHE = ROOT / "data" / "parquet" / "pmdata" / "day"
REGIME_CUTOFF = datetime(2026, 8, 14, tzinfo=timezone.utc)


def _parse_ts(text: str) -> datetime:
    return parse_ts(text)


def _days(start: datetime, end: datetime) -> list[str]:
    cur = start.date()
    last = end.date()
    out: list[str] = []
    while cur <= last:
        out.append(cur.isoformat())
        cur = cur + timedelta(days=1)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="PMData range pull. Never prints the key.")
    parser.add_argument("--from-ts", required=True)
    parser.add_argument("--to-ts", required=True)
    parser.add_argument("--asset", default="btc")
    parser.add_argument("--tf", default="5m")
    parser.add_argument("--type", dest="data_type", default="onchain_fills", choices=("l2", "trades", "onchain_fills"))
    parser.add_argument("--unlock-new-days", action="store_true")
    args = parser.parse_args()
    ensure_pmdata_env_file(ROOT / "configs" / ".env.pmdata")
    load_pmdata_env(ROOT / "configs" / ".env.pmdata")
    if not api_key_name():
        print(json.dumps({"ok": False, "reason": "no PMDATA_API_KEY"}))
        return 1
    start = _parse_ts(args.from_ts)
    end = _parse_ts(args.to_ts)
    if start < REGIME_CUTOFF:
        print(json.dumps({"ok": False, "reason": "pre_2026_08_14_DEBUG refused as truth"}))
        return 2
    series = f"{args.asset.strip().lower()}-{args.tf.strip().lower()}"
    tables = []
    used = []
    skipped = []
    day_rows: dict[str, int] = {}
    day_members: dict[str, int] = {}
    no_unlock = {"2026-08-16"}
    for day in _days(start, end):
        if day in no_unlock and not args.unlock_new_days:
            skipped.append(day)
            continue
        cached = DAY_CACHE / f"{series}_{args.data_type}_{day}.zip"
        if not cached.is_file() and not args.unlock_new_days:
            skipped.append(day)
            continue
        path = download_day(series, args.data_type, day, dest_dir=DAY_CACHE)
        for name, df in iter_day_parquets(path):
            if df is None or df.empty:
                continue
            if args.data_type == "l2":
                slim = bbo_timeline_full(df)
                if slim.empty:
                    continue
                tables.append(pa.Table.from_pandas(slim, preserve_index=False))
                day_rows[day] = day_rows.get(day, 0) + int(len(slim))
            else:
                tables.append(pa.Table.from_pandas(df, preserve_index=False))
                day_rows[day] = day_rows.get(day, 0) + int(len(df))
            day_members[day] = day_members.get(day, 0) + 1
        if day in day_rows:
            used.append({
                "day": day,
                "n_members": day_members[day],
                "rows": day_rows[day],
                "regime": regime_for_date(day),
            })
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / f"{series}_{args.data_type}_{start.date()}_{end.date()}.parquet"
    if tables:
        table = pa.concat_tables(tables, promote_options="default")
        pq.write_table(table, dest)
        nbytes = dest.stat().st_size
        nrows = table.num_rows
        if nbytes <= 0:
            dest.unlink(missing_ok=True)
            dest = None
            nbytes = 0
            nrows = 0
    else:
        dest.write_bytes(b"")
        nbytes = 0
        nrows = 0
        dest.unlink(missing_ok=True)
        dest = None
    summary = {
        "ok": dest is not None and nbytes > 0,
        "series": series,
        "type": args.data_type,
        "from_ts": start.isoformat(),
        "to_ts": end.isoformat(),
        "path": None if dest is None else str(dest),
        "bytes": nbytes,
        "rows": nrows,
        "days_used": used,
        "days_skipped_no_unlock": skipped,
        "key_env": api_key_name(),
        "wrote_via": "pyarrow",
        "new_days_unlocked": False,
    }
    (ROOT / "data" / "processed").mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "processed" / "pmdata_client.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))
    return 0 if dest is not None and nbytes > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
