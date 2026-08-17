# MICRO latency grid

Generated: 2026-08-17 01:52 UTC
Gates fixed. No clip/pair/still250-false-send changes. Max 3 variants, sequential.

## Rank (post_ack_ms p50, then p95)

| rank | variant | n_intent | n_sent | n_ws_age | post_ack p50 | post_ack p95 | still_ms p50 | still_ms p95 | still_ms ws_age p50 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | v1_cache_parallel | 25 | 0 | 0 | — | — | 370.5 | 391.9 | — |
| 2 | v2_ws_age | 115 | 0 | 26 | — | — | 371.5 | 413.0 | 0.01 |

Enough (≥20 intents): V1 yes, V2 yes.
V3 Rust sketch: skip. `post_ack_ms` p50 is missing (n_sent=0), not >500. No full migrate.

`post_ack_ms` is sign+HTTP on SEND only. Neither variant produced a still250-true live send on BTC 5m during this grid (book stayed rich; the two live V1 rests were `still250_false`). Rank by post_ack is therefore a **tie / not ranked**. The sort put V1 first only because mixed V2 `still_ms` p50 includes REST fallbacks.

## What actually moved

| clock | V1 | V2 when WS age ≤250ms | V2 fallback (age >250ms) |
|---|---:|---:|---:|
| still_ms p50 | 370.5 | **0.01** | ~370 (same as V1) |
| book_get_ms p50 | 119.1 | 147.5 | 127.8 |
| post_ack_ms | no send | no send | no send |

V2 did what it was asked: if the WS book is ≤250ms old, still250 does **not** sleep 250ms. 26 rests used `ws_age`. 89 used `rest_sleep_fallback` (cache empty / window rollover / first subscribe). Fallback is allowed; it is not a gate change.

## Live BTC 5m only

| variant | n_intent | still250 true | sent | post_ack |
|---|---:|---:|---:|---|
| V1 | 2 | 0 | 0 | — |
| V2 | 0 | 0 | 0 | — |

Both live V1 rests: bid_sum ≤0.90 then bid_sum_250=0.99 → `send_blocked=still250_false`. Gate held. No invented fills.

## Sample

Rest intents for the ≥20 count are snapshot `reason=rest` rows (paper maker GET-only on btc/eth/sol/xrp/doge 5m+15m plus live BTC 5m). Paper never posts. Live sender stayed clip 5, pair_max 0.90, still250-false → SEND YOK.

## Default after grid

Live sender left on **V2** (`data/ops/LATENCY_VARIANT=v2_ws_age`). Token cache + parallel GETs stay on. websocket-client is optional in the VPS venv, not a `pyproject.toml` dep.

## Unchanged

- clip 5 live / pair_max 0.90 / pair_gt_1_trade=false
- still250 false or bid_sum_250>0.90 → no send
- no LIVE_READY, no G5, no Whiskas/06dc live
