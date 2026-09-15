import unittest
from pathlib import Path

import pandas as pd

from account_review import asset_evidence_year_open, current_vs_year_open, year_open_baseline_snapshot
from app import YEAR_TO_DATE_MODE, comparison_modes_for_snapshot


def fixture_rows():
    def row(date, name, account, value, income=0.0):
        return dict(
            snapshot_date=date, snapshot_month=date[:7], snapshot_status="official",
            asset_key=name, asset_name=name, asset_code=name, trade_code=name,
            account_bucket=account, asset_class="股票", manager="经理甲",
            full_market_value=value, market_value_year_open=float("nan"),
            avg_capital_ytd=100.0, comprehensive_income_ytd=income, finance_income_ytd=income / 2,
            avg_capital_mtd=50.0, comprehensive_income_mtd=1.0, finance_income_mtd=0.5,
        )
    return pd.DataFrame([
        row("2024-12-31", "存续", "传统", 100.0, 900.0),
        row("2024-12-31", "退出", "退出账户", 20.0, 800.0),
        row("2025-01-31", "存续", "传统", 105.0, 3.0),
        row("2025-02-28", "存续", "传统", 110.0, 4.0),
        row("2025-02-28", "新增", "新增账户", 30.0, 2.0),
    ])


class YearOpenSnapshotTest(unittest.TestCase):
    def test_year_end_baseline_includes_exits_and_uses_current_ytd_income(self):
        data = fixture_rows()
        original = data.copy(deep=True)
        result = current_vs_year_open(data, "2025-02-28", ["account_bucket"]).set_index("account_bucket")
        self.assertEqual(year_open_baseline_snapshot(data, "2025-02-28"), "2024-12-31")
        self.assertEqual(result.full_market_value_prior.sum(), 120.0)
        self.assertEqual(result.full_market_value_current.sum(), 140.0)
        self.assertEqual(result.full_market_value_delta.sum(), 20.0)
        self.assertEqual(result.comprehensive_income_period.sum(), 6.0)
        self.assertEqual(result.net_full_market_value_delta.sum(), 14.0)
        self.assertEqual(result.loc["退出账户", "full_market_value_delta"], -20.0)
        self.assertEqual(result.loc["退出账户", "record_count_current"], 0.0)
        self.assertEqual(result.loc["新增账户", "full_market_value_prior"], 0.0)
        self.assertEqual(result.loc["传统", "comprehensive_return_mtd"], 0.04)
        self.assertTrue(result.market_value_year_open_current.isna().all())
        pd.testing.assert_frame_equal(data, original)

    def test_asset_evidence_keeps_year_open_and_monthly_baselines_distinct(self):
        result = asset_evidence_year_open(fixture_rows(), "2025-02-28", prior_month="2025-01-31").set_index("asset_name")
        self.assertEqual(result.full_market_value_prior.sum(), 120.0)
        self.assertEqual(result.full_market_value_delta.sum(), 20.0)
        self.assertEqual(result.loc["存续", "ytd_position_flow_delta"], 6.0)
        self.assertEqual(result.loc["存续", "monthly_position_flow_delta"], 4.0)
        self.assertEqual(result.loc["退出", "change_type"], "年初有持仓、本月无持仓")
        self.assertEqual(result.loc["新增", "change_type"], "年初无持仓、本月有持仓")
        self.assertEqual(result.loc["退出", "comprehensive_income_mtd_current"], 0.0)
        self.assertEqual(result.loc["存续", "comprehensive_return_mtd"], 0.04)

    def test_filtered_new_book_can_use_baseline_resolved_before_filtering(self):
        data = fixture_rows()
        baseline = year_open_baseline_snapshot(data, "2025-02-28")
        subset = data[data.account_bucket.eq("新增账户")]
        result = asset_evidence_year_open(subset, "2025-02-28", year_open_snapshot=baseline)
        self.assertEqual(result.full_market_value_prior.tolist(), [0.0])
        self.assertEqual(result.full_market_value_delta.tolist(), [30.0])
        exited = asset_evidence_year_open(data, "2025-02-28", account="退出账户")
        self.assertEqual(exited.full_market_value_delta.tolist(), [-20.0])

    def test_source_opening_values_take_precedence(self):
        data = fixture_rows()
        data.loc[data.snapshot_date.eq("2025-02-28"), "market_value_year_open"] = [80.0, 10.0]
        self.assertEqual(year_open_baseline_snapshot(data, "2025-02-28"), "")
        result = current_vs_year_open(data, "2025-02-28", ["account_bucket"])
        self.assertEqual(result.full_market_value_prior.sum(), 90.0)
        self.assertEqual(result.full_market_value_delta.sum(), 50.0)
        evidence = asset_evidence_year_open(data, "2025-02-28")
        self.assertEqual(evidence.full_market_value_prior.sum(), 90.0)

    def test_interim_and_wrong_year_baselines_are_not_accepted(self):
        for mutation in ["interim", "wrong_year"]:
            with self.subTest(mutation=mutation):
                data = fixture_rows()
                mask = data.snapshot_date.eq("2024-12-31")
                if mutation == "interim":
                    data.loc[mask, "snapshot_status"] = "interim"
                else:
                    data.loc[mask, "snapshot_date"] = "2023-12-31"
                self.assertEqual(year_open_baseline_snapshot(data, "2025-02-28"), "")
                self.assertNotIn(YEAR_TO_DATE_MODE, comparison_modes_for_snapshot(data, "2025-02-28"))
                self.assertTrue(current_vs_year_open(data, "2025-02-28", ["account_bucket"]).full_market_value_delta.isna().all())

    def test_all_imported_months_reconcile_to_their_previous_year_end(self):
        root = Path(__file__).resolve().parents[1] / "data/snapshot_parquet"
        paths = sorted(path for path in root.glob("*.parquet") if path.stem <= "2026-02-28")
        data = pd.concat([pd.read_parquet(path) for path in paths], ignore_index=True)
        for date in sorted(data.snapshot_date.unique()):
            if date == "2024-12-31":
                self.assertNotIn(YEAR_TO_DATE_MODE, comparison_modes_for_snapshot(data, date))
                continue
            with self.subTest(date=date):
                baseline = "2024-12-31" if date.startswith("2025") else "2025-12-31"
                self.assertEqual(year_open_baseline_snapshot(data, date), baseline)
                self.assertIn(YEAR_TO_DATE_MODE, comparison_modes_for_snapshot(data, date))
                current = data[data.snapshot_date.eq(date)]
                prior = data[data.snapshot_date.eq(baseline)]
                for groups in [["account_bucket"], ["asset_class"], ["mandate_type"], ["account_bucket", "asset_class"]]:
                    summary = current_vs_year_open(data, date, groups)
                    self.assertAlmostEqual(summary.full_market_value_prior.sum(), prior.full_market_value.sum(), places=8)
                    self.assertAlmostEqual(summary.full_market_value_delta.sum(), current.full_market_value.sum() - prior.full_market_value.sum(), places=8)
                    self.assertAlmostEqual(summary.comprehensive_income_period.sum(), current.comprehensive_income_ytd.sum(), places=8)
                    self.assertAlmostEqual(summary.avg_capital_mtd_current.sum(), current.avg_capital_ytd.sum(), places=8)


if __name__ == "__main__":
    unittest.main()
