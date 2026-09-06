import unittest

import pandas as pd

from manager_position_views import position_peer_history


def row(name, asset_class, value, date="2026-07-31", scope="委内", board="权益", status="official", included=True):
    return dict(attribution_entity_id=f"{scope}::{name}", attribution_entity_name=name,
                attribution_scope=scope, attribution_board=board, attribution_in_scope=included,
                snapshot_date=date, snapshot_month=date[:7], snapshot_status=status,
                asset_class=asset_class, full_market_value=value)


class PositionPeerHistoryTest(unittest.TestCase):
    def test_same_manager_splits_assets_and_does_not_allocate_shared_cash(self):
        data = pd.DataFrame([row("甲", "股票", 80), row("甲", "股票型基金", 20), row("甲", "活期存款", 10)])
        history, peers = position_peer_history(data, "2026-07-31", "权益")
        values = peers.set_index("peer_group")["investment_value"].to_dict()
        self.assertEqual(values, {"委内股票": 80, "委内权益产品": 20})
        self.assertTrue(history["investment_share"].isna().all())

    def test_external_keeps_products_and_direct_in_one_trustee_group(self):
        data = pd.DataFrame([row("机构", "股票", 70, scope="委外"), row("机构", "股票型基金", 10, scope="委外"), row("机构", "活期存款", 20, scope="委外")])
        history, peers = position_peer_history(data, "2026-07-31", "权益")
        self.assertEqual(peers["peer_group"].tolist(), ["权益委外"])
        self.assertAlmostEqual(history["investment_share"].iloc[0], .8)

    def test_fixed_groups_include_deposits_and_exclude_hierarchy_duplicates(self):
        data = pd.DataFrame([row("甲", "存款", 100, board="固收"), row("乙", "债券型基金", 30, board="固收"), row("机构", "企业债", 40, board="固收", scope="委外"), row("乙", "债券型基金", 999, board="固收", included=False)])
        history, peers = position_peer_history(data, "2026-07-31", "固收")
        self.assertEqual(set(peers["peer_group"]), {"委内固收直投", "委内固收产品", "固收委外"})
        self.assertAlmostEqual(history["investment_value"].sum(), 170)

    def test_missing_snapshot_is_not_a_zero_or_a_cross_gap_change(self):
        data = pd.DataFrame([row("甲", "股票", 10, "2026-05-31"), row("乙", "股票", 20, "2026-06-30"), row("甲", "股票", 30, "2026-07-31")])
        history, _ = position_peer_history(data, "2026-07-31", "权益")
        a = history[history["attribution_entity_name"].eq("甲")]
        self.assertTrue(a["market_value_change"].isna().all())
        self.assertTrue(pd.isna(a.loc[a.snapshot_date.eq("2026-06-30"), "investment_value"].iloc[0]))

    def test_latest_interim_is_automatic_and_bounded_by_selected_date(self):
        data = pd.DataFrame([row("甲", "股票", 10), row("甲", "股票", 20, "2026-08-06", status="interim"), row("甲", "股票", 999, "2026-08-31")])
        history, _ = position_peer_history(data, "2026-08-06", "权益")
        self.assertEqual(history.snapshot_date.tolist(), ["2026-07-31", "2026-08-06"])
        history, _ = position_peer_history(data, "2026-08-06", "权益", True)
        self.assertEqual(history.snapshot_date.tolist(), ["2026-07-31", "2026-08-06"])
        self.assertEqual(history.market_value_change.iloc[-1], 10)

    def test_latest_interim_compares_to_formal_month_end_not_previous_interim(self):
        data = pd.DataFrame([
            row("甲", "股票", 10), row("甲", "股票", 20, "2026-08-06", status="interim"),
            row("甲", "股票", 25, "2026-08-27", status="interim"),
            row("甲", "股票", 40, "2026-09-03", status="interim"),
        ])
        history, _ = position_peer_history(data, "2026-09-03", "权益")
        self.assertEqual(history.snapshot_date.tolist(), ["2026-07-31", "2026-09-03"])
        self.assertEqual(history.market_value_change.iloc[-1], 30)
        self.assertEqual(history.baseline_snapshot_date.iloc[-1], "2026-07-31")
        data = pd.concat([data, pd.DataFrame([row("甲", "股票", 32, "2026-08-31")])], ignore_index=True)
        history, _ = position_peer_history(data, "2026-09-03", "权益")
        self.assertEqual(history.market_value_change.iloc[-1], 8)
        self.assertEqual(history.baseline_snapshot_date.iloc[-1], "2026-08-31")

    def test_formal_date_does_not_append_older_interim_and_no_baseline_stays_missing(self):
        data = pd.DataFrame([row("甲", "股票", 20, "2026-07-23", status="interim"), row("甲", "股票", 30)])
        history, _ = position_peer_history(data, "2026-07-31", "权益")
        self.assertEqual(history.snapshot_date.tolist(), ["2026-07-31"])
        self.assertTrue(history.market_value_change.isna().all())
        history, _ = position_peer_history(data, "2026-07-23", "权益")
        self.assertEqual(history.snapshot_date.tolist(), ["2026-07-23"])
        self.assertTrue(history.market_value_change.isna().all())

    def test_income_stays_in_group_and_shared_adjustments_are_not_duplicated(self):
        def income_row(asset_class, value, income, capital):
            return dict(row("甲", asset_class, value), comprehensive_income_ytd=income, avg_capital_ytd=capital)
        data = pd.DataFrame([income_row("股票", 80, 8, 40), income_row("股票型基金", 20, -2, 10), income_row("其它", 0, 5, 0)])
        history, _ = position_peer_history(data, "2026-07-31", "权益")
        by_group = history.set_index("peer_group")
        self.assertEqual(by_group.loc["委内股票", "comprehensive_income_ytd"], 8)
        self.assertEqual(by_group.loc["委内权益产品", "comprehensive_income_ytd"], -2)
        self.assertAlmostEqual(by_group.loc["委内股票", "comprehensive_return_ytd"], .2)
        self.assertAlmostEqual(by_group.loc["委内权益产品", "comprehensive_return_ytd"], -.2)
        history, _ = position_peer_history(data.iloc[[0, 2]], "2026-07-31", "权益")
        self.assertEqual(history.comprehensive_income_ytd.iloc[0], 13)


if __name__ == "__main__":
    unittest.main()
