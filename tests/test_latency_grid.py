from pathlib import Path

import scripts.paper_maker as paper_maker_mod
from scripts.paper_maker import _probe_still250, snapshot_maker
from whiskas.latency_grid import (
    V1,
    V2,
    BookAgeCache,
    current_variant,
    infer_variant,
    percentile,
    rank_variants,
    summarize_ms,
)


def test_current_variant_env_and_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("LATENCY_VARIANT", raising=False)
    monkeypatch.setattr("whiskas.latency_grid.VARIANT_FILE", tmp_path / "LATENCY_VARIANT")
    assert current_variant() == V1
    (tmp_path / "LATENCY_VARIANT").write_text("v2_ws_age\n", encoding="utf-8")
    assert current_variant() == V2
    monkeypatch.setenv("LATENCY_VARIANT", "v1")
    assert current_variant() == V1


def test_percentile_and_summarize() -> None:
    assert percentile([], 50) is None
    assert percentile([10], 95) == 10
    assert abs(float(percentile([10, 20, 30, 40], 50) or 0) - 25.0) < 1e-12
    summary = summarize_ms([100, 200, 300])
    assert summary["n"] == 3
    assert summary["p50"] == 200


def test_book_age_fresh_and_stale() -> None:
    cache = BookAgeCache()
    cache._handle(
        {
            "event_type": "book",
            "asset_id": "u",
            "bids": [{"price": "0.40", "size": "12"}],
            "asks": [{"price": "0.42", "size": "12"}],
        }
    )
    cache._handle(
        {
            "event_type": "book",
            "asset_id": "d",
            "bids": [{"price": "0.48", "size": "12"}],
            "asks": [{"price": "0.50", "size": "12"}],
        }
    )
    fresh = cache.fresh_books("u", "d", max_age_sec=0.25)
    assert fresh is not None
    assert fresh["Up"]["bids"][0]["price"] == "0.40"
    cache._recv_ts["u"] = cache._recv_ts["u"] - 1.0
    assert cache.fresh_books("u", "d", max_age_sec=0.25) is None


def test_v2_skips_sleep_when_ws_age_ok(monkeypatch) -> None:
    class Cache:
        def fresh_books(self, *_a, **_k):
            return {
                "Up": {"bids": [{"price": "0.40", "size": "12"}], "asks": [{"price": "0.42", "size": "12"}]},
                "Down": {"bids": [{"price": "0.48", "size": "12"}], "asks": [{"price": "0.50", "size": "12"}]},
                "age_up_ms": 40.0,
                "age_down_ms": 41.0,
            }

    def boom(*_a, **_k):
        raise AssertionError("v2 must not sleep when WS age ≤250ms")

    monkeypatch.setattr(paper_maker_mod.time, "sleep", boom)
    out = _probe_still250(
        tokens={"Up": "u", "Down": "d"},
        clip=5,
        pair_max=0.90,
        latency_variant=V2,
        book_cache=Cache(),
    )
    assert out is not None
    assert out["still250_source"] == "ws_age"
    assert out["still_there_250ms"] is True
    assert out["bid_sum_250"] == 0.88
    assert out["book_age_up_ms"] == 40.0


def test_v2_fallback_sleeps_when_stale(monkeypatch) -> None:
    slept = {"n": 0}

    def fake_sleep(_s):
        slept["n"] += 1

    monkeypatch.setattr(paper_maker_mod.time, "sleep", fake_sleep)
    monkeypatch.setattr(
        paper_maker_mod,
        "fetch_books_parallel",
        lambda *_a, **_k: (
            {"bids": [{"price": "0.40", "size": "12"}], "asks": [{"price": "0.42", "size": "12"}]},
            {"bids": [{"price": "0.48", "size": "12"}], "asks": [{"price": "0.50", "size": "12"}]},
        ),
    )

    class Cache:
        def fresh_books(self, *_a, **_k):
            return None

    out = _probe_still250(
        tokens={"Up": "u", "Down": "d"},
        clip=5,
        pair_max=0.90,
        latency_variant=V2,
        book_cache=Cache(),
    )
    assert slept["n"] == 1
    assert out is not None
    assert out["still250_source"] == "rest_sleep_fallback"
    assert out["still_there_250ms"] is True


def test_injected_books_do_not_sleep(monkeypatch) -> None:
    def boom(*_a, **_k):
        raise AssertionError("injected books must not sleep")

    monkeypatch.setattr(paper_maker_mod.time, "sleep", boom)
    books = {
        "Up": {"bids": [{"price": "0.40", "size": "12"}], "asks": [{"price": "0.42", "size": "12"}]},
        "Down": {"bids": [{"price": "0.48", "size": "12"}], "asks": [{"price": "0.50", "size": "12"}]},
    }
    rec, _state = snapshot_maker(
        asset="btc",
        tf="5m",
        clip=5,
        tokens={"Up": "u", "Down": "d"},
        books=books,
        now=1786886400,
        latency_variant=V1,
    )
    assert rec["reason"] == "rest"
    assert rec["latency_variant"] == V1
    assert rec["still250_source"] == "injected"
    assert rec["would_send"] is True
    assert rec.get("send_blocked") is None


def test_rank_by_post_ack_and_rust_gate() -> None:
    rows = []
    for i in range(20):
        rows.append(
            {
                "reason": "rest",
                "intent": True,
                "latency_variant": V1,
                "still_ms": 250,
                "live_order": True,
                "post_ack_ms": 200 + i,
            }
        )
    for i in range(20):
        rows.append(
            {
                "reason": "rest",
                "intent": True,
                "latency_variant": V2,
                "still_ms": 20,
                "still250_source": "ws_age",
                "live_order": True,
                "post_ack_ms": 180 + i,
            }
        )
    result = rank_variants(rows)
    assert result["variants"][0]["variant"] == V2
    assert result["variants"][0]["post_ack_ms"]["p50"] is not None
    assert result["enough"][V1] is True
    assert result["enough"][V2] is True
    assert result["rust_sketch"] is False
    slow = [
        {
            "reason": "rest",
            "intent": True,
            "latency_variant": V1,
            "token_cache_hit": True,
            "live_order": True,
            "post_ack_ms": 600,
            "still_ms": 250,
        }
        for _ in range(20)
    ]
    slow_result = rank_variants(slow)
    assert slow_result["rust_sketch"] is True
    assert infer_variant({"token_cache_hit": False, "book_get_ms": 12}) == V1
    assert infer_variant({"reason": "rich_bid_sum"}) is None


def test_gates_and_clip_unchanged() -> None:
    src = Path("scripts/paper_maker.py").read_text(encoding="utf-8")
    live = Path("scripts/micro_live.py").read_text(encoding="utf-8")
    assert "apply_still250_send_gate" in src
    assert "PAIR_MAX = 0.90" in src
    assert "CLIP_DEFAULT = 10.0" in src
    assert "trial_clip" in live
    assert "MICRO_TRIAL_CLIP = 5.0" in live
    assert "pair_gt_1_trade" in live
