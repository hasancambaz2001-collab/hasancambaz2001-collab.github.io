# MICRO latency grid

Gates fixed. No clip/pair/still250-false-send changes. Max 3 variants, sequential.

| variant | change | status |
|---|---|---|
| V1 `v1_cache_parallel` | token cache + parallel book GETs | armed; collect ≥20 rest intents |
| V2 `v2_ws_age` | + still250 via WS book age ≤250ms (no extra 250 sleep if age ok) | wait until V1 has ≥20 intents |
| V3 Rust sketch | only if post_ack_ms p50 > 500 after V1/V2 | not started; no full migrate |

Rank by `post_ack_ms` p50, then p95. `post_ack_ms` exists on SEND only. Do not invent fills.
