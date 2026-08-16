import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.paper_06dc import (
    R6_BID_MAX,
    daily_slug,
    decide_06dc,
    in_rule_band,
    keep_monthly_event,
    snapshot_market,
    summarize_06dc,
)


def test_daily_slugs() -> None:
    day = datetime(2026, 8, 16, tzinfo=timezone.utc)
    assert daily_slug("bitcoin", day, "up-or-down") == "bitcoin-up-or-down-on-august-16-2026"
    assert daily_slug("xrp", day, "price") == "xrp-price-on-august-16-2026"
    assert daily_slug("ethereum", day, "above") == "ethereum-above-on-august-16-2026"


def test_monthly_enddate_filter() -> None:
    now = datetime(2026, 8, 16, tzinfo=timezone.utc)
    keep = {"title": "What price will Bitcoin hit in August?", "slug": "what-price-will-bitcoin-hit-in-august-2026", "endDate": "2026-09-01T04:00:00Z"}
    drop_far = {"title": "What price will Bitcoin hit in 2026?", "slug": "what-price-will-bitcoin-hit-before-2027", "endDate": "2027-01-01T05:00:00Z"}
    drop_old = {"title": "What price will Bitcoin hit in July?", "slug": "what-price-will-bitcoin-hit-in-july-2026", "endDate": "2026-08-01T04:00:00Z"}
    assert keep_monthly_event(keep, now) is True
    assert keep_monthly_event(drop_far, now) is False
    assert keep_monthly_event(drop_old, now) is False
    august_far = {"title": "Bitcoin August 2027", "slug": "x", "endDate": "2027-01-01T05:00:00Z"}
    assert keep_monthly_event(august_far, now) is True


def test_r1_r3_r4_r5_r6_and_locks() -> None:
    lock = decide_06dc(kind="bracket", yes_ask=0.995, no_ask=0.01, yes_bid=0.99, no_bid=0.001, depth_yes=50, depth_no=50)
    assert lock["resolved_lock"] is True
    assert lock["taker_intend"] is False

    r1 = decide_06dc(kind="bracket", yes_ask=0.02, no_ask=0.99, yes_bid=0.01, no_bid=0.98, depth_yes=5, depth_no=25)
    assert r1["r1"] is True and r1["taker_intend"] is True
    assert r1["orders"][0]["outcome"] == "No"

    r1y = decide_06dc(kind="monthly", yes_ask=0.975, no_ask=0.04, yes_bid=0.97, no_bid=0.03, depth_yes=25, depth_no=25)
    assert r1y["r1"] is True and r1y["orders"][0]["outcome"] == "Yes"

    r3 = decide_06dc(kind="daily_ud", yes_ask=0.40, no_ask=0.55, yes_bid=0.39, no_bid=0.54, depth_yes=21, depth_no=21)
    assert r3["r3"] is True and len(r3["orders"]) == 2
    assert r3["ask_sum"] is not None and abs(r3["ask_sum"] - 0.95) < 1e-12

    both_dear = decide_06dc(kind="daily_ud", yes_ask=0.51, no_ask=0.50, yes_bid=0.50, no_bid=0.49, depth_yes=21, depth_no=21)
    assert both_dear["taker_intend"] is False
    assert both_dear["r3"] is False
    assert both_dear["ask_sum"] > 1.0

    r4 = decide_06dc(kind="monthly", yes_ask=0.79, no_ask=0.22, yes_bid=0.78, no_bid=0.21, depth_yes=20, depth_no=20)
    assert r4["r4"] is True and r4["orders"][0]["outcome"] == "Yes"
    daily_no_r4 = decide_06dc(kind="daily_ud", yes_ask=0.79, no_ask=0.22, yes_bid=0.78, no_bid=0.21, depth_yes=20, depth_no=20)
    assert daily_no_r4["r4"] is False

    r5 = decide_06dc(kind="bracket", yes_ask=0.22, no_ask=0.79, yes_bid=0.21, no_bid=0.78, depth_yes=20, depth_no=20)
    assert r5["r5"] is True and r5["orders"][0]["outcome"] == "No"

    r6 = decide_06dc(kind="bracket", yes_ask=0.50, no_ask=0.51, yes_bid=0.48, no_bid=0.49, depth_yes=20, depth_no=20)
    assert r6["r6"] is True and r6["maker_intend"] is True
    assert r6["atm_watch"] is True
    assert r6["taker_intend"] is False
    assert r6["bid_sum"] is not None and abs(r6["bid_sum"] - 0.97) < 1e-12

    monthly_atm = decide_06dc(kind="monthly", yes_ask=0.50, no_ask=0.51, yes_bid=0.48, no_bid=0.49, depth_yes=20, depth_no=20)
    assert monthly_atm["r6"] is False
    assert monthly_atm["atm_watch"] is True
    assert monthly_atm["taker_intend"] is False

    daily_atm_099 = decide_06dc(
        kind="daily_ud", yes_ask=0.50, no_ask=0.51, yes_bid=0.50, no_bid=0.49, depth_yes=20, depth_no=20
    )
    assert daily_atm_099["ask_sum"] is not None and daily_atm_099["ask_sum"] > 0.96
    assert daily_atm_099["bid_sum"] is not None and abs(daily_atm_099["bid_sum"] - 0.99) < 1e-12
    assert daily_atm_099["r6"] is True and daily_atm_099["maker_intend"] is True
    assert daily_atm_099["atm_watch"] is True
    assert daily_atm_099["taker_intend"] is False
    assert daily_atm_099["r4"] is False and daily_atm_099["r5"] is False

    daily_atm_100 = decide_06dc(
        kind="daily_ud", yes_ask=0.50, no_ask=0.51, yes_bid=0.50, no_bid=0.50, depth_yes=20, depth_no=20
    )
    assert daily_atm_100["r6"] is False
    assert daily_atm_100["maker_intend"] is False
    assert daily_atm_100["atm_watch"] is True
    assert daily_atm_100["taker_intend"] is False
    assert daily_atm_100["reason"] == "atm_watch"


def test_snapshot_no_live_and_injected_books() -> None:
    target = {
        "kind": "bracket",
        "asset": "btc",
        "day": "2026-08-18",
        "event_slug": "bitcoin-price-on-august-18-2026",
        "market_slug": "bitcoin-price-between-62k-64k",
        "question": "between",
        "tokens": {"Yes": "y", "No": "n"},
        "gamma_yes": 0.64,
    }
    books = {
        "Yes": {"asks": [{"price": "0.64", "size": "30"}], "bids": [{"price": "0.63", "size": "30"}]},
        "No": {"asks": [{"price": "0.37", "size": "30"}], "bids": [{"price": "0.34", "size": "30"}]},
    }
    rec = snapshot_market(target, clip=20, books=books)
    assert rec["live_order"] is False
    assert rec["r4"] is False
    assert rec["r6"] is True
    assert rec["maker_intend"] is True
    assert rec["bid_sum"] is not None and abs(rec["bid_sum"] - 0.97) < 1e-12
    assert rec["atm_watch"] is True


def test_in_band_and_summary() -> None:
    assert in_rule_band(0.22, "monthly") is True
    assert in_rule_band(0.79, "bracket") is True
    assert in_rule_band(0.50, "bracket") is True
    assert in_rule_band(0.995, "bracket") is False
    assert in_rule_band(0.50, "daily_ud") is True
    rows = [
        {"ts": "2026-08-16T16:00:00+00:00", "kind": "monthly", "r4": True, "taker_intend": True},
        {"ts": "2026-08-16T16:01:00+00:00", "kind": "bracket", "r5": True, "taker_intend": True},
        {"ts": "2026-08-16T16:02:00+00:00", "kind": "bracket", "r6": True, "maker_intend": True, "atm_watch": True},
        {"ts": "2026-08-16T12:00:00+00:00", "kind": "daily_ud", "r1": True, "taker_intend": True},
    ]
    since = datetime(2026, 8, 16, 15, 0, tzinfo=timezone.utc)
    stats = summarize_06dc(rows, since=since)
    assert stats["rows"] == 3
    assert stats["R4"] == 1 and stats["R5"] == 1 and stats["R6"] == 1
    assert stats["kinds"]["monthly"]["rows"] == 1
    src = Path("scripts/paper_06dc.py").read_text(encoding="utf-8")
    assert "create_order" not in src
    assert "post_order" not in src
    assert "data/paper/intended.jsonl" in src
    assert R6_BID_MAX == 0.99
    assert "R6_BID_MAX = 0.99" in src
    assert "R7" not in src or "no R7" in src.lower() or "Do not add R7" in Path("configs/06dc.yaml").read_text()
