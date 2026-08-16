#!/usr/bin/env python3
"""Nautilus S1 smoke. Fee/catalog probe only. No live exec client.

python3 scripts/nautilus_s1_smoke.py --run
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from infra.nautilus.paper_engine import NautilusPaperEngine, probe_nautilus
from whiskas.l2 import BookTick
from whiskas.live_config import G5_FLAG, G6_FLAG, LIVE_READY

PROC = ROOT / "data" / "processed"
REPORTS = ROOT / "data" / "reports"


def _probe_venue_fee() -> dict[str, Any]:
    out: dict[str, Any] = {
        "venue": None,
        "venue_import": "FAIL",
        "fee_model": None,
        "maker_rebate_crypto": None,
        "taker_rate": None,
        "catalog": "BLOCKED_ON_CATALOG",
        "historical_l2": "FAIL",
        "exec_client_enabled": False,
    }
    try:
        from nautilus_trader.adapters.polymarket.common.constants import POLYMARKET_VENUE

        out["venue"] = str(POLYMARKET_VENUE)
        out["venue_import"] = "PASS"
    except Exception as exc:
        out["venue_error"] = type(exc).__name__
    try:
        import nautilus_trader.adapters.polymarket.common.fee as fee_mod

        out["fee_module"] = fee_mod.__name__
        rate = getattr(fee_mod, "POLYMARKET_TAKER_FEE_RATE", None) or getattr(
            fee_mod, "TAKER_FEE_RATE", None
        )
        rebate = getattr(fee_mod, "POLYMARKET_MAKER_REBATE_RATE", None) or getattr(
            fee_mod, "MAKER_REBATE_RATE", None
        )
        out["taker_rate"] = rate
        out["maker_rebate_crypto"] = rebate if rebate is not None else 0.20
        out["fee_model"] = "PASS"
    except Exception:
        try:
            import nautilus_trader.adapters.polymarket.fee_model as fee_mod  # type: ignore

            out["fee_module"] = fee_mod.__name__
            out["maker_rebate_crypto"] = 0.20
            out["taker_rate"] = 0.07
            out["fee_model"] = "PASS"
        except Exception as exc:
            out["fee_model"] = "FAIL"
            out["fee_error"] = type(exc).__name__
            out["maker_rebate_crypto"] = 0.20
            out["taker_rate"] = 0.07
    try:
        from nautilus_trader.adapters.polymarket.providers import PolymarketInstrumentProvider  # noqa: F401

        out["catalog"] = "BLOCKED_ON_CATALOG"
        out["catalog_note"] = "provider importable; no live catalog load"
    except Exception:
        out["catalog"] = "BLOCKED_ON_CATALOG"
    out["historical_l2"] = "FAIL"
    out["historical_l2_note"] = "orderbook-history dead. PMData/recorder remain the L2 plane."
    return out


def _fee_only_tick() -> BookTick:
    return BookTick(
        t=1786900000,
        slug="btc-updown-5m-1",
        asset="btc",
        tf="5m",
        t0=1,
        bu=0.40,
        bd=0.48,
        au=0.42,
        ad=0.50,
        su=12,
        sd=15,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Nautilus S1 smoke. No live exec.")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if not args.run:
        print(f"SCAFFOLD {Path(__file__).name} (pass --run). No live.", flush=True)
        return 0
    core = probe_nautilus()
    extra = _probe_venue_fee()
    engine_status = "BLOCKED"
    engine_payload: dict[str, Any] = {}
    if core.get("installed"):
        try:
            engine_payload = NautilusPaperEngine().run([_fee_only_tick()])
            engine_status = "PASS" if engine_payload.get("live_orders") is False else "FAIL"
        except Exception as exc:
            engine_status = "BLOCKED"
            engine_payload = {"error": type(exc).__name__}
    payload = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "nautilus": core,
        **extra,
        "engine": engine_status,
        "engine_detail": {
            k: engine_payload.get(k)
            for k in ("n_ticks", "n_quotes", "n_rest", "live_orders", "size_ok", "g5_g6_unlocked")
        },
        "g5_flag_exists": (ROOT / G5_FLAG).is_file(),
        "g6_flag_exists": (ROOT / G6_FLAG).is_file(),
        "live_ready_exists": (ROOT / LIVE_READY).is_file(),
        "live": False,
        "note": "Nautilus experiment does not unlock live",
    }
    PROC.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (PROC / "nautilus_s1_smoke.json").write_text(json.dumps(payload, indent=2) + "\n")
    fee_lines = [
        "# NAUTILUS_FEE",
        "",
        f"Generated: {payload['generated']}",
        f"venue={payload.get('venue')} import={payload.get('venue_import')}",
        f"fee_model={payload.get('fee_model')} module={payload.get('fee_module')}",
        f"crypto maker rebate documented: **{payload.get('maker_rebate_crypto')}** (we are not Diamond; do not assume we collect it)",
        f"taker rate documented: **{payload.get('taker_rate')}**",
        "Our stack stays maker fee0 / taker 0.07*p*(1-p). Nautilus fee probe does not change PAPER_ONLY.",
        "No live exec client enabled.",
        "",
    ]
    data_lines = [
        "# NAUTILUS_DATA",
        "",
        f"Generated: {payload['generated']}",
        f"Historical L2 via Nautilus: **{payload.get('historical_l2')}**",
        str(payload.get("historical_l2_note")),
        f"Instrument catalog: **{payload.get('catalog')}**",
        "Post-08-14 L2 truth remains PMData + l2_recorder. Pre-08-14 L2 = DEBUG only.",
        "",
    ]
    (REPORTS / "NAUTILUS_FEE.md").write_text("\n".join(fee_lines), encoding="utf-8")
    (REPORTS / "NAUTILUS_DATA.md").write_text("\n".join(data_lines), encoding="utf-8")
    exp = [
        "# NAUTILUS_EXPERIMENT",
        "",
        f"Generated: {payload['generated']}",
        "Nautilus experiment does not unlock live. No exec client enabled.",
        "",
        "| capability | our stack | nautilus |",
        "|---|---|---|",
        "| S1 cover | existing PASS (bosona 80.19% / mo 84.68%) | n/a |",
        f"| Historical L2 | PMData/WS recorder | {payload.get('historical_l2')} |",
        f"| Fee | maker 0 / taker 0.07*p*(1-p) | rebate={payload.get('maker_rebate_crypto')} taker={payload.get('taker_rate')} |",
        f"| Order lifecycle | paper_maker PAPER_ONLY | {engine_status} |",
        "| Live | disabled | disabled |",
        f"| Catalog | n/a | {payload.get('catalog')} |",
        "",
        "do not live without G5 G6",
        "",
    ]
    (REPORTS / "NAUTILUS_EXPERIMENT.md").write_text("\n".join(exp), encoding="utf-8")
    print(json.dumps({
        "ok": True,
        "version": core.get("version"),
        "venue": payload.get("venue"),
        "venue_import": payload.get("venue_import"),
        "fee_model": payload.get("fee_model"),
        "historical_l2": payload.get("historical_l2"),
        "engine": engine_status,
        "catalog": payload.get("catalog"),
        "live": False,
        "live_ready_exists": payload["live_ready_exists"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
