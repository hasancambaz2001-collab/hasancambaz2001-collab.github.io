# NAUTILUS_FEE

Generated: 2026-08-16 18:35 UTC
venue=POLYMARKET import=PASS
fee_model=PASS module=nautilus_trader.adapters.polymarket.fee_model
crypto maker rebate documented: **0.2** (we are not Diamond; do not assume we collect it)
taker rate documented: **0.07**
Our stack stays maker fee0 / taker 0.07*p*(1-p). Nautilus fee probe does not change PAPER_ONLY.
No live exec client enabled.
