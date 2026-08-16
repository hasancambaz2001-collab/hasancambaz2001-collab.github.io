# L2 TWIN + PARQUET

No live. No pair>1. `size_ok` stays false. S1 maker complete-set (`bid_sum≤0.90`). Not residual/TWAP directional.

## Regime

Polymarket TWAP/oracle shift ~2026-08-14.

- Pre-2026-08-14 L2 (kachoio Mar–May) = **DEBUG / policy wiring only**.
- Do **not** claim live parity from pre-08-14 data alone.
- Post-08-14 validation = `data/l2` recorder + activity dumps since 2026-08-14 + optional PMData.

**pre-08-14 parquet is DEBUG only; live parity needs post-08-14 L2**

## Shared PolicyMaker

`whiskas/l2.py` `PolicyMaker` — used by `paper_maker`, `twin_l2 --source record`, `twin_l2 --source parquet`.

- `pair_max=0.90`, `cancel_above=0.92`, `clip=10`
- Rest BOTH iff `bid_sum≤0.90` and `min(bid_size)≥clip`
- Replace/join best; cancel if sum>0.92 or stale>45s
- Adverse: complete only if `fill_px+opp_ask≤0.90` else cancel (`--fill residual`)

## Runs

```
python3 scripts/l2_recorder.py --interval 1 --out-dir data/l2
python3 scripts/twin_l2.py --source parquet --path data/parquet/btc_ticks.parquet --clip 10 --fill none
python3 scripts/twin_l2.py --source record --glob "data/l2/*.jsonl" --clip 10 --fill residual
```
