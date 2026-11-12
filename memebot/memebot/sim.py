"""Synthetic pump.fun market for plumbing tests and demos.

Emits PumpPortal-shaped messages so the exact same parse/replay path is exercised.
THE ARCHETYPE MIX IS MADE UP. Results on synthetic data say nothing about real edge;
use recorded live data (`memebot record`) for any performance claim.
"""
from __future__ import annotations

import heapq
import json
import random
import string

from .curve import INITIAL_V_SOL, INITIAL_V_TOKENS, apply_buy, apply_sell, mcap_sol
from .events import TOTAL_SUPPLY

GRADUATION_V_SOL = 115.0  # ~85 real SOL raised

DEFAULT_MIX = {"dead": 0.74, "rug": 0.15, "pump_dump": 0.10, "runner": 0.01}


def _addr(rng: random.Random) -> str:
    return "".join(rng.choices(string.ascii_letters + string.digits, k=44))


class _Curve:
    def __init__(self):
        self.vs, self.vt = INITIAL_V_SOL, INITIAL_V_TOKENS
        self.amm = None  # (S, T) after migration

    @property
    def mcap(self):
        if self.amm:
            s, t = self.amm
            return s / t * TOTAL_SUPPLY
        return mcap_sol(self.vs, self.vt)

    def buy(self, sol):
        if self.amm:
            s, t = self.amm
            out = t - s * t / (s + sol)
            self.amm = (s + sol, t - out)
            return out
        self.vs, self.vt, out = apply_buy(self.vs, self.vt, sol)
        return out

    def sell(self, tokens):
        if self.amm:
            s, t = self.amm
            out = s - s * t / (t + tokens)
            self.amm = (s - out, t + tokens)
            return out
        self.vs, self.vt, out = apply_sell(self.vs, self.vt, tokens)
        return out


def simulate_token(rng: random.Random, t0: float, kind: str) -> list[tuple[float, dict]]:
    mint = _addr(rng)[:43] + "p"
    dev = _addr(rng)
    c = _Curve()
    out: list[tuple[float, dict]] = []
    bal: dict[str, float] = {}

    dev_sol = rng.uniform(6, 20) if kind == "rug" and rng.random() < 0.5 else rng.uniform(0.2, 2.0)
    dev_tok = c.buy(dev_sol)
    bal[dev] = dev_tok
    out.append((t0, {"txType": "create", "mint": mint, "traderPublicKey": dev, "initialBuy": dev_tok,
                     "solAmount": dev_sol, "vSolInBondingCurve": c.vs, "vTokensInBondingCurve": c.vt,
                     "marketCapSol": c.mcap, "name": f"SIM {kind}", "symbol": kind[:4].upper(), "pool": "pump"}))
    holders = [dev]

    def trade(ts, who, side, amount):
        if c.amm is None and c.vs >= GRADUATION_V_SOL:
            return False
        if side == "buy":
            tok = c.buy(amount)
            sol = amount
            bal[who] = bal.get(who, 0.0) + tok
            if who not in holders:
                holders.append(who)
        else:
            tok = min(amount, bal.get(who, 0.0))
            if tok <= 0:
                return True
            sol = c.sell(tok)
            bal[who] -= tok
        msg = {"txType": side, "mint": mint, "traderPublicKey": who, "tokenAmount": tok, "solAmount": sol,
               "newTokenBalance": bal[who], "marketCapSol": c.mcap, "pool": "pump-amm" if c.amm else "pump"}
        if not c.amm:
            msg.update(vSolInBondingCurve=c.vs, vTokensInBondingCurve=c.vt)
        out.append((ts, msg))
        return True

    def migrate(ts):
        s = c.vs - INITIAL_V_SOL
        c.amm = (s, s / (c.mcap / TOTAL_SUPPLY))
        out.append((ts, {"txType": "migrate", "mint": mint, "pool": "pump-amm"}))

    t = t0
    if kind == "rug" or rng.random() < 0.1:  # snipers / bundle
        for _ in range(rng.randint(4, 10)):
            trade(t + rng.uniform(0.2, 2.0), _addr(rng), "buy", rng.uniform(0.5, 3.0))
        out.sort(key=lambda x: x[0])
        t = out[-1][0]

    if kind == "dead":
        for _ in range(rng.randint(3, 30)):
            t += rng.expovariate(1 / 8)
            if rng.random() < 0.55 and len(holders) > 1:
                w = rng.choice(holders[1:])
                trade(t, w, "sell", bal.get(w, 0) * rng.uniform(0.5, 1))
            else:
                trade(t, _addr(rng), "buy", rng.lognormvariate(-1.5, 0.8))
        return out

    # organic-looking accumulation phase
    # pump tops are unpredictable: most die well before a 3x from a typical entry
    target = {"rug": rng.uniform(55, 160),
              "pump_dump": min(390.0, 55 * rng.lognormvariate(0.5, 0.6)),
              "runner": 1e9}[kind]
    buyers_pool = [_addr(rng) for _ in range(rng.randint(40, 200))]
    # hidden insiders: fresh wallets that buy *after* the snipe window and look like retail
    insiders = [_addr(rng) for _ in range(rng.randint(5, 15))] if kind in ("rug", "pump_dump") else []
    while c.mcap < target and t - t0 < 1500:
        t += rng.expovariate(1 / 2.5)
        if insiders and rng.random() < 0.3:
            ok = trade(t, rng.choice(insiders), "buy", rng.lognormvariate(-0.3, 0.5))
        elif rng.random() < 0.25 and len(holders) > 2:
            w = rng.choice(holders[1:])
            ok = trade(t, w, "sell", bal.get(w, 0) * rng.uniform(0.2, 1))
        else:
            ok = trade(t, rng.choice(buyers_pool), "buy", rng.lognormvariate(-0.9, 0.7))
        if not ok:
            migrate(t + 1)
            t += 1
            break

    if kind in ("rug", "pump_dump"):
        t += rng.uniform(5, 60)
        # coordinated dump: insiders hit the bid within ~a second, dev (if rug) after them
        for w in insiders:
            t += rng.expovariate(1 / 0.15)
            trade(t, w, "sell", bal.get(w, 0))
        if kind == "rug":
            t += rng.uniform(0.2, 3)
            trade(t, dev, "sell", bal[dev])
        # retail panic
        for w in sorted(holders, key=lambda h: -bal.get(h, 0))[:15]:
            t += rng.expovariate(1 / 4)
            trade(t, w, "sell", bal.get(w, 0) * rng.uniform(0.5, 1.0))
        return out

    # runner: post-migration trend with random peak, then bleed
    if c.amm is None:
        return out
    peak = c.mcap * rng.lognormvariate(1.2, 1.0)
    while c.mcap < peak and t - t0 < 20000:
        t += rng.expovariate(1 / 1.5)
        if rng.random() < 0.3 and len(holders) > 2:
            w = rng.choice(holders[1:])
            trade(t, w, "sell", bal.get(w, 0) * rng.uniform(0.1, 0.6))
        else:
            trade(t, _addr(rng) if rng.random() < 0.7 else rng.choice(buyers_pool), "buy",
                  rng.lognormvariate(0.0, 0.9))
    floor = c.mcap * rng.uniform(0.05, 0.3)
    while c.mcap > floor and t - t0 < 40000:
        t += rng.expovariate(1 / 2)
        w = rng.choice(holders)
        if bal.get(w, 0) > 0:
            trade(t, w, "sell", bal[w] * rng.uniform(0.3, 1))
        elif rng.random() < 0.2:
            trade(t, _addr(rng), "buy", rng.lognormvariate(-0.5, 0.7))
        if all(bal.get(h, 0) <= 0 for h in holders):
            break
    return out


def generate(path: str, n_tokens: int = 500, seed: int = 1, launches_per_min: float = 20.0,
             mix: dict | None = None) -> dict:
    rng = random.Random(seed)
    mix = mix or DEFAULT_MIX
    kinds, weights = zip(*mix.items())
    heap: list = []
    counts: dict[str, int] = {}
    t = 1_700_000_000.0
    for i in range(n_tokens):
        t += rng.expovariate(launches_per_min / 60)
        k = rng.choices(kinds, weights)[0]
        counts[k] = counts.get(k, 0) + 1
        for ts, msg in simulate_token(rng, t, k):
            heapq.heappush(heap, (ts, i, len(heap), msg))
    with open(path, "w") as fh:
        while heap:
            ts, _, _, msg = heapq.heappop(heap)
            fh.write(json.dumps({"ts": round(ts, 3), "msg": msg}) + "\n")
    return counts
