"""Order execution: a realistic paper simulator and a live PumpPortal/Solana executor."""
from __future__ import annotations

import asyncio
import base64
import logging
import os
from typing import Optional

from .config import ExecCfg
from .curve import buy_tokens_out, sell_sol_out
from .features import TokenState
from .positions import Fill

log = logging.getLogger("memebot.exec")


class Pricer:
    """Fee/slippage-aware quotes. Bonding curve math while on the curve,
    a constant-product estimate (depth = mcap * amm_depth_ratio) after migration."""

    def __init__(self, cfg: ExecCfg, extra_slip_pct: float):
        self.cfg = cfg
        self.extra = extra_slip_pct / 100

    def _reserves(self, st: TokenState):
        if st.on_curve:
            return st.v_sol, st.v_tokens
        depth = max(st.mcap * self.cfg.amm_depth_ratio, 1e-9)
        return depth, depth / max(st.price, 1e-18)

    def tokens_for_sol(self, st: TokenState, sol: float) -> float:
        fee = self.cfg.fee_pct / 100
        net_in = sol * (1 - fee) - self.cfg.priority_fee_sol
        if net_in <= 0:
            return 0.0
        vs, vt = self._reserves(st)
        return buy_tokens_out(vs, vt, net_in) * (1 - self.extra)

    def quote_sell(self, st: TokenState, tokens: float) -> float:
        if tokens <= 0:
            return 0.0
        vs, vt = self._reserves(st)
        gross = sell_sol_out(vs, vt, tokens)
        net = gross * (1 - self.cfg.fee_pct / 100) * (1 - self.extra) - self.cfg.priority_fee_sol
        return max(0.0, net)


class PaperExecutor:
    instant = True

    def __init__(self, cfg: ExecCfg):
        self.pricer = Pricer(cfg, cfg.paper_extra_slippage_pct)
        self.latency_s = cfg.paper_latency_s

    def quote_sell(self, st: TokenState, tokens: float) -> float:
        return self.pricer.quote_sell(st, tokens)

    async def buy(self, st: TokenState, sol: float, now: float) -> Optional[Fill]:
        tokens = self.pricer.tokens_for_sol(st, sol)
        if tokens <= 0:
            return None
        return Fill(now, "buy", sol, tokens, "entry")

    async def sell(self, st: TokenState, tokens: float, reason: str, now: float) -> Optional[Fill]:
        return Fill(now, "sell", self.pricer.quote_sell(st, tokens), tokens, reason)

    async def close(self):
        pass


class LiveExecutor:
    """Builds the tx via PumpPortal's local-transaction API, signs locally, sends via your RPC.

    The private key is read ONLY from the MEMEBOT_PRIVATE_KEY env var (base58) and never logged.
    Fills are reconciled from on-chain balance deltas, not from quotes.
    NOTE: verify the trade-local request fields against PumpPortal's current docs before going live.
    """

    instant = False

    def __init__(self, cfg: ExecCfg):
        import httpx
        from solders.keypair import Keypair

        key = os.environ.get("MEMEBOT_PRIVATE_KEY", "").strip()
        if not key:
            raise RuntimeError("MEMEBOT_PRIVATE_KEY env var is not set")
        self.kp = Keypair.from_base58_string(key)
        del key
        self.pubkey = str(self.kp.pubkey())
        self.cfg = cfg
        self.pricer = Pricer(cfg, 0.0)
        self.http = httpx.AsyncClient(timeout=20)

    def quote_sell(self, st: TokenState, tokens: float) -> float:
        return self.pricer.quote_sell(st, tokens)

    async def _rpc(self, method: str, params: list):
        r = await self.http.post(self.cfg.rpc_url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        r.raise_for_status()
        j = r.json()
        if "error" in j:
            raise RuntimeError(f"rpc {method}: {j['error']}")
        return j["result"]

    async def sol_balance(self) -> float:
        return (await self._rpc("getBalance", [self.pubkey, {"commitment": "confirmed"}]))["value"] / 1e9

    async def token_balance(self, mint: str) -> float:
        res = await self._rpc("getTokenAccountsByOwner",
                              [self.pubkey, {"mint": mint}, {"encoding": "jsonParsed", "commitment": "confirmed"}])
        total = 0.0
        for acc in res.get("value", []):
            amt = acc["account"]["data"]["parsed"]["info"]["tokenAmount"]
            total += float(amt.get("uiAmount") or 0.0)
        return total

    async def _trade(self, action: str, mint: str, amount, in_sol: bool) -> bool:
        from solders.transaction import VersionedTransaction

        r = await self.http.post(self.cfg.trade_api_url, data={
            "publicKey": self.pubkey,
            "action": action,
            "mint": mint,
            "amount": amount,
            "denominatedInSol": "true" if in_sol else "false",
            "slippage": self.cfg.slippage_pct,
            "priorityFee": self.cfg.priority_fee_sol,
            "pool": "auto",
        })
        if r.status_code != 200:
            log.error("trade-local %s %s failed: %s %s", action, mint, r.status_code, r.text[:200])
            return False
        unsigned = VersionedTransaction.from_bytes(r.content)
        tx = VersionedTransaction(unsigned.message, [self.kp])
        sig = await self._rpc("sendTransaction", [base64.b64encode(bytes(tx)).decode(),
                                                  {"encoding": "base64", "skipPreflight": True, "maxRetries": 3}])
        log.info("%s %s sent sig=%s", action, mint, sig)
        for _ in range(45):
            await asyncio.sleep(1)
            st = (await self._rpc("getSignatureStatuses", [[sig]]))["value"][0]
            if st and st.get("confirmationStatus") in ("confirmed", "finalized"):
                if st.get("err"):
                    log.error("tx %s failed on-chain: %s", sig, st["err"])
                    return False
                return True
        log.error("tx %s not confirmed in time", sig)
        return False

    async def buy(self, st: TokenState, sol: float, now: float) -> Optional[Fill]:
        sol0, tok0 = await self.sol_balance(), await self.token_balance(st.mint)
        if not await self._trade("buy", st.mint, sol, True):
            return None
        sol1, tok1 = await self.sol_balance(), await self.token_balance(st.mint)
        got = tok1 - tok0
        if got <= 0:
            return None
        return Fill(now, "buy", max(sol0 - sol1, 0.0), got, "entry")

    async def sell(self, st: TokenState, tokens: float, reason: str, now: float) -> Optional[Fill]:
        sol0, tok0 = await self.sol_balance(), await self.token_balance(st.mint)
        amt = "100%" if tokens >= tok0 * 0.999 else round(tokens, 6)
        if not await self._trade("sell", st.mint, amt, False):
            return None
        sol1, tok1 = await self.sol_balance(), await self.token_balance(st.mint)
        return Fill(now, "sell", max(sol1 - sol0, 0.0), max(tok0 - tok1, 0.0), reason)

    async def close(self):
        await self.http.aclose()
