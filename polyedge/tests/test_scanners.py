import unittest
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from polyedge.scanners import (  # noqa: E402
    scan_completeness,
    scan_dutch,
    scan_holding,
    scan_rewards,
)


YES = "111"
NO = "222"


class ScannerTests(unittest.TestCase):
    def test_rewards_ranks_thin_high_pool_first(self):
        markets = [
            {
                "question": "crowded",
                "slug": "crowded",
                "clobRewards": [{"rewardsDailyRate": 100}],
                "liquidityNum": 500_000,
                "volume24hr": 200_000,
                "rewardsMinSize": 200,
                "rewardsMaxSpread": 3.5,
                "feeType": "politics_fees",
                "holdingRewardsEnabled": False,
            },
            {
                "question": "quiet",
                "slug": "quiet",
                "clobRewards": [{"rewardsDailyRate": 80}],
                "liquidityNum": 8_000,
                "volume24hr": 1_000,
                "rewardsMinSize": 50,
                "rewardsMaxSpread": 4.5,
                "feeType": None,
                "holdingRewardsEnabled": True,
            },
            {
                "question": "dust",
                "slug": "dust",
                "clobRewards": [{"rewardsDailyRate": 0.001}],
                "liquidityNum": 10,
                "volume24hr": 10,
            },
        ]
        rows = scan_rewards(markets)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].slug, "quiet")
        self.assertGreater(rows[0].farm_score, rows[1].farm_score)

    def test_holding_filter(self):
        markets = [
            {"question": "a", "slug": "a", "holdingRewardsEnabled": True, "volume24hr": 10},
            {"question": "b", "slug": "b", "holdingRewardsEnabled": False, "volume24hr": 99},
        ]
        rows = scan_holding(markets)
        self.assertEqual([r.slug for r in rows], ["a"])

    def test_completeness_uses_fees_and_live_prices(self):
        market = {
            "question": "Will X happen?",
            "slug": "x",
            "enableOrderBook": True,
            "clobTokenIds": f'["{YES}","{NO}"]',
            "outcomes": '["Yes","No"]',
            "feesEnabled": False,
            "feeType": "geopolitics_fees",
            "volume24hr": 1000,
        }
        fake_prices = {
            YES: {"BUY": 0.40, "SELL": 0.41},
            NO: {"BUY": 0.40, "SELL": 0.42},
        }
        with patch("polyedge.scanners.clob.fetch_prices", return_value=fake_prices):
            hits = scan_completeness([market], min_net_edge=0.01)
        kinds = {h.kind for h in hits}
        self.assertIn("buy_both", kinds)
        buy = next(h for h in hits if h.kind == "buy_both")
        self.assertAlmostEqual(buy.net_edge, 0.17, places=3)

        crypto = dict(market)
        crypto["feesEnabled"] = True
        crypto["feeSchedule"] = {"rate": 0.07}
        # 0.48+0.50 = 0.98 raw 2¢ — fees kill it
        fake_prices2 = {
            YES: {"BUY": 0.47, "SELL": 0.48},
            NO: {"BUY": 0.49, "SELL": 0.50},
        }
        with patch("polyedge.scanners.clob.fetch_prices", return_value=fake_prices2):
            hits2 = scan_completeness([crypto], min_net_edge=0.001)
        self.assertEqual(hits2, [])

    def test_dutch_neg_risk_only(self):
        yes_ids = ["a", "b", "c"]
        event = {
            "title": "Winner?",
            "slug": "winner",
            "negRisk": True,
            "markets": [
                {
                    "enableOrderBook": True,
                    "closed": False,
                    "clobTokenIds": f'["{tid}","x"]',
                    "groupItemTitle": name,
                    "feesEnabled": False,
                }
                for tid, name in zip(yes_ids, ["A", "B", "C"])
            ],
        }
        prices = {tid: {"BUY": 0.2, "SELL": 0.22} for tid in yes_ids}
        with patch("polyedge.scanners.clob.fetch_prices", return_value=prices):
            hits = scan_dutch([event], min_net_edge=0.05)
        self.assertEqual(len(hits), 1)
        self.assertAlmostEqual(hits[0].sum_asks, 0.66, places=4)

        event["negRisk"] = False
        event["enableNegRisk"] = False
        with patch("polyedge.scanners.clob.fetch_prices", return_value=prices):
            self.assertEqual(scan_dutch([event]), [])


if __name__ == "__main__":
    unittest.main()
