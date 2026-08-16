# MICRO one-leg diagnosis (evidence only)

Generated: 2026-08-16 22:05 UTC
Source: AMS3 VPS `/root/whiskas/data/micro_live/intended.jsonl` + CLOB `get_order` / `get_trades` / `get_open_orders` / `get_balance_allowance`.
No size bump. No pair>1 trade. No new strategy. No invented fills.

CLOB cash now: **$50.601083** (`balance=50601083`). `get_open_orders` **n=0**.
`intended.jsonl`: 3 `reason=rest` only; `adverse` never set; `cancel_reason` never written.
CLOB `get_order` fields have **no** `cancel_reason` / `cancelled_at`.

## 1) The six orders

### Window A — slug `btc-updown-5m-1786916700` t0 `1786916700` (21:45–21:50)

Book at intent (`intended.jsonl` 2026-08-16T21:46:53.480321+00:00):
bid_up **0.37** ask_up **0.38** depth_up **729.66** / bid_down **0.51** ask_down **0.52** depth_down **100** / bid_sum **0.88** / min_bid_size **100** / clip **5**.
`maker_bid: true` both legs. `still_there_250ms=false` `bid_sum_250=0.99` `min_size_250=32.37`.

| leg | order_id | place ts | CLOB created_at | px (GTC) | size | send snapshot | CLOB now | trades |
|---|---|---|---|---|---|---|---|---|
| Up | `0x58ab7b872db31ea58e5c60d3e6868c77e8a97bda20f25918201b1d9cd545dfdd` | 21:46:53.480Z | 21:46:55Z (`1786916815`) | 0.37 | 5 | LIVE / open / filled 0 | **CANCELED** / filled 0 / `associate_trades=[]` | none |
| Down | `0x72774980fc247939f5d0b3604ed63b22ad509e4450c48aeba84646760a6a5dd8` | 21:46:53.480Z | 21:46:55Z | 0.51 | 5 | MATCHED / filled 5/5 | **MATCHED** / filled 5/5 | trade `c5e0a3f4-…` match **21:46:55Z** |

Down trade (CLOB `get_trades`): `trader_side=TAKER`, `taker_order_id`=our Down, size 5, **fill px 0.36** (not the 0.51 GTC), `fee_rate_bps=0`, counterparty maker BUY Up @ **0.64** (`0x20c7a0b2…`). 0.36+0.64=1.00.

Next snapshot 21:46:56.459Z same t0: `reason=rich_bid_sum` bid_sum **0.99** bid_up **0.63** ask_up **0.64**. Up GTC 0.37 is then **26¢ below** best bid.

### Window B — same t0 / same slug (second rest)

Book at intent (2026-08-16T21:48:04.420249+00:00):
bid_up **0.56** ask_up **0.67** depth_up **778.81** / bid_down **0.32** ask_down **0.33** depth_down **9.82** / bid_sum **0.88** / min_bid_size **9.82**.
`maker_bid: true`. `still_there_250ms=false` `bid_sum_250=0.99` `min_size_250=1.77`.

| leg | order_id | place ts | CLOB created_at | px (GTC) | size | send snapshot | CLOB now | trades |
|---|---|---|---|---|---|---|---|---|
| Up | `0xd908d6ef19553ff2d3e508618fa4637b368e00e1ba17744b50b3d86e42b6db3b` | 21:48:04.420Z | 21:48:06Z (`1786916886`) | 0.56 | 5 | LIVE / open / filled 0 | **CANCELED** / filled 0 / `associate_trades=[]` | none |
| Down | `0x93cc0fb2fc67e2be193b2f470c52bd81ad25376af0c969766e5ef4b09b2e29fd` | 21:48:04.420Z | 21:48:06Z | 0.32 | 5 | MATCHED / filled 5/5 | **MATCHED** / filled 5/5 | trade `330c5903-…` match **21:48:05Z** |

Down trade: `trader_side=TAKER`, size 5, **fill px 0.27** (not 0.32), maker BUY Up @ **0.73**. 0.27+0.73=1.00.

Next snapshot 21:48:07.361Z: `rich_bid_sum` bid_sum **0.99** bid_up **0.76** ask_up **0.77**. Up GTC 0.56 is then **20¢ below** best bid.

### Window C — slug `btc-updown-5m-1786917000` t0 `1786917000` (21:50–21:55)

Book at intent (2026-08-16T21:50:54.148469+00:00):
bid_up **0.68** ask_up **0.69** depth_up **1565.51** / bid_down **0.22** ask_down **0.29** depth_down **21** / bid_sum **0.90** / min_bid_size **21**.
`maker_bid: true`. `still_there_250ms=false` `bid_sum_250=0.99` `min_size_250=83.14`.
Send-time `raw_status` null / `rested_size` null on both (post ack only).

| leg | order_id | place ts | CLOB created_at | px (GTC) | size | send snapshot | CLOB now | trades |
|---|---|---|---|---|---|---|---|---|
| Up | `0x841bf8e4235e7c66ee03c6f07a4d1d113d5bc2f9ed05ef1d71dabc7d07e4d5aa` | 21:50:54.148Z | 21:50:56Z (`1786917056`) | 0.68 | 5 | open / filled 0 | **CANCELED** / filled 0 / `associate_trades=[]` | none |
| Down | `0x18e266174ae08d52497cbcd832ae9a83f302ad72e37451606652cceead98c43e` | 21:50:54.148Z | 21:50:56Z | 0.22 | 5 | open / filled 0 | **MATCHED** / filled **0.36**/5 (partial) | trade `e7e237ac-…` match **21:50:55Z** |

Down trade: `trader_side=TAKER`, size **0.36**, **fill px 0.22**, maker BUY Up @ **0.78**. 0.22+0.78=1.00.
Remainder 4.64 is **not** in `get_open_orders`. CLOB status stays `MATCHED` (no separate cancel-partial field).

Next snapshot 21:50:57.059Z: `rich_bid_sum` bid_sum **0.99** bid_up **0.77** ask_up **0.78**. Up GTC 0.68 is then **9¢ below** best bid.

## 2) Why Up did not fill while Down did

**At send, Up was at the then-best bid** (`price == bid_up`, `maker_bid: true`).
- A: 0.37 vs ask 0.38 (1 tick).
- B: 0.56 vs ask **0.67** (at best bid, 11¢ wide).
- C: 0.68 vs ask 0.69 (1 tick).

**Up did not stay at best bid.** still250 already `bid_sum_250=0.99` on all three rests. CLOB create is ~2s after the jsonl ts. Next loop (~3s) best Up bid had jumped to 0.63 / 0.76 / 0.77. The Up GTC was then **off-touch, below the new bid**, with `associate_trades=[]`. That is why Up is 0/5, not “auth failed” and not “never posted”.

**Down filled as TAKER against complementary Up bids**, not as a resting bid getting hit at our GTC px:
- A: we paid **0.36** vs GTC 0.51, vs a resting BUY Up @ 0.64.
- B: we paid **0.27** vs GTC 0.32, vs a resting BUY Up @ 0.73.
- C: we paid **0.22** vs GTC 0.22, vs a resting BUY Up @ 0.78 (0.36 of 5).

At the *snapshot* those complementary Up bids were **not** the displayed best bid (A bid_up 0.37, B 0.56, C 0.68). The match times equal CLOB `created_at` (±1s). The book had already ripped (`still250` false) before/as the GTCs landed. Down’s stale-high limit could take the new complementary Up bid; Up’s stale-low limit could not.

Queue depth at send (Up 730 / 779 / 1566 vs Down 100 / 9.82 / 21) is consistent with Up being harder to eat *if both rested*, but the CLOB tape for A/B is **immediate taker**, not a queue-drain at 0.51/0.32.

## 3) Cancel path (what the tape can and cannot prove)

`intended.jsonl` has **0** rows with `cancel_reason` or `adverse` (1640 rows scanned). `manage_open` writes `cancel_reason` onto the cancel RPC result, not onto the logged snapshot.

Code (`scripts/micro_live.py` `manage_open`): if `bid_sum > 0.92` it **`rich_cancel`s first**, before one-leg / FOK complete.

Every window’s next snapshot is `rich_bid_sum` **0.99** (~3s later). That is the only logged condition that matches a cancel. CLOB then shows the three Ups `CANCELED` fill 0, and open orders 0.

**Not proven per-order:** the cancel RPC response, or a CLOB cancel-reason string (field absent).

**Adverse complete did not run** (no `adverse` stamp; no FOK `order_id` on this tape). At *send* book, Down GTC 0.51 + ask_up 0.38 = 0.89 ≤ 0.90 would have been `complete` *if* that branch ran. The next book is already rich, so `rich_cancel` wins. Using *actual* fill px: A 0.36+0.64=1.00 → would be `rich_complete` / not complete anyway.

## 4) Same-t0 second rest (A then B)

After A, the next cheap print on the same t0 is B at 21:48:04 (`reason=rest` again). Between them every row is `rich_bid_sum`. `rich_cancel` pops `open_windows[t0]`, so a later cheap print **re-rests the same 5m**. Result: two Down TAKER fills on one window (5+5), still 0 Up.

## 5) Cash $53.98 → $50.60

CLOB collateral now **50601083** = $50.601083. Open orders 0.

Trade notionals: `5*0.36 + 5*0.27 + 0.36*0.22 = 3.2292`.
Implied taker fee `0.07*p*(1-p)*size`: 0.08064 + 0.06899 + 0.00432 = **0.15395**.
3.2292 + 0.15395 = **3.38315**. 53.984223 − 3.38314 = **50.60108**. Matches CLOB cash.
`fee_rate_bps` on the three trade objects is `"0"`; the cash delta still matches the published taker formula.

No pair>1 trade on the tape (`pair_gt_1_trade` false on all three REAL FILL rows).
