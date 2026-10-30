import unittest
import pandas as pd
from tests.test_company_stock_holdings import source_row
from company_stock_holdings import company_stock_holding_ranking
from stock_industry_concentration import concentration_rows, concentration_distribution, industry_stock_details


class StockIndustryConcentrationTest(unittest.TestCase):
    def setUp(self):
        self.source = pd.DataFrame([
            source_row(full_market_value=3),
            source_row(full_market_value=2, manager="另一经理"),
            source_row(full_market_value=7, manager="鲍淼", trade_strategy="配置"),
            source_row(full_market_value=4, mandate_type="委托华泰", fund_book_name="华泰权益专户", trade_strategy="未填报"),
            source_row(full_market_value=1, asset_code="999999.STK.SH"),
        ])
        self.mapping = pd.DataFrame([{"code": "000001.SZ", "industry": "银行"}])
        self.rows = concentration_rows(self.source, "2026-07-31", self.mapping)

    def test_partition_and_denominators(self):
        dist = concentration_distribution(self.rows)
        self.assertAlmostEqual(dist.market_value.sum(), 17)
        self.assertAlmostEqual(dist.selected_share.sum(), 1)
        self.assertAlmostEqual(dist.company_share.sum(), 1)
        self.assertTrue((dist.groupby("portfolio").portfolio_share.sum().round(8) == 1).all())
        internal = concentration_distribution(self.rows, "委内合计")
        self.assertAlmostEqual(internal.company_share.sum(), 13 / 17)
        self.assertAlmostEqual(internal.selected_share.sum(), 1)
        self.assertIn("未分类/境外股", dist.industry.tolist())

    def test_details_combine_managers_but_keep_books(self):
        detail = industry_stock_details(self.rows, "银行")
        self.assertEqual(len(detail), 3)
        self.assertAlmostEqual(detail.market_value.sum(), 16)
        self.assertAlmostEqual(detail.industry_share.sum(), 1)
        self.assertAlmostEqual(detail.selected_share.sum(), 16 / 17)

    def test_missing_mapping_and_empty_scope(self):
        rows = concentration_rows(self.source, "2026-07-31", pd.DataFrame())
        self.assertEqual(rows.industry.unique().tolist(), ["未分类/境外股"])
        self.assertTrue(concentration_distribution(concentration_rows(self.source, "2025-01-01")).empty)
        with self.assertRaises(ValueError):
            concentration_distribution(rows, "wrong")

    def test_unknown_internal_strategy_not_called_trading(self):
        source = pd.DataFrame([source_row(trade_strategy="未填报")])
        rows = concentration_rows(source, "2026-07-31", self.mapping)
        # The existing ranking universe excludes unrecognised source strategies.
        # Preserve that boundary rather than silently turning them into trading.
        self.assertTrue(rows.empty)
        self.assertTrue(concentration_distribution(rows, "委内交易盘").empty)

    def test_latest_matches_existing_universe(self):
        source = pd.read_parquet("data/snapshot_parquet/2026-10-29.parquet")
        before = source.copy(deep=True)
        rows = concentration_rows(source, "2026-10-29")
        dist = concentration_distribution(rows)
        expected = sum(company_stock_holding_ranking(source, "2026-10-29", holding_scope=s, include_oci=True).full_market_value_current.sum() for s in ["委内", "委外"])
        self.assertAlmostEqual(dist.market_value.sum(), expected)
        self.assertAlmostEqual(dist.selected_share.sum(), 1)
        self.assertEqual(set(rows.portfolio), {"委内交易盘", "委内 OCI", "委外股票"})
        pd.testing.assert_frame_equal(source, before)


if __name__ == "__main__":
    unittest.main()
