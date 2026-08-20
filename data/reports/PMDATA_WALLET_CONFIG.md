# PMDATA_WALLET_CONFIG

Generated: 2026-08-16 18:08 UTC
Post-08-14 only. No Mar–May bulk. No live. size_ok=false. pair_gt_1_trade=false.
Key from env (`PMDATA_API_KEY`). Never hardcoded.

## APIs (docs shape)

Day:

```
GET https://api.pmdata.dev/polymarket/{series}/{type}/{series}_{type}_{date}.zip
headers={"api_key": <env>}
```

Slug / curl:

```
GET https://api.pmdata.dev/download/{type}/{slug}.parquet
pandas.read_parquet(url, storage_options={"api_key": <env>, "User-Agent": "Mozilla/5.0"})
```

`2026-08-01` in the vendor example is **pre-08-14 DEBUG**. Days used here: **2026-08-14** and **2026-08-15**.
Nautilus historical L2 = false. Chainlink/TWAP Day streams exist (paid) and are **not** the S1 edge.
PMData / Day API do **not** cover 06dc daily/monthly. 06dc truth = dump + paper_06dc + T6.

## Day API onchain_fills (2026-08-14 + 2026-08-15)

20 zips · 3840 market files · series btc/eth/sol/xrp/doge × 5m/15m.

| wallet | n_fills | maker_share | size_p50 | size_p90 | notes |
|---|---:|---:|---:|---:|---|
| mo-money | 11381 | **0.759** | **10.00** | 90.84 | mostly btc-5m + eth-5m |
| bosona | 11186 | **0.748** | **10.21** | 100.00 | same shape as mo |
| 06dc | 0 | — | — | — | not on 5m/15m updown |
| whiskas | 38543 | 0.423 | 17.24 | 80.00 | **btc-5m only**; official ledger locked |

Hottest-10-slug sample earlier (~50% maker) was the most competitive books. Two full post-14 days → ~75% maker for mo/bosona. Full 4000-row dump fee-match remains ~90%. Do not invent a new mix rule.

## Inferred vs yaml (no new alpha)

- pair_max **0.90** from dump S1 (PMData L2 is Yes-token only; do not reconstruct bid_sum)
- cancel_above **0.92** (cancels not in onchain fills)
- paper_clip **10** — Day API maker size p50 = 10.00 / 10.21
- maker rest both; pair>1 trade=false
- primary = paper_maker 5m/15m
- 06dc = dump + paper_06dc + T6
- Whiskas 5m counts are ATTR only

pre-08-14 parquet is DEBUG only
S1 go/no-go = replay edge, NOT queue fill%
size_ok=false live=false pair_gt1_trade=false
