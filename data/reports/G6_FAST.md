# G6_FAST

Generated: 2026-08-16 18:59 UTC
Result: **PASS**

## Limits

- G6-fast is historical twin calibration, **not** live fill proof
- Does not set G5 `size_ok`
- Does not write `LIVE_READY`
- Still recommend short live paper smoke after G6-fast before real size
- No pair>1 trade. No clip 67. No full-size.
- Do not unlock PMData day 2026-08-16 (slug API only for that calendar day)
- PMData L2 is Yes-token only. Complement Down is **not** used.
- Joined books are `joined_yes_l2_plus_dump_down` when dump Down exists; else one-leg stats only

## PASS criteria (this run)

- n_rest >= 50: **169**
- edge_proxy_fee0 >= 0: **419.6999321905117**
- report written: **yes**

## Stop table

1. n_slugs_downloaded=960 n_rest=169 cover_bosona/mo=0.8359 (107/128)
2. fill_ratio risk_averse=0.10164835164835165 vs prob=0.10714285714285714
3. maker edge fee0=419.6999321905117 / with rebate=429.5627181905117
4. G6 flag written? **YES**
5. G5 still FAIL (flag exists=False)
6. LIVE still BLOCKED (LIVE_READY exists=False)
7. G6-fast replaces week-long wait for calibration evidence; micro live still needed before size

## Counts

- n_slugs_downloaded: 960
- n_slugs_one_leg: 832
- n_slugs_joined: 128
- n_rest unique (slug,t0): 169 (raw recorder=905 raw joined=24907; dense BBO can re-rest after cancel_age)
- leader S1 union: 128 · downloaded overlap: 128
- AGREE: 107 · cover: 0.8359 (107/128)
- bosona S1 cover on downloaded: 0.8865979381443299
- mo S1 cover on downloaded: 0.8736842105263158
- worst synthetic day: 2026-08-16 edge/notion=0.3304 edge=419.6999 notion=1270.3001
- pair_gt_1_trade: false
- days_unlocked_this_run: False
- fail_reasons: []

## Fill bands (never mix)

| band | source | fill_ratio | n_rest | note |
|---|---|---|---|---|
| (a) residual-sim | paper_maker tape | 0.12256267409470752 | 718 | 2s/1s poll residual |
| (b) hist queue risk_averse | recorder two-leg + pessimistic | 0.10164835164835165 | 364 | hidden 1.60 lat 2 |
| (c) hist queue prob | recorder two-leg + base | 0.10714285714285714 | 364 | hidden 1.25 lat 1 |
| paper live CLOB fills | none expected | n/a | n/a | paper does not send |

G6-fast replaces week-long wait for calibration evidence; micro live still needed before size
