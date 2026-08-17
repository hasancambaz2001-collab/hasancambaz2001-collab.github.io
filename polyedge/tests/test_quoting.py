import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from polyedge.quoting import (  # noqa: E402
    BookTouch,
    QuoteParams,
    construct_quotes,
    order_score,
    round_to_tick,
)
from polyedge.scoring import score_market  # noqa: E402
from polyedge.farm import FarmConfig, _toxic  # noqa: E402


class QuotingTests(unittest.TestCase):
    def test_quadratic_score(self):
        self.assertAlmostEqual(order_score(0, 3), 1.0)
        self.assertAlmostEqual(order_score(3, 3), 0.0)
        self.assertEqual(order_score(4, 3), 0.0)
        self.assertGreater(order_score(1, 3), order_score(2, 3))

    def test_tick_round(self):
        self.assertAlmostEqual(round_to_tick(0.447, 0.001, up=False), 0.447)
        self.assertAlmostEqual(round_to_tick(0.4476, 0.001, up=False), 0.447)
        self.assertAlmostEqual(round_to_tick(0.4471, 0.001, up=True), 0.448)

    def test_two_sided_bids_sum_below_one(self):
        q = construct_quotes(
            yes_token="Y",
            no_token="N",
            yes_touch=BookTouch(0.49, 0.51),
            no_touch=BookTouch(0.49, 0.51),
            tick=0.01,
            min_size=50,
            max_spread_cents=4.5,
        )
        self.assertTrue(q.two_sided)
        self.assertIsNotNone(q.yes)
        self.assertIsNotNone(q.no)
        self.assertLess(q.yes.price + q.no.price, 1.0)
        self.assertGreater(q.locked_edge, 0)
        self.assertGreater(q.reward_score, 0)
        self.assertGreater(q.capital_usdc, 0)
        # post-only: never at or through the ask
        self.assertLess(q.yes.price, 0.51)
        self.assertLess(q.no.price, 0.51)

    def test_does_not_cross_ask(self):
        q = construct_quotes(
            yes_token="Y",
            no_token="N",
            yes_touch=BookTouch(0.40, 0.401),
            no_touch=BookTouch(0.598, 0.60),
            tick=0.001,
            min_size=100,
            max_spread_cents=3.5,
            params=QuoteParams(delta_min_ticks=1, min_edge_ticks=1),
        )
        self.assertTrue(q.two_sided)
        self.assertLess(q.yes.price, 0.401)
        self.assertLess(q.no.price, 0.60)

    def test_inventory_skew_lowers_long_side(self):
        flat = construct_quotes(
            yes_token="Y",
            no_token="N",
            yes_touch=BookTouch(0.50, 0.52),
            no_touch=BookTouch(0.48, 0.50),
            tick=0.01,
            min_size=50,
            max_spread_cents=4.5,
        )
        long_yes = construct_quotes(
            yes_token="Y",
            no_token="N",
            yes_touch=BookTouch(0.50, 0.52),
            no_touch=BookTouch(0.48, 0.50),
            tick=0.01,
            min_size=50,
            max_spread_cents=4.5,
            params=QuoteParams(inventory_yes=200, q_max_usdc=100),
        )
        self.assertLessEqual(long_yes.yes.price, flat.yes.price)


class ScoringAndFilterTests(unittest.TestCase):
    def test_score_prefers_balanced_rewarded_book(self):
        good = score_market(
            condition_id="a",
            daily_rate=100,
            liquidity=20_000,
            volume_24h=5_000,
            best_bid=0.48,
            best_ask=0.50,
            fee_rate=0.04,
            rebate_rate=0.25,
        )
        extreme = score_market(
            condition_id="b",
            daily_rate=100,
            liquidity=20_000,
            volume_24h=5_000,
            best_bid=0.02,
            best_ask=0.03,
            fee_rate=0.04,
            rebate_rate=0.25,
        )
        self.assertGreater(good.score, extreme.score)

    def test_toxic_filters(self):
        cfg = FarmConfig()
        self.assertEqual(_toxic("Bitcoin Up or Down 5-minute", "", 4.5, 50, cfg), "short-crypto-twap")
        self.assertEqual(_toxic("Some race", "", 1.5, 7500, cfg), "tight-band-hft")
        self.assertEqual(_toxic("Will X post 10 tweets this week?", "", 4.5, 80, cfg), "mentions-clock")
        self.assertEqual(
            _toxic("Will Silver hit $69 Week of August 17 2026?", "", 5.5, 50, cfg),
            "same-week-expiry",
        )
        self.assertEqual(_toxic("OpenAI IPO", "2027-01-01T00:00:00+00:00", 4.5, 80, cfg), "")


if __name__ == "__main__":
    unittest.main()
