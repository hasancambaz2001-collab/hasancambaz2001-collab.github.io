# Goal

Polymarket S1 micro — maker complete-set, `both_fill`↑, `one_leg_taker`≈0.

This file is the lock. Later phases do not widen it.

## Locks

- clip **5** (no clip up)
- `pair_max` **0.90**
- no `pair>1`
- maker-only: join **<** ask (join ≥ ask is a taker; block)
- `still250` + `ws_age` on **first send**
- requote max **8** while cheap + maker

## Success metrics

- fixture **PASS** (`0714` BLOCK, `0827` BLOCK, `0759` ALLOW)
- live counters (observe only; this setup does not deploy):
  - `both_fill`
  - `one_leg_taker`
  - `would_be_taker_blocked`
  - `requote_n`

## Non-goals

- mo-money directional sleeve
- size ladder
- multi-asset live

## Explicit non-actions

- No live trading changes in the pipeline-setup task
- Do not deploy the sender
- Human must type `deploy` explicitly after `make verify` PASS
