"""CLI:  python -m memebot {paper|live|record|replay|simulate|report} ..."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import time

from .config import load_config
from .engine import Engine
from .executor import LiveExecutor, PaperExecutor
from .feed import PumpPortalFeed, Recorder, ReplayFeed
from .journal import Journal, format_summary, load, summarize
from .risk import RiskManager


def _stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


async def run_live_feed(cfg, mode: str, record: str | None, data_dir: str) -> int:
    os.makedirs(data_dir, exist_ok=True)
    if mode == "live":
        if os.environ.get("MEMEBOT_LIVE_CONFIRM") != "YES":
            print("Live mode needs MEMEBOT_LIVE_CONFIRM=YES (and MEMEBOT_PRIVATE_KEY). Refusing.", file=sys.stderr)
            return 2
        ex = LiveExecutor(cfg.exec)
        bal = await ex.sol_balance()
        print(f"LIVE wallet {ex.pubkey[:6]}... balance {bal:.4f} SOL")
        if bal < cfg.risk.position_size_sol + 0.02:
            print("Balance too low for one position + fees. Refusing.", file=sys.stderr)
            return 2
        self_wallets = {ex.pubkey}
    else:
        ex = PaperExecutor(cfg.exec)
        self_wallets = set()
    recorder = Recorder(record) if record else None
    feed = PumpPortalFeed(cfg.exec.ws_url, recorder)
    journal = Journal(os.path.join(data_dir, f"journal-{mode}-{_stamp()}.jsonl"))
    eng = Engine(cfg, ex, journal, RiskManager(cfg.risk, data_dir), feed,
                 creators_path=os.path.join(data_dir, "creators.json"), self_wallets=self_wallets)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass

    async def consume():
        async for ev in feed.events():
            await eng.on_event(ev)
            if stop.is_set():
                break

    async def ticker():
        while not stop.is_set():
            await asyncio.sleep(1)
            await eng.tick(time.time())

    async def status():
        while not stop.is_set():
            await asyncio.sleep(60)
            logging.info("status open=%d tracked=%d stats=%s", len(eng.positions), len(eng.tokens), dict(eng.stats))

    tasks = [asyncio.create_task(c) for c in (consume(), ticker(), status())]
    await stop.wait()
    for t in tasks:
        t.cancel()
    print("Shutting down: flattening open positions...")
    await eng.flatten(time.time())
    eng.save_creators()
    journal.write("stats", **dict(eng.stats))
    journal.close()
    await ex.close()
    if recorder:
        recorder.close()
    print(format_summary(summarize(journal.rows), cfg.sol_usd))
    return 0


async def run_replay(cfg, paths, journal_path: str | None, quiet: bool = False):
    feed = ReplayFeed(*paths)
    journal = Journal(journal_path)
    eng = Engine(cfg, PaperExecutor(cfg.exec), journal, RiskManager(cfg.risk, cfg.data_dir), feed)
    last = 0.0
    async for ev in feed.events():
        await eng.on_event(ev)
        last = ev.ts
    await eng.flatten(last, "end_of_data")
    journal.write("stats", **dict(eng.stats))
    journal.close()
    s = summarize(journal.rows)
    if not quiet:
        print(format_summary(s, cfg.sol_usd))
        print("\nFunnel:", json.dumps(dict(sorted(eng.stats.items())), indent=1))
    return s, eng


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="memebot")
    ap.add_argument("-c", "--config", help="TOML config file")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("paper", "live"):
        p = sub.add_parser(name)
        p.add_argument("--record", help="also record raw stream to this JSONL")
    r = sub.add_parser("record", help="paper-trade and record the raw stream (data collection)")
    r.add_argument("out", nargs="?")
    rp = sub.add_parser("replay")
    rp.add_argument("files", nargs="+")
    rp.add_argument("--journal")
    sm = sub.add_parser("simulate", help="generate a synthetic market and replay it")
    sm.add_argument("--tokens", type=int, default=2000)
    sm.add_argument("--seed", type=int, default=1)
    sm.add_argument("--out", default="data/sim.jsonl")
    rep = sub.add_parser("report")
    rep.add_argument("journal")
    a = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO if a.verbose or a.cmd in ("paper", "live", "record") else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config(a.config)

    if a.cmd in ("paper", "live"):
        return asyncio.run(run_live_feed(cfg, a.cmd, a.record, cfg.data_dir))
    if a.cmd == "record":
        out = a.out or os.path.join(cfg.data_dir, f"stream-{_stamp()}.jsonl")
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        print(f"Recording to {out}")
        return asyncio.run(run_live_feed(cfg, "paper", out, cfg.data_dir))
    if a.cmd == "replay":
        asyncio.run(run_replay(cfg, a.files, a.journal))
        return 0
    if a.cmd == "simulate":
        from .sim import generate

        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        counts = generate(a.out, a.tokens, a.seed)
        print(f"Synthetic market -> {a.out}  archetypes={counts}")
        print("UYARI: sentetik veri. Bu sonuclar gercek piyasada edge oldugunu GOSTERMEZ.\n")
        asyncio.run(run_replay(cfg, [a.out], a.out.replace(".jsonl", "-journal.jsonl")))
        return 0
    if a.cmd == "report":
        print(format_summary(summarize(load(a.journal)), cfg.sol_usd))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
