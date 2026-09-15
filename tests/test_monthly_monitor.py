import json
import shutil
import uuid
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from app import (
    MONTH_REVIEW_MODE, SNAPSHOT_COMPARISON_MODE, YEAR_TO_DATE_MODE,
    comparison_modes_for_snapshot, previous_official_snapshots,
)
from account_review import asset_evidence_year_open, current_vs_year_open
from config import FIELD_MAP, NUMERIC_COLUMNS, OPTIONAL_FIELDS, REQUIRED_FIELDS
from portfolio_data import (
    _load_parquet_snapshots, _parquet_frame_matches_manifest, _validated_manifest_entries,
    normalize_snapshot_rows,
)
from scripts.import_monthly_monitor import _date_from_serial, import_monitor


def source_rows():
    rows = []
    for date, row_number, amount in [('2025-12-31', 5, 10.0), ('2026-01-31', 12, 11.0)]:
        row = {field: 1.0 if FIELD_MAP[field] in NUMERIC_COLUMNS else 'source value'
               for field in REQUIRED_FIELDS+OPTIONAL_FIELDS if field != '年初市值(亿)'}
        row.update(snapshot_date=date, source_row_no=row_number)
        row['全价市值(亿)'] = amount
        rows.append(row)
    return pd.DataFrame(rows, index=[3, 10])


class MonthlyMonitorImportTest(unittest.TestCase):
    def test_imported_history_has_frozen_source_controls(self):
        parquet_dir = Path(__file__).resolve().parents[1]/'data/snapshot_parquet'
        expected = {
            '2024-12-31': (7769, 5561.1281629714, 4.5144737093, 156.0097730337),
            '2025-01-31': (6983, 5701.9936019260, 8.3637465440, 21.2604389546),
            '2025-02-28': (5039, 5833.7647531789, 20.7258325768, -29.5588507246),
            '2025-03-31': (5425, 5791.7551542603, 8.9852054228, -39.0384101295),
            '2025-04-30': (5745, 5932.4112196911, 6.9635575445, 103.4258185332),
            '2025-05-31': (7584, 6002.6643982636, 20.2233354714, 12.4531752283),
            '2025-06-30': (8247, 6177.7753858400, 34.0753880651, 80.7608865589),
            '2025-07-31': (9438, 6332.1582703986, 31.3363434552, 9.4457405809),
            '2025-08-31': (9960, 6361.8546537109, 34.6054332066, -49.9030590412),
            '2025-09-30': (10388, 6288.6935273803, 19.7575188445, -89.8268283530),
            '2025-10-31': (10566, 6364.4986990811, 13.1061637711, 76.5995038573),
            '2025-11-30': (10810, 6348.0891045577, 2.7892978222, -21.7510415230),
            '2025-12-31': (11226, 6299.7408032911, 15.0028098352, -28.6582887137),
            '2026-01-31': (6420, 6635.5758391000, 36.5527348793, 50.8299660493),
            '2026-02-28': (6942, 6841.9695640950, 11.5096798737, 9.7397630589),
        }
        for date, (rows, *totals) in expected.items():
            with self.subTest(date=date):
                frame = pd.read_parquet(parquet_dir/f'{date}.parquet')
                self.assertEqual(len(frame), rows)
                self.assertTrue(frame.market_value_year_open.isna().all())
                self.assertTrue(frame.source_row_no.is_unique)
                self.assertEqual(frame.snapshot_date.unique().tolist(), [date])
                for field, total in zip(['full_market_value','finance_income_mtd','comprehensive_income_mtd'], totals):
                    self.assertAlmostEqual(float(frame[field].sum()), total, places=7)

    def test_import_is_parquet_only_preserves_overlap_and_is_idempotent(self):
        root = Path(__file__).resolve().parents[1]/'test_tmp'/uuid.uuid4().hex
        root.mkdir(parents=True)
        try:
            source = root/'monthly monitor.xlsx'
            source.write_bytes(b'fixture source; extraction is mocked')
            output = root/'snapshot_parquet'
            with patch('scripts.import_monthly_monitor.extract_detail', return_value=(source_rows(), {})):
                preview = import_monitor(source, output, root/'preview.json')
                self.assertEqual(preview['added_snapshots'], 2)
                self.assertFalse(output.exists())
                result = import_monitor(source, output, root/'report.json', apply=True)
                self.assertTrue(result['applied'])
                before = {p.name: p.read_bytes() for p in output.iterdir()}
                changed_rows = source_rows()
                changed_rows['全价市值(亿)'] = 99.0
                with patch('scripts.import_monthly_monitor.extract_detail', return_value=(changed_rows, {})):
                    repeat = import_monitor(source, output, root/'repeat.json', apply=True)
                self.assertEqual(repeat['added_snapshots'], 0)
                self.assertTrue(all(p.read_bytes() == before[p.name] for p in output.iterdir()))
            frame, validation, errors = _load_parquet_snapshots(root/'monthly_snapshots', [])
            self.assertEqual(errors, [])
            self.assertEqual(len(validation), 2)
            self.assertEqual(frame.source_row_no.tolist(), [5, 12])
            self.assertEqual(frame.full_market_value.tolist(), [10.0, 11.0])
            self.assertTrue(frame.market_value_year_open.isna().all())
            manifest = json.loads((output/'manifest.json').read_text(encoding='utf8'))
            self.assertIsNotNone(_validated_manifest_entries(manifest))
            corrupted = frame.iloc[:1].copy()
            corrupted['market_value_year_open'] = 0.0
            self.assertFalse(_parquet_frame_matches_manifest(corrupted, manifest['snapshots'][0]))
            manifest['snapshots'][0]['source_date_column'] = 'B'
            self.assertIsNone(_validated_manifest_entries(manifest))
        finally:
            self.assertEqual(root.resolve().parent, (Path(__file__).resolve().parents[1]/'test_tmp').resolve())
            shutil.rmtree(root)

    def test_dates_must_be_complete_excel_dates(self):
        self.assertEqual(_date_from_serial(45657), '2024-12-31')
        for invalid in [None, '2025-01', 45657.5, float('nan'), 1]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                _date_from_serial(invalid)

    def test_missing_open_does_not_become_zero_or_false_position_change(self):
        raw = source_rows().iloc[:1]
        frame = normalize_snapshot_rows(raw, '2025-12-31', 'monitor.xlsx', 'a'*64, missing_year_open=True)
        result = current_vs_year_open(frame, '2025-12-31', ['account_bucket'])
        self.assertTrue(result.full_market_value_prior.isna().all())
        self.assertTrue(result.full_market_value_delta.isna().all())
        self.assertEqual(result.finance_income_mtd_current.tolist(), [1.0])
        with self.assertRaisesRegex(ValueError, '年初市值'):
            asset_evidence_year_open(frame, '2025-12-31')

    def test_modes_use_month_end_across_year_boundary_and_handle_earliest_snapshot(self):
        data = pd.DataFrame([
            dict(snapshot_date='2025-12-31', snapshot_month='2025-12', snapshot_status='official', market_value_year_open=float('nan')),
            dict(snapshot_date='2026-01-31', snapshot_month='2026-01', snapshot_status='official', market_value_year_open=float('nan')),
            dict(snapshot_date='2026-02-28', snapshot_month='2026-02', snapshot_status='official', market_value_year_open=1.0),
        ])
        self.assertEqual(comparison_modes_for_snapshot(data, '2025-12-31'), [SNAPSHOT_COMPARISON_MODE])
        self.assertEqual(comparison_modes_for_snapshot(data, '2026-01-31'), [YEAR_TO_DATE_MODE, MONTH_REVIEW_MODE, SNAPSHOT_COMPARISON_MODE])
        self.assertEqual(previous_official_snapshots(data, '2026-01-31'), ['2025-12-31'])
        self.assertIn(YEAR_TO_DATE_MODE, comparison_modes_for_snapshot(data, '2026-02-28'))


if __name__ == '__main__':
    unittest.main()
