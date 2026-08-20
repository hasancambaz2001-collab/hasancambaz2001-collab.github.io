from whiskas.fees import taker_fee_usdc
from whiskas.policy import (
    FORBIDDEN_PAIR_MAX,
    BookInventory,
    assert_pair_max_legal,
    complete_set_pnl,
    decide,
    decide_a,
    decide_a2,
    decide_repeat,
)


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


def test_a_requires_depth() -> None:
    d = decide_a(0.40, 0.55, 10, 40)
    assert not d.intend
    assert d.reason == "depth_short"
    both = decide_a(0.40, 0.55, 21, 21)
    assert both.intend
    assert both.reason == "complete_set_fok"


def test_a2_first_leg_only_on_valid_pair() -> None:
    hit = decide_a2(0.40, 0.55, 10, 40)
    assert hit.intend
    assert hit.reason == "a2_first_leg"
    assert len(hit.orders) == 1
    assert hit.orders[0].outcome == "Up"
    assert hit.orders[0].size == 10.0
    lone = decide_a2(0.30, None, 50, 0)
    assert not lone.intend
    dear = decide_a2(0.30, 0.70, 50, 10)
    assert not dear.intend
    assert dear.reason == "ask_sum_above_pair_max"
    not_cheap = decide_a2(0.46, 0.50, 10, 40)
    assert not not_cheap.intend
    assert not_cheap.reason == "a2_cheap_above_045"


def test_a2_complete_and_never_above_pair_max() -> None:
    inv = BookInventory()
    inv.apply_buy("Down", 10, 0.40)
    ok = decide_a2(0.50, 0.60, 30, 5, inv)
    assert ok.intend
    assert ok.reason == "a2_complete"
    assert ok.orders[0].outcome == "Up"
    assert ok.orders[0].size == 10.0
    blocked = decide_a2(0.57, 0.60, 30, 5, inv)
    assert not blocked.intend
    assert blocked.reason == "a2_complete_above_pair_max"


def test_inventory_not_netted_across_assets() -> None:
    btc = BookInventory()
    eth = BookInventory()
    btc.apply_buy("Up", 21, 0.40)
    assert btc.residual_leg() == "Up"
    assert eth.is_flat()
    assert eth.residual_qty() == 0.0


def test_repeat_is_measure_only_same_cap() -> None:
    idle = decide_repeat(0.40, 0.55, 30, 30, filled_this_window=False, clips_this_window=0)
    assert not idle.intend
    hit = decide_repeat(0.40, 0.55, 30, 30, filled_this_window=True, clips_this_window=1)
    assert hit.intend
    assert hit.reason == "repeat_pair"
    assert len(hit.orders) == 2
    dear = decide_repeat(0.49, 0.48, 30, 30, filled_this_window=True, clips_this_window=1)
    assert not dear.intend
    cap = decide_repeat(0.40, 0.55, 30, 30, filled_this_window=True, clips_this_window=8)
    assert not cap.intend
    assert cap.reason == "repeat_clip_cap"
    inv = BookInventory()
    inv.apply_buy("Up", 10, 0.40)
    hold_ok = decide_repeat(0.50, 0.55, 30, 30, inv, filled_this_window=True, clips_this_window=1)
    assert hold_ok.intend
    hold_no = decide_repeat(0.50, 0.57, 30, 30, inv, filled_this_window=True, clips_this_window=1)
    assert not hold_no.intend
    assert hold_no.reason == "repeat_above_pair_max"
