# PHASE3 A vs A+A2 (BTC tape only)

A replay is unchanged (`PHASE3_REPLAY.md`). No T6. No pair>1 force. No Diamond.
No live. Inventory is per-window leftover, not cross-asset.

## Policy

- **A:** flat + `ask_u+ask_d≤0.96` + `min_size≥21` → FOK both, clip 21
- **A2 first-leg:** flat + valid pair + one side `<21` + `cheap_ask≤0.45` → FOK cheap `min(21, cheap_size)`
- **A2 complete:** holding one leg + `avg+ask≤0.96` → FOK the other, `min(held, 21, ask_size)`
- Never complete if `avg+ask>0.96`. Never a lone cheap ask.

A+A2 = A windows (existing VWAP complete-set) **plus** sequential A2 on the other BTC windows.

| | windows | pnl @100% | pnl @30% EV | max naked s | worst day @30% EV |
|---|---:|---:|---:|---:|---:|
| A | 6556 | 11649.56 | 3494.87 | 0.0 | 0.09% |
| A2 extra | 6423 | 5265.52 | 1579.66 | 285.0 | — |
| **A+A2** | 12979 | 16915.08 | 5074.53 | 285.0 | 0.18% |

A2 extra first-legs=3233, completes=3719, leftover windows=793.
A+A2 30% MC pnl=4880.14, worst MC day=-0.18%.

## PASS

| gate | need | ok |
|---|---|---|
| A2 pnl ≥ A (30% EV) | 5074.53 ≥ 3494.87 | True |
| no day −15% | worst=0.18% | True |

**PASS**. Fail reasons: none.
