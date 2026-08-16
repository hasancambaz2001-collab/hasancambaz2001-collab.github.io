from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from whiskas.constants import USER_AGENT


def get_json(
    url: str,
    params: dict[str, Any] | None = None,
    *,
    timeout: float = 45.0,
    retries: int = 6,
    pause: float = 0.12,
) -> Any:
    if params:
        q = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{url}?{q}"
    last_err: Exception | None = None
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            time.sleep(pause)
            return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_err = exc
            if exc.code in {429, 500, 502, 503, 504} and attempt + 1 < retries:
                time.sleep(min(32.0, (2**attempt) * 0.75))
                continue
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            raise RuntimeError(f"HTTP {exc.code} {url}: {body[:400]}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_err = exc
            if attempt + 1 < retries:
                time.sleep(min(32.0, (2**attempt) * 0.75))
                continue
            raise
    raise RuntimeError(f"GET failed {url}: {last_err}")
