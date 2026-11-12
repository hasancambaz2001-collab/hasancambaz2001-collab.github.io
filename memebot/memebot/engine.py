"""Event-driven trading engine: state -> filters -> risk -> executor -> exits."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import Counter

from .config import Config
from .events import Event, Migration, NewToken, Trade
from .features import TokenState
from .filters import evaluate
from .journal import Journal
from .positions import Position, decide_exit
from .risk import RiskManager

log = logging.getLogger("memebot.engine")


class Engine:
    TICK_S = 1.0

    def __init__(self, cfg: Config, executor, journal: Journal, risk: RiskManager,
                 feed=None, creators_path: str | None = None, self_wallets: set[str] | None = None):
        self.cfg = cfg
        self.ex = executor
        self.journal = journal
        self.risk = risk
        self.feed = feed
        self.self_wallets = self_wallets or set()
        self.tokens: dict[str, TokenState] = {}
        self.rejected: set[str] = set()
        self.entered: set[str] = set()
        self.pending: set[str] = set()
        self.positions: dict[str, Position] = {}
        self.initial_tokens: dict[str, float] = {}
        self.closed: list[Position] = []
        self.stats: Counter = Counter()
        self.blocked_once: set[str] = set()
        self._last_tick = 0.0
        self._tasks: set[asyncio.Task] = set()
        self.latency = float(getattr(executor, "latency_s", 0.0) or 0.0) if getattr(executor, "instant", False) else 0.0
        self.deferred: list = []  # (due_ts, mint, factory) - simulated network latency
        self.creators_path = creators_path
        self.creator_launches: Counter = Counter()
        if creators_path and os.path.exists(creators_path):
            with open(creators_path) as fh:
                self.creator_launches.update(json.load(fh))

    # ------------------------------------------------------------------ events
    async def on_event(self, ev: Event) -> None:
        if self.deferred:
            await self._flush_due(ev.ts)
        if isinstance(ev, NewToken):
            await self._on_new(ev)
        elif isinstance(ev, Trade):
            st = self.tokens.get(ev.mint)
            if st is not None:
                st.on_trade(ev)
                await self._after_update(st, ev.ts)
        elif isinstance(ev, Migration):
            st = self.tokens.get(ev.mint)
            if st is not None:
                st.on_migration(ev)
                self.stats["migrations_seen"] += 1
                await self._after_update(st, ev.ts)
        if ev.ts - self._last_tick >= self.TICK_S:
            await self.tick(ev.ts)

    async def _on_new(self, ev: NewToken):
        if ev.mint in self.tokens or ev.mint in self.rejected:
            return
        self.stats["tokens_seen"] += 1
        if ev.creator:
            self.creator_launches[ev.creator] += 1
        self.tokens[ev.mint] = TokenState(ev, self.cfg.filters.snipe_window_s)
        await self._sub([ev.mint])

    async def _after_update(self, st: TokenState, now: float):
        if st.mint in self.positions:
            await self._manage(st, now)
        else:
            await self._maybe_enter(st, now)

    async def tick(self, now: float) -> None:
        self._last_tick = now
        if self.deferred:
            await self._flush_due(now)
        for mint in list(self.positions):
            st = self.tokens.get(mint)
            if st is not None:
                await self._manage(st, now)
        drop = [m for m, st in self.tokens.items() if not self._keep(st, now)]
        for m in drop:
            del self.tokens[m]
        if drop:
            await self._unsub(drop)

    def _keep(self, st: TokenState, now: float) -> bool:
        if st.mint in self.positions or st.mint in self.pending:
            return True
        ec = self.cfg.entry
        if st.migrated_ts is not None and ec.mode in ("migration", "both") and st.mint not in self.entered:
            return now - st.migrated_ts <= ec.migration_max_age_s
        return now - st.created_ts <= ec.observe_window_s

    # ------------------------------------------------------------------ entries
    async def _maybe_enter(self, st: TokenState, now: float):
        m = st.mint
        if m in self.entered or m in self.pending or m in self.rejected:
            return
        v = evaluate(st, now, self.cfg.filters, self.cfg.entry,
                     self.creator_launches.get(st.creator, 0), self.self_wallets)
        if v.permanent_reject:
            self.rejected.add(m)
            self.stats["rejected:" + v.reasons[0].split(" ")[0]] += 1
            self.tokens.pop(m, None)
            await self._unsub([m])
            return
        if not v.enter:
            return
        ok, why = self.risk.can_enter(now, len(self.positions), self._at_risk())
        if not ok:
            if m not in self.blocked_once:
                self.blocked_once.add(m)
                self.stats["risk_blocked:" + why] += 1
            return
        self.entered.add(m)
        snap = st.snapshot(now)
        await self._run(m, lambda t: self._do_buy(st, t, snap, v.signals), now)

    async def _do_buy(self, st: TokenState, now: float, snap: dict, signals: dict):
        size = self.cfg.risk.position_size_sol
        fill = await self.ex.buy(st, size, now)
        if fill is None:
            self.stats["buy_failed"] += 1
            self.journal.write("buy_failed", mint=st.mint, ts=now)
            return
        pos = Position(st.mint, st.symbol, now, fill.sol, fill.tokens, entry_signals=signals,
                       peak_price=st.price, dev_sold_at_entry=st.dev_sold_tokens)
        pos.fills.append(fill)
        self.positions[st.mint] = pos
        self.initial_tokens[st.mint] = fill.tokens
        self.risk.on_entry(now)
        self.stats["entries"] += 1
        self.journal.write("entry", mint=st.mint, symbol=st.symbol, ts=now, cost_sol=fill.sol,
                           tokens=fill.tokens, price=fill.price, features=snap, signals=signals)
        log.info("ENTRY %s %s cost=%.4f SOL mcap=%.0f SOL", st.symbol, st.mint[:8], fill.sol, st.mcap)

    # ------------------------------------------------------------------ exits
    async def _manage(self, st: TokenState, now: float):
        pos = self.positions.get(st.mint)
        if pos is None or st.mint in self.pending:
            return
        order = decide_exit(pos, st, now, self.cfg.exits, self.ex.quote_sell, self.initial_tokens[st.mint])
        if order is None:
            return
        await self._run(st.mint, lambda t: self._do_sell(st, pos, order, t), now)

    async def _do_sell(self, st, pos: Position, order, now: float):
        fill = await self.ex.sell(st, order.tokens, order.reason, now)
        if fill is None or fill.tokens <= 0:
            self.stats["sell_failed"] += 1
            self.journal.write("sell_failed", mint=pos.mint, ts=now, reason=order.reason)
            return
        pos.apply_sell(fill)
        if order.kind == "recover" and pos.realized_sol >= pos.cost_sol * 0.98:
            pos.recovered, pos.recovered_ts = True, now
            self.stats["principal_recovered"] += 1
        elif order.kind == "ladder":
            pos.ladder_idx += 1
        self.journal.write("exit_fill", mint=pos.mint, symbol=pos.symbol, ts=now, reason=order.reason,
                           sol=fill.sol, tokens=fill.tokens, remaining=pos.tokens, realized=pos.realized_sol)
        log.info("SELL %s %s %s got=%.4f SOL realised=%.4f/%.4f", pos.symbol, pos.mint[:8], order.reason,
                 fill.sol, pos.realized_sol, pos.cost_sol)
        if pos.closed:
            self._finalize(pos, now)
            await self._unsub([pos.mint])

    def _finalize(self, pos: Position, now: float):
        self.positions.pop(pos.mint, None)
        self.closed.append(pos)
        self.risk.on_close(now, pos.pnl_sol)
        self.journal.write("close", mint=pos.mint, symbol=pos.symbol, opened_ts=pos.opened_ts, closed_ts=now,
                           hold_s=round(now - pos.opened_ts, 1), cost_sol=pos.cost_sol, realized_sol=pos.realized_sol,
                           pnl_sol=pos.pnl_sol, multiple=pos.realized_sol / pos.cost_sol if pos.cost_sol else 0,
                           recovered=pos.recovered, peak_net_multiple=round(pos.peak_net_multiple, 3),
                           exit_reasons=pos.exit_reasons, entry_signals=pos.entry_signals)

    async def flatten(self, now: float, reason: str = "shutdown"):
        """Exit everything (used on shutdown / end of replay)."""
        await self._flush_due(float("inf"))
        for mint, pos in list(self.positions.items()):
            st = self.tokens.get(mint)
            if st is None:
                continue
            fill = await self.ex.sell(st, pos.tokens, reason, now)
            if fill:
                pos.apply_sell(fill)
                if not pos.closed:
                    pos.closed_ts = now
                self._finalize(pos, now)

    # ------------------------------------------------------------------ plumbing
    def _at_risk(self) -> float:
        return sum(max(0.0, p.cost_sol - p.realized_sol) for p in self.positions.values() if not p.recovered)

    async def _run(self, mint: str, factory, now: float):
        """factory(fill_ts) -> coroutine. Paper: optionally delayed by `latency`. Live: background task."""
        self.pending.add(mint)
        if getattr(self.ex, "instant", False):
            if self.latency > 0:
                self.deferred.append((now + self.latency, mint, factory))
                return
            try:
                await factory(now)
            finally:
                self.pending.discard(mint)
            return
        coro = factory(now)

        async def guarded():
            try:
                await coro
            except Exception:  # never let one order kill the engine
                log.exception("order task failed for %s", mint)
            finally:
                self.pending.discard(mint)

        t = asyncio.create_task(guarded())
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)

    async def _flush_due(self, now: float):
        due = sorted((d for d in self.deferred if d[0] <= now), key=lambda d: d[0])
        if not due:
            return
        self.deferred = [d for d in self.deferred if d[0] > now]
        for ts, mint, factory in due:
            try:
                await factory(ts)
            finally:
                self.pending.discard(mint)

    async def _sub(self, mints):
        if self.feed is not None:
            await self.feed.subscribe(mints)

    async def _unsub(self, mints):
        if self.feed is not None:
            await self.feed.unsubscribe(mints)

    def save_creators(self):
        if self.creators_path:
            os.makedirs(os.path.dirname(self.creators_path) or ".", exist_ok=True)
            top = dict(self.creator_launches.most_common(200_000))
            with open(self.creators_path, "w") as fh:
                json.dump(top, fh)
