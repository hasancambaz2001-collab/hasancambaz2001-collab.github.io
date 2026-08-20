from __future__ import annotations

import re

from whiskas.constants import BTC_5M_PREFIX, WINDOW_SECONDS

_SLUG_RE = re.compile(rf"^{re.escape(BTC_5M_PREFIX)}(\d+)$")


def parse_btc_5m_slug(slug: str | None) -> int | None:
    if not slug:
        return None
    m = _SLUG_RE.match(slug.strip())
    if not m:
        return None
    t0 = int(m.group(1))
    if t0 <= 0 or t0 % WINDOW_SECONDS != 0:
        return None
    return t0


def is_btc_5m(event_slug: str | None, slug: str | None = None) -> bool:
    return parse_btc_5m_slug(event_slug) is not None or parse_btc_5m_slug(slug) is not None


def window_slug(t0: int) -> str:
    return f"{BTC_5M_PREFIX}{t0}"
