import unittest
from unittest.mock import patch

import pandas as pd

from app import render_manager_holding_treemap


class ManagerHoldingTreemapTest(unittest.TestCase):
    def test_compact_text_layout_keeps_small_holding_labels_readable(self):
        holdings = pd.DataFrame(
            [
                {
                    "prior_snapshot_date": "2026-07-31",
                    "asset_class": "股票",
                    "holding_label": "测试资产",
                    "holding_kind": "单项资产",
                    "holding_count": 1,
                    "full_market_value": 1.0,
                    "market_value_share": 1.0,
                    "prior_full_market_value": 0.8,
                    "monthly_position_flow_delta": 0.1,
                    "comprehensive_income_mtd": 0.02,
                    "avg_capital_mtd": 0.5,
                    "comprehensive_return_mtd": 0.04,
                    "comprehensive_income_ytd": 0.1,
                    "avg_capital_ytd": 1.0,
                    "comprehensive_return_ytd": 0.1,
                    "position_change_status": "increase",
                }
            ]
        )

        with (
            patch("app.st.markdown"),
            patch("app.st.caption"),
            patch("app.st.plotly_chart") as plotly_chart,
        ):
            render_manager_holding_treemap(
                holdings,
                pd.DataFrame(),
                chart_key="manager-holding-map-test",
            )

        figure = plotly_chart.call_args.args[0]
        self.assertEqual(
            figure.data[0].texttemplate,
            "<b>%{label}</b><br>%{customdata[2]} %{customdata[6]}",
        )
        self.assertEqual(figure.layout.uniformtext.minsize, 10)
        self.assertEqual(figure.layout.uniformtext.mode, "hide")

    def test_period_choice_updates_holding_map_values_and_tooltip(self):
        holdings = pd.DataFrame(
            [
                {
                    "prior_snapshot_date": "2026-07-31",
                    "asset_class": "股票",
                    "holding_label": "测试资产",
                    "holding_kind": "单项资产",
                    "holding_count": 1,
                    "full_market_value": 1.0,
                    "market_value_share": 1.0,
                    "prior_full_market_value": 0.8,
                    "monthly_position_flow_delta": 0.1,
                    "comprehensive_income_mtd": 0.02,
                    "avg_capital_mtd": 0.5,
                    "comprehensive_return_mtd": 0.04,
                    "comprehensive_income_ytd": 0.1,
                    "avg_capital_ytd": 1.0,
                    "comprehensive_return_ytd": 0.1,
                    "position_change_status": "increase",
                }
            ]
        )

        with (
            patch("app.st.markdown"),
            patch("app.st.caption"),
            patch("app.st.plotly_chart") as plotly_chart,
        ):
            render_manager_holding_treemap(
                holdings,
                pd.DataFrame(),
                chart_key="manager-holding-map-mtd-test",
                period_choice="单月复盘",
            )

        trace = plotly_chart.call_args.args[0].data[0]
        self.assertIn("MTD 综合收益", trace.hovertemplate)
        self.assertNotIn("YTD 综合收益", trace.hovertemplate)
        self.assertEqual(trace.customdata[0][3], "+0.02 亿")
        self.assertEqual(trace.customdata[0][4], "4.00%")


if __name__ == "__main__":
    unittest.main()
