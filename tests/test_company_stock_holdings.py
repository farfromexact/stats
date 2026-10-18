import unittest

import pandas as pd

from company_stock_holdings import (
    company_stock_holding_ranking,
    company_stock_industry_distribution,
)


def source_row(
    *,
    asset_name="测试股票",
    asset_code="000001.STK.SZ",
    trade_code="000001SZ",
    account_bucket="传统",
    manager="经理甲",
    mandate_type="委托资管",
    fund_book_name="传统邮储",
    full_market_value=1.0,
    comprehensive_income_mtd=0.1,
    comprehensive_income_ytd=0.2,
    avg_capital_mtd=1.0,
    avg_capital_ytd=1.0,
    asset_major_class="权益",
    trade_strategy="交易",
):
    return {
        "snapshot_date": "2026-07-31",
        "snapshot_month": "2026-07",
        "snapshot_status": "official",
        "asset_name": asset_name,
        "asset_code": asset_code,
        "trade_code": trade_code,
        "account_bucket": account_bucket,
        "mandate_type": mandate_type,
        "fund_book_name": fund_book_name,
        "group_book_name": "",
        "manager": manager,
        "asset_class": "股票",
        "full_market_value": full_market_value,
        "avg_capital_mtd": avg_capital_mtd,
        "avg_capital_ytd": avg_capital_ytd,
        "finance_income_mtd": comprehensive_income_mtd / 2,
        "finance_income_ytd": comprehensive_income_ytd / 2,
        "comprehensive_income_mtd": comprehensive_income_mtd,
        "comprehensive_income_ytd": comprehensive_income_ytd,
        "asset_major_class": asset_major_class,
        "asset_class_level_1": "权益",
        "asset_class_level_2": "股票",
        "asset_class_level_3": "股票",
        "trade_strategy": trade_strategy,
    }


class CompanyStockHoldingRankingTest(unittest.TestCase):
    def test_aggregates_across_accounts_and_managers_by_scope(self):
        source = pd.DataFrame(
            [
                source_row(full_market_value=5.0, comprehensive_income_mtd=0.5, account_bucket="传统", manager="经理甲"),
                source_row(full_market_value=3.0, comprehensive_income_mtd=0.3, account_bucket="分红一", manager="经理乙"),
                source_row(
                    full_market_value=2.0,
                    comprehensive_income_mtd=0.2,
                    mandate_type="委托华泰",
                    fund_book_name="华泰权益专户",
                    account_bucket="分红二",
                    manager="",
                ),
                source_row(
                    asset_name="另一只股票",
                    asset_code="000002.STK.SZ",
                    trade_code="000002SZ",
                    full_market_value=4.0,
                    comprehensive_income_mtd=0.4,
                ),
                source_row(full_market_value=0.0),
            ]
        )

        internal = company_stock_holding_ranking(
            source,
            "2026-07-31",
            holding_scope="委内",
        )
        outsourced = company_stock_holding_ranking(
            source,
            "2026-07-31",
            holding_scope="委外",
        )

        first_internal = internal.iloc[0]
        first_outsourced = outsourced.iloc[0]
        self.assertEqual(first_internal["asset_code"], "000001.STK.SZ")
        self.assertAlmostEqual(float(first_internal["full_market_value_current"]), 8.0)
        self.assertAlmostEqual(float(first_internal["cost_basis_period"]), 7.2)
        self.assertAlmostEqual(float(first_internal["profit_amount_period"]), 0.8)
        self.assertAlmostEqual(float(internal["full_market_value_current"].sum()), 12.0)
        self.assertEqual(list(internal["rank"]), [1, 2])
        self.assertEqual(first_outsourced["asset_code"], "000001.STK.SZ")
        self.assertAlmostEqual(float(first_outsourced["full_market_value_current"]), 2.0)
        self.assertAlmostEqual(float(first_outsourced["outsourced_market_value_current"]), 2.0)
        self.assertAlmostEqual(float(outsourced["full_market_value_current"].sum()), 2.0)

    def test_excludes_single_plan_duplicate_source_level(self):
        source = pd.DataFrame(
            [
                source_row(
                    asset_name="富国顶层汇总",
                    asset_code="000003.STK.SZ",
                    trade_code="000003SZ",
                    mandate_type="富国基金单一计划",
                    fund_book_name="分红邮储单一委外专户",
                    full_market_value=5.0,
                ),
                source_row(
                    asset_name="富国底层持仓",
                    asset_code="000003.STK.SZ",
                    trade_code="000003SZ",
                    mandate_type="单一委外",
                    fund_book_name="富国基金中邮1号单一资产管理计划",
                    full_market_value=6.0,
                ),
            ]
        )

        ranking = company_stock_holding_ranking(
            source,
            "2026-07-31",
            holding_scope="委外",
        )

        self.assertEqual(len(ranking), 1)
        self.assertAlmostEqual(float(ranking.iloc[0]["full_market_value_current"]), 6.0)
        self.assertEqual(int(ranking.iloc[0]["source_rows_current"]), 1)

    def test_oci_toggle_uses_existing_equity_dashboard_scope(self):
        source = pd.DataFrame(
            [
                source_row(
                    asset_name="普通股票",
                    asset_code="000004.STK.SZ",
                    trade_code="000004SZ",
                    full_market_value=5.0,
                ),
                source_row(
                    asset_name="OCI股票",
                    asset_code="000005.STK.SZ",
                    trade_code="000005SZ",
                    manager="鲍淼",
                    trade_strategy="配置",
                    full_market_value=7.0,
                    comprehensive_income_mtd=-1.4,
                ),
            ]
        )

        without_oci = company_stock_holding_ranking(
            source,
            "2026-07-31",
            include_oci=False,
        )
        with_oci = company_stock_holding_ranking(
            source,
            "2026-07-31",
            include_oci=True,
        )

        self.assertAlmostEqual(float(without_oci["full_market_value_current"].sum()), 5.0)
        self.assertAlmostEqual(float(with_oci["full_market_value_current"].sum()), 12.0)
        self.assertIn("OCI股票", with_oci["asset_name"].tolist())
        self.assertNotIn("OCI股票", without_oci["asset_name"].tolist())
        oci_row = with_oci.loc[with_oci["asset_name"].eq("OCI股票")].iloc[0]
        self.assertAlmostEqual(float(oci_row["loss_amount_period"]), 1.4)
        self.assertAlmostEqual(float(oci_row["cost_basis_period"]), 8.4)

    def test_industry_distribution_uses_mapping_and_keeps_unmapped_value(self):
        source = pd.DataFrame(
            [
                source_row(full_market_value=5.0),
                source_row(
                    full_market_value=3.0,
                    mandate_type="委托华泰",
                    fund_book_name="华泰权益专户",
                    manager="",
                ),
                source_row(
                    asset_name="另一只股票",
                    asset_code="000002.STK.SZ",
                    trade_code="000002SZ",
                    full_market_value=4.0,
                ),
            ]
        )
        mapping = pd.DataFrame(
            [
                {
                    "code": "000001.SZ",
                    "industry": "银行",
                    "mapping_method": "申万一级",
                    "observed_date": "2026-10-16",
                }
            ]
        )

        distribution = company_stock_industry_distribution(
            source,
            "2026-07-31",
            holding_scope="委内",
            industry_mapping=mapping,
        )

        bank = distribution.set_index("industry").loc["银行"]
        unmapped = distribution.set_index("industry").loc["未分类/境外股"]
        self.assertAlmostEqual(float(bank["full_market_value_current"]), 5.0)
        self.assertAlmostEqual(float(unmapped["full_market_value_current"]), 4.0)
        self.assertAlmostEqual(float(distribution["market_value_share"].sum()), 1.0)
        self.assertEqual(int(bank["stock_count"]), 1)
        self.assertEqual(unmapped["industry_mapping_method"], "未映射")


if __name__ == "__main__":
    unittest.main()
