# REPLAY_MOBO

Generated: 2026-08-16 17:13 UTC
Validated on **their tape** (`data/raw/mobo_*_activity.jsonl`). Not paper intends.
Do **not** treat `paper_maker` rest lines as PnL.

Config: `pair_max=0.90` `maker_only=true` `clip=10`. TFs 5m+15m.
PASS = cover ≥80% of their pair<0.90 two-leg 5m/15m windows.

## GATE **PASS**

cover ≥80% of pair<0.90 two-leg 5m/15m: mo-money 85% (71/84), bosona 84% (67/80).

| wallet | two-leg 5m/15m | pair<0.90 | covered | cover | maker both legs |
|---|---:|---:|---:|---:|---:|
| mo-money | 152 | 84 | 71 | 84.5% | 66 |
| bosona | 137 | 80 | 67 | 83.8% | 72 |

Covered iff the cheap window has a maker fill and min size ≥ clip 10 (rest-both rule on their observed set). maker-both-legs is a separate count (bosona 72/80 = 90%); it is not PnL.

No live. No paper restart. No clip bump on 5m/06dc.
