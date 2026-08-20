from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from whiskas.constants import (
    ACTIVITY_LIMIT,
    ACTIVITY_OFFSET_MAX,
    CLOSED_POS_LIMIT,
    CLOSED_POS_OFFSET_MAX,
    DATA_API,
    WHISKAS_WALLET,
)
from whiskas.http import get_json


def activity_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("transactionHash"),
        row.get("type"),
        row.get("timestamp"),
        row.get("asset"),
        row.get("side"),
        row.get("size"),
        row.get("price"),
        row.get("outcomeIndex"),
        row.get("usdcSize"),
    )


def iter_activity(user: str = WHISKAS_WALLET) -> Iterator[dict[str, Any]]:
    """Page /activity past the offset=5000 cap using start/end windows.

    Official docs: each start/end window has its own offset budget (max 5000).
    sortDirection=ASC + start=1 reads from the beginning of the account.
    """
    start = 1
    seen: set[tuple[Any, ...]] = set()
    stall = 0
    while True:
        newest_in_window: int | None = None
        produced = 0
        offset = 0
        while offset <= ACTIVITY_OFFSET_MAX:
            rows = get_json(
                f"{DATA_API}/activity",
                {
                    "user": user,
                    "limit": ACTIVITY_LIMIT,
                    "offset": offset,
                    "start": start,
                    "sortBy": "TIMESTAMP",
                    "sortDirection": "ASC",
                },
            )
            if not isinstance(rows, list) or not rows:
                if produced == 0 and offset == 0:
                    return
                break
            for row in rows:
                ts = int(row.get("timestamp") or 0)
                newest_in_window = ts if newest_in_window is None else max(newest_in_window, ts)
                key = activity_key(row)
                if key in seen:
                    continue
                seen.add(key)
                produced += 1
                yield row
            if len(rows) < ACTIVITY_LIMIT:
                if produced == 0:
                    return
                break
            offset += ACTIVITY_LIMIT
            if offset > ACTIVITY_OFFSET_MAX:
                break
        if newest_in_window is None:
            return
        if produced == 0:
            stall += 1
            start = newest_in_window + 1
            if stall >= 3:
                return
            continue
        stall = 0
        start = newest_in_window
        if offset <= ACTIVITY_OFFSET_MAX and produced < ACTIVITY_LIMIT:
            return


def iter_closed_positions(user: str = WHISKAS_WALLET) -> Iterator[dict[str, Any]]:
    offset = 0
    while offset <= CLOSED_POS_OFFSET_MAX:
        rows = get_json(
            f"{DATA_API}/closed-positions",
            {
                "user": user,
                "limit": CLOSED_POS_LIMIT,
                "offset": offset,
                "sortBy": "TIMESTAMP",
                "sortDirection": "ASC",
            },
        )
        if not isinstance(rows, list) or not rows:
            return
        yield from rows
        if len(rows) < CLOSED_POS_LIMIT:
            return
        offset += CLOSED_POS_LIMIT


def write_jsonl(path: Path, rows: Iterator[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")
            n += 1
            if n % 1000 == 0:
                print(f"  wrote {n} rows -> {path.name}", flush=True)
    return n
