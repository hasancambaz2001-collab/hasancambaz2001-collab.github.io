from whiskas.micro_report import build_24h, render_24h_md, signal_health


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
    assert payload["signal_health"]["verdict"] == "OK_rich_skips_only"


def test_signal_health_alarm_only_on_intent_without_order() -> None:
    ok = signal_health(live_cheap_intent=0, live_order_id=0, paper_btc5_rest=0, hours_up=5)
    assert ok["verdict"] == "OK_rich_skips_only"
    alarm = signal_health(live_cheap_intent=1, live_order_id=0, paper_btc5_rest=0, hours_up=0.1)
    assert alarm["verdict"] == "ALARM_intent_no_order_id"
    watch = signal_health(live_cheap_intent=0, live_order_id=0, paper_btc5_rest=8, hours_up=13)
    assert watch["verdict"] == "WATCH_paper_rest_live_zero_intent"
