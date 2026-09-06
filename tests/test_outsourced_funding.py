import unittest

import pandas as pd

from outsourced_funding import adjust_outsourced_funding_capital, funding_capital_audit
from manager_attribution import build_manager_attribution_rows, manager_attribution_summary
from manager_position_views import position_peer_history
from strategy_books import strategy_book_summary


class OutsourcedFundingTest(unittest.TestCase):
    def test_day_counts_copy_preservation_and_idempotence(self):
        data = pd.DataFrame({
            "strategy_book": ["华泰权益", "大成基金权益", "太平资产香港", "人保固收"],
            "strategy_book_scope": ["委外"] * 4,
            "snapshot_date": ["2026-09-03"] * 4,
            "avg_capital_ytd": [3., .75, 8., 100.],
            "avg_capital_mtd": [5., 3., 8., 100.],
            "comprehensive_income_ytd": [.3, -.1, .2, 5.],
        })
        original = data.copy(deep=True)
        result = adjust_outsourced_funding_capital(data)
        self.assertAlmostEqual(result.avg_capital_ytd.iloc[0], 3 * 246 / 156)
        self.assertAlmostEqual(result.avg_capital_ytd.iloc[1], .75 * 246 / 65)
        self.assertEqual(result.avg_capital_ytd.iloc[2:].tolist(), [8., 100.])
        pd.testing.assert_frame_equal(data, original)
        pd.testing.assert_series_equal(result.avg_capital_mtd, data.avg_capital_mtd)
        pd.testing.assert_series_equal(result.comprehensive_income_ytd, data.comprehensive_income_ytd)
        pd.testing.assert_frame_equal(adjust_outsourced_funding_capital(result), result)

    def test_before_start_is_missing_and_next_year_no_time_inflation(self):
        data = pd.DataFrame({"strategy_book": ["广发基金权益"] * 3, "snapshot_date": ["2026-06-30", "2026-07-01", "2027-01-10"], "avg_capital_ytd": [.1, .01, 3.]})
        result = adjust_outsourced_funding_capital(data)
        self.assertTrue(pd.isna(result.avg_capital_ytd.iloc[0]))
        self.assertAlmostEqual(result.avg_capital_ytd.iloc[1], .01 * 182)
        self.assertEqual(result.avg_capital_ytd.iloc[2], 3.)

    def test_actual_six_accounts_match_across_summary_and_peer_trend(self):
        raw = pd.read_parquet("data/snapshot_parquet/2026-09-03.parquet")
        original = raw.copy(deep=True)
        rows = build_manager_attribution_rows(raw)
        audit = funding_capital_audit(rows, "2026-09-03").set_index("strategy_book")
        self.assertEqual(len(audit), 6)
        expected = {"华泰权益": .053026426, "富国权益": -.031122391, "华夏基金权益": -.005524293, "国泰海通权益": -.070961211, "大成基金权益": .007335536, "广发基金权益": -.0496798}
        for book, value in expected.items():
            self.assertAlmostEqual(audit.loc[book, "funding_return"], value, places=5)
        for book in ["大成基金权益", "广发基金权益"]:
            self.assertGreater(audit.loc[book, "avg_capital_ytd"], 2.7)
            self.assertLess(audit.loc[book, "avg_capital_ytd"], 3.1)
        summary = manager_attribution_summary(rows, "2026-09-03", "权益").set_index("attribution_entity_name")
        trend, _ = position_peer_history(rows, "2026-09-03", "权益")
        trend = trend[trend.peer_group.eq("权益委外")].set_index("attribution_entity_name")
        strategy = strategy_book_summary(raw, "2026-09-03", "年初以来").set_index("strategy_book")
        for book, name in {"华泰权益": "华泰", "富国权益": "富国基金", "华夏基金权益": "华夏基金", "国泰海通权益": "国泰海通", "大成基金权益": "大成基金", "广发基金权益": "广发基金"}.items():
            self.assertAlmostEqual(summary.loc[name, "comprehensive_return_ytd"], audit.loc[book, "funding_return"])
            self.assertAlmostEqual(trend.loc[name, "comprehensive_return_ytd"], audit.loc[book, "funding_return"])
            self.assertAlmostEqual(strategy.loc[book, "comprehensive_return_mtd"], audit.loc[book, "funding_return"])
        pd.testing.assert_frame_equal(raw, original)


if __name__ == "__main__":
    unittest.main()
