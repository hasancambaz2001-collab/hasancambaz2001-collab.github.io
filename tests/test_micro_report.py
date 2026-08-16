from whiskas.micro_report import build_24h, render_24h_md


def test_24h_null_real_fill_when_not_sent() -> None:
    payload = build_24h(auth_reason="AUTH_ABSENT", sent=False, halted_on_loss=False, clip=5)
    assert payload["sent"] is False
    assert payload["real_fill_rate"] is None
    assert payload["net_pnl_usd"] is None
    assert payload["hit_max_daily_loss"] is False
    assert payload["pair_gt_1_trade"] == 0
    assert payload["clip"] == 5
    md = render_24h_md(payload)
    assert "real_fill_rate | null" in md
    assert "any pair>1 trade? | 0" in md
    assert "micro trial ≠ full live" in md
