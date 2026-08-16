# G6_CLOSED

Generated: 2026-08-16 18:59 UTC
Three columns. Never mix residual-sim, historical queue, and paper/live fills.

G6-fast is historical twin calibration, not live fill proof.
Does not set G5 size_ok. Does not write LIVE_READY.
Still recommend short live paper smoke after G6-fast before real size.

| metric | g6_fast | paper_live | notes |
|---|---|---|---|
| n_rest | 169 | 718 | rest intents; columns not mixed |
| fill_band | ra=0.10164835164835165 / prob=0.10714285714285714 | 0.1226 residual-sim | (a) residual-sim (b) hist queue (c) paper live — never mix |
| still250 | n/a | 65/80=0.8125 | hist has no 250ms probe |

- G6 flag written? **YES**
- G5 still **FAIL**
- LIVE still **BLOCKED**
- MICRO yaml is not LIVE_READY

G6-fast replaces week-long wait for calibration evidence; micro live still needed before size
