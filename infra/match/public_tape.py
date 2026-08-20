"""Dump-native + live public trades. Old 5m may purge — prefer dump."""

from __future__ import annotations

from typing import Any

from whiskas.constants import DATA_API
from whiskas.http import get_json

COMPETITORS = {
    "mo-money": "0x32ed2e546b187ca15e2841edc82b22c713cf8ec3",
    "bosona": "0xc2ad03f79ca3f3c17d8c7de2612ce0c89b7d40ed",
    "06dc": "0x06dc51826bc524d9a83770e7de9dd7e005b04524",
    "whiskas": "0x3048d65321be3497164cdfc2996f94f98a2e7537",
}


def live_trades_for_slug(slug: str, *, limit: int = 50) -> list[dict[str, Any]]:
    try:
        rows = get_json(
            f"{DATA_API}/trades",
            {"eventSlug": slug, "limit": limit},
            timeout=15,
            retries=2,
            pause=0.05,
        )
    except Exception:
        return []
    return rows if isinstance(rows, list) else []


def dump_tape_for_slug(rows: list[dict[str, Any]], slug: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("type") or "") != "TRADE":
            continue
        ev = str(row.get("eventSlug") or row.get("slug") or "")
        if ev != slug and str(row.get("slug") or "") != slug:
            continue
        out.append(row)
    return out


def competitor_flow(rows: list[dict[str, Any]], slug: str) -> dict[str, int]:
    counts = {name: 0 for name in COMPETITORS}
    wallets = {w.lower(): n for n, w in COMPETITORS.items()}
    for row in dump_tape_for_slug(rows, slug):
        who = str(row.get("proxyWallet") or row.get("user") or "").lower()
        name = wallets.get(who)
        if name:
            counts[name] += 1
    return counts
