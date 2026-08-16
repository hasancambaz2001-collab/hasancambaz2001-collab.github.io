from datetime import datetime, timezone
from pathlib import Path

from whiskas.paper import (
    asset_window_slug,
    best_ask,
    confirm_ask_exists,
    snapshot_window,
    summarize_paper,
    tokens_from_market,
)


def test_best_ask_is_min_price_not_first_row() -> None:
    book = {
        "asks": [
            {"price": "0.62", "size": "100"},
            {"price": "0.51", "size": "8"},
            {"price": "0.51", "size": "13"},
            {"price": "0.70", "size": "9"},
        ]
    }
    price, size = best_ask(book)
    assert price == 0.51
    assert size == 21.0


def test_tokens_from_gamma_market() -> None:
    market = {
        "outcomes": '["Up", "Down"]',
        "clobTokenIds": '["111", "222"]',
    }
    assert tokens_from_market(market) == {"Up": "111", "Down": "222"}


def test_snapshot_intends_only_when_sum_le_096() -> None:
    tokens = {"Up": "u", "Down": "d"}
    books_cheap = {
        "Up": {"asks": [{"price": "0.40", "size": "30"}]},
        "Down": {"asks": [{"price": "0.55", "size": "30"}]},
    }
    rec = snapshot_window(now=1786886400, tokens=tokens, books=books_cheap, asset="eth")
    assert rec["intend"] is True
    assert rec["a_intend"] is True
    assert rec["a2_intend"] is True
    assert rec["asset"] == "eth"
    assert rec["slug"] == "eth-updown-5m-1786886400"
    assert rec["live_order"] is False
    assert rec["maker_bid"] is False
    assert rec["ask_sum"] is not None and abs(rec["ask_sum"] - 0.95) < 1e-12
    assert rec["depth_ok"] is True
    assert rec["still_there_250ms"] is None
    assert all(o["side"] == "BUY" and o["type"] == "FOK" for o in rec["orders"])

    books_dear = {
        "Up": {"asks": [{"price": "0.49", "size": "30"}]},
        "Down": {"asks": [{"price": "0.48", "size": "30"}]},
    }
    skip = snapshot_window(now=1786886400, tokens=tokens, books=books_dear, asset="sol")
    assert skip["intend"] is False
    assert skip["orders"] == []
    assert skip["asset"] == "sol"


def test_intend_requires_depth_ge_clip() -> None:
    tokens = {"Up": "u", "Down": "d"}
    thin = {
        "Up": {"asks": [{"price": "0.40", "size": "10"}]},
        "Down": {"asks": [{"price": "0.55", "size": "40"}]},
    }
    rec = snapshot_window(now=1786886400, tokens=tokens, books=thin, asset="xrp")
    assert rec["ask_sum"] is not None and rec["ask_sum"] < 0.96
    assert rec["a_intend"] is False
    assert rec["intend"] is False
    assert rec["a2_intend"] is True
    assert rec["a2_reason"] == "a2_first_leg"
    assert rec["a2_orders"][0]["outcome"] == "Up"
    assert rec["a2_orders"][0]["size"] == 10.0


def test_asset_slugs_share_clock() -> None:
    t0 = 1786886400
    assert asset_window_slug("btc", t0) == "btc-updown-5m-1786886400"
    assert asset_window_slug("eth", t0) == "eth-updown-5m-1786886400"
    assert asset_window_slug("sol", t0) == "sol-updown-5m-1786886400"
    assert asset_window_slug("xrp", t0) == "xrp-updown-5m-1786886400"


def test_confirm_ask_still_there() -> None:
    tokens = {"Up": "u", "Down": "d"}
    books_ok = {
        "Up": {"asks": [{"price": "0.40", "size": "21"}]},
        "Down": {"asks": [{"price": "0.55", "size": "21"}]},
    }
    assert confirm_ask_exists(tokens, 0.40, 0.55, 21, books=books_ok) is True
    books_gone = {
        "Up": {"asks": [{"price": "0.41", "size": "100"}]},
        "Down": {"asks": [{"price": "0.55", "size": "21"}]},
    }
    assert confirm_ask_exists(tokens, 0.40, 0.55, 21, books=books_gone) is False


def test_summarize_counts_le096_and_depth() -> None:
    rows = [
        {"ts": "2026-08-16T20:00:00+00:00", "asset": "btc", "ask_sum": 1.01, "depth_up": 100, "depth_down": 100},
        {"ts": "2026-08-16T21:00:00+00:00", "asset": "eth", "ask_sum": 0.95, "depth_up": 30, "depth_down": 30, "still_there_250ms": True, "a_intend": True, "a2_intend": True},
        {"ts": "2026-08-16T22:00:00+00:00", "asset": "sol", "ask_sum": 0.94, "depth_up": 10, "depth_down": 40, "still_there_250ms": False},
        {"ts": "2026-08-16T12:00:00+00:00", "asset": "xrp", "ask_sum": 0.90, "depth_up": 50, "depth_down": 50},
    ]
    since = datetime(2026, 8, 16, 19, 0, tzinfo=timezone.utc)
    stats = summarize_paper(rows, since=since, pair_max=0.96, clip=21)
    assert stats["n_poll"] == 3
    assert stats["n_le_096"] == 2
    assert stats["n_a_hits"] == 1
    assert stats["n_a2_hits"] == 1
    assert stats["n_le_096_depth_ge_clip"] == 1
    assert stats["n_still_there_250ms"] == 1
    assert stats["assets"]["eth"]["n_le_096"] == 1
    assert stats["assets"]["eth"]["n_still_there_250ms"] == 1
    assert stats["assets"]["sol"]["n_le_096_depth_ge_clip"] == 0
    assert stats["paper_pass_if_zero_edge"] is False
    zero = summarize_paper(rows[:1], pair_max=0.96, clip=21)
    assert zero["n_le_096"] == 0
    assert zero["paper_pass_if_zero_edge"] is True


def test_paper_is_get_only() -> None:
    src = Path("whiskas/paper.py").read_text(encoding="utf-8")
    script = Path("scripts/paper_whiskas.py").read_text(encoding="utf-8")
    blob = src + "\n" + script
    assert "get_json(" in src
    assert "urlopen" not in blob
    assert "Request(" not in blob
    assert "create_order" not in blob
    assert "post_order" not in blob
