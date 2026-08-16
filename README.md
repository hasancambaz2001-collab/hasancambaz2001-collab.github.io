# Whiskas — BTC 5m research

Public reconstruction of [@x-moneyforwhiskas](https://polymarket.com/@x-moneyforwhiskas) (`0x3048d65321be3497164cdfc2996f94f98a2e7537`) on Polymarket `btc-updown-5m-*` windows.

This repo is research + paper scaffolding. It is **not** a copy-trader and **not** a live execution tutorial.

## What exists now (Phase 1)

1. `scripts/dump_whiskas.py` — full Data API activity + closed positions (no keys).
2. `scripts/build_windows.py` — parquet windows/fills + `data/reports/PHASE1.md`.
3. `configs/whiskas.yaml` — filled from Phase 1 quantiles after the build.
4. Tests for slug parse, pair_cost / residual sign, kill-switch.

Do **not** start `python -m whiskas.bot` until `PHASE1.md` exists and you have read the T1–T5 table.

## Dump

```bash
python3 -m pip install -e ".[dev]"
python3 scripts/dump_whiskas.py
```

Writes `data/raw/whiskas_activity.jsonl` and `data/raw/whiskas_closed_positions.jsonl`.

Pagination follows the official Data API: `/activity` `limit≤500`, `offset≤5000`, then `start`/`end` windows for deeper history. `/closed-positions` uses `offset≤100000`.

## Reconstruct

```bash
python3 scripts/build_windows.py
```

Prints PHASE1 numbers, writes:

- `data/processed/whiskas_windows.parquet`
- `data/processed/whiskas_fills.parquet`
- `data/reports/PHASE1.md`
- `configs/whiskas.yaml`

Winners come from redeem rows, then closed-position `curPrice`, then Gamma `outcomePrices` for leftovers. Nothing is invented.

## Paper (later)

Paper against the live CLOB is Phase 3B. It must log *intended* orders only. It is not implemented in this Phase 1 drop.

## Live (warning, not a how-to)

Do not send live orders from this tree.

- Never flip live unless you paste `PHASE3_PASS` and the three env flags the operator defined.
- First live notional in the spec is $25 after paper is green. That is a cap, not a target.
- Wrong fee, stale WS, or a one-sided book will eat the pair edge. The official crypto taker curve is `fee = C × 0.07 × p × (1−p)`.
- This is not financial advice. You can lose the entire bankroll.

## Tests

```bash
python3 -m pytest
```
