import unittest

import pandas as pd

from app import _annualization_factor, previous_official_snapshots


class SnapshotSelectionTest(unittest.TestCase):
    def setUp(self):
        self.data = pd.DataFrame(
            [
                {
                    "snapshot_date": "2026-06-30",
                    "snapshot_month": "2026-06",
                    "snapshot_status": "official",
                },
                {
                    "snapshot_date": "2026-07-16",
                    "snapshot_month": "2026-07",
                    "snapshot_status": "interim",
                },
                {
                    "snapshot_date": "2026-07-31",
                    "snapshot_month": "2026-07",
                    "snapshot_status": "official",
                },
            ]
        )

    def test_interim_and_month_end_use_previous_month_official_snapshot(self):
        self.assertEqual(previous_official_snapshots(self.data, "2026-07-16"), ["2026-06-30"])
        self.assertEqual(previous_official_snapshots(self.data, "2026-07-31"), ["2026-06-30"])

    def test_missing_previous_natural_month_does_not_fall_back_further(self):
        without_june = self.data[self.data["snapshot_month"].ne("2026-06")]
        self.assertEqual(previous_official_snapshots(without_june, "2026-07-16"), [])

    def test_interim_annualization_uses_elapsed_days(self):
        self.assertAlmostEqual(_annualization_factor("2026-07-16"), 365 / 197)
        self.assertAlmostEqual(_annualization_factor("2024-02-29"), 366 / 60)


if __name__ == "__main__":
    unittest.main()
