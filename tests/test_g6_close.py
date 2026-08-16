from pathlib import Path

from scripts.g6_close import N_REST_MIN, analyze_layers, write_closed


def _row(reason: str, **extra):
    rec = {
        "book": "maker",
        "ts": "2026-08-16T19:00:00+00:00",
        "reason": reason,
        "live_order": False,
        "pair_gt_1_trade": False,
        "real_fill": None,
        "real_fill_rate": None,
    }
    rec.update(extra)
    return rec


def test_pass_on_rest_count_even_if_still250_absent(tmp_path: Path) -> None:
    rows = [_row("rest") for _ in range(N_REST_MIN)] + [_row("rich_bid_sum", skip_reason="rich_bid_sum")]
    stats = analyze_layers(rows)
    assert stats["n_rest"] == N_REST_MIN
    assert stats["still250_absent"] is True
    assert stats["real_fill_rate"] is None
    assert stats["pair_gt_1_trade"] is False
    assert stats["g6_pass"] is True
    out = write_closed(stats, root=tmp_path, write_flag=True)
    assert out["g6_flag_written"] is True
    text = (tmp_path / "data" / "reports" / "G6_CLOSED.md").read_text()
    assert "| n_rest |" in text
    assert "ABSENT" in text
    assert "still250_absent" in text
    assert "null" in text
    assert not (tmp_path / "configs" / "generated" / "LIVE_READY.yaml").is_file()


def test_fail_below_100_rests(tmp_path: Path) -> None:
    rows = [_row("rest") for _ in range(20)] + [_row("thin_bid", skip_reason="thin_bid")]
    stats = analyze_layers(rows)
    assert stats["g6_pass"] is False
    write_closed(stats, root=tmp_path, write_flag=True)
    assert not (tmp_path / "data" / "ops" / "G6_fill_calibrated.flag").is_file()


def test_never_mix_sim_and_real() -> None:
    rows = [
        _row("rest", still_there_250ms=True, still250=True),
        _row("filled_both"),
        _row("rich_bid_sum", skip_reason="rich_bid_sum"),
    ]
    stats = analyze_layers(rows)
    assert stats["sim_fill_label"] == "SIM"
    assert stats["real_fill_rate"] is None
    src = Path("scripts/g6_close.py").read_text()
    assert "Never mix" in src
    assert "hours not a gate" in src
