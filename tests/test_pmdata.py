from whiskas.pmdata import (
    chainlink_url,
    day_file_name,
    day_url,
    is_pmdata_slug,
    join_best,
    regime_for_date,
    slug_url,
)


def test_pmdata_slugs_are_5m_15m_not_4h_or_daily() -> None:
    assert is_pmdata_slug("btc-updown-5m-1786869000")
    assert is_pmdata_slug("eth-updown-15m-1786871700")
    assert is_pmdata_slug("btc-updown-4h-1786867200") is False
    assert is_pmdata_slug("bitcoin-up-or-down-on-august-15-2026") is False


def test_join_best_yes_and_no_complement() -> None:
    yes = join_best(price=0.40, outcome="Yes", best_bid=0.40, best_ask=0.42)
    assert yes["yes_leg"] is True
    assert yes["join_best_yes"] is True
    no = join_best(price=0.58, outcome="No", best_bid=0.40, best_ask=0.42)
    assert no["yes_leg"] is False
    assert no["join_best_no_comp"] is True
    miss = join_best(price=0.30, outcome="Yes", best_bid=0.40, best_ask=0.42)
    assert miss["join_best_yes"] is False


def test_day_and_slug_urls_match_docs() -> None:
    assert slug_url("l2", "btc-updown-5m-1784332800") == (
        "https://api.pmdata.dev/download/l2/btc-updown-5m-1784332800.parquet"
    )
    assert day_file_name("btc-5m", "l2", "2026-08-01") == "btc-5m_l2_2026-08-01.zip"
    assert day_url("btc-5m", "l2", "2026-08-01") == (
        "https://api.pmdata.dev/polymarket/btc-5m/l2/btc-5m_l2_2026-08-01.zip"
    )
    assert day_url("btc-15m", "onchain_fills", "2026-08-15") == (
        "https://api.pmdata.dev/polymarket/btc-15m/onchain_fills/btc-15m_onchain_fills_2026-08-15.zip"
    )
    assert chainlink_url("BTCUSD", "streams", "2026-08-01").endswith("BTCUSD_streams_2026-08-01.parquet")
    assert regime_for_date("2026-08-01") == "pre_2026_08_14_DEBUG"
    assert regime_for_date("2026-08-14") == "post_2026_08_14"
    src = __import__("pathlib").Path("whiskas/pmdata.py").read_text()
    assert "sk-" not in src
    assert "PMDATA_API_KEY" in src
