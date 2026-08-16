from datetime import datetime, timezone
from pathlib import Path

from whiskas.paper import best_ask, snapshot_window, summarize_paper, tokens_from_market


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
    rec = snapshot_window(now=1786886400, tokens=tokens, books=books_cheap)
    assert rec["intend"] is True
    assert rec["live_order"] is False
    assert rec["maker_bid"] is False
    assert rec["ask_sum"] is not None and abs(rec["ask_sum"] - 0.95) < 1e-12
    assert rec["depth_ok"] is True
    assert all(o["side"] == "BUY" and o["type"] == "FOK" for o in rec["orders"])

    books_dear = {
        "Up": {"asks": [{"price": "0.49", "size": "30"}]},
        "Down": {"asks": [{"price": "0.48", "size": "30"}]},
    }
    skip = snapshot_window(now=1786886400, tokens=tokens, books=books_dear)
    assert skip["intend"] is False
    assert skip["orders"] == []


def test_summarize_counts_le096_and_depth() -> None:
    rows = [
        {"ts": "2026-08-16T20:00:00+00:00", "ask_sum": 1.01, "depth_up": 100, "depth_down": 100},
        {"ts": "2026-08-16T21:00:00+00:00", "ask_sum": 0.95, "depth_up": 30, "depth_down": 30},
        {"ts": "2026-08-16T22:00:00+00:00", "ask_sum": 0.94, "depth_up": 10, "depth_down": 40},
        {"ts": "2026-08-16T12:00:00+00:00", "ask_sum": 0.90, "depth_up": 50, "depth_down": 50},
    ]
    since = datetime(2026, 8, 16, 19, 0, tzinfo=timezone.utc)
    stats = summarize_paper(rows, since=since, pair_max=0.96, clip=21)
    assert stats["n_poll"] == 3
    assert stats["n_le_096"] == 2
    assert stats["n_le_096_depth_ge_clip"] == 1
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
