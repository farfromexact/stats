import unittest

import pandas as pd

from config import DATA_DIR
from portfolio_data import load_snapshots
from strategy_books import (
    EXCLUDED_STRATEGY_BOOK,
    assign_strategy_book_columns,
    classify_strategy_book,
    ensure_strategy_book_columns,
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
