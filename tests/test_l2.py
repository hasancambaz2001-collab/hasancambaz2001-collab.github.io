from pathlib import Path

from whiskas.l2 import (
    BookTick,
    PolicyMaker,
    REGIME_PRE,
    action_bucket,
    decide_maker,
    regime_for_ts,
)


def test_policy_maker_rest_replace_cancel_rich() -> None:
    pm = PolicyMaker(pair_max=0.90, cancel_above=0.92, clip=10, fill="residual")
    cheap = BookTick(t=1000, slug="btc-updown-5m-1", asset="btc", tf="5m", t0=1, bu=0.40, bd=0.48, au=0.42, ad=0.50, su=12, sd=15)
    rec, state = pm.step(cheap, None)
    assert rec["reason"] == "rest"
    assert rec["live_order"] is False
    assert rec["size_ok"] is False
    assert rec["pair_gt_1"] is False
    moved = BookTick(t=1002, slug=cheap.slug, asset="btc", tf="5m", t0=1, bu=0.41, bd=0.48, au=0.43, ad=0.50, su=20, sd=20)
    rec2, state2 = pm.step(moved, state)
    assert rec2["reason"] == "requote"
    assert action_bucket(rec2["reason"]) == "replace"
    rich = BookTick(t=1004, slug=cheap.slug, asset="btc", tf="5m", t0=1, bu=0.47, bd=0.46, au=0.48, ad=0.47, su=20, sd=20)
    rec3, state3 = pm.step(rich, state2)
    assert rec3["reason"] == "rich_cancel"
    assert rec3["cancel"] is True
    assert state3 is None


def test_fill_none_never_completes() -> None:
    pm = PolicyMaker(fill="none", clip=10)
    rest = BookTick(t=1000, slug="s", asset="btc", tf="5m", t0=1, bu=0.40, bd=0.48, au=0.42, ad=0.50, su=20, sd=20)
    _, state = pm.step(rest, None)
    eaten = BookTick(t=1002, slug="s", asset="btc", tf="5m", t0=1, bu=0.38, bd=0.48, au=0.39, ad=0.49, su=20, sd=20)
    rec, _ = pm.step(eaten, state)
    assert rec["complete"] is False
    assert rec["reason"] != "complete"


def test_never_complete_pair_gt_1() -> None:
    rec, state = decide_maker(
        bid_up=0.40,
        bid_down=0.48,
        bid_sz_up=20,
        bid_sz_down=20,
        ask_up=0.42,
        ask_down=0.50,
        state=None,
        now=1000.0,
        t0=1,
        clip=10,
        fill="residual",
    )
    rec2, _ = decide_maker(
        bid_up=0.38,
        bid_down=0.48,
        bid_sz_up=20,
        bid_sz_down=20,
        ask_up=0.39,
        ask_down=0.70,
        state=state,
        now=1002.0,
        t0=1,
        clip=10,
        fill="residual",
    )
    assert rec["reason"] == "rest"
    assert rec2["complete"] is False
    assert rec2["pair_gt_1"] is False
    assert rec2["reason"] in {"rich_complete", "pair_gt_1"}


def test_booktick_parquet_and_jsonl_roundtrip() -> None:
    tick = BookTick.from_parquet_row(
        t=1774390200,
        bu=0.40,
        bd=0.48,
        au=0.42,
        ad=0.50,
        su=11,
        sd=12,
        sau=9,
        sad=8,
        condition_id="0xabc",
        slug="btc-updown-5m-1774390200",
        asset="btc",
    )
    assert tick.bid_sum is not None and abs(tick.bid_sum - 0.88) < 1e-12
    rec = tick.to_record()
    back = BookTick.from_record(rec)
    assert back.slug == tick.slug
    assert back.bu == 0.40
    assert regime_for_ts(tick.t) == REGIME_PRE


def test_no_live_and_size_ok_false() -> None:
    assert "create_order" not in Path("scripts/l2_recorder.py").read_text()
    assert "create_order" not in Path("scripts/twin_l2.py").read_text()
    assert "create_order" not in Path("whiskas/l2.py").read_text()
    yaml = Path("configs/l2.yaml").read_text()
    assert "size_ok: false" in yaml
    assert "pair_max: 0.90" in yaml
    assert Path("configs/size_schedule.yaml").read_text().count("size_ok: false") >= 1
