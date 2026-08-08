import math
import unittest

import pandas as pd

from manager_attribution import (
    ATTRIBUTION_BOARD_EQUITY,
    ATTRIBUTION_BOARD_FIXED,
    ATTRIBUTION_BOARD_UNATTRIBUTED,
    build_manager_attribution_rows,
    default_manager_entities,
    hierarchy_exclusion_summary,
    manager_asset_class_attribution,
    manager_asset_detail,
    manager_exited_holdings,
    manager_holding_map,
    manager_attribution_change_summary,
    manager_attribution_coverage_summary,
    manager_attribution_reconciliation,
    manager_attribution_summary,
    manager_attribution_timeseries,
    rank_manager_timeseries,
)


def source_row(
    *,
    snapshot_date="2026-07-31",
    snapshot_status="official",
    manager="固收甲",
    mandate_type="委托资管",
    asset_major_class="固收",
    trade_strategy="配置",
    asset_class="企业债",
    asset_name="测试资产",
    fund_book_name="",
    full_market_value=10.0,
    avg_capital_mtd=10.0,
    avg_capital_ytd=10.0,
    comprehensive_income_mtd=1.0,
    comprehensive_income_ytd=2.0,
):
    return {
        "snapshot_date": snapshot_date,
        "snapshot_month": snapshot_date[:7],
        "snapshot_status": snapshot_status,
        "manager": manager,
        "mandate_type": mandate_type,
        "fund_book_name": fund_book_name,
        "group_book_name": "",
        "asset_major_class": asset_major_class,
        "asset_class_level_1": asset_major_class,
        "asset_class_level_2": asset_class,
        "asset_class_level_3": asset_class,
        "trade_strategy": trade_strategy,
        "asset_class": asset_class,
        "asset_name": asset_name,
        "asset_key": f"{snapshot_date}-{asset_name}",
        "asset_code": asset_name,
        "trade_code": asset_name,
        "account_bucket": "传统",
        "full_market_value": full_market_value,
        "avg_capital_mtd": avg_capital_mtd,
        "avg_capital_ytd": avg_capital_ytd,
        "finance_income_mtd": comprehensive_income_mtd / 2,
        "finance_income_ytd": comprehensive_income_ytd / 2,
        "comprehensive_income_mtd": comprehensive_income_mtd,
        "comprehensive_income_ytd": comprehensive_income_ytd,
    }


class ManagerAttributionTest(unittest.TestCase):
    def test_classifies_adjustments_joint_teams_and_unattributed_rows(self):
        source = pd.DataFrame(
            [
                source_row(manager="固收甲", asset_name="固收核心"),
                source_row(manager="固收乙", asset_name="固收乙核心"),
                source_row(
                    manager="权益乙",
                    mandate_type="委托资管",
                    asset_major_class="权益",
                    trade_strategy="交易",
                    asset_class="股票",
                    asset_name="权益核心",
                ),
                source_row(
                    manager="",
                    mandate_type="委托人保",
                    asset_major_class="固收",
                    trade_strategy="配置",
                    asset_class="企业债",
                    asset_name="人保债券",
                ),
                source_row(
                    manager="固收甲",
                    asset_major_class="未填报",
                    trade_strategy="",
                    asset_class="其他（应收）",
                    asset_name="固收调节项",
                ),
                source_row(
                    manager="固收甲,固收乙",
                    asset_major_class="未填报",
                    trade_strategy="",
                    asset_class="其他（应收）",
                    asset_name="同板块联合调节项",
                ),
                source_row(
                    manager="固收甲,权益乙",
                    asset_major_class="未填报",
                    trade_strategy="",
                    asset_class="其他（应收）",
                    asset_name="跨板块联合调节项",
                ),
                source_row(
                    manager="",
                    asset_major_class="未填报",
                    trade_strategy="",
                    asset_class="其他（应收）",
                    asset_name="未分配调节项",
                ),
            ]
        )

        attributed = build_manager_attribution_rows(source).set_index("asset_name")

        self.assertNotIn("attribution_board", source.columns)
        self.assertEqual(attributed.loc["固收核心", "attribution_board"], ATTRIBUTION_BOARD_FIXED)
        self.assertEqual(attributed.loc["权益核心", "attribution_board"], ATTRIBUTION_BOARD_EQUITY)
        self.assertEqual(attributed.loc["人保债券", "attribution_scope"], "委外")
        self.assertEqual(attributed.loc["人保债券", "attribution_entity_name"], "人保")
        self.assertEqual(attributed.loc["固收调节项", "attribution_board"], ATTRIBUTION_BOARD_FIXED)
        self.assertEqual(attributed.loc["同板块联合调节项", "attribution_board"], ATTRIBUTION_BOARD_FIXED)
        self.assertEqual(
            attributed.loc["同板块联合调节项", "attribution_entity_name"],
            "固收甲,固收乙",
        )
        self.assertEqual(
            attributed.loc["跨板块联合调节项", "attribution_board"],
            ATTRIBUTION_BOARD_UNATTRIBUTED,
        )
        self.assertEqual(
            attributed.loc["未分配调节项", "attribution_board"],
            ATTRIBUTION_BOARD_UNATTRIBUTED,
        )

    def test_single_plan_hierarchy_is_excluded_before_reconciliation(self):
        source = pd.DataFrame(
            [
                source_row(
                    manager="",
                    mandate_type="富国基金单一计划",
                    asset_major_class="权益",
                    trade_strategy="交易",
                    asset_class="单一资产管理计划（股票类产品）",
                    asset_name="富国顶层",
                    full_market_value=10.0,
                ),
                source_row(
                    manager="",
                    mandate_type="单一委外",
                    fund_book_name="富国基金中邮1号单一资产管理计划",
                    asset_major_class="权益",
                    trade_strategy="交易",
                    asset_class="股票",
                    asset_name="富国底层",
                    full_market_value=6.0,
                ),
            ]
        )

        attributed = build_manager_attribution_rows(source)
        indexed = attributed.set_index("asset_name")
        reconciliation = manager_attribution_reconciliation(attributed, "2026-07-31")
        excluded = hierarchy_exclusion_summary(attributed, "2026-07-31")

        self.assertFalse(bool(indexed.loc["富国顶层", "attribution_in_scope"]))
        self.assertTrue(bool(indexed.loc["富国底层", "attribution_in_scope"]))
        self.assertAlmostEqual(float(reconciliation["full_market_value"].sum()), 6.0)
        self.assertEqual(excluded["row_count"], 1.0)
        self.assertAlmostEqual(excluded["full_market_value"], 10.0)

    def test_summary_returns_and_reconciliation_use_aggregated_denominators(self):
        source = pd.DataFrame(
            [
                source_row(
                    manager="固收甲",
                    asset_name="债券A",
                    full_market_value=10.0,
                    avg_capital_mtd=8.0,
                    avg_capital_ytd=8.0,
                    comprehensive_income_mtd=0.8,
                    comprehensive_income_ytd=1.6,
                ),
                source_row(
                    manager="固收甲",
                    asset_name="债券B",
                    full_market_value=20.0,
                    avg_capital_mtd=12.0,
                    avg_capital_ytd=12.0,
                    comprehensive_income_mtd=1.2,
                    comprehensive_income_ytd=2.4,
                ),
                source_row(
                    manager="固收零",
                    asset_name="零资本债券",
                    full_market_value=1.0,
                    avg_capital_mtd=0.0,
                    avg_capital_ytd=0.0,
                    comprehensive_income_mtd=0.1,
                    comprehensive_income_ytd=0.2,
                ),
                source_row(
                    manager="",
                    asset_major_class="未填报",
                    trade_strategy="",
                    asset_class="其他（应收）",
                    asset_name="未归属收益",
                    full_market_value=3.0,
                    comprehensive_income_ytd=0.3,
                ),
            ]
        )
        attributed = build_manager_attribution_rows(source)

        summary = manager_attribution_summary(attributed, "2026-07-31", ATTRIBUTION_BOARD_FIXED)
        manager_a = summary.set_index("attribution_entity_name").loc["固收甲"]
        manager_zero = summary.set_index("attribution_entity_name").loc["固收零"]
        reconciliation = manager_attribution_reconciliation(attributed, "2026-07-31")
        eligible = attributed[attributed["attribution_in_scope"]]

        self.assertAlmostEqual(manager_a["full_market_value"], 30.0)
        self.assertAlmostEqual(manager_a["comprehensive_return_mtd"], 0.10)
        self.assertAlmostEqual(manager_a["comprehensive_return_ytd"], 0.20)
        self.assertTrue(math.isnan(manager_zero["comprehensive_return_ytd"]))
        self.assertAlmostEqual(
            float(reconciliation["full_market_value"].sum()),
            float(eligible["full_market_value"].sum()),
        )
        self.assertAlmostEqual(
            float(reconciliation["comprehensive_income_ytd"].sum()),
            float(eligible["comprehensive_income_ytd"].sum()),
        )

    def test_timeseries_defaults_to_official_dates_and_preserves_gaps(self):
        source = pd.DataFrame(
            [
                source_row(
                    snapshot_date="2026-06-30",
                    manager="固收甲",
                    asset_name="六月债券",
                    avg_capital_mtd=10.0,
                    comprehensive_income_mtd=1.0,
                ),
                source_row(
                    snapshot_date="2026-07-16",
                    snapshot_status="interim",
                    manager="固收甲",
                    asset_name="七月中债券",
                    avg_capital_mtd=20.0,
                    comprehensive_income_mtd=1.0,
                ),
                source_row(
                    snapshot_date="2026-07-31",
                    manager="固收甲",
                    asset_name="七月末债券",
                    avg_capital_mtd=20.0,
                    comprehensive_income_mtd=2.0,
                ),
                source_row(
                    snapshot_date="2026-07-31",
                    manager="固收乙",
                    asset_name="七月新增债券",
                    avg_capital_mtd=5.0,
                    comprehensive_income_mtd=0.5,
                ),
            ]
        )
        attributed = build_manager_attribution_rows(source)

        official = manager_attribution_timeseries(
            attributed,
            "2026-07-31",
            ATTRIBUTION_BOARD_FIXED,
        )
        with_interim = manager_attribution_timeseries(
            attributed,
            "2026-07-31",
            ATTRIBUTION_BOARD_FIXED,
            include_interim=True,
        )
        interim_cutoff = manager_attribution_timeseries(
            attributed,
            "2026-07-16",
            ATTRIBUTION_BOARD_FIXED,
        )

        self.assertEqual(sorted(official["snapshot_date"].unique().tolist()), ["2026-06-30", "2026-07-31"])
        self.assertEqual(
            sorted(with_interim["snapshot_date"].unique().tolist()),
            ["2026-06-30", "2026-07-16", "2026-07-31"],
        )
        self.assertEqual(interim_cutoff["snapshot_date"].unique().tolist(), ["2026-06-30"])
        manager_b = official[official["attribution_entity_name"].eq("固收乙")]
        self.assertEqual(manager_b["snapshot_date"].tolist(), ["2026-07-31"])
        manager_a = official[official["attribution_entity_name"].eq("固收甲")]
        self.assertTrue((manager_a["comprehensive_return_mtd"].round(6) == 0.1).all())

    def test_timeseries_ranking_uses_full_board_before_filtering_selection(self):
        timeseries = pd.DataFrame(
            {
                "snapshot_date": [
                    "2026-06-30",
                    "2026-06-30",
                    "2026-06-30",
                    "2026-06-30",
                    "2026-07-31",
                    "2026-07-31",
                ],
                "attribution_entity_id": ["甲", "乙", "丙", "未选择", "甲", "乙"],
                "comprehensive_income_ytd": [3.0, 1.0, math.nan, 10.0, -1.0, 2.0],
            }
        )

        ranked = rank_manager_timeseries(
            timeseries,
            ["甲", "乙", "丙"],
            "comprehensive_income_ytd",
        )
        june = ranked[ranked["snapshot_date"].eq("2026-06-30")].set_index(
            "attribution_entity_id"
        )
        july = ranked[ranked["snapshot_date"].eq("2026-07-31")].set_index(
            "attribution_entity_id"
        )

        self.assertNotIn("未选择", ranked["attribution_entity_id"].tolist())
        self.assertEqual(int(june.loc["甲", "board_rank"]), 2)
        self.assertEqual(int(june.loc["乙", "board_rank"]), 3)
        self.assertTrue(pd.isna(june.loc["丙", "board_rank"]))
        self.assertEqual(int(june.loc["甲", "board_count"]), 3)
        self.assertEqual(int(july.loc["乙", "board_rank"]), 1)
        self.assertEqual(int(july.loc["甲", "board_rank"]), 2)

    def test_coverage_uses_absolute_market_value_without_netting_adjustments(self):
        source = pd.DataFrame(
            [
                source_row(manager="固收甲", asset_name="固收", full_market_value=10.0),
                source_row(
                    manager="权益乙",
                    asset_major_class="权益",
                    trade_strategy="交易",
                    asset_class="股票",
                    asset_name="权益",
                    full_market_value=5.0,
                ),
                source_row(
                    manager="",
                    asset_major_class="未填报",
                    trade_strategy="",
                    asset_class="其他（应收）",
                    asset_name="未归属调节",
                    full_market_value=-2.0,
                ),
                source_row(
                    manager="",
                    mandate_type="富国基金单一计划",
                    asset_major_class="权益",
                    trade_strategy="交易",
                    asset_class="单一资产管理计划（股票类产品）",
                    asset_name="层级排除",
                    full_market_value=4.0,
                ),
            ]
        )
        attributed = build_manager_attribution_rows(source)
        attributed.loc[
            attributed["asset_name"].eq("层级排除"),
            "attribution_in_scope",
        ] = False

        coverage = manager_attribution_coverage_summary(attributed, "2026-07-31")

        self.assertAlmostEqual(coverage["market_value_coverage"], 15.0 / 17.0)
        self.assertAlmostEqual(coverage["net_market_value_coverage"], 15.0 / 13.0)
        self.assertAlmostEqual(coverage["row_coverage"], 2.0 / 3.0)
        self.assertAlmostEqual(coverage["unattributed_market_value"], -2.0)
        self.assertAlmostEqual(coverage["excluded_market_value"], 4.0)
        self.assertEqual(coverage["excluded_row_count"], 1.0)

    def test_manager_change_summary_keeps_new_and_exited_entities(self):
        source = pd.DataFrame(
            [
                source_row(
                    snapshot_date="2026-06-30",
                    manager="固收甲",
                    asset_name="甲旧",
                    full_market_value=100.0,
                    comprehensive_income_mtd=0.0,
                ),
                source_row(
                    snapshot_date="2026-06-30",
                    manager="固收乙",
                    asset_name="乙退出",
                    full_market_value=30.0,
                    comprehensive_income_mtd=0.0,
                ),
                source_row(
                    snapshot_date="2026-07-31",
                    manager="固收甲",
                    asset_name="甲新",
                    full_market_value=112.0,
                    comprehensive_income_mtd=2.0,
                ),
                source_row(
                    snapshot_date="2026-07-31",
                    manager="固收丙",
                    asset_name="丙新建",
                    full_market_value=20.0,
                    comprehensive_income_mtd=1.0,
                ),
            ]
        )
        attributed = build_manager_attribution_rows(source)

        changes = manager_attribution_change_summary(
            attributed,
            "2026-07-31",
            "2026-06-30",
            ATTRIBUTION_BOARD_FIXED,
        ).set_index("attribution_entity_name")

        self.assertAlmostEqual(changes.loc["固收甲", "estimated_flow"], 10.0)
        self.assertAlmostEqual(changes.loc["固收乙", "estimated_flow"], -30.0)
        self.assertAlmostEqual(changes.loc["固收丙", "estimated_flow"], 19.0)
        self.assertAlmostEqual(float(changes["estimated_flow"].sum()), -1.0)

    def test_default_entities_and_detail_outputs(self):
        summary = pd.DataFrame(
            {
                "attribution_entity_id": [f"委内::经理{i}" for i in range(7)],
                "full_market_value": [1.0, 7.0, 2.0, 6.0, 3.0, 5.0, 4.0],
            }
        )
        self.assertEqual(
            default_manager_entities(summary),
            ["委内::经理1", "委内::经理3", "委内::经理5", "委内::经理6", "委内::经理4"],
        )

        source = pd.DataFrame(
            [
                source_row(manager="固收甲", asset_name="债券A", asset_class="企业债"),
                source_row(
                    manager="固收甲",
                    asset_name="存款A",
                    asset_class="存款",
                    full_market_value=5.0,
                ),
            ]
        )
        attributed = build_manager_attribution_rows(source)
        entity_id = manager_attribution_summary(
            attributed,
            "2026-07-31",
            ATTRIBUTION_BOARD_FIXED,
        )["attribution_entity_id"].iloc[0]
        classes = manager_asset_class_attribution(
            attributed,
            "2026-07-31",
            ATTRIBUTION_BOARD_FIXED,
            entity_id,
        )
        detail = manager_asset_detail(
            attributed,
            "2026-07-31",
            ATTRIBUTION_BOARD_FIXED,
            entity_id,
        )

        self.assertEqual(set(classes["asset_class"]), {"企业债", "存款"})
        self.assertAlmostEqual(float(classes["market_value_share"].sum()), 1.0)
        self.assertEqual(set(detail["asset_name"]), {"债券A", "存款A"})

    def test_holding_map_rolls_up_long_tail_and_omits_negative_adjustments(self):
        source = pd.DataFrame(
            [
                source_row(manager="固收甲", asset_name="债券A", full_market_value=10.0),
                source_row(manager="固收甲", asset_name="债券B", full_market_value=9.0),
                source_row(manager="固收甲", asset_name="债券C", full_market_value=8.0),
                source_row(manager="固收甲", asset_name="债券D", full_market_value=1.0),
                source_row(
                    manager="固收甲",
                    asset_name="负值调节项",
                    asset_major_class="未填报",
                    trade_strategy="",
                    asset_class="其他（应收）",
                    full_market_value=-2.0,
                ),
            ]
        )
        attributed = build_manager_attribution_rows(source)
        entity_id = manager_attribution_summary(
            attributed,
            "2026-07-31",
            ATTRIBUTION_BOARD_FIXED,
        ).set_index("attribution_entity_name").loc["固收甲", "attribution_entity_id"]

        holdings = manager_holding_map(
            attributed,
            "2026-07-31",
            ATTRIBUTION_BOARD_FIXED,
            entity_id,
            max_assets=2,
        )

        self.assertEqual(set(holdings["holding_label"]), {"债券A", "债券B", "其他企业债持仓（2项）"})
        self.assertNotIn("负值调节项", holdings["holding_label"].tolist())
        self.assertAlmostEqual(float(holdings["full_market_value"].sum()), 28.0)
        self.assertAlmostEqual(float(holdings["market_value_share"].sum()), 1.0)
        tail = holdings[holdings["holding_kind"].eq("长尾合并")].iloc[0]
        self.assertEqual(int(tail["holding_count"]), 2)

    def test_holding_map_marks_new_increased_decreased_and_flat_positions(self):
        source = pd.DataFrame(
            [
                source_row(
                    snapshot_date="2026-06-30",
                    asset_name="债券A",
                    full_market_value=8.0,
                    comprehensive_income_mtd=0.0,
                ),
                source_row(
                    snapshot_date="2026-07-31",
                    asset_name="债券A",
                    full_market_value=10.0,
                    comprehensive_income_mtd=1.0,
                ),
                source_row(
                    snapshot_date="2026-06-30",
                    asset_name="债券B",
                    full_market_value=12.0,
                    comprehensive_income_mtd=0.0,
                ),
                source_row(
                    snapshot_date="2026-07-31",
                    asset_name="债券B",
                    full_market_value=9.0,
                    comprehensive_income_mtd=0.0,
                ),
                source_row(
                    snapshot_date="2026-07-31",
                    asset_name="债券C",
                    full_market_value=5.0,
                    comprehensive_income_mtd=0.0,
                ),
                source_row(
                    snapshot_date="2026-06-30",
                    asset_name="债券D",
                    full_market_value=4.0,
                    comprehensive_income_mtd=0.0,
                ),
                source_row(
                    snapshot_date="2026-07-31",
                    asset_name="债券D",
                    full_market_value=4.0,
                    comprehensive_income_mtd=0.0,
                ),
            ]
        )
        attributed = build_manager_attribution_rows(source)
        entity_id = manager_attribution_summary(
            attributed,
            "2026-07-31",
            ATTRIBUTION_BOARD_FIXED,
        )["attribution_entity_id"].iloc[0]

        holdings = manager_holding_map(
            attributed,
            "2026-07-31",
            ATTRIBUTION_BOARD_FIXED,
            entity_id,
            max_assets=10,
            prior_snapshot_date="2026-06-30",
        ).set_index("holding_label")

        self.assertEqual(holdings.loc["债券A", "position_change_status"], "increase")
        self.assertEqual(holdings.loc["债券A", "position_change_badge"], "↑")
        self.assertAlmostEqual(holdings.loc["债券A", "monthly_position_flow_delta"], 1.0)
        self.assertEqual(holdings.loc["债券B", "position_change_status"], "decrease")
        self.assertEqual(holdings.loc["债券B", "position_change_badge"], "↓")
        self.assertEqual(holdings.loc["债券C", "position_change_status"], "new")
        self.assertEqual(holdings.loc["债券C", "position_change_badge"], "NEW")
        self.assertEqual(holdings.loc["债券D", "position_change_status"], "flat")
        self.assertEqual(holdings.loc["债券D", "position_change_badge"], "→")

    def test_holding_map_keeps_fully_exited_assets_out_of_treemap_and_exposes_them(self):
        source = pd.DataFrame(
            [
                source_row(
                    snapshot_date="2026-06-30",
                    asset_name="保留债券",
                    full_market_value=10.0,
                    comprehensive_income_mtd=0.0,
                ),
                source_row(
                    snapshot_date="2026-07-31",
                    asset_name="保留债券",
                    full_market_value=11.0,
                    comprehensive_income_mtd=1.0,
                ),
                source_row(
                    snapshot_date="2026-06-30",
                    asset_name="完全退出债券",
                    full_market_value=6.0,
                    comprehensive_income_mtd=0.0,
                ),
            ]
        )
        attributed = build_manager_attribution_rows(source)
        entity_id = manager_attribution_summary(
            attributed,
            "2026-07-31",
            ATTRIBUTION_BOARD_FIXED,
        )["attribution_entity_id"].iloc[0]

        holdings = manager_holding_map(
            attributed,
            "2026-07-31",
            ATTRIBUTION_BOARD_FIXED,
            entity_id,
            prior_snapshot_date="2026-06-30",
        )
        exited = manager_exited_holdings(
            attributed,
            "2026-07-31",
            ATTRIBUTION_BOARD_FIXED,
            entity_id,
            prior_snapshot_date="2026-06-30",
        )

        self.assertEqual(holdings["holding_label"].tolist(), ["保留债券"])
        self.assertEqual(exited["asset_name"].tolist(), ["完全退出债券"])
        self.assertTrue(bool(exited.loc[0, "is_exited"]))
        self.assertEqual(exited.loc[0, "flow_status"], "exited")
        self.assertAlmostEqual(exited.loc[0, "full_market_value"], 0.0)
        self.assertAlmostEqual(exited.loc[0, "prior_full_market_value"], 6.0)
        self.assertAlmostEqual(exited.loc[0, "full_market_value_delta"], -6.0)
        self.assertAlmostEqual(exited.loc[0, "monthly_position_flow_delta"], -6.0)

    def test_holding_change_matching_survives_asset_class_migration(self):
        prior = source_row(
            snapshot_date="2026-06-30",
            asset_name="迁移债券旧名称",
            asset_class="企业债",
            full_market_value=8.0,
            comprehensive_income_mtd=0.0,
        )
        current = source_row(
            snapshot_date="2026-07-31",
            asset_name="迁移债券新名称",
            asset_class="金融债",
            full_market_value=10.0,
            comprehensive_income_mtd=1.0,
        )
        prior["asset_code"] = "BOND-STABLE-001"
        current["asset_code"] = "BOND-STABLE-001"
        attributed = build_manager_attribution_rows(pd.DataFrame([prior, current]))
        entity_id = manager_attribution_summary(
            attributed,
            "2026-07-31",
            ATTRIBUTION_BOARD_FIXED,
        )["attribution_entity_id"].iloc[0]

        holdings = manager_holding_map(
            attributed,
            "2026-07-31",
            ATTRIBUTION_BOARD_FIXED,
            entity_id,
            prior_snapshot_date="2026-06-30",
        ).set_index("holding_label")
        exited = manager_exited_holdings(
            attributed,
            "2026-07-31",
            ATTRIBUTION_BOARD_FIXED,
            entity_id,
            prior_snapshot_date="2026-06-30",
        )

        self.assertTrue(exited.empty)
        self.assertEqual(holdings.index.tolist(), ["迁移债券新名称"])
        self.assertAlmostEqual(holdings.loc["迁移债券新名称", "prior_full_market_value"], 8.0)
        self.assertAlmostEqual(holdings.loc["迁移债券新名称", "monthly_position_flow_delta"], 1.0)
        self.assertEqual(holdings.loc["迁移债券新名称", "position_change_status"], "increase")


if __name__ == "__main__":
    unittest.main()
