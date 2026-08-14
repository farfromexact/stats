import unittest

import pandas as pd

from config import DATA_DIR
from portfolio_data import load_snapshots
from strategy_books import (
    EQUITY_DASHBOARD_LABEL_ORDER,
    EXCLUDED_STRATEGY_BOOK,
    MANAGER_DISPLAY_COLUMN,
    assign_strategy_book_columns,
    classify_strategy_book,
    ensure_strategy_book_columns,
    equity_dashboard_summary,
    exclusion_reason,
    outsourced_equity_holding_slice,
    outsourced_equity_holding_type,
    strategy_book_item,
    strategy_book_summary,
)


def row(**overrides):
    base = {
        "mandate_type": "委托资管",
        "fund_book_name": "",
        "asset_major_class": "",
        "asset_class_level_1": "",
        "asset_class_level_2": "",
        "asset_class": "",
        "trade_strategy": "",
        "manager": "",
    }
    base.update(overrides)
    return base


class StrategyBookClassificationTest(unittest.TestCase):
    def test_outsourced_rows_use_trustee_display_when_manager_is_unassigned(self):
        source = pd.DataFrame(
            [
                row(
                    mandate_type="单一委外",
                    fund_book_name="大成基金中邮1号单一资产管理计划",
                    asset_major_class="权益",
                    asset_class="股票",
                    manager="未分配/待确认",
                ),
                row(
                    mandate_type="委托太保投资香港",
                    fund_book_name="传统保险产品QDII（太保委托专户）",
                    asset_major_class="权益",
                    asset_class="股票",
                    manager="未分配/待确认",
                ),
                row(
                    mandate_type="委托资管",
                    asset_major_class="权益",
                    trade_strategy="交易",
                    asset_class="股票",
                    manager="鲍淼",
                ),
            ]
        )

        result = assign_strategy_book_columns(source)

        self.assertEqual(result.loc[0, "strategy_book"], "大成基金权益")
        self.assertEqual(result.loc[0, MANAGER_DISPLAY_COLUMN], "大成基金")
        self.assertEqual(result.loc[1, MANAGER_DISPLAY_COLUMN], "太保投资香港")
        self.assertEqual(result.loc[2, MANAGER_DISPLAY_COLUMN], "鲍淼")

    def test_ensure_strategy_book_columns_reuses_complete_classification_without_aliasing(self):
        source = pd.DataFrame(
            [
                row(
                    mandate_type="委托人保",
                    asset_class="企业债",
                    asset_name="人保债",
                    full_market_value=1.0,
                )
            ]
        )
        prepared = assign_strategy_book_columns(source)
        reused = ensure_strategy_book_columns(prepared)

        self.assertEqual(reused.loc[0, "strategy_book"], "人保固收")
        self.assertIsNot(reused, prepared)
        reused.loc[0, "strategy_book"] = "被修改"
        self.assertEqual(prepared.loc[0, "strategy_book"], "人保固收")

    def test_ensure_strategy_book_columns_rebuilds_when_any_output_column_is_missing(self):
        source = pd.DataFrame(
            [row(mandate_type="委托泰康", asset_class="政府债", asset_name="泰康债")]
        )
        prepared = assign_strategy_book_columns(source)

        for missing_column in [
            "strategy_book",
            "strategy_book_scope",
            "strategy_book_display_label",
            "strategy_book_section",
            "strategy_book_item",
            "strategy_book_exclusion_reason",
        ]:
            with self.subTest(missing_column=missing_column):
                rebuilt = ensure_strategy_book_columns(prepared.drop(columns=[missing_column]))
                self.assertIn(missing_column, rebuilt.columns)
                self.assertEqual(rebuilt.loc[0, "strategy_book"], "泰康固收")

    def test_assign_strategy_book_columns_still_forces_reclassification(self):
        source = pd.DataFrame(
            [row(mandate_type="委托人保", asset_class="企业债", asset_name="委外债")]
        )
        prepared = assign_strategy_book_columns(source)
        prepared.loc[0, "mandate_type"] = "委托泰康"
        prepared.loc[0, "asset_class"] = "政府债"

        rebuilt = assign_strategy_book_columns(prepared)

        self.assertEqual(rebuilt.loc[0, "strategy_book"], "泰康固收")

    def test_fixed_income_books_and_exclusions(self):
        self.assertEqual(
            classify_strategy_book(
                row(asset_major_class="固收", trade_strategy="配置", asset_class="政府债")
            ),
            "固收-配置盘",
        )
        self.assertEqual(
            classify_strategy_book(
                row(asset_major_class="固收", trade_strategy="交易", asset_class="金融债")
            ),
            "固收-交易盘",
        )
        self.assertEqual(
            classify_strategy_book(
                row(asset_major_class="固收", trade_strategy="交易,流动性", asset_class="固收类保险资管产品")
            ),
            "固收-交易盘",
        )
        self.assertEqual(
            classify_strategy_book(
                row(asset_major_class="固收", trade_strategy="交易,流动性", asset_class="货币类产品")
            ),
            EXCLUDED_STRATEGY_BOOK,
        )

    def test_nonstandard_and_item_rollups(self):
        self.assertEqual(
            classify_strategy_book(
                row(asset_major_class="固收", trade_strategy="配置", asset_class="信托计划")
            ),
            "非标",
        )
        self.assertEqual(
            strategy_book_item(row(asset_class="资产支持证券")),
            "企业债",
        )
        self.assertEqual(
            strategy_book_item(row(asset_class="债券型基金")),
            "固收类基金及产品",
        )

    def test_equity_books(self):
        self.assertEqual(
            classify_strategy_book(
                row(asset_major_class="权益", trade_strategy="配置", asset_class="股票", manager="鲍淼")
            ),
            "权益-配置盘",
        )
        self.assertEqual(
            classify_strategy_book(
                row(asset_major_class="权益", trade_strategy="交易", asset_class="股票", manager="鲍淼（交易）")
            ),
            "权益-交易盘",
        )
        self.assertEqual(
            classify_strategy_book(
                row(asset_major_class="权益", trade_strategy="交易", asset_class="混合型基金", manager="马楠")
            ),
            "权益-交易盘",
        )
        self.assertEqual(strategy_book_item(row(asset_class="混合型基金")), "股票型产品")
        self.assertEqual(
            classify_strategy_book(
                row(asset_major_class="权益", trade_strategy="交易", asset_class="买入返售", manager="王睿智")
            ),
            EXCLUDED_STRATEGY_BOOK,
        )

    def test_outsourced_books(self):
        self.assertEqual(
            classify_strategy_book(row(mandate_type="委托人保", asset_class="企业债")),
            "人保固收",
        )
        self.assertEqual(
            classify_strategy_book(row(mandate_type="委托泰康", asset_class="政府债")),
            "泰康固收",
        )
        self.assertEqual(
            classify_strategy_book(
                row(mandate_type="单一委外", fund_book_name="富国基金中邮1号单一资产管理计划", asset_class="混合型基金")
            ),
            "富国权益",
        )
        self.assertEqual(
            classify_strategy_book(
                row(mandate_type="单一委外", fund_book_name="富国基金中邮1号单一资产管理计划", asset_class="活期存款")
            ),
            "富国权益",
        )
        self.assertEqual(
            classify_strategy_book(
                row(
                    mandate_type="富国基金单一计划",
                    fund_book_name="分红邮储单一委外专户",
                    asset_class="单一资产管理计划（股票类产品）",
                )
            ),
            "富国权益",
        )
        expected_single_plans = {
            "中信建投单一计划": "中信建投固收",
            "中邮证券单一计划": "中邮证券固收",
            "华夏基金单一计划": "华夏基金权益",
            "国泰海通单一计划": "国泰海通权益",
            "大成基金单一计划": "大成基金权益",
            "广发基金单一计划": "广发基金权益",
        }
        for mandate_type, expected in expected_single_plans.items():
            with self.subTest(mandate_type=mandate_type):
                self.assertEqual(
                    classify_strategy_book(row(mandate_type=mandate_type)),
                    expected,
                )
        self.assertEqual(
            classify_strategy_book(row(mandate_type="委托华泰", asset_class="股票")),
            "华泰权益",
        )
        self.assertEqual(
            classify_strategy_book(row(mandate_type="委托华泰", asset_class="其他（应收）")),
            "华泰权益",
        )
        self.assertEqual(
            classify_strategy_book(row(mandate_type="委托太平资产香港", asset_class="其他（应收）")),
            "太平资产香港",
        )
        self.assertEqual(
            classify_strategy_book(row(mandate_type="委托太保投资香港", asset_class="股权基金")),
            "太保投资香港",
        )
        self.assertEqual(
            classify_strategy_book(row(mandate_type="委托国寿富兰克林", asset_class="货币类基金")),
            "国寿富兰克林",
        )
        self.assertEqual(
            classify_strategy_book(row(mandate_type="委托人保", asset_class="正回购")),
            EXCLUDED_STRATEGY_BOOK,
        )

    def test_outsourced_equity_holding_slice_filters_to_external_equity_assets(self):
        frame = pd.DataFrame(
            [
                row(mandate_type="委托人保", asset_class="企业债", asset_name="人保债"),
                row(mandate_type="委托泰康", asset_class="债券型基金", asset_name="泰康债基"),
                row(
                    mandate_type="单一委外",
                    fund_book_name="富国基金中邮1号单一资产管理计划",
                    asset_class="混合型基金",
                    asset_name="富国混基",
                ),
                row(
                    mandate_type="单一委外",
                    fund_book_name="富国基金中邮1号单一资产管理计划",
                    asset_class="货币类基金",
                    asset_name="富国货基",
                ),
                row(mandate_type="委托华泰", asset_class="股票", asset_name="华泰股票"),
                row(mandate_type="委托太平资产香港", asset_class="股票", asset_name="太平股票"),
                row(mandate_type="委托太保投资香港", asset_class="股权基金", asset_name="太保股权基金"),
                row(mandate_type="委托太保投资香港", asset_class="不动产基金", asset_name="太保不动产"),
                row(mandate_type="委托国寿富兰克林", asset_class="货币类基金", asset_name="国寿货基"),
                row(mandate_type="委托资管", asset_major_class="权益", trade_strategy="交易", asset_class="股票", asset_name="委内股票"),
            ]
        )

        result = outsourced_equity_holding_slice(frame)

        self.assertEqual(
            set(result["asset_name"]),
            {"富国混基", "华泰股票", "太平股票", "太保股权基金"},
        )
        self.assertEqual(set(result["strategy_book_scope"]), {"委外"})
        self.assertEqual(
            set(result["outsourced_equity_holding_type"]),
            {"股票", "基金及产品"},
        )
        self.assertNotIn("人保债", set(result["asset_name"]))
        self.assertNotIn("泰康债基", set(result["asset_name"]))
        self.assertNotIn("国寿货基", set(result["asset_name"]))

    def test_outsourced_equity_holding_type_labels_stock_vs_funds(self):
        self.assertEqual(outsourced_equity_holding_type("股票"), "股票")
        self.assertEqual(outsourced_equity_holding_type("股票型基金"), "基金及产品")
        self.assertEqual(outsourced_equity_holding_type("混合型基金"), "基金及产品")
        self.assertEqual(outsourced_equity_holding_type("股权基金"), "基金及产品")
        self.assertEqual(outsourced_equity_holding_type("债券型基金"), "其他")

    def test_exclusion_reason_marks_private_equity_real_estate(self):
        self.assertEqual(
            exclusion_reason(row(mandate_type="直投", asset_class="不动产基金")),
            "股权/不动产直投，未纳入委内/委外比较核心分类",
        )
        self.assertEqual(
            exclusion_reason(row(mandate_type="直投", asset_class="股权基金")),
            "股权/不动产直投，未纳入委内/委外比较核心分类",
        )
    def test_single_plan_hierarchy_prefers_nonzero_market_value_level(self):
        frame = pd.DataFrame(
            [
                row(
                    snapshot_date="2026-07-16",
                    snapshot_month="2026-07",
                    mandate_type="富国基金单一计划",
                    fund_book_name="分红邮储单一委外专户",
                    full_market_value=5.46,
                    asset_name="六月顶层",
                ),
                row(
                    snapshot_date="2026-07-16",
                    snapshot_month="2026-07",
                    mandate_type="单一委外",
                    fund_book_name="富国基金中邮1号单一资产管理计划",
                    full_market_value=5.47,
                    asset_name="六月底层",
                ),
                row(
                    snapshot_date="2026-07-31",
                    snapshot_month="2026-07",
                    mandate_type="富国基金单一计划",
                    fund_book_name="分红邮储单一委外专户",
                    full_market_value=5.10,
                    asset_name="七月顶层",
                ),
                row(
                    snapshot_date="2026-07-31",
                    snapshot_month="2026-07",
                    mandate_type="单一委外",
                    fund_book_name="富国基金中邮1号单一资产管理计划",
                    full_market_value=0.0,
                    asset_name="七月底层",
                ),
            ]
        )

        result = assign_strategy_book_columns(frame).set_index("asset_name")

        self.assertEqual(result.loc["六月底层", "strategy_book"], "富国权益")
        self.assertEqual(result.loc["六月顶层", "strategy_book"], EXCLUDED_STRATEGY_BOOK)
        self.assertEqual(result.loc["七月顶层", "strategy_book"], "富国权益")
        self.assertEqual(result.loc["七月底层", "strategy_book"], EXCLUDED_STRATEGY_BOOK)
        self.assertIn("避免重复计算底层持仓", result.loc["六月顶层", "strategy_book_exclusion_reason"])
        self.assertIn("已改用顶层产品汇总行", result.loc["七月底层", "strategy_book_exclusion_reason"])


    def test_equity_dashboard_summary_uses_fixed_groups_and_exact_oci_scope(self):
        def dashboard_row(asset_name, **overrides):
            base = row(
                snapshot_date="2026-07-23",
                snapshot_month="2026-07",
                asset_name=asset_name,
                full_market_value=1.0,
                avg_capital_mtd=1.0,
                avg_capital_ytd=1.0,
                finance_income_mtd=0.01,
                comprehensive_income_mtd=0.02,
                finance_income_ytd=0.05,
                comprehensive_income_ytd=0.10,
            )
            base.update(overrides)
            return base

        frame = pd.DataFrame(
            [
                dashboard_row(
                    "鲍淼OCI",
                    asset_major_class="权益",
                    trade_strategy="配置",
                    asset_class="股票",
                    manager="鲍淼",
                    full_market_value=10.0,
                    avg_capital_ytd=10.0,
                    comprehensive_income_ytd=1.0,
                ),
                dashboard_row(
                    "鲍淼2普通股票",
                    asset_major_class="权益",
                    trade_strategy="配置",
                    asset_class="股票",
                    manager="鲍淼2",
                    full_market_value=3.0,
                    avg_capital_ytd=3.0,
                    comprehensive_income_ytd=0.6,
                ),
                dashboard_row(
                    "鲍淼交易股票",
                    asset_major_class="权益",
                    trade_strategy="交易",
                    asset_class="股票",
                    manager="鲍淼（交易）",
                    full_market_value=4.0,
                    avg_capital_ytd=4.0,
                    comprehensive_income_ytd=0.4,
                ),
                *[
                    dashboard_row(
                        asset_class,
                        asset_major_class="权益",
                        trade_strategy="交易",
                        asset_class=asset_class,
                    )
                    for asset_class in [
                        "股票型基金",
                        "混合型基金",
                        "股票型保险资管产品",
                        "混合型保险资管产品",
                    ]
                ],
                dashboard_row(
                    "长股投排除",
                    asset_major_class="权益",
                    trade_strategy="长股投",
                    asset_class="长股投股票",
                    manager="鲍淼",
                    full_market_value=5.0,
                ),
                dashboard_row(
                    "华泰股票",
                    mandate_type="委托华泰",
                    asset_class="股票",
                    full_market_value=2.0,
                ),
                dashboard_row(
                    "华泰现金排除",
                    mandate_type="委托华泰",
                    asset_class="活期存款",
                    full_market_value=4.0,
                ),
                dashboard_row(
                    "太保未上市股权",
                    mandate_type="委托太保投资香港",
                    asset_class="未上市企业股权",
                    full_market_value=3.0,
                ),
                dashboard_row(
                    "太保股权基金",
                    mandate_type="委托太保投资香港",
                    asset_class="股权基金",
                    full_market_value=1.0,
                ),
            ]
        )

        summary = equity_dashboard_summary(frame, "2026-07-23", "年初以来")
        indexed = summary.set_index("equity_group_display_label")

        self.assertEqual(summary["equity_group_display_label"].tolist(), EQUITY_DASHBOARD_LABEL_ORDER)
        self.assertEqual(len(summary), 12)
        self.assertAlmostEqual(indexed.loc["委内-股票", "full_market_value_current"], 7.0)
        self.assertEqual(indexed.loc["委内-股票", "record_count_current"], 2)
        self.assertAlmostEqual(indexed.loc["委内-OCI股票", "full_market_value_current"], 10.0)
        self.assertEqual(indexed.loc["委内-OCI股票", "record_count_current"], 1)
        self.assertAlmostEqual(indexed.loc["委内-权益产品", "full_market_value_current"], 4.0)
        self.assertAlmostEqual(indexed.loc["委外-华泰", "full_market_value_current"], 2.0)
        self.assertAlmostEqual(indexed.loc["委外-太保投资香港", "full_market_value_current"], 4.0)
        self.assertAlmostEqual(indexed.loc["委外-国寿富兰克林", "full_market_value_current"], 0.0)
        self.assertTrue(pd.isna(indexed.loc["委外-国寿富兰克林", "comprehensive_return_mtd"]))

    def test_equity_dashboard_summary_switches_period_metrics(self):
        frame = pd.DataFrame(
            [
                row(
                    snapshot_date="2026-07-23",
                    snapshot_month="2026-07",
                    asset_name="测试股票型基金",
                    asset_major_class="权益",
                    trade_strategy="交易",
                    asset_class="股票型基金",
                    full_market_value=8.0,
                    avg_capital_mtd=2.0,
                    avg_capital_ytd=6.0,
                    finance_income_mtd=0.5,
                    comprehensive_income_mtd=1.0,
                    finance_income_ytd=1.5,
                    comprehensive_income_ytd=3.0,
                )
            ]
        )

        monthly = equity_dashboard_summary(frame, "2026-07-23", "单月复盘").set_index(
            "equity_group_display_label"
        )
        ytd = equity_dashboard_summary(frame, "2026-07-23", "年初以来").set_index(
            "equity_group_display_label"
        )

        self.assertAlmostEqual(monthly.loc["委内-权益产品", "comprehensive_income_mtd_current"], 1.0)
        self.assertAlmostEqual(monthly.loc["委内-权益产品", "comprehensive_return_mtd"], 0.5)
        self.assertAlmostEqual(ytd.loc["委内-权益产品", "comprehensive_income_mtd_current"], 3.0)
        self.assertAlmostEqual(ytd.loc["委内-权益产品", "comprehensive_return_mtd"], 0.5)


class StrategyBookActualSnapshotTest(unittest.TestCase):
    def assert_control_totals(self, month, expected):
        data, _, errors = load_snapshots(DATA_DIR)
        self.assertEqual(errors, [])
        summary = strategy_book_summary(data, month, "年初以来")
        actual = dict(zip(summary["strategy_book"], summary["full_market_value_current"]))
        for label, value in expected.items():
            self.assertAlmostEqual(actual[label], value, places=2)

    def test_20260531_control_totals(self):
        self.assert_control_totals(
            "2026-05-31",
            {
                "固收-配置盘": 5021.527813,
                "固收-交易盘": 952.914891,
                "非标": 227.487674,
                "权益-配置盘": 391.734296,
                "权益-交易盘": 216.014149,
                "人保固收": 127.585198,
                "泰康固收": 44.725977,
                "富国权益": 5.304112,
                "华泰权益": 5.279801,
                "太平资产香港": 4.358990,
                "太保投资香港": 6.805692,
                "国寿富兰克林": 8.348263,
            },
        )

    def test_20260630_control_totals(self):
        self.assert_control_totals(
            "2026-06-30",
            {
                "固收-配置盘": 5095.656198,
                "固收-交易盘": 976.528121,
                "非标": 236.675092,
                "权益-配置盘": 369.793145,
                "权益-交易盘": 242.281259,
                "人保固收": 126.788807,
                "泰康固收": 44.388522,
                "富国权益": 5.465564,
                "华泰权益": 5.606492,
                "太平资产香港": 4.165945,
                "太保投资香港": 6.642500,
                "国寿富兰克林": 8.349550,
            },
        )

    def test_20260716_control_totals(self):
        self.assert_control_totals(
            "2026-07-16",
            {
                "人保固收": 126.847375,
                "泰康固收": 44.433428,
                "中信建投固收": 7.508443,
                "中邮证券固收": 7.464992,
                "富国权益": 5.105000,
                "华泰权益": 5.393595,
                "华夏基金权益": 4.927794,
                "国泰海通权益": 4.725369,
                "大成基金权益": 2.972434,
                "广发基金权益": 2.859837,
                "太平资产香港": 4.253103,
                "太保投资香港": 6.620834,
                "国寿富兰克林": 8.338286,
            },
        )

    def test_20260723_control_totals(self):
        self.assert_control_totals(
            "2026-07-23",
            {
                "固收-配置盘": 5164.443061,
                "固收-交易盘": 997.549488,
                "非标": 237.093911,
                "权益-配置盘": 408.617445,
                "权益-交易盘": 355.609737,
                "人保固收": 127.133418,
                "泰康固收": 44.439693,
                "中信建投固收": 7.512007,
                "中邮证券固收": 7.467390,
                "富国权益": 4.937240,
                "华泰权益": 5.271389,
                "华夏基金权益": 4.818120,
                "国泰海通权益": 4.556547,
                "大成基金权益": 3.006285,
                "广发基金权益": 2.856924,
                "太平资产香港": 4.276681,
                "太保投资香港": 6.699298,
                "国寿富兰克林": 8.341285,
            },
        )

    def test_20260730_control_totals(self):
        self.assert_control_totals(
            "2026-07-30",
            {
                "固收-配置盘": 5198.315209,
                "固收-交易盘": 990.653703,
                "非标": 235.210710,
                "权益-配置盘": 426.590698,
                "权益-交易盘": 353.627487,
                "人保固收": 129.182287,
                "泰康固收": 44.407563,
                "中信建投固收": 7.513819,
                "中邮证券固收": 7.454358,
                "富国权益": 4.763796,
                "华泰权益": 4.905433,
                "华夏基金权益": 4.633333,
                "国泰海通权益": 4.330255,
                "大成基金权益": 3.021332,
                "广发基金权益": 2.632091,
                "太平资产香港": 4.374968,
                "太保投资香港": 6.736225,
                "国寿富兰克林": 8.340885,
            },
        )

    def test_20260731_control_totals(self):
        self.assert_control_totals(
            "2026-07-31",
            {
                "固收-配置盘": 5204.812892,
                "固收-交易盘": 991.215380,
                "非标": 235.229275,
                "权益-配置盘": 420.577577,
                "权益-交易盘": 359.825116,
                "人保固收": 128.720815,
                "泰康固收": 44.425402,
                "中信建投固收": 7.515424,
                "中邮证券固收": 7.452429,
                "富国权益": 4.697120,
                "华泰权益": 4.937460,
                "华夏基金权益": 4.721918,
                "国泰海通权益": 4.412165,
                "大成基金权益": 3.024118,
                "广发基金权益": 2.681748,
                "太平资产香港": 4.403869,
                "太保投资香港": 6.811128,
                "国寿富兰克林": 8.339163,
            },
        )

    def test_20260806_control_totals(self):
        self.assert_control_totals(
            "2026-08-06",
            {
                "固收-配置盘": 5216.346281,
                "固收-交易盘": 990.419610,
                "非标": 235.336167,
                "权益-配置盘": 408.606020,
                "权益-交易盘": 386.673799,
                "人保固收": 128.850382,
                "泰康固收": 44.141438,
                "中信建投固收": 7.519233,
                "中邮证券固收": 7.479676,
                "富国权益": 4.896889,
                "华泰权益": 5.180671,
                "华夏基金权益": 4.978069,
                "国泰海通权益": 4.632137,
                "大成基金权益": 3.037196,
                "广发基金权益": 2.849701,
                "太平资产香港": 4.323285,
                "太保投资香港": 6.896342,
                "国寿富兰克林": 8.345743,
            },
        )

    def test_20260813_control_totals(self):
        self.assert_control_totals(
            "2026-08-13",
            {
                "固收-配置盘": 5244.915801,
                "固收-交易盘": 991.301027,
                "非标": 235.466860,
                "权益-配置盘": 406.602607,
                "权益-交易盘": 373.806951,
                "人保固收": 128.277759,
                "泰康固收": 43.474846,
                "中信建投固收": 7.520943,
                "中邮证券固收": 7.473360,
                "富国权益": 4.983190,
                "华泰权益": 5.342653,
                "华夏基金权益": 5.041976,
                "国泰海通权益": 4.721747,
                "大成基金权益": 3.060895,
                "广发基金权益": 2.903062,
                "太平资产香港": 4.328249,
                "太保投资香港": 6.868812,
                "国寿富兰克林": 8.342002,
            },
        )

    def test_20260723_equity_dashboard_controls(self):
        data, _, errors = load_snapshots(DATA_DIR)
        self.assertEqual(errors, [])
        summary = equity_dashboard_summary(data, "2026-07-23", "年初以来").set_index(
            "equity_group_display_label"
        )
        expected_market_values = {
            "委内-股票": 128.3823312035,
            "委内-权益产品": 227.2276287323,
            "委内-OCI股票": 408.6174452043,
            "委外-富国": 4.5509548101,
            "委外-华泰": 5.1347308957,
            "委外-华夏基金": 2.8016626223,
            "委外-国泰海通": 3.8092182366,
            "委外-大成基金": 1.5829507944,
            "委外-广发基金": 2.7844222937,
            "委外-太平资产香港": 1.7497896485,
            "委外-太保投资香港": 2.9822281950,
            "委外-国寿富兰克林": 0.0,
        }
        expected_comprehensive_income = {
            "委内-股票": -14.7709466097,
            "委内-权益产品": 8.4853370217,
            "委内-OCI股票": 15.3142426560,
            "委外-富国": -0.0628327534,
            "委外-华泰": 0.2707341040,
            "委外-华夏基金": -0.1817457536,
            "委外-国泰海通": -0.4431840354,
            "委外-大成基金": 0.0740532090,
            "委外-广发基金": -0.1428590069,
            "委外-太平资产香港": -0.6019822658,
            "委外-太保投资香港": -0.8854345953,
            "委外-国寿富兰克林": 0.0,
        }

        self.assertEqual(summary.index.tolist(), EQUITY_DASHBOARD_LABEL_ORDER)
        for label, expected in expected_market_values.items():
            self.assertAlmostEqual(summary.loc[label, "full_market_value_current"], expected, places=6)
        for label, expected in expected_comprehensive_income.items():
            self.assertAlmostEqual(
                summary.loc[label, "comprehensive_income_mtd_current"],
                expected,
                places=6,
            )
        self.assertTrue(pd.isna(summary.loc["委外-国寿富兰克林", "comprehensive_return_mtd"]))

    def test_20260730_equity_dashboard_controls(self):
        data, _, errors = load_snapshots(DATA_DIR)
        self.assertEqual(errors, [])
        summary = equity_dashboard_summary(data, "2026-07-30", "年初以来").set_index(
            "equity_group_display_label"
        )
        expected_market_values = {
            "委内-股票": 135.7896219540,
            "委内-权益产品": 217.8380718143,
            "委内-OCI股票": 426.5906975901,
            "委外-富国": 4.2835977733,
            "委外-华泰": 4.7770776529,
            "委外-华夏基金": 3.7526065566,
            "委外-国泰海通": 3.5697605536,
            "委外-大成基金": 1.8822039763,
            "委外-广发基金": 2.1708634583,
            "委外-太平资产香港": 1.8483986367,
            "委外-太保投资香港": 3.0770500626,
            "委外-国寿富兰克林": 0.0,
        }
        expected_comprehensive_income = {
            "委内-股票": -16.5701156707,
            "委内-权益产品": -4.8217749059,
            "委内-OCI股票": 32.8830524276,
            "委外-富国": -0.2362126600,
            "委外-华泰": -0.0951577706,
            "委外-华夏基金": -0.3664560100,
            "委外-国泰海通": -0.6693886998,
            "委外-大成基金": 0.0215344894,
            "委外-广发基金": -0.3676981457,
            "委外-太平资产香港": -0.5033732776,
            "委外-太保投资香港": -0.8476368905,
            "委外-国寿富兰克林": 0.0,
        }

        self.assertEqual(summary.index.tolist(), EQUITY_DASHBOARD_LABEL_ORDER)
        for label, expected in expected_market_values.items():
            self.assertAlmostEqual(summary.loc[label, "full_market_value_current"], expected, places=6)
        for label, expected in expected_comprehensive_income.items():
            self.assertAlmostEqual(
                summary.loc[label, "comprehensive_income_mtd_current"],
                expected,
                places=6,
            )
        self.assertTrue(pd.isna(summary.loc["委外-国寿富兰克林", "comprehensive_return_mtd"]))

    def test_20260731_equity_dashboard_controls(self):
        data, _, errors = load_snapshots(DATA_DIR)
        self.assertEqual(errors, [])
        summary = equity_dashboard_summary(data, "2026-07-31", "年初以来").set_index(
            "equity_group_display_label"
        )
        expected_market_values = {
            "委内-股票": 143.9111290602,
            "委内-权益产品": 215.9141976741,
            "委内-OCI股票": 420.5775773938,
            "委外-富国": 4.2957343350,
            "委外-华泰": 4.8147533415,
            "委外-华夏基金": 4.1252175447,
            "委外-国泰海通": 3.7268620207,
            "委外-大成基金": 1.9118378810,
            "委外-广发基金": 2.2193222292,
            "委外-太平资产香港": 1.8778843480,
            "委外-太保投资香港": 3.1527264751,
            "委外-国寿富兰克林": 0.0,
        }
        expected_comprehensive_income = {
            "委内-股票": -14.3783470151,
            "委内-权益产品": -4.8702332645,
            "委内-OCI股票": 26.8268153677,
            "委外-富国": -0.3028851687,
            "委外-华泰": -0.0631255527,
            "委外-华夏基金": -0.2778602178,
            "委外-国泰海通": -0.5874664770,
            "委外-大成基金": 0.0243226750,
            "委外-广发基金": -0.3180336617,
            "委外-太平资产香港": -0.4738875663,
            "委外-太保投资香港": -0.7719604780,
            "委外-国寿富兰克林": 0.0,
        }

        self.assertEqual(summary.index.tolist(), EQUITY_DASHBOARD_LABEL_ORDER)
        for label, expected in expected_market_values.items():
            self.assertAlmostEqual(summary.loc[label, "full_market_value_current"], expected, places=6)
        for label, expected in expected_comprehensive_income.items():
            self.assertAlmostEqual(
                summary.loc[label, "comprehensive_income_mtd_current"],
                expected,
                places=6,
            )
        self.assertTrue(pd.isna(summary.loc["委外-国寿富兰克林", "comprehensive_return_mtd"]))

    def test_20260806_equity_dashboard_controls(self):
        data, _, errors = load_snapshots(DATA_DIR)
        self.assertEqual(errors, [])
        summary = equity_dashboard_summary(data, "2026-08-06", "年初以来").set_index(
            "equity_group_display_label"
        )
        expected_market_values = {
            "委内-股票": 152.5502987876,
            "委内-权益产品": 234.1237234359,
            "委内-OCI股票": 408.6060200822,
            "委外-富国": 4.6423490441,
            "委外-华泰": 5.0588428061,
            "委外-华夏基金": 4.3944873513,
            "委外-国泰海通": 3.8632508814,
            "委外-大成基金": 1.9249609726,
            "委外-广发基金": 2.1746052664,
            "委外-太平资产香港": 1.7953494031,
            "委外-太保投资香港": 3.1997688753,
            "委外-国寿富兰克林": 0.0,
        }
        expected_comprehensive_income = {
            "委内-股票": -10.0554480152,
            "委内-权益产品": 6.8259210924,
            "委内-OCI股票": 12.6710948123,
            "委外-富国": -0.1030152043,
            "委外-华泰": 0.1801418955,
            "委外-华夏基金": -0.0216392267,
            "委外-国泰海通": -0.3674201775,
            "委外-大成基金": 0.0374457666,
            "委外-广发基金": -0.1500358848,
            "委外-太平资产香港": -0.5564225112,
            "委外-太保投资香港": -0.6914949635,
            "委外-国寿富兰克林": 0.0,
        }

        self.assertEqual(summary.index.tolist(), EQUITY_DASHBOARD_LABEL_ORDER)
        for label, expected in expected_market_values.items():
            self.assertAlmostEqual(summary.loc[label, "full_market_value_current"], expected, places=6)
        for label, expected in expected_comprehensive_income.items():
            self.assertAlmostEqual(
                summary.loc[label, "comprehensive_income_mtd_current"],
                expected,
                places=6,
            )
        self.assertTrue(pd.isna(summary.loc["委外-国寿富兰克林", "comprehensive_return_mtd"]))

    def test_20260630_outsourced_equity_holding_total(self):
        data, _, errors = load_snapshots(DATA_DIR)
        self.assertEqual(errors, [])
        current = outsourced_equity_holding_slice(data[data["snapshot_date"] == "2026-06-30"])

        self.assertAlmostEqual(float(current["full_market_value"].sum()), 14.884508, places=6)
        actual = dict(current.groupby("strategy_book")["full_market_value"].sum())
        self.assertAlmostEqual(actual["富国权益"], 4.666486, places=6)
        self.assertAlmostEqual(actual["华泰权益"], 5.402002, places=6)
        self.assertAlmostEqual(actual["华夏基金权益"], 0.077609, places=6)
        self.assertAlmostEqual(actual["国泰海通权益"], 0.103667, places=6)
        self.assertAlmostEqual(actual["大成基金权益"], 0.058735, places=6)
        self.assertAlmostEqual(actual["广发基金权益"], 0.063514, places=6)
        self.assertAlmostEqual(actual["太平资产香港"], 1.703431, places=6)
        self.assertAlmostEqual(actual["太保投资香港"], 2.809063, places=6)
        type_actual = dict(current.groupby("outsourced_equity_holding_type")["full_market_value"].sum())
        self.assertAlmostEqual(type_actual["股票"], 7.179149, places=6)
        self.assertAlmostEqual(type_actual["基金及产品"], 7.705359, places=6)


if __name__ == "__main__":
    unittest.main()
