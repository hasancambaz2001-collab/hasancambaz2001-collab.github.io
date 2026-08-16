from whiskas.fees import taker_fee_usdc
from whiskas.policy import FORBIDDEN_PAIR_MAX, assert_pair_max_legal, complete_set_pnl, decide


def test_intend_when_ask_sum_at_pair_max() -> None:
    d = decide(0.48, 0.48)
    assert d.intend
    assert d.reason == "complete_set_fok"
    assert d.ask_sum == 0.96
    assert d.clip == 21.0
    assert len(d.orders) == 2
    assert all(o.side == "BUY" and o.order_type == "FOK" and o.size == 21.0 for o in d.orders)
    assert {o.outcome for o in d.orders} == {"Up", "Down"}


def test_skip_when_ask_sum_above_pair_max() -> None:
    d = decide(0.49, 0.48)
    assert not d.intend
    assert d.reason == "ask_sum_above_pair_max"
    assert d.orders == ()


def test_skip_missing_or_invalid_ask() -> None:
    assert decide(None, 0.40).reason == "missing_ask"
    assert decide(0.40, None).reason == "missing_ask"
    assert decide(0.0, 0.50).reason == "invalid_ask"
    assert decide(0.50, 1.0).reason == "invalid_ask"


def test_no_sell_orders() -> None:
    d = decide(0.40, 0.50)
    assert d.intend
    assert all(o.side == "BUY" for o in d.orders)


def test_complete_set_positive_at_096() -> None:
    pnl = complete_set_pnl(0.48, 0.48, 21.0)
    fees = taker_fee_usdc(21, 0.48) + taker_fee_usdc(21, 0.48)
    assert abs(pnl - (21 * 0.04 - fees)) < 1e-9
    assert pnl > 0


def test_complete_set_winner_independent() -> None:
    a = complete_set_pnl(0.30, 0.60, 21.0)
    b = complete_set_pnl(0.60, 0.30, 21.0)
    assert abs(a - b) < 1e-9


def test_complete_set_can_be_negative_at_097() -> None:
    # Not traded. Documents why cap is not the default.
    pnl = complete_set_pnl(0.485, 0.485, 21.0)
    assert pnl < 0


def test_no_diamond_rebate() -> None:
    try:
        complete_set_pnl(0.40, 0.50, diamond_rebate=True)
    except ValueError as exc:
        assert "Diamond" in str(exc)
    else:
        raise AssertionError("expected diamond rebate reject")


def test_pair_max_9513_forbidden() -> None:
    try:
        assert_pair_max_legal(FORBIDDEN_PAIR_MAX)
    except ValueError as exc:
        assert "0.9513" in str(exc)
    else:
        raise AssertionError("expected forbidden pair_max")
    try:
        decide(0.40, 0.50, pair_max=0.9513)
    except ValueError:
        pass
    else:
        raise AssertionError("decide must reject 0.9513")
