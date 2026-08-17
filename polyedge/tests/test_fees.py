import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from polyedge.fees import (  # noqa: E402
    FeeSchedule,
    completeness_net_edge,
    dutch_book_net_edge,
    reverse_completeness_net_edge,
    taker_fee,
)


class FeeMathTests(unittest.TestCase):
    def test_crypto_peak_matches_official_table(self):
        # 100 shares @ 0.50, rate 0.07 → $1.75
        self.assertAlmostEqual(taker_fee(100, 0.50, 0.07), 1.75, places=5)

    def test_politics_peak_matches_official_table(self):
        # 100 shares @ 0.50, rate 0.04 → $1.00
        self.assertAlmostEqual(taker_fee(100, 0.50, 0.04), 1.00, places=5)

    def test_extremes_and_zero_rate(self):
        self.assertEqual(taker_fee(100, 0.0, 0.07), 0.0)
        self.assertEqual(taker_fee(100, 1.0, 0.07), 0.0)
        self.assertEqual(taker_fee(100, 0.5, 0.0), 0.0)
        self.assertEqual(taker_fee(0, 0.5, 0.07), 0.0)

    def test_symmetry_around_half(self):
        a = taker_fee(100, 0.30, 0.05)
        b = taker_fee(100, 0.70, 0.05)
        self.assertAlmostEqual(a, b, places=5)

    def test_fee_schedule_from_gamma_object(self):
        market = {
            "feesEnabled": True,
            "feeSchedule": {"rate": 0.07, "rebateRate": 0.2, "takerOnly": True},
        }
        s = FeeSchedule.from_market(market)
        self.assertEqual(s.rate, 0.07)
        self.assertEqual(s.rebate_rate, 0.2)

        geo = {"feesEnabled": False, "feeType": "geopolitics_fees"}
        self.assertEqual(FeeSchedule.from_market(geo).rate, 0.0)

    def test_completeness_fee_illusion(self):
        # 3¢ raw gap looks like arb; crypto taker fees eat it.
        market = {
            "feesEnabled": True,
            "feeSchedule": {"rate": 0.07, "takerOnly": True},
        }
        raw = 1.0 - (0.45 + 0.52)
        self.assertAlmostEqual(raw, 0.03, places=6)
        net = completeness_net_edge(0.45, 0.52, market)
        self.assertLess(net, 0.0)

        geo = {"feesEnabled": False, "feeType": "geopolitics_fees"}
        self.assertGreater(completeness_net_edge(0.45, 0.52, geo), 0.029)

    def test_reverse_and_dutch(self):
        geo = {"feesEnabled": False}
        self.assertGreater(reverse_completeness_net_edge(0.51, 0.51, geo), 0.019)
        crypto = {"feesEnabled": True, "feeSchedule": {"rate": 0.07}}
        # bids 0.51+0.51 = 1.02 raw 2¢; fees ~ 2 * 0.07*0.51*0.49 ≈ 0.035 → negative
        self.assertLess(reverse_completeness_net_edge(0.51, 0.51, crypto), 0.0)
        self.assertGreater(dutch_book_net_edge([0.20, 0.20, 0.20, 0.20], geo), 0.19)
        self.assertLess(dutch_book_net_edge([0.40, 0.40, 0.25], crypto), 0.0)


if __name__ == "__main__":
    unittest.main()
