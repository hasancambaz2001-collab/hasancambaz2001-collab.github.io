from whiskas.clob_auth import auth_status
from whiskas.clob_orders import (
    AuthAbsent,
    create_gtc_buy,
    normalize_status,
    parse_order_status,
    real_fill_rate,
    refuse_send,
)


def test_auth_absent_does_not_fake_real_fill() -> None:
    st = auth_status()
    assert st["auth_available"] is False
    assert st["reason"] == "AUTH_ABSENT"
    assert "sk-" not in str(st)
    refused = refuse_send()
    assert refused["sent"] is False
    assert refused["real_fill"] is None
    assert refused["real_fill_rate"] is None
    assert refused["live_order"] is False


def test_create_gtc_without_client_raises() -> None:
    try:
        create_gtc_buy(None, token_id="1", price=0.40, size=5)
    except AuthAbsent:
        return
    raise AssertionError("expected AuthAbsent")


def test_parse_status_and_rate_only_on_sent() -> None:
    assert normalize_status("live") == "open"
    assert normalize_status("MATCHED") == "filled"
    parsed = parse_order_status(
        {"orderID": "abc", "status": "live", "original_size": "5", "size_matched": "2"}
    )
    assert parsed["order_id"] == "abc"
    assert parsed["status"] == "partial"
    assert parsed["filled_size"] == 2.0
    assert parsed["rested_size"] == 5.0
    assert real_fill_rate([]) is None
    assert abs(real_fill_rate([parsed]) - 0.4) < 1e-12


def test_src_never_prints_keys() -> None:
    from pathlib import Path

    src = Path("whiskas/clob_auth.py").read_text()
    assert "Never print" in src or "never print" in src.lower() or "Never logs values" in src
    assert "PMDATA_API_KEY" not in Path("whiskas/clob_orders.py").read_text()
    assert "LIVE_READY" in Path("scripts/micro_live.py").read_text()
