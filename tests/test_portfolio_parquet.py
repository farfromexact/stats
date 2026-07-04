import json
import shutil
import unittest
import uuid
from pathlib import Path
from unittest import mock

import pandas as pd

import portfolio_data
from config import FIELD_MAP, NUMERIC_COLUMNS, REQUIRED_FIELDS
from portfolio_data import load_snapshots, snapshot_parquet_dir, snapshot_parquet_manifest_path
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

    def write_snapshot(self, value: float) -> None:
        row = {}
        for source_field in REQUIRED_FIELDS:
            target_field = FIELD_MAP[source_field]
            row[source_field] = value if target_field in NUMERIC_COLUMNS else f"{target_field}-{value}"
        pd.DataFrame([row]).to_excel(self.snapshot_path, index=False)

    def test_load_snapshots_prefers_matching_parquet(self):
        build_snapshot_parquet(self.data_dir)

        with mock.patch("portfolio_data._read_one", side_effect=AssertionError("Excel fallback used")):
            data, validation, errors = load_snapshots(self.data_dir)

        self.assertEqual(errors, [])
        self.assertEqual(len(data), 1)
        self.assertEqual(len(validation), 1)
        self.assertEqual(float(data["full_market_value"].iloc[0]), 1.0)
        self.assertEqual(validation["source_rows"].iloc[0], 1)

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


if __name__ == "__main__":
    unittest.main()
