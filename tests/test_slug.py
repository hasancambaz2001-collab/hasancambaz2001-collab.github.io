from whiskas.slug import is_btc_5m, parse_btc_5m_slug, window_slug


def test_parse_valid() -> None:
    assert parse_btc_5m_slug("btc-updown-5m-1786886400") == 1786886400
    assert window_slug(1786886400) == "btc-updown-5m-1786886400"


def test_parse_rejects_non_300() -> None:
    assert parse_btc_5m_slug("btc-updown-5m-1786886401") is None
    assert parse_btc_5m_slug("btc-updown-15m-1786886400") is None
    assert parse_btc_5m_slug("nhl-car-las-2026-06-09") is None


def test_is_btc_5m() -> None:
    assert is_btc_5m("btc-updown-5m-1786886400")
    assert not is_btc_5m("eth-updown-5m-1786886400")
