"""Market data feeds: live PumpPortal websocket (with recorder) and JSONL replay."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncIterator, Optional

from .events import Event, parse_pumpportal

log = logging.getLogger("memebot.feed")


class Recorder:
    def __init__(self, path: str):
        self.fh = open(path, "a", buffering=1)

    def write(self, ts: float, msg: dict):
        self.fh.write(json.dumps({"ts": round(ts, 3), "msg": msg}) + "\n")

    def close(self):
        self.fh.close()


class PumpPortalFeed:
    """Single websocket connection (PumpPortal asks clients not to open many)."""

    def __init__(self, url: str, recorder: Optional[Recorder] = None, migrations: bool = True):
        self.url = url
        self.recorder = recorder
        self.migrations = migrations
        self.keys: set[str] = set()
        self.ws = None
        self._lock = asyncio.Lock()

    async def _send(self, payload: dict):
        if self.ws is not None:
            async with self._lock:
                try:
                    await self.ws.send(json.dumps(payload))
                except Exception as e:  # reconnect loop will resubscribe
                    log.warning("send failed: %s", e)

    async def subscribe(self, mints):
        new = [m for m in mints if m not in self.keys]
        if new:
            self.keys.update(new)
            await self._send({"method": "subscribeTokenTrade", "keys": new})

    async def unsubscribe(self, mints):
        old = [m for m in mints if m in self.keys]
        if old:
            self.keys.difference_update(old)
            await self._send({"method": "unsubscribeTokenTrade", "keys": old})

    async def events(self) -> AsyncIterator[Event]:
        import websockets

        backoff = 1.0
        while True:
            try:
                async with websockets.connect(self.url, ping_interval=20, max_size=2**22) as ws:
                    self.ws = ws
                    backoff = 1.0
                    await self._send({"method": "subscribeNewToken"})
                    if self.migrations:
                        await self._send({"method": "subscribeMigration"})
                    if self.keys:
                        await self._send({"method": "subscribeTokenTrade", "keys": list(self.keys)})
                    log.info("connected to %s (%d trade subs)", self.url, len(self.keys))
                    async for raw in ws:
                        ts = time.time()
                        try:
                            msg = json.loads(raw)
                        except ValueError:
                            continue
                        if self.recorder:
                            self.recorder.write(ts, msg)
                        ev = parse_pumpportal(msg, ts)
                        if ev is not None:
                            yield ev
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("feed error: %s; reconnecting in %.0fs", e, backoff)
            finally:
                self.ws = None
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)


class ReplayFeed:
    """Replays a recording made by Recorder (or by the simulator)."""

    def __init__(self, *paths: str):
        self.paths = paths

    async def subscribe(self, mints):
        pass

    async def unsubscribe(self, mints):
        pass

    async def events(self) -> AsyncIterator[Event]:
        for p in self.paths:
            with open(p) as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    ev = parse_pumpportal(row["msg"], row["ts"])
                    if ev is not None:
                        yield ev
