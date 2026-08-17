"""Tiny JSON HTTP helper (stdlib only)."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Optional


DEFAULT_HEADERS = {
    "User-Agent": "polyedge/0.1 (research scanner; +https://github.com)",
    "Accept": "application/json",
}


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: Optional[Any] = None,
    timeout: float = 30.0,
    retries: int = 3,
    extra_headers: Optional[dict[str, str]] = None,
) -> Any:
    body = None
    headers = dict(DEFAULT_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    last_err: Exception | None = None
    for attempt in range(retries):
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if not raw:
                    return None
                return json.loads(raw.decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_err = exc
            if isinstance(exc, urllib.error.HTTPError) and exc.code in (400, 401, 403, 404):
                raise
            time.sleep(0.4 * (2**attempt))
    raise RuntimeError(f"HTTP failed for {url}: {last_err}")
