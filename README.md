# Whiskas — BTC 5m research

Public reconstruction of [@x-moneyforwhiskas](https://polymarket.com/@x-moneyforwhiskas) (`0x3048d65321be3497164cdfc2996f94f98a2e7537`) on Polymarket `btc-updown-5m-*` windows.

This repo is research + paper scaffolding. It is **not** a copy-trader and **not** a live execution tutorial.

## What exists now (Phase 1 + tie-out)

1. `scripts/dump_whiskas.py` — full Data API activity + closed positions (no keys).
2. `scripts/build_windows.py` — parquet windows/fills + `data/reports/PHASE1.md`.
3. `scripts/tieout_pnl.py` — official +$211k vs reconstructed books (`PHASE1_TIEOUT.md`).
4. `scripts/analyze_maker.py` / `analyze_tape.py` / `analyze_cluster.py` — role split, Aug tape (T6–T9), proxy cluster.
5. `configs/whiskas.yaml` — **pair_max default 0.96, cap 0.97, clip 21**. Not live.
6. `scripts/replay_whiskas.py` — taker complete-set replay on `ask_sum ≤ 0.96` (`PHASE3_REPLAY.md`).
7. `scripts/paper_whiskas.py` — live CLOB **GET** logger of intended BUY FOKs. No orders.
8. Tests for slug parse, pair_cost / residual sign, kill-switch, fee/maker identity, policy/replay/paper.

**Read `PHASE1_TIEOUT.md` then `PHASE1_MAKER.md` / `TAPE.md` / `CLUSTER.md`, then `PHASE3_REPLAY.md`.** PHASE1 `total_pnl=−$103k` is the broken register. Tie-out is green (`|$137|`). T6–T9 stay closed.

Product is **taker complete-set only**: BUY both asks FOK, no SELL, no residual, no spot/TWAP, redeem after resolve. Maker/Diamond rebate is their edge. No live.

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

## Replay + paper (no live)

```bash
python3 scripts/replay_whiskas.py
python3 scripts/paper_whiskas.py --once
```

Replay uses their taker fill prices as the ask proxy and sizes `clip=21`. Paper polls `GET /book` and writes `data/paper/intended.jsonl`. Neither script posts an order. See `data/reports/PHASE3_REPLAY.md`.

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
