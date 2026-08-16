from __future__ import annotations

WHISKAS_USERNAME = "x-MoneyForWhiskas"
WHISKAS_PROFILE = "https://polymarket.com/@x-moneyforwhiskas"
WHISKAS_WALLET = "0x3048d65321be3497164cdfc2996f94f98a2e7537"

DATA_API = "https://data-api.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"

BTC_5M_PREFIX = "btc-updown-5m-"
WINDOW_SECONDS = 300
LATE_T_SECONDS = 240

# Official crypto taker fee: fee = C * feeRate * p * (1-p)
# https://docs.polymarket.com/trading/fees
CRYPTO_TAKER_FEE_RATE = 0.07

ACTIVITY_LIMIT = 500
ACTIVITY_OFFSET_MAX = 5000
CLOSED_POS_LIMIT = 50
CLOSED_POS_OFFSET_MAX = 100_000

USER_AGENT = "whiskas-research/0.1 (+phase1; no live orders)"
