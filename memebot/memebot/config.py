"""Strategy configuration. Defaults are *uncalibrated priors* - tune them with replay."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path


@dataclass
class FilterCfg:
    # --- hard red flags (any one => reject) ---
    max_dev_initial_buy_pct: float = 8.0      # dev's own buy at launch, % of supply
    snipe_window_s: float = 3.0               # "first blocks" window after create
    max_sniper_supply_pct: float = 15.0       # supply bought by non-dev wallets in that window
    max_top10_pct: float = 35.0               # top-10 wallets (excl. curve), % of supply
    max_dev_sold_pct: float = 50.0            # dev already dumped this much of their bag
    max_creator_launches: int = 3             # serial launcher wallet
    # --- soft signals (count how many pass) ---
    min_unique_buyers: int = 20
    min_buy_sell_ratio: float = 1.5           # buys/sells count, last 60s
    min_net_inflow_sol_60s: float = 1.0
    min_new_buyers_60s: int = 8
    max_single_buy_share: float = 0.20        # biggest single buy / all buy SOL
    min_mcap_momentum_60s: float = 1.15       # mcap now / mcap 60s ago
    min_score: int = 4                        # out of 6


@dataclass
class EntryCfg:
    mode: str = "curve"                       # curve | migration | both
    min_age_s: float = 60.0
    max_age_s: float = 900.0
    min_mcap_sol: float = 60.0
    max_mcap_sol: float = 350.0               # graduation is ~410 SOL mcap
    migration_wait_s: float = 600.0           # survive this long after migrating
    migration_min_hold_ratio: float = 0.8     # mcap now / mcap at migration
    migration_max_age_s: float = 3600.0
    observe_window_s: float = 1800.0          # stop tracking an un-entered token after this


@dataclass
class ExitCfg:
    recover_at_multiple: float = 3.0          # net proceeds of whole bag >= 3x cost => take principal out
    stop_loss_pct: float = 45.0               # before recovery
    breakeven_arm_multiple: float = 2.0       # once net value hit 2x, never let it go back below 1x (0 = off)
    max_hold_before_recovery_s: float = 1800.0
    rug_dev_sell_pct: float = 50.0            # dev sells this much of bag after our entry => exit
    rug_single_drop_pct: float = 35.0         # one sell crashes price this much => exit
    ladder: list = field(default_factory=lambda: [[10.0, 0.25], [30.0, 0.25], [100.0, 0.25]])
    trailing_drawdown_pct: float = 50.0       # after recovery, exit rest on this drawdown from peak
    max_hold_s: float = 86400.0


@dataclass
class RiskCfg:
    position_size_sol: float = 0.25
    max_open_positions: int = 4
    max_total_exposure_sol: float = 1.0       # sum of open (unrecovered) cost
    max_daily_loss_sol: float = 1.5           # rolling 24h realised loss => halt entries
    max_entries_per_hour: int = 6
    kill_switch_file: str = "STOP"            # create this file to halt new entries


@dataclass
class ExecCfg:
    fee_pct: float = 1.25                     # protocol + router fee per side, %
    priority_fee_sol: float = 0.0005          # per transaction
    slippage_pct: float = 15.0                # live: max tolerated
    paper_extra_slippage_pct: float = 2.0     # paper: adverse-selection penalty on top of curve impact
    paper_latency_s: float = 1.5              # paper: orders fill at the market state this many seconds later
    amm_depth_ratio: float = 0.15             # paper: est. pool SOL depth / mcap after migration
    rpc_url: str = "https://api.mainnet-beta.solana.com"
    trade_api_url: str = "https://pumpportal.fun/api/trade-local"
    ws_url: str = "wss://pumpportal.fun/api/data"


@dataclass
class Config:
    filters: FilterCfg = field(default_factory=FilterCfg)
    entry: EntryCfg = field(default_factory=EntryCfg)
    exits: ExitCfg = field(default_factory=ExitCfg)
    risk: RiskCfg = field(default_factory=RiskCfg)
    exec: ExecCfg = field(default_factory=ExecCfg)
    data_dir: str = "data"
    sol_usd: float = 150.0                    # display only


def _merge(obj, data: dict, path: str = ""):
    names = {f.name: f for f in fields(obj)}
    for k, v in data.items():
        if any(w in k.lower() for w in ("private", "secret", "seed")):
            raise ValueError("Config files must never hold keys/secrets; use the MEMEBOT_PRIVATE_KEY env var.")
        if k not in names:
            raise ValueError(f"unknown config key: {path}{k}")
        cur = getattr(obj, k)
        if is_dataclass(cur):
            if not isinstance(v, dict):
                raise ValueError(f"{path}{k} must be a table")
            _merge(cur, v, f"{path}{k}.")
        else:
            setattr(obj, k, type(cur)(v) if isinstance(cur, (int, float, str)) and not isinstance(cur, bool) else v)


def load_config(path: str | None = None, overrides: dict | None = None) -> Config:
    cfg = Config()
    if path:
        _merge(cfg, tomllib.loads(Path(path).read_text()))
    if overrides:
        _merge(cfg, overrides)
    if cfg.entry.mode not in ("curve", "migration", "both"):
        raise ValueError("entry.mode must be curve | migration | both")
    return cfg
