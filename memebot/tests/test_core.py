import asyncio
import os

import pytest

from memebot.config import load_config
from memebot.curve import INITIAL_V_SOL, INITIAL_V_TOKENS, buy_tokens_out, sell_sol_out
from memebot.engine import Engine
from memebot.events import Migration, NewToken, Trade, parse_pumpportal
from memebot.executor import PaperExecutor
from memebot.features import TokenState
from memebot.filters import evaluate
from memebot.journal import Journal, summarize
from memebot.risk import RiskManager
from memebot.sim import _Curve, generate


class TokenSim:
    """Drives one synthetic token through the real parser."""

    def __init__(self, t0=1000.0, dev_sol=0.5, mint="MINT1", dev="DEV"):
        self.t, self.mint, self.dev, self.c, self.bal = t0, mint, dev, _Curve(), {}
        tok = self.c.buy(dev_sol)
        self.bal[dev] = tok
        self.create = parse_pumpportal({"txType": "create", "mint": mint, "traderPublicKey": dev,
                                        "initialBuy": tok, "solAmount": dev_sol, "vSolInBondingCurve": self.c.vs,
                                        "vTokensInBondingCurve": self.c.vt, "marketCapSol": self.c.mcap,
                                        "name": "T", "symbol": "T"}, t0)

    def _msg(self, side, who, tok, sol):
        m = {"txType": side, "mint": self.mint, "traderPublicKey": who, "tokenAmount": tok, "solAmount": sol,
             "newTokenBalance": self.bal[who], "marketCapSol": self.c.mcap,
             "pool": "pump-amm" if self.c.amm else "pump"}
        if not self.c.amm:
            m.update(vSolInBondingCurve=self.c.vs, vTokensInBondingCurve=self.c.vt)
        return parse_pumpportal(m, self.t)

    def buy(self, who, sol, dt=1.0):
        self.t += dt
        tok = self.c.buy(sol)
        self.bal[who] = self.bal.get(who, 0) + tok
        return self._msg("buy", who, tok, sol)

    def sell(self, who, frac=1.0, dt=1.0):
        self.t += dt
        tok = self.bal.get(who, 0) * frac
        sol = self.c.sell(tok)
        self.bal[who] -= tok
        return self._msg("sell", who, tok, sol)


def relaxed_cfg(latency=0.0, **exits):
    return load_config(overrides={
        "filters": {"snipe_window_s": 1.0, "min_score": 3, "min_unique_buyers": 10, "min_new_buyers_60s": 5,
                    "min_net_inflow_sol_60s": 0.5, "max_single_buy_share": 0.5},
        "entry": {"min_age_s": 15, "min_mcap_sol": 30, "max_mcap_sol": 350},
        "exits": exits,
        "risk": {"max_entries_per_hour": 100},
        "exec": {"paper_latency_s": latency},
    })


def make_engine(cfg, tmp_path):
    return Engine(cfg, PaperExecutor(cfg.exec), Journal(None), RiskManager(cfg.risk, str(tmp_path)))


async def feed_organic(eng, ts, n=25, sol=0.6):
    await eng.on_event(ts.create)
    for i in range(n):
        await eng.on_event(ts.buy(f"W{i}", sol, dt=1.5))


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------- parsing / math
def test_parser_handles_all_message_kinds():
    assert isinstance(parse_pumpportal({"txType": "create", "mint": "m", "traderPublicKey": "d", "initialBuy": 1e7,
                                        "marketCapSol": 30}, 1.0), NewToken)
    t = parse_pumpportal({"txType": "buy", "mint": "m", "traderPublicKey": "x", "tokenAmount": "5", "solAmount": 0.1,
                          "vSolInBondingCurve": 31, "vTokensInBondingCurve": 1.0e9}, 2.0)
    assert isinstance(t, Trade) and t.mcap_sol == pytest.approx(31.0)
    assert isinstance(parse_pumpportal({"txType": "migrate", "mint": "m"}, 3.0), Migration)
    assert parse_pumpportal({"message": "Successfully subscribed"}, 4.0) is None


def test_curve_roundtrip_loses_money():
    tok = buy_tokens_out(INITIAL_V_SOL, INITIAL_V_TOKENS, 1.0)
    vs, vt = INITIAL_V_SOL + 1.0, INITIAL_V_TOKENS - tok
    assert sell_sol_out(vs, vt, tok) == pytest.approx(1.0, rel=1e-9)  # no fee in raw curve
    cfg = load_config()
    st = TokenState(TokenSim().create)
    ex = PaperExecutor(cfg.exec)
    assert ex.quote_sell(st, ex.pricer.tokens_for_sol(st, 1.0)) < 0.95  # fees + slippage bite


# ---------------------------------------------------------------- filters
def test_heavy_dev_buy_is_permanently_rejected():
    cfg = load_config()
    ts = TokenSim(dev_sol=15)
    st = TokenState(ts.create, cfg.filters.snipe_window_s)
    v = evaluate(st, ts.t + 5, cfg.filters, cfg.entry, 1)
    assert v.permanent_reject and v.reasons[0].startswith("dev_buy")


def test_sniper_bundle_is_rejected():
    cfg = load_config()
    ts = TokenSim()
    st = TokenState(ts.create, cfg.filters.snipe_window_s)
    for i in range(8):
        st.on_trade(ts.buy(f"S{i}", 2.5, dt=0.1))
    v = evaluate(st, ts.t + 5, cfg.filters, cfg.entry, 1)
    assert v.permanent_reject and v.reasons[0].startswith("snipers")


def test_serial_creator_rejected():
    cfg = load_config()
    ts = TokenSim()
    st = TokenState(ts.create)
    v = evaluate(st, ts.t + 5, cfg.filters, cfg.entry, creator_launches=10)
    assert v.permanent_reject and "serial_creator" in v.reasons[0]


# ---------------------------------------------------------------- exits
def test_principal_recovered_at_3x_then_trailing_exit(tmp_path):
    cfg = relaxed_cfg(breakeven_arm_multiple=0.0)
    eng = make_engine(cfg, tmp_path)
    ts = TokenSim()

    async def go():
        await feed_organic(eng, ts)
        assert ts.mint in eng.positions, eng.stats
        pos = eng.positions[ts.mint]
        cost, tok0 = pos.cost_sol, pos.tokens
        i = 0
        while not pos.recovered and i < 400:
            await eng.on_event(ts.buy(f"B{i}", 1.5))
            i += 1
        assert pos.recovered, "price ran but principal was never pulled"
        assert pos.realized_sol >= cost * 0.98
        sold_frac = 1 - pos.tokens / tok0
        assert 0.25 < sold_frac < 0.5, sold_frac   # ~1/3 of bag at 3x (+fees/slippage)
        # crash -> trailing stop closes the house-money remainder
        for j in range(i):
            await eng.on_event(ts.sell(f"B{j}", 1.0, dt=0.5))
            if pos.closed:
                break
        assert pos.closed and pos.pnl_sol > 0
        assert any(r.startswith("trailing_stop") or r.startswith("rug") for r in pos.exit_reasons)

    run(go())


def test_stop_loss_caps_loss(tmp_path):
    cfg = relaxed_cfg(breakeven_arm_multiple=0.0, rug_single_drop_pct=99.0, stop_loss_pct=25.0)
    eng = make_engine(cfg, tmp_path)
    ts = TokenSim()

    async def go():
        await feed_organic(eng, ts)
        pos = eng.positions[ts.mint]
        for i in range(25):
            await eng.on_event(ts.sell(f"W{i}", 1.0, dt=2))
            if pos.closed:
                break
        assert pos.closed
        assert any(r.startswith("stop_loss") for r in pos.exit_reasons)
        assert -0.5 < pos.pnl_sol / pos.cost_sol < -0.2

    run(go())


def test_dev_dump_triggers_rug_exit(tmp_path):
    cfg = relaxed_cfg()
    eng = make_engine(cfg, tmp_path)
    ts = TokenSim(dev_sol=1.5)

    async def go():
        await feed_organic(eng, ts)
        pos = eng.positions[ts.mint]
        await eng.on_event(ts.sell(ts.dev, 1.0))
        assert pos.closed and pos.exit_reasons[-1].startswith("rug:dev_sold")

    run(go())


def test_time_stop(tmp_path):
    cfg = relaxed_cfg(max_hold_before_recovery_s=120)
    eng = make_engine(cfg, tmp_path)
    ts = TokenSim()

    async def go():
        await feed_organic(eng, ts)
        pos = eng.positions[ts.mint]
        await eng.tick(ts.t + 121)
        assert pos.closed and pos.exit_reasons[-1] == "time_stop"

    run(go())


def test_latency_fills_after_the_insider_burst(tmp_path):
    """With latency the rug exit fills *after* the follow-up dump -> worse price than instant."""
    results = {}
    for lat in (0.0, 1.5):
        cfg = relaxed_cfg(latency=lat)
        eng = make_engine(cfg, tmp_path)
        ts = TokenSim(dev_sol=1.5)

        async def go():
            await feed_organic(eng, ts)
            await eng.tick(ts.t + 2)          # let a delayed entry fill
            pos = eng.positions[ts.mint]
            await eng.on_event(ts.sell(ts.dev, 1.0, dt=1.0))
            for i in range(10):              # insiders keep dumping inside the latency window
                await eng.on_event(ts.sell(f"W{i}", 1.0, dt=0.1))
            await eng.tick(ts.t + 5)
            assert pos.closed
            return pos.pnl_sol

        results[lat] = run(go())
    assert results[1.5] < results[0.0]


# ---------------------------------------------------------------- risk / safety
def test_kill_switch_blocks_entries(tmp_path):
    cfg = relaxed_cfg()
    (tmp_path / "STOP").write_text("")
    eng = make_engine(cfg, tmp_path)
    run(feed_organic(eng, TokenSim()))
    assert not eng.positions and eng.stats["risk_blocked:kill_switch"] == 1


def test_max_open_positions(tmp_path):
    cfg = relaxed_cfg()
    cfg.risk.max_open_positions = 1
    eng = make_engine(cfg, tmp_path)

    async def go():
        await feed_organic(eng, TokenSim(mint="A", dev="DA"))
        await feed_organic(eng, TokenSim(mint="B", dev="DB"))

    run(go())
    assert list(eng.positions) == ["A"]


def test_daily_loss_limit(tmp_path):
    cfg = relaxed_cfg()
    rm = RiskManager(cfg.risk, str(tmp_path))
    rm.on_close(100.0, -cfg.risk.max_daily_loss_sol)
    assert rm.can_enter(200.0, 0, 0.0) == (False, "daily_loss_limit")
    assert rm.can_enter(100.0 + 86401, 0, 0.0)[0]


def test_config_refuses_secrets(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text('private_key = "abc"\n')
    with pytest.raises(ValueError, match="never hold keys"):
        load_config(str(p))


def test_live_mode_requires_explicit_confirmation(monkeypatch, tmp_path):
    from memebot.__main__ import main

    monkeypatch.delenv("MEMEBOT_LIVE_CONFIRM", raising=False)
    monkeypatch.chdir(tmp_path)
    assert main(["live"]) == 2


# ---------------------------------------------------------------- end-to-end
def test_simulated_market_replay_is_consistent(tmp_path):
    from memebot.__main__ import run_replay

    path = str(tmp_path / "sim.jsonl")
    generate(path, n_tokens=300, seed=3)
    cfg = load_config(overrides={"data_dir": str(tmp_path)})
    s, eng = run(run_replay(cfg, [path], str(tmp_path / "j.jsonl"), quiet=True))
    assert not eng.positions  # everything flattened
    assert s.get("trades", 0) == eng.stats["entries"]
    for p in eng.closed:
        assert p.tokens == 0 and p.cost_sol > 0
    assert os.path.getsize(tmp_path / "j.jsonl") > 0
