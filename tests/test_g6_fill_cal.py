from pathlib import Path

from scripts.g6_fill_cal import analyze


def test_g6_counts_and_does_not_pass() -> None:
    rows = [
        {"book": "maker", "ts": "2026-08-16T17:00:00+00:00", "reason": "rest", "live_order": False},
        {"book": "maker", "ts": "2026-08-16T17:00:02+00:00", "reason": "rich_bid_sum", "live_order": False},
        {"book": "maker", "ts": "2026-08-16T17:00:04+00:00", "reason": "filled_both", "live_order": False},
        {"book": "maker", "ts": "2026-08-15T17:00:00+00:00", "reason": "rest", "live_order": False},
    ]
    stats = analyze(rows)
    assert stats["rests"] == 2
    assert stats["skips"] == 1
    assert stats["fill_sim"] == 1
    assert abs(stats["fill_pct"] - 0.5) < 1e-12
    assert stats["g6_flag_written"] is False
    assert stats["g6_pass"] is False
    assert stats["live_order"] is False
    assert stats["worst_day"]["day"] == "2026-08-15"
    src = Path("scripts/g6_fill_cal.py").read_text()
    assert "Does NOT write the G6 flag" in src
    assert "G6_FLAG.write" not in src
