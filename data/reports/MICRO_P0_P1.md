# MICRO P0+P1 send gates

Generated: 2026-08-16 22:20 UTC
No clip up. No pair>1. MICRO ≠ LIVE_READY.

## What changed

P0
1. `still_there_250ms is not True` or `bid_sum_250 > 0.90` → `send_blocked`, no CLOB post.
2. No second still250 sleep. Sign both GTCs, `post_orders` one HTTP. `lag_ms` = intent→ack (includes the one 250ms probe).
3. First leg MATCHED → re-read book; FOK complete only if `fill_px+opp_ask≤0.90`, else cancel leftover now.
4. One-leg/adverse **before** `rich_cancel` (bid_sum>0.92).

P1
5. Post only at best bid (`bid_up_250`/`bid_down_250`).
6. `trader_side` maker|taker from CLOB trades; `s1_edge` stays the rest pair.
7. Post-ack 250ms (200–500): off-touch → cancel both unfilled.
8. Same t0 re-rest only if inventory flat (Up filled == Down filled).

P2 (same patch)
9. Log `lag_ms`, `adverse_action`, `residual`, `fill_role`, `both_fill`, `one_leg`.
10. Unpaired timeout 45s / window-end flatten leftover; daily loss cap $25 (unpaired notional).
11. Paper uses `apply_still250_send_gate` (same helper). `would_send=false` drops paper rest state.

## Before (windows 21:46 / 21:48 / 21:50 UTC) — live tape + CLOB

| window | still250 | both_fill | one_leg | lag_ms (jsonl→CLOB created) | residual |
|---|---|---|---|---|---|
| A 21:46 | false (0.99) | no | Down 5/5 taker @0.36 | ~2000 | Up 5, Down 0 |
| B 21:48 | false (0.99) | no | Down 5/5 taker @0.27 | ~1600 | Up 5, Down 0 |
| C 21:50 | false (0.99) | no | Down 0.36/5 taker @0.22 | ~1800 | Up 5, Down 4.64 |

All three would now be **SEND YOK** (`still250_false`). Same-t0 B would also be blocked by inventory not flat after A.

## After — next windows

No new send yet at patch time. Next cheap prints: expect `send_blocked=still250_false` until still250 stays true, then `lag_ms` / `both_fill` / `one_leg` / `residual` on the REAL FILL row.

Judge next rest by those four fields, not by clock.
