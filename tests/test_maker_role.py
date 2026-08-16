from whiskas.fees import looks_like_taker, notional_usdc, taker_fee_usdc
from whiskas.windows import build_windows


def test_role_tag_maker_vs_taker() -> None:
    shares, price = 20.0, 0.40
    maker_usdc = notional_usdc(shares, price)
    taker_usdc = maker_usdc + taker_fee_usdc(shares, price)
    assert not looks_like_taker(maker_usdc, shares, price)
    assert looks_like_taker(taker_usdc, shares, price)


def test_role_pair_costs_separate() -> None:
    slug = "btc-updown-5m-1786886400"
    t0 = 1786886400
    fee = taker_fee_usdc(10, 0.40)
    rows = [
        {
            "type": "TRADE",
            "timestamp": t0 + 10,
            "eventSlug": slug,
            "slug": slug,
            "outcome": "Up",
            "outcomeIndex": 0,
            "side": "BUY",
            "size": 10,
            "price": 0.40,
            "usdcSize": 10 * 0.40 + fee,
            "transactionHash": "0xtaker",
        },
        {
            "type": "TRADE",
            "timestamp": t0 + 20,
            "eventSlug": slug,
            "slug": slug,
            "outcome": "Down",
            "outcomeIndex": 1,
            "side": "BUY",
            "size": 10,
            "price": 0.55,
            "usdcSize": 10 * 0.55,
            "transactionHash": "0xmaker",
        },
    ]
    w = build_windows(rows)[t0]
    assert w.q_up == 10
    assert w.q_down == 10
    taker_usdc = 10 * 0.40 + fee
    maker_usdc = 10 * 0.55
    assert looks_like_taker(taker_usdc, 10, 0.40)
    assert not looks_like_taker(maker_usdc, 10, 0.55)
