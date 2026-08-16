# MICRO lag_ms — 6 live orders

Source: VPS `data/micro_live/intended.jsonl` `ts` + CLOB `get_order.created_at` + `get_trades.match_time`.
No invented timestamps. CLOB `created_at` / `match_time` are **unix seconds** (1s resolution). jsonl `ts` has microseconds.
`lag_ms = created_at_ms - intent_ts_ms` (created_at taken as `unix * 1000`).
`fill_ms = match_time_ms - intent_ts_ms` when MATCHED; else empty.
`still250` from the same intent row. `side` from CLOB `trader_side` (no trade → empty).

| window | leg | intent_ts | clob_created_ts | lag_ms | fill_ms | still250 | side |
|---|---|---|---|---|---|---|---|
| A 21:46 t0=1786916700 | Up | 2026-08-16T21:46:53.480321Z | 2026-08-16T21:46:55Z (`1786916815`) | **1520** | | false | |
| A 21:46 | Down | 2026-08-16T21:46:53.480321Z | 2026-08-16T21:46:55Z (`1786916815`) | **1520** | 1520 | false | taker |
| B 21:48 t0=1786916700 | Up | 2026-08-16T21:48:04.420249Z | 2026-08-16T21:48:06Z (`1786916886`) | **1580** | | false | |
| B 21:48 | Down | 2026-08-16T21:48:04.420249Z | 2026-08-16T21:48:06Z (`1786916886`) | **1580** | 580 | false | taker |
| C 21:50 t0=1786917000 | Up | 2026-08-16T21:50:54.148469Z | 2026-08-16T21:50:56Z (`1786917056`) | **1852** | | false | |
| C 21:50 | Down | 2026-08-16T21:50:54.148469Z | 2026-08-16T21:50:56Z (`1786917056`) | **1852** | 852 | false | taker |

order_id: A Up `0x58ab7b87…d545dfdd` · A Down `0x72774980…0a6a5dd8` · B Up `0xd908d6ef…42b6db3b` · B Down `0x93cc0fb2…9b2e29fd` · C Up `0x841bf8e4…07e4d5aa` · C Down `0x18e26617…ad98c43e`

## Summary (n=6 lag_ms)

| min | median | max |
|---|---|---|
| **1520** | **1580** | **1852** |

- **all 6 lag_ms > 500**
- **all 6 lag_ms > 1000**

B/C Down `match_time` is 1s **before** `created_at` (CLOB 1s clocks). `fill_ms` still uses match − intent, not invented.

jsonl `ts` is the snapshot row that posted (includes the 250ms still250 sleep already done in that snapshot). still250 was **false** on all three intents.
