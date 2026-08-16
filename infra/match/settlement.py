"""Gamma settlement probe. Old 5m windows may be purged (0 is OK)."""

from __future__ import annotations

from typing import Any

from whiskas.http import get_json
from whiskas.constants import GAMMA_API


def gamma_market(slug: str) -> dict[str, Any] | None:
    try:
        rows = get_json(f"{GAMMA_API}/markets", {"slug": slug}, timeout=15, retries=2, pause=0.05)
    except Exception:
        return None
    if isinstance(rows, list) and rows:
        rec = rows[0]
        return rec if isinstance(rec, dict) else None
    if isinstance(rows, dict):
        return rows
    return None


def settlement_for_slug(slug: str) -> dict[str, Any]:
    m = gamma_market(slug)
    if not m:
        return {"slug": slug, "found": False, "outcome": None, "closed": None, "note": "purged_or_missing"}
    outcome = m.get("outcome") or m.get("umaResolutionStatus")
    closed = m.get("closed")
    return {
        "slug": slug,
        "found": True,
        "outcome": outcome,
        "closed": closed,
        "uma": m.get("umaResolutionStatus"),
    }
