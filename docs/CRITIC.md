# CRITIC

Do NOT improve. Breaks against GOAL locks and success metrics.

| claim | evidence | severity | required fix |
| --- | --- | --- | --- |
| $1000/day wish is not met and must not be “fixed” by raising clip | ARCH + RESEARCH: clip-5 perfect-day cap ~$144; live sample loss | info | none — GOAL says $1000/day is not a lock |
| Live sender is absent; “çalıştır” did not place orders | no micro_live process; STATE sender_pid none | info | none — GOAL/ARCH forbid deploy unless human types deploy |
| join>=ask still blocked (0714, 0827) | fixtures + s1_gate | ok | none |
| pair>1 still refused | test_pair_gt1_refused | ok | none |
| still250 false still blocks | test_still250_false_blocks_even_if_maker | ok | none |
| capital_max>5000 would break GOAL | invariants require capital_max==5000 on s1_micro.yaml | ok | none if verify PASS |
| Residual / one-leg taker is not simulated in fixtures | fixtures are first-send only; live tape had one-leg taker | medium | none in this ARCH step — live manage path not in scope; do not deploy |
| X research is incomplete | X MCP needsAuth | low | none for impl; do not invent tweets |
