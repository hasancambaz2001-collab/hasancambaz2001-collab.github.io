# BID_BUCKET (5m paper only)

Apply only when `PHASE1_MAKER_MOBO` GATE=PASS. Measure-only. No live.

## What

On `paper_whiskas` / `whiskas.paper.snapshot_window`:

- Always log `bid_up`, `bid_down`, `bid_sum` (best bid each leg).
- On **5m and 15m only**: if `bid_sum ≤ 0.98`, set `maker_intend=True` and log GTC BUY both best bids (clip 21). `live_order` stays false.
- **4h stays poll-only**: log bids, never `maker_intend`.
- Ask buckets stay `0.90` / `0.96`. Do not trade `ask_sum > 0.96`. Never pair>1 taker.
- No clip bump. No R7. No size.yaml bump.

## Why

mo-money + bosona are mostly maker (GATE PASS). Their cheap two-leg sets sit on the bid, which the ask-only 5m paper never counted.

## Do not

- Post orders.
- Lift `pair_max` / both-taker above 0.96.
- Apply this patch to `paper_06dc` (06dc already has R6).
- Change 06dc R6 (that threshold is 0.99, separate).
