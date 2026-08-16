# G6_FILL_CAL

Generated: 2026-08-16 18:35 UTC
paper_maker residual-sim only. Not live fill. Not PnL. G6 flag **not** written.
do not live without G5 G6

- rows: 12793 · 2026-08-16T17:09:06.246063+00:00 → 2026-08-16T18:35:26.516515+00:00
- rests: **580**
- skips: **11307** (rich/thin/missing)
- still@250ms: not recorded (paper_maker interval=2s)
- fill% (residual-sim complete+filled_both / rest): **0.1259** (complete=1 filled_both=72)
- worst day: 2026-08-16 fill_sim%=0.1259 rest=580 skip=11307
- pair>1 cancel (measure, not trade): 340

G6 stays FAIL until a human writes `data/ops/G6_fill_calibrated.flag` after reviewing this tape vs queue sim.
Do not treat paper intends as PnL. Low fill% on short L2 = calibrate, don't kill S1.
