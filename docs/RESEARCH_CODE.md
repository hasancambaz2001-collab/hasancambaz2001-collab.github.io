# RESEARCH_CODE

Phase 1 repo/tape only. Current branch is pipeline + S1 fixtures. Full tape on `origin/cursor/whiskas-phase1-4921`. No invented prices.

| claim | evidence | source | date | confidence | supports_goal | contradicts |
| --- | --- | --- | --- | --- | --- | --- |
| 07:14 join=ask is BLOCK `would_be_taker_blocked` (Down 0.57=0.57) | fixture + report table | `tests/fixtures/s1/0714.json`; `origin/cursor/whiskas-phase1-4921:data/reports/MICRO_BOTH_FILL.md` | 2026-08-17 | 5 | partial | no |
| 08:27 cross-ask is BLOCK (Up 0.26>ask 0.23) | fixture + report table | `tests/fixtures/s1/0827.json`; same MICRO_BOTH_FILL.md | 2026-08-17 | 5 | partial | no |
| 07:59 maker-both is ALLOW (0.52/0.17 vs 0.84/0.18, bid_sum 0.69, depth 52) | fixture + report table | `tests/fixtures/s1/0759.json`; same MICRO_BOTH_FILL.md | 2026-08-17 | 5 | partial | no |
| mo-money cheap two-leg: first-leg gap p50 **107s**; fill span p50 **193s**; 88/111 maker both | report table vs “we judge both in ~250ms” | `origin/cursor/whiskas-phase1-4921:data/reports/MICRO_BOTH_FILL.md` | 2026-08-17 | 5 | partial | yes — sit-in-book minutes, not 250ms pair print |
| Live lag on 6 orders: min 1520 / med 1580 / max 1852 ms; all >1000 | MICRO_LAG table | `origin/cursor/whiskas-phase1-4921:data/reports/MICRO_LAG.md` | 2026-08-16 | 5 | no | yes — multi-second lag vs tight maker join |
| Live sample both_fill **0/3**; all still250 false (bid_sum_250=0.99) | MICRO_P0_P1 | `origin/cursor/whiskas-phase1-4921:data/reports/MICRO_P0_P1.md` | 2026-08-16 | 5 | no | yes — zero both-fill |
| Live sample one_leg_taker: Down filled taker in all 3 windows; Up 0/5 | MICRO_ONE_LEG | `origin/cursor/whiskas-phase1-4921:data/reports/MICRO_ONE_LEG.md` | 2026-08-16 | 5 | no | yes — taker one-leg, not locked maker complete-set |
| Observed live cash **~$50.60**; sample loss **~$3.38** (not $5000 book) | CLOB cash $50.601083; notionals+fees 3.38315 | same MICRO_ONE_LEG.md | 2026-08-16 | 5 | no | yes — not $5k deployed; net loss |
| 24h micro: real_fill_rate null; net_pnl_usd null; ALARM_intent_no_order_id; clip 5 | MICRO_LIVE_24H + json | `origin/cursor/whiskas-phase1-4921:data/reports/MICRO_LIVE_24H.md` | 2026-08-16 | 5 | no | yes — no 24h PnL |
| Their-size S1 replay $14110.75 n=209; same windows clip10 **$797.60**; clip5 row absent | KASA + REPLAY_FULL | `origin/cursor/whiskas-phase1-4921:data/reports/KASA.md`; `REPLAY_FULL.md` | 2026-08-16 | 4 | partial | yes — clip10 << their-size; no $1000/day rate |
| Paper residual fill sim 12.59% (73/580); pair>1 cancel measure 340 | G6_FILL_CAL | `origin/cursor/whiskas-phase1-4921:data/reports/G6_FILL_CAL.md` | 2026-08-16 | 4 | partial | yes — low both-fill |
| LIVE_BLOCKED; G5 size_ok FAIL; trial max_daily_loss_usd 25; clip 5 | LIVE_CONFIG + MICRO_LIVE_TRIAL.yaml | whiskas branch configs/reports | 2026-08-16 | 5 | no | no — matches no-deploy lock |
| pair_gt_1_trade false in processed live/replay artifacts | micro_live_24h.json, unified_mo-money.json | whiskas processed json | 2026-08-16 | 5 | partial | no |
| Whiskas whale one day +$1021.67 (2026-07-01); 2026-08-16 −$585.51; many large down days | PHASE1 daily table | `origin/cursor/whiskas-phase1-4921:data/reports/PHASE1.md` | 2026-08-16 | 4 | partial | yes — +$1k day is whale-scale and inconsistent, not clip-5/$5k |
| Under clip 5 and pair_max 0.90, max edge/window is 0.10×5=**$0.50**; 288 BTC 5m windows ⇒ **$144/day** if every window both-fills at the cap | arithmetic from GOAL locks + 5m cadence; not a live tape | `docs/GOAL.md` locks + 5m window count | 2026-08-17 | 4 | no | yes — even a perfect clip-5 day is ~$144, not $1000 |
| No artifact shows $5000 capital producing $1000/day under these locks | GOAL lock vs live ~$54 and null 24h pnl | GOAL.md; MICRO_ONE_LEG; micro_live_24h.json | 2026-08-17 | 5 | no | yes — $1000/day wish unsupported in-repo |
