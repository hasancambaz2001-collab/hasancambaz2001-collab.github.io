from whiskas.fees import embedded_fee_usdc, looks_like_taker, notional_usdc, taker_fee_usdc


def test_official_crypto_curve_not_flat_pct() -> None:
    fee = taker_fee_usdc(100, 0.50)
    assert abs(fee - 1.75) < 1e-9
    assert abs(fee - 100 * 0.50 * 0.015) > 0.5


def test_taker_buy_usdc_includes_curve_fee() -> None:
    shares, price = 5.0, 0.70
    fee = taker_fee_usdc(shares, price)
    usdc = notional_usdc(shares, price) + fee
    assert abs(embedded_fee_usdc(usdc, shares, price) - fee) < 1e-9
    assert looks_like_taker(usdc, shares, price)


def test_maker_buy_usdc_equals_notional() -> None:
    shares, price = 21.0, 0.44
    usdc = notional_usdc(shares, price)
    assert abs(embedded_fee_usdc(usdc, shares, price)) < 1e-12
    assert not looks_like_taker(usdc, shares, price)


def test_double_count_if_fee_applied_on_top_of_usdc() -> None:
    shares, price = 100.0, 0.50
    fee = taker_fee_usdc(shares, price)
    usdc = notional_usdc(shares, price) + fee
    payout = shares
    after_real_fee = payout - usdc
    after_double_fee = payout - usdc - fee
    assert abs(after_real_fee - (payout - shares * price - fee)) < 1e-9
    assert after_double_fee < after_real_fee
    assert abs((after_real_fee - after_double_fee) - fee) < 1e-9
