import inspect
import unittest
from unittest.mock import patch

import pandas as pd
import app as app_module

from app import (
    MONTH_REVIEW_MODE,
    YEAR_TO_DATE_MODE,
    manager_attribution_metric_config,
    render_manager_asset_contribution_chart,
    render_manager_attribution_coverage,
    render_manager_attribution_overview,
    render_manager_contribution_ranking,
    render_manager_exited_holdings,
    render_action_cards,
    render_filter_pills,
    sidebar_nav,
)


class ManagerAttributionViewsTest(unittest.TestCase):
    def test_metric_config_keeps_period_and_view_in_sync(self):
        self.assertEqual(
            manager_attribution_metric_config(YEAR_TO_DATE_MODE, "综合收益率"),
            ("comprehensive_return_ytd", "YTD综合收益率", "YTD综合收益率", ".1%"),
        )
        self.assertEqual(
            manager_attribution_metric_config(MONTH_REVIEW_MODE, "综合收益额"),
            ("comprehensive_income_mtd", "MTD综合收益额", "MTD综合收益额(亿)", ",.1f"),
        )

    def test_overview_surfaces_contributor_detractor_and_estimated_flows(self):
        summary = pd.DataFrame(
            {
                "attribution_entity_name": ["甲", "乙"],
                "attribution_scope": ["委内", "委外"],
                "full_market_value": [100.0, 50.0],
                "comprehensive_income_ytd": [8.0, -3.0],
            }
        )
        changes = pd.DataFrame(
            {
                "attribution_entity_name": ["甲", "乙"],
                "estimated_flow": [10.0, -12.0],
                "prior_snapshot_date": ["2026-06-30", "2026-06-30"],
            }
        )

        with patch("app.render_kpi_grid") as render_grid, patch("app.st.caption"):
            render_manager_attribution_overview(summary, changes, YEAR_TO_DATE_MODE)

        cards = render_grid.call_args.args[0]
        self.assertEqual(len(cards), 6)
        self.assertEqual(cards[2]["value"], "甲")
        self.assertEqual(cards[3]["value"], "乙")
        self.assertEqual(cards[4]["value"], "甲")
        self.assertEqual(cards[5]["value"], "乙")

    def test_contribution_and_asset_charts_render_separate_views(self):
        summary = pd.DataFrame(
            {
                "attribution_entity_id": ["委内::甲", "委外::乙"],
                "attribution_entity_name": ["甲", "乙"],
                "attribution_scope": ["委内", "委外"],
                "full_market_value": [100.0, 50.0],
                "comprehensive_income_ytd": [8.0, -3.0],
                "comprehensive_return_ytd": [0.08, -0.06],
            }
        )
        assets = pd.DataFrame(
            {
                "asset_key": ["a", "b"],
                "asset_name": ["贡献资产", "拖累资产"],
                "asset_class": ["企业债", "股票"],
                "account_bucket": ["传统", "自有"],
                "full_market_value": [20.0, 10.0],
                "comprehensive_income_ytd": [2.0, -1.0],
                "comprehensive_return_ytd": [0.10, -0.10],
            }
        )

        with (
            patch("app.st.markdown"),
            patch("app.st.caption"),
            patch("app.st.altair_chart") as altair_chart,
        ):
            render_manager_contribution_ranking(summary, YEAR_TO_DATE_MODE)
            render_manager_asset_contribution_chart(assets, YEAR_TO_DATE_MODE)

        self.assertEqual(altair_chart.call_count, 2)
        for call in altair_chart.call_args_list:
            self.assertGreaterEqual(call.args[0].to_dict()["height"], 300)

    def test_contribution_panorama_keeps_every_manager_visible(self):
        names = [f"主体{i}" for i in range(16)] + ["华泰", "富国基金"]
        summary = pd.DataFrame(
            {
                "attribution_entity_id": [f"委外::{name}" for name in names],
                "attribution_entity_name": names,
                "attribution_scope": ["委外"] * len(names),
                "full_market_value": [5.0] * len(names),
                "comprehensive_income_mtd": [float(index) / 100 for index in range(len(names))],
                "comprehensive_return_mtd": [0.01] * len(names),
            }
        )

        with (
            patch("app.st.markdown"),
            patch("app.st.altair_chart") as altair_chart,
            patch("app.st.caption") as caption,
        ):
            render_manager_contribution_ranking(summary, MONTH_REVIEW_MODE)

        chart_spec = altair_chart.call_args.args[0].to_dict()
        dataset_rows = [
            row
            for dataset in chart_spec.get("datasets", {}).values()
            for row in dataset
            if "_entity_label" in row
        ]
        labels = {row["_entity_label"] for row in dataset_rows}
        self.assertIn("华泰 · 委外", labels)
        self.assertIn("富国基金 · 委外", labels)
        self.assertIn("18 / 18", caption.call_args.args[0])

    def test_retired_manager_breakdown_is_removed_from_navigation(self):
        with patch("app.st.markdown") as markdown:
            sidebar_nav()

        navigation = markdown.call_args.args[0]
        self.assertIn('href="#manager-attribution"', navigation)
        self.assertNotIn('href="#manager-breakdown"', navigation)
        self.assertNotIn("品种内投资经理/受托机构拆解", navigation)
        self.assertNotIn('href="#asset-evidence"', navigation)

        with patch("app.st.markdown") as markdown:
            render_action_cards()
        action_cards = markdown.call_args.args[0]
        self.assertIn('href="#manager-attribution"', action_cards)
        self.assertIn("看经理归因", action_cards)
        self.assertNotIn('href="#manager-breakdown"', action_cards)
        self.assertNotIn('href="#asset-evidence"', action_cards)

    def test_filter_pills_drop_retired_asset_and_manager_filters(self):
        with patch("app.st.markdown") as markdown:
            render_filter_pills(
                "2026-08-06",
                YEAR_TO_DATE_MODE,
                "2026-07-31",
                "传统",
            )

        rendered = markdown.call_args.args[0]
        self.assertIn("当前视角", rendered)
        self.assertIn("账户", rendered)
        self.assertNotIn("投资品种", rendered)
        self.assertNotIn("投资经理/受托机构", rendered)

    def test_main_removes_legacy_manager_breakdown_but_keeps_attribution(self):
        source = inspect.getsource(app_module.main)

        self.assertIn('section_anchor("manager-attribution")', source)
        self.assertIn('st.subheader("投资经理 / 受托方归因")', source)
        self.assertIn("render_manager_attribution_dashboard", source)
        self.assertNotIn('section_anchor("manager-breakdown")', source)
        self.assertNotIn('st.subheader("品种内投资经理/受托机构拆解")', source)
        self.assertNotIn("资产明细｜跟随品种与投资经理", source)

    def test_coverage_strip_labels_absolute_and_net_coverage(self):
        coverage = {
            "market_value_coverage": 0.88,
            "net_market_value_coverage": 0.997,
            "row_coverage": 0.89,
            "unattributed_market_value": 21.0,
            "excluded_market_value": 35.0,
            "excluded_row_count": 7.0,
        }

        with patch("app.st.markdown") as markdown:
            render_manager_attribution_coverage(coverage, "2026-08-06")

        rendered = markdown.call_args.args[0]
        self.assertIn("88.00%", rendered)
        self.assertIn("签名净额归属比 99.70%", rendered)
        self.assertIn("按绝对市值计算", rendered)

    def test_exited_holdings_are_rendered_as_a_separate_reduction_view(self):
        exited = pd.DataFrame(
            {
                "asset_name": ["完全退出债券"],
                "asset_class": ["企业债"],
                "account_bucket": ["传统"],
                "prior_full_market_value": [6.0],
                "full_market_value_delta": [-6.0],
                "monthly_position_flow_delta": [-6.0],
            }
        )

        with (
            patch("app.st.markdown") as markdown,
            patch("app.st.caption") as caption,
            patch("app.st.dataframe") as dataframe,
        ):
            render_manager_exited_holdings(
                exited,
                "2026-06-30",
                table_key="manager-attribution-exited-test",
            )

        self.assertIn("本月完全退出资产", markdown.call_args.args[0])
        self.assertIn("不进入持仓面积图", caption.call_args.args[0])
        self.assertEqual(dataframe.call_count, 1)


if __name__ == "__main__":
    unittest.main()
