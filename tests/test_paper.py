from datetime import datetime, timezone
from pathlib import Path

from whiskas.paper import (
    asset_window_slug,
    best_ask,
    confirm_ask_exists,
    current_t0,
    snapshot_window,
    summarize_paper,
    tokens_from_market,
)
from whiskas.policy import BookInventory


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
    assert rec["tf"] == "5m"
    assert rec["slug"] == "eth-updown-5m-1786886400"
    assert rec["bucket_le_096"] is True
    assert rec["bucket_le_090"] is False
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
    assert rec["repeat_intend"] is False
    assert rec["clips_this_window"] == 1


def test_repeat_after_a_not_a_new_strategy() -> None:
    tokens = {"Up": "u", "Down": "d"}
    books = {
        "Up": {"asks": [{"price": "0.40", "size": "30"}]},
        "Down": {"asks": [{"price": "0.55", "size": "30"}]},
    }
    first = snapshot_window(now=1786886400, tokens=tokens, books=books, asset="btc")
    assert first["a_intend"] is True
    assert first["repeat_intend"] is False
    assert first["clips_this_window"] == 1
    inv = BookInventory()
    for order in first["a2_orders"]:
        inv.apply_buy(order["outcome"], order["size"], order["price"])
    again = snapshot_window(
        now=1786886400,
        tokens=tokens,
        books=books,
        asset="btc",
        inventory=inv,
        filled_this_window=True,
        clips_this_window=1,
    )
    assert again["a_intend"] is False
    assert again["a2_intend"] is False
    assert again["repeat_intend"] is True
    assert again["clips_this_window"] == 2
    cap = snapshot_window(
        now=1786886400,
        tokens=tokens,
        books=books,
        asset="btc",
        inventory=inv,
        filled_this_window=True,
        clips_this_window=8,
    )
    assert cap["repeat_intend"] is False
    assert cap["repeat_reason"] == "repeat_clip_cap"
    assert cap["clips_this_window"] == 8


def test_asset_slugs_share_clock() -> None:
    t0 = 1786886400
    assert asset_window_slug("btc", t0) == "btc-updown-5m-1786886400"
    assert asset_window_slug("eth", t0) == "eth-updown-5m-1786886400"
    assert asset_window_slug("sol", t0) == "sol-updown-5m-1786886400"
    assert asset_window_slug("xrp", t0) == "xrp-updown-5m-1786886400"
    assert current_t0(1786886400, tf="5m") == 1786886400
    assert current_t0(1786886400, tf="15m") == 1786886100
    assert current_t0(1786886400, tf="4h") == 1786881600
    assert asset_window_slug("btc", 1786886100, "15m") == "btc-updown-15m-1786886100"
    assert asset_window_slug("eth", 1786881600, "4h") == "eth-updown-4h-1786881600"


def test_15m_intends_same_rules() -> None:
    tokens = {"Up": "u", "Down": "d"}
    books = {
        "Up": {"asks": [{"price": "0.40", "size": "30"}]},
        "Down": {"asks": [{"price": "0.48", "size": "30"}]},
    }
    rec = snapshot_window(now=1786886400, tokens=tokens, books=books, asset="sol", tf="15m")
    assert rec["tf"] == "15m"
    assert rec["slug"] == "sol-updown-15m-1786886100"
    assert rec["poll_only"] is False
    assert rec["a_intend"] is True
    assert rec["ask_sum"] is not None and abs(rec["ask_sum"] - 0.88) < 1e-12
    assert rec["bucket_le_090"] is True
    assert rec["bucket_le_096"] is True
    dear = {
        "Up": {"asks": [{"price": "0.50", "size": "30"}]},
        "Down": {"asks": [{"price": "0.51", "size": "30"}]},
    }
    skip = snapshot_window(now=1786886400, tokens=tokens, books=dear, asset="sol", tf="15m")
    assert skip["a_intend"] is False
    assert skip["repeat_intend"] is False
    assert skip["ask_sum"] is not None and skip["ask_sum"] > 1.00


def test_4h_is_poll_only() -> None:
    tokens = {"Up": "u", "Down": "d"}
    books = {
        "Up": {"asks": [{"price": "0.40", "size": "30"}]},
        "Down": {"asks": [{"price": "0.48", "size": "30"}]},
    }
    rec = snapshot_window(now=1786886400, tokens=tokens, books=books, asset="btc", tf="4h")
    assert rec["tf"] == "4h"
    assert rec["slug"] == "btc-updown-4h-1786881600"
    assert rec["poll_only"] is True
    assert rec["reason"] == "poll_only"
    assert rec["a_intend"] is False
    assert rec["a2_intend"] is False
    assert rec["repeat_intend"] is False
    assert rec["orders"] == []
    assert rec["ask_sum"] is not None and abs(rec["ask_sum"] - 0.88) < 1e-12
    assert rec["depth_ok"] is True
    assert rec["bucket_le_090"] is True
    assert rec["live_order"] is False


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
        {"ts": "2026-08-16T21:00:00+00:00", "asset": "eth", "ask_sum": 0.95, "depth_up": 30, "depth_down": 30, "still_there_250ms": True, "a_intend": True, "a2_intend": True, "repeat_intend": False, "clips_this_window": 1},
        {"ts": "2026-08-16T21:00:05+00:00", "asset": "eth", "ask_sum": 0.95, "depth_up": 30, "depth_down": 30, "still_there_250ms": True, "repeat_intend": True, "clips_this_window": 3},
        {"ts": "2026-08-16T22:00:00+00:00", "asset": "sol", "ask_sum": 0.94, "depth_up": 10, "depth_down": 40, "still_there_250ms": False},
        {"ts": "2026-08-16T12:00:00+00:00", "asset": "xrp", "ask_sum": 0.90, "depth_up": 50, "depth_down": 50},
    ]
    since = datetime(2026, 8, 16, 19, 0, tzinfo=timezone.utc)
    stats = summarize_paper(rows, since=since, pair_max=0.96, clip=21)
    assert stats["n_poll"] == 4
    assert stats["n_le_096"] == 3
    assert stats["n_a_hits"] == 1
    assert stats["n_a2_hits"] == 1
    assert stats["n_repeat_hits"] == 1
    assert stats["max_clips_on_hit"] == 3
    assert stats["n_le_096_depth_ge_clip"] == 2
    assert stats["n_still_there_250ms"] == 2
    assert stats["assets"]["eth"]["n_le_096"] == 2
    assert stats["assets"]["eth"]["n_repeat_hits"] == 1
    assert stats["assets"]["eth"]["max_clips_on_hit"] == 3
    assert stats["assets"]["eth"]["n_still_there_250ms"] == 2
    assert stats["assets"]["sol"]["n_le_096_depth_ge_clip"] == 0
    assert stats["paper_pass_if_zero_edge"] is False

    def cell(asset: str, tf: str, bucket: str) -> dict:
        for row in stats["table"]:
            if row["asset"] == asset and row["tf"] == tf and row["bucket"] == bucket:
                return row
        raise AssertionError(f"missing {asset} {tf} {bucket}")

    eth_096 = cell("eth", "5m", "0.96")
    assert eth_096["polls"] == 2
    assert eth_096["A_hits"] == 1
    assert eth_096["A2_hits"] == 1
    assert eth_096["repeat_hits"] == 1
    assert eth_096["depth_ok"] == 2
    assert eth_096["still250"] == 2
    eth_090 = cell("eth", "5m", "0.90")
    assert eth_090["polls"] == 2
    assert eth_090["A_hits"] == 0
    assert eth_090["depth_ok"] == 0
    sol_096 = cell("sol", "5m", "0.96")
    assert sol_096["depth_ok"] == 0
    assert cell("btc", "15m", "0.96")["polls"] == 0
    assert cell("btc", "4h", "0.96")["polls"] == 0
    zero = summarize_paper(rows[:1], pair_max=0.96, clip=21)
    assert zero["n_le_096"] == 0
    assert zero["paper_pass_if_zero_edge"] is True


def test_summarize_buckets_and_4h_zero_hits() -> None:
    rows = [
        {"ts": "2026-08-16T21:00:00+00:00", "asset": "btc", "tf": "5m", "ask_sum": 0.88, "depth_ok": True, "a_intend": True, "a2_intend": True, "repeat_intend": False, "still_there_250ms": True},
        {"ts": "2026-08-16T21:00:01+00:00", "asset": "btc", "tf": "15m", "ask_sum": 0.94, "depth_ok": True, "a_intend": True, "a2_intend": False, "still_there_250ms": False},
        {"ts": "2026-08-16T21:00:02+00:00", "asset": "btc", "tf": "4h", "ask_sum": 0.88, "depth_ok": True, "a_intend": False, "a2_intend": False, "repeat_intend": False, "still_there_250ms": True, "poll_only": True},
        {"ts": "2026-08-16T21:00:03+00:00", "asset": "eth", "tf": "5m", "ask_sum": 1.02, "depth_ok": True, "a_intend": False},
    ]
    stats = summarize_paper(rows, pair_max=0.96, clip=21)
    by = {(r["asset"], r["tf"], r["bucket"]): r for r in stats["table"]}
    assert by[("btc", "5m", "0.90")]["A_hits"] == 1
    assert by[("btc", "5m", "0.90")]["A2_hits"] == 1
    assert by[("btc", "5m", "0.90")]["depth_ok"] == 1
    assert by[("btc", "5m", "0.90")]["still250"] == 1
    assert by[("btc", "15m", "0.90")]["A_hits"] == 0
    assert by[("btc", "15m", "0.96")]["A_hits"] == 1
    assert by[("btc", "15m", "0.96")]["depth_ok"] == 1
    assert by[("btc", "4h", "0.90")]["A_hits"] == 0
    assert by[("btc", "4h", "0.90")]["A2_hits"] == 0
    assert by[("btc", "4h", "0.90")]["repeat_hits"] == 0
    assert by[("btc", "4h", "0.90")]["depth_ok"] == 1
    assert by[("btc", "4h", "0.90")]["still250"] == 1
    assert by[("eth", "5m", "0.96")]["A_hits"] == 0
    assert by[("eth", "5m", "0.96")]["depth_ok"] == 0


def test_paper_is_get_only() -> None:
    src = Path("whiskas/paper.py").read_text(encoding="utf-8")
    script = Path("scripts/paper_whiskas.py").read_text(encoding="utf-8")
    blob = src + "\n" + script
    assert "get_json(" in src
    assert "urlopen" not in blob
    assert "Request(" not in blob
    assert "create_order" not in blob
    assert "post_order" not in blob
