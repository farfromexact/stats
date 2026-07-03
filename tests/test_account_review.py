import unittest

import pandas as pd

from account_review import asset_evidence_year_open


class AssetEvidenceTest(unittest.TestCase):
    def test_extra_group_columns_keep_outsourced_books_separate(self):
        data = pd.DataFrame(
            [
                {
                    "snapshot_month": "2026-06",
                    "strategy_book": "富国权益",
                    "strategy_book_display_label": "委外-富国权益",
                    "asset_key": "600000",
                    "asset_name": "同一股票",
                    "asset_code": "600000.STK.SH",
                    "trade_code": "600000SH",
                    "account_bucket": "传统",
                    "asset_class": "股票",
                    "manager": "委外经理",
                    "full_market_value": 1.2,
                    "market_value_year_open": 1.0,
                    "finance_income_ytd": 0.03,
                    "comprehensive_income_ytd": 0.20,
                },
                {
                    "snapshot_month": "2026-06",
                    "strategy_book": "华泰权益",
                    "strategy_book_display_label": "委外-华泰权益",
                    "asset_key": "600000",
                    "asset_name": "同一股票",
                    "asset_code": "600000.STK.SH",
                    "trade_code": "600000SH",
                    "account_bucket": "传统",
                    "asset_class": "股票",
                    "manager": "委外经理",
                    "full_market_value": 2.3,
                    "market_value_year_open": 2.0,
                    "finance_income_ytd": 0.04,
                    "comprehensive_income_ytd": 0.30,
                },
            ]
        )

        evidence = asset_evidence_year_open(
            data,
            "2026-06",
            extra_group_cols=["strategy_book", "strategy_book_display_label"],
        )

        self.assertEqual(len(evidence), 2)
        actual = dict(zip(evidence["strategy_book"], evidence["full_market_value_current"]))
        self.assertEqual(actual, {"富国权益": 1.2, "华泰权益": 2.3})


if __name__ == "__main__":
    unittest.main()
