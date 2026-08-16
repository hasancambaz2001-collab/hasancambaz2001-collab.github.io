# FULL KASA

No live. `pair_gt_1_trade=false`. paper_maker is the primary 5m signal. Ask FOK is not primary.

## Tape

mo-money, bosona, 0x06dc. Dump ≤4000 newest `/activity` rows each. Not paper intends.
Two-leg windows group by **market slug** (Yes+No on the same binary). 06dc ladders are not one event-wide set.

## Books

- **S1** (primary): maker two-leg, pair < 0.90, 5m/15m (06dc any tf). Winner-independent `$ = size × (1 − pair)`. No taker fee.
- **S3** (measure only): taker two-leg, pair ≤ 0.96 and pair < 1. `$ = size × (1 − pair) − fee`. Not the 5m signal.

Never trade pair ≥ 1.

## Size

`size_ok=false`. Ladder only: **10 → after_parity → target_p50 (~67)**.
Do not arm after_parity or p50. Do not bump `size.yaml`.

## Runs

```
python3 scripts/kasa_attribution.py --run
python3 scripts/size_schedule.py --run
python3 scripts/replay_full.py --run
python3 scripts/replay_full.py --run --clip 10
```

Stop line: S1$, S3$, parity their-size, parity clip10, target_clip_p50.
