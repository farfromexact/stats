import json
import shutil
import unittest
import uuid
from pathlib import Path
from unittest import mock

import pandas as pd

import portfolio_data
from config import FIELD_MAP, NUMERIC_COLUMNS, REQUIRED_FIELDS
from portfolio_data import (
    SNAPSHOT_STATUS_INTERIM,
    SNAPSHOT_STATUS_OFFICIAL,
    _snapshot_date,
    _snapshot_month,
    _snapshot_status,
    available_snapshots,
    load_snapshots,
    snapshot_display_label,
    snapshot_parquet_dir,
    snapshot_parquet_manifest_path,
)
from scripts.build_snapshot_parquet import build_snapshot_parquet


class ParquetSnapshotLoaderTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1] / "test_tmp" / uuid.uuid4().hex
        self.data_dir = self.root / "data" / "monthly_snapshots"
        self.data_dir.mkdir(parents=True)
        self.snapshot_path = self.data_dir / "snapshot 20260630.xlsx"
        self.write_snapshot(1.0)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write_snapshot(self, value: float, path: Path | None = None) -> None:
        path = path or self.snapshot_path
        row = {}
        for source_field in REQUIRED_FIELDS:
            target_field = FIELD_MAP[source_field]
            row[source_field] = value if target_field in NUMERIC_COLUMNS else f"{target_field}-{value}"
        pd.DataFrame([row]).to_excel(path, index=False)

    def test_snapshot_identity_uses_full_valid_date(self):
        cases = [
            ("snapshot 20260331.xlsx", "2026-03-31", "2026-03", SNAPSHOT_STATUS_OFFICIAL),
            ("snapshot 20260716.xlsx", "2026-07-16", "2026-07", SNAPSHOT_STATUS_INTERIM),
            ("snapshot 20240229.xlsx", "2024-02-29", "2024-02", SNAPSHOT_STATUS_OFFICIAL),
        ]
        for name, expected_date, expected_month, expected_status in cases:
            with self.subTest(name=name):
                self.assertEqual(_snapshot_date(name), expected_date)
                self.assertEqual(_snapshot_month(name), expected_month)
                self.assertEqual(_snapshot_status(expected_date), expected_status)

        self.assertIsNone(_snapshot_date("snapshot 20260230.xlsx"))
        self.assertEqual(snapshot_display_label("2026-07-16"), "2026-07-16（临时中间版）")

    def test_load_snapshots_prefers_matching_parquet(self):
        manifest_path = build_snapshot_parquet(self.data_dir)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        with mock.patch("portfolio_data._read_one", side_effect=AssertionError("Excel fallback used")):
            data, validation, errors = load_snapshots(self.data_dir)

        self.assertEqual(errors, [])
        self.assertEqual(len(data), 1)
        self.assertEqual(len(validation), 1)
        self.assertEqual(float(data["full_market_value"].iloc[0]), 1.0)
        self.assertEqual(validation["source_rows"].iloc[0], 1)
        self.assertEqual(available_snapshots(data), ["2026-06-30"])
        self.assertEqual(manifest["snapshots"][0]["snapshot_date"], "2026-06-30")
        self.assertEqual(manifest["snapshots"][0]["snapshot_status"], SNAPSHOT_STATUS_OFFICIAL)
        self.assertEqual(manifest["snapshots"][0]["parquet_file"], "2026-06-30.parquet")
        self.assertRegex(manifest["snapshots"][0]["parquet_file_hash"], r"^[0-9a-f]{64}$")

    def test_load_snapshots_works_without_excel_sources(self):
        build_snapshot_parquet(self.data_dir)
        shutil.rmtree(self.data_dir)

        with mock.patch("portfolio_data._read_one", side_effect=AssertionError("Excel fallback used")):
            data, validation, errors = load_snapshots(self.data_dir)

        self.assertEqual(errors, [])
        self.assertEqual(len(data), 1)
        self.assertEqual(len(validation), 1)
        self.assertEqual(float(data["full_market_value"].iloc[0]), 1.0)

    def test_parquet_only_load_fails_closed_without_manifest(self):
        build_snapshot_parquet(self.data_dir)
        snapshot_parquet_manifest_path(self.data_dir).unlink()
        shutil.rmtree(self.data_dir)

        data, validation, errors = load_snapshots(self.data_dir)

        self.assertTrue(data.empty)
        self.assertTrue(validation.empty)
        self.assertIn("Parquet", errors[0])

    def test_parquet_only_load_fails_closed_when_file_is_corrupt(self):
        build_snapshot_parquet(self.data_dir)
        manifest = json.loads(snapshot_parquet_manifest_path(self.data_dir).read_text(encoding="utf-8"))
        parquet_name = manifest["snapshots"][0]["parquet_file"]
        (snapshot_parquet_dir(self.data_dir) / parquet_name).write_bytes(b"not parquet")
        shutil.rmtree(self.data_dir)

        data, validation, errors = load_snapshots(self.data_dir)

        self.assertTrue(data.empty)
        self.assertTrue(validation.empty)
        self.assertIn("Parquet", errors[0])

    def test_parquet_only_load_fails_closed_when_required_column_is_missing(self):
        manifest_path = build_snapshot_parquet(self.data_dir)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entry = manifest["snapshots"][0]
        parquet_path = snapshot_parquet_dir(self.data_dir) / entry["parquet_file"]
        frame = pd.read_parquet(parquet_path).drop(columns=["asset_key"])
        frame.to_parquet(parquet_path, index=False)
        entry["parquet_file_hash"] = portfolio_data._file_hash(parquet_path)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        shutil.rmtree(self.data_dir)

        data, validation, errors = load_snapshots(self.data_dir)

        self.assertTrue(data.empty)
        self.assertTrue(validation.empty)
        self.assertIn("Parquet", errors[0])

    def test_parquet_only_load_rejects_unsafe_manifest_path(self):
        manifest_path = build_snapshot_parquet(self.data_dir)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["snapshots"][0]["parquet_file"] = "../2026-06-30.parquet"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        shutil.rmtree(self.data_dir)

        data, validation, errors = load_snapshots(self.data_dir)

        self.assertTrue(data.empty)
        self.assertTrue(validation.empty)
        self.assertIn("Parquet", errors[0])

    def test_parquet_only_load_fails_closed_on_invalid_utf8_manifest(self):
        manifest_path = build_snapshot_parquet(self.data_dir)
        manifest_path.write_bytes(b"\xff\xfe\xfd")
        shutil.rmtree(self.data_dir)

        data, validation, errors = load_snapshots(self.data_dir)

        self.assertTrue(data.empty)
        self.assertTrue(validation.empty)
        self.assertIn("Parquet", errors[0])

    def test_builder_preserves_history_when_only_new_excel_is_local(self):
        first_manifest_path = build_snapshot_parquet(self.data_dir)
        first_manifest = json.loads(first_manifest_path.read_text(encoding="utf-8"))
        first_entry = first_manifest["snapshots"][0]
        first_parquet_hash = first_entry["parquet_file_hash"]

        self.snapshot_path.unlink()
        july_path = self.data_dir / "snapshot 20260731.xlsx"
        self.write_snapshot(2.0, july_path)
        second_manifest_path = build_snapshot_parquet(self.data_dir)
        second_manifest = json.loads(second_manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(
            [entry["snapshot_date"] for entry in second_manifest["snapshots"]],
            ["2026-06-30", "2026-07-31"],
        )
        self.assertEqual(second_manifest["snapshots"][0]["parquet_file_hash"], first_parquet_hash)

        with mock.patch("portfolio_data._read_one", side_effect=AssertionError("Excel fallback used")):
            data, validation, errors = load_snapshots(self.data_dir)
        self.assertEqual(errors, [])
        self.assertEqual(len(validation), 2)
        self.assertEqual(sorted(data["snapshot_date"].unique().tolist()), ["2026-06-30", "2026-07-31"])

        shutil.rmtree(self.data_dir)
        data, validation, errors = load_snapshots(self.data_dir)
        self.assertEqual(errors, [])
        self.assertEqual(len(validation), 2)
        self.assertEqual(len(data), 2)

    def test_same_month_snapshots_remain_separate(self):
        interim = self.data_dir / "snapshot 20260716.xlsx"
        official = self.data_dir / "snapshot 20260731.xlsx"
        self.write_snapshot(16.0, interim)
        self.write_snapshot(31.0, official)

        manifest_path = build_snapshot_parquet(self.data_dir)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        july_entries = [entry for entry in manifest["snapshots"] if entry["snapshot_month"] == "2026-07"]
        self.assertEqual(
            [entry["parquet_file"] for entry in july_entries],
            ["2026-07-16.parquet", "2026-07-31.parquet"],
        )

        data, _, errors = load_snapshots(self.data_dir)
        self.assertEqual(errors, [])
        july = data[data["snapshot_month"].eq("2026-07")]
        self.assertEqual(july.groupby("snapshot_date")["full_market_value"].sum().to_dict(), {
            "2026-07-16": 16.0,
            "2026-07-31": 31.0,
        })

    def test_duplicate_snapshot_date_is_rejected(self):
        duplicate = self.data_dir / "copy 20260630.xlsx"
        self.write_snapshot(2.0, duplicate)

        data, _, errors = load_snapshots(self.data_dir)
        self.assertTrue(data.empty)
        self.assertIn("2026-06-30", errors[0])
        with self.assertRaisesRegex(RuntimeError, "Duplicate snapshot date"):
            build_snapshot_parquet(self.data_dir)

    def test_builder_rejects_snapshot_without_data_rows(self):
        pd.DataFrame(columns=REQUIRED_FIELDS).to_excel(self.snapshot_path, index=False)

        with self.assertRaisesRegex(RuntimeError, "no data rows"):
            build_snapshot_parquet(self.data_dir)

    def test_load_snapshots_falls_back_when_manifest_missing(self):
        build_snapshot_parquet(self.data_dir)
        snapshot_parquet_manifest_path(self.data_dir).unlink()

        with mock.patch("portfolio_data._read_one", wraps=portfolio_data._read_one) as read_one:
            data, _, errors = load_snapshots(self.data_dir)

        self.assertEqual(errors, [])
        self.assertTrue(read_one.called)
        self.assertEqual(len(data), 1)

    def test_load_snapshots_falls_back_when_source_hash_mismatches(self):
        build_snapshot_parquet(self.data_dir)
        self.write_snapshot(2.0)

        with mock.patch("portfolio_data._read_one", wraps=portfolio_data._read_one) as read_one:
            data, _, errors = load_snapshots(self.data_dir)

        self.assertEqual(errors, [])
        self.assertTrue(read_one.called)
        self.assertEqual(float(data["full_market_value"].iloc[0]), 2.0)

    def test_load_snapshots_falls_back_when_parquet_is_corrupt(self):
        build_snapshot_parquet(self.data_dir)
        manifest = json.loads(snapshot_parquet_manifest_path(self.data_dir).read_text(encoding="utf-8"))
        parquet_name = manifest["snapshots"][0]["parquet_file"]
        (snapshot_parquet_dir(self.data_dir) / parquet_name).write_bytes(b"not parquet")

        with mock.patch("portfolio_data._read_one", wraps=portfolio_data._read_one) as read_one:
            data, _, errors = load_snapshots(self.data_dir)

        self.assertEqual(errors, [])
        self.assertTrue(read_one.called)
        self.assertEqual(len(data), 1)

    def test_load_snapshots_falls_back_when_manifest_totals_mismatch(self):
        build_snapshot_parquet(self.data_dir)
        manifest_path = snapshot_parquet_manifest_path(self.data_dir)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["snapshots"][0]["full_market_value"] = 99.0
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        with mock.patch("portfolio_data._read_one", wraps=portfolio_data._read_one) as read_one:
            data, _, errors = load_snapshots(self.data_dir)

        self.assertEqual(errors, [])
        self.assertTrue(read_one.called)
        self.assertEqual(float(data["full_market_value"].iloc[0]), 1.0)

    def test_load_snapshots_falls_back_when_manifest_identity_mismatches(self):
        build_snapshot_parquet(self.data_dir)
        manifest_path = snapshot_parquet_manifest_path(self.data_dir)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["snapshots"][0]["snapshot_status"] = SNAPSHOT_STATUS_INTERIM
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        with mock.patch("portfolio_data._read_one", wraps=portfolio_data._read_one) as read_one:
            data, _, errors = load_snapshots(self.data_dir)

        self.assertEqual(errors, [])
        self.assertTrue(read_one.called)
        self.assertEqual(data["snapshot_status"].iloc[0], SNAPSHOT_STATUS_OFFICIAL)


if __name__ == "__main__":
    unittest.main()
