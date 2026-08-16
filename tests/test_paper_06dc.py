import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.paper_06dc import (
    daily_slug,
    decide_complete_set,
    list_targets,
    snapshot_market,
    summarize_06dc,
)


def test_daily_slug() -> None:
    day = datetime(2026, 8, 16, tzinfo=timezone.utc)
    assert daily_slug("bitcoin", day) == "bitcoin-up-or-down-on-august-16-2026"
    assert daily_slug("xrp", day) == "xrp-up-or-down-on-august-16-2026"
    targets = list_targets(now=day, extra_days=1)
    slugs = {t["slug"] for t in targets}
    assert "ethereum-up-or-down-on-august-17-2026" in slugs
    assert len(targets) == 8


def test_intend_both_legs_only_when_pair_lt_1() -> None:
    hit = decide_complete_set(0.40, 0.55, 25, 25, clip=20)
    assert hit["intend"] is True
    assert len(hit["orders"]) == 2
    assert all(o["side"] == "BUY" and o["type"] == "FOK" and o["size"] == 20 for o in hit["orders"])
    assert {o["outcome"] for o in hit["orders"]} == {"Up", "Down"}

    assert decide_complete_set(0.50, 0.50, 25, 25, clip=20)["intend"] is False
    assert decide_complete_set(0.50, 0.50, 25, 25, clip=20)["reason"] == "pair_ge_1"
    assert decide_complete_set(0.51, 0.50, 25, 25, clip=20)["reason"] == "pair_ge_1"
    assert decide_complete_set(0.40, None, 25, 0, clip=20)["intend"] is False
    assert decide_complete_set(None, 0.49, 0, 25, clip=20)["reason"] == "missing_ask"
    assert decide_complete_set(0.40, 0.55, 19, 40, clip=20)["reason"] == "depth_short"


def test_snapshot_blocks_single_leg_and_pair_ge_1() -> None:
    tokens = {"Up": "u", "Down": "d"}
    target = {"asset": "btc", "day": "2026-08-16", "slug": "bitcoin-up-or-down-on-august-16-2026"}
    cheap = {
        "Up": {"asks": [{"price": "0.40", "size": "20"}]},
        "Down": {"asks": [{"price": "0.55", "size": "20"}]},
    }
    rec = snapshot_market(target, clip=20, tokens=tokens, books=cheap)
    assert rec["intend"] is True
    assert rec["live_order"] is False
    assert rec["atm_directional"] is False
    assert rec["book"] == "06dc"

    dear = {
        "Up": {"asks": [{"price": "0.50", "size": "20"}]},
        "Down": {"asks": [{"price": "0.51", "size": "20"}]},
    }
    skip = snapshot_market(target, clip=20, tokens=tokens, books=dear)
    assert skip["intend"] is False
    assert skip["orders"] == []
    assert skip["ask_sum"] is not None and skip["ask_sum"] > 1.0

    one = {
        "Up": {"asks": [{"price": "0.49", "size": "50"}]},
        "Down": {"asks": []},
    }
    atm = snapshot_market(target, clip=20, tokens=tokens, books=one)
    assert atm["intend"] is False
    assert atm["orders"] == []


def test_summarize_and_script_is_get_only() -> None:
    rows = [
        {"ts": "2026-08-16T16:00:00+00:00", "asset": "btc", "day": "2026-08-16", "ask_sum": 0.97, "intend": True, "depth_ok": True, "still_there_250ms": True},
        {"ts": "2026-08-16T16:01:00+00:00", "asset": "btc", "day": "2026-08-16", "ask_sum": 1.02, "intend": False, "depth_ok": True},
        {"ts": "2026-08-16T12:00:00+00:00", "asset": "eth", "day": "2026-08-16", "ask_sum": 0.90, "intend": True},
    ]
    since = datetime(2026, 8, 16, 15, 0, tzinfo=timezone.utc)
    stats = summarize_06dc(rows, since=since, clip=20)
    assert stats["n_poll"] == 2
    assert stats["n_intend"] == 1
    assert stats["table"][0]["n_lt_1"] == 1
    assert stats["table"][0]["n_ge_1"] == 1
    src = Path("scripts/paper_06dc.py").read_text(encoding="utf-8")
    assert "get_json" in src or "fetch_book" in src
    assert "create_order" not in src
    assert "post_order" not in src
    assert "data/paper/intended.jsonl" in src  # refuse path
