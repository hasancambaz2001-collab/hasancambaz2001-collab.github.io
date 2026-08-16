from whiskas.pmdata import is_pmdata_slug, join_best


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
