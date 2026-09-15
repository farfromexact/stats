"""Stream monthly monitor detail into dated Parquet snapshots; never replace history.

Run with --apply only after reviewing the JSON report from a dry run.
The original workbook is read-only and stays local.
"""
from __future__ import annotations

import argparse
import json
import math
import posixpath
import sys
import shutil
import uuid
import zipfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from lxml import etree as ET

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import DATA_DIR, FIELD_MAP, NUMERIC_COLUMNS, OPTIONAL_FIELDS, REQUIRED_FIELDS
from portfolio_data import (
    PARQUET_MANIFEST_VERSION, _file_hash, _parquet_frame_matches_manifest,
    _snapshot_status, _validated_manifest_entries, normalize_snapshot_rows,
    snapshot_parquet_dir,
)
from scripts.build_snapshot_parquet import _load_existing_entries

M = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
SOURCE_SHEET = '资产明细表'
EXTRA_FIELDS = ['配置计划分类', '策略盘分类']
CONTROL_FIELDS = ['full_market_value', 'finance_income_mtd', 'comprehensive_income_mtd']


@contextmanager
def staging_directory(parent: Path):
    """Use inherited workspace permissions on Windows sandbox accounts."""
    parent = parent.resolve()
    stage = parent/f'monitor-{uuid.uuid4().hex}'
    stage.mkdir()
    try:
        yield stage
    finally:
        if stage.resolve().parent != parent or stage.is_symlink():
            raise ValueError('Unsafe staging cleanup path')
        shutil.rmtree(stage)


def _sheet_paths(z: zipfile.ZipFile) -> dict[str, str]:
    rels = {r.get('Id'): r.get('Target') for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
    workbook = ET.fromstring(z.read('xl/workbook.xml'))
    props = workbook.find(M+'workbookPr')
    if props is not None and props.get('date1904') in {'1', 'true'}:
        raise ValueError('1904 date system is not supported')
    return {s.get('name'): posixpath.normpath(posixpath.join('xl', rels[s.get(R+'id')])).lstrip('/')
            for s in workbook.find(M+'sheets')}


def _cell_value(cell, strings: list[str]):
    value = cell.find(M+'v')
    if value is None or value.text is None:
        inline = cell.find(M+'is')
        return ''.join(t.text or '' for t in inline.iter(M+'t')) if inline is not None else None
    if cell.get('t') == 's':
        return strings[int(value.text)]
    if cell.get('t') in {'str', 'e', 'd'}:
        return value.text
    return float(value.text)


def _date_from_serial(value) -> str:
    if not isinstance(value, (int, float)) or not math.isfinite(value) or value != int(value):
        raise ValueError(f'Invalid snapshot date serial: {value!r}')
    date = (datetime(1899, 12, 30) + timedelta(days=value)).date()
    if not 2000 <= date.year <= 2100:
        raise ValueError(f'Out-of-range date: {date}')
    return date.isoformat()


def extract_detail(source: Path) -> tuple[pd.DataFrame, dict]:
    """Select source columns without evaluating formulas or allocating the full sheet."""
    records, headers_removed = [], []
    with zipfile.ZipFile(source) as z:
        paths = _sheet_paths(z)
        strings = []
        if 'xl/sharedStrings.xml' in z.namelist():
            strings = [''.join(t.text or '' for t in e.iter(M+'t'))
                       for e in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        with z.open(paths[SOURCE_SHEET]) as stream:
            selected = {}
            for _, row in ET.iterparse(stream, events=('end',), tag=M+'row'):
                row_no = int(row.get('r'))
                if row_no == 1:
                    headers = {c.get('r').rstrip('0123456789'): _cell_value(c, strings) for c in row}
                    required = set(REQUIRED_FIELDS) - {'年初市值(亿)'}
                    missing = required - set(headers.values())
                    if missing or '年初市值(亿)' in headers.values():
                        raise ValueError(f'Unexpected monitor schema: missing={sorted(missing)}')
                    selected = {col: name for col, name in headers.items()
                                if name in REQUIRED_FIELDS+OPTIONAL_FIELDS+EXTRA_FIELDS}
                    if len(selected.values()) != len(set(selected.values())):
                        raise ValueError('Duplicate selected headers')
                    selected['A'] = 'snapshot_serial'
                else:
                    record, errors = {'source_row_no': row_no}, []
                    for cell in row:
                        col = cell.get('r', '').rstrip('0123456789')
                        if col not in selected:
                            continue
                        value = _cell_value(cell, strings)
                        record[selected[col]] = value
                        if selected[col] not in EXTRA_FIELDS and (
                            cell.get('t') == 'e' or cell.find(M+'f') is not None and value is None
                        ):
                            errors.append(cell.get('r'))
                    if record.get('资产名称') == '资产名称':
                        if not all(record.get(name) == name for name in required):
                            raise ValueError(f'Partial repeated header at row {row_no}')
                        headers_removed.append(row_no)
                    elif any(v is not None for k, v in record.items() if k != 'source_row_no'):
                        if errors:
                            raise ValueError(f'Excel error or missing formula cache: {errors[:5]}')
                        record['snapshot_date'] = _date_from_serial(record.get('snapshot_serial'))
                        records.append(record)
                row.clear()
                while row.getprevious() is not None:
                    del row.getparent()[0]
                if row_no % 50000 == 0:
                    print(f'Scanned {row_no:,} source rows', flush=True)
        frame = pd.DataFrame(records)
        if frame.empty:
            raise ValueError('No source detail rows')
        for field in REQUIRED_FIELDS+OPTIONAL_FIELDS:
            if field not in frame:
                continue
            if FIELD_MAP[field] in NUMERIC_COLUMNS:
                values = pd.to_numeric(frame[field], errors='coerce')
                invalid = frame[field].notna() & values.isna()
                if invalid.any() or values.dropna().map(lambda v: not math.isfinite(v)).any():
                    raise ValueError(f'Invalid numeric data in {field}')
                frame[field] = values
            elif field != '账套编号':
                frame[field] = frame[field].map(
                    lambda v: str(int(v)) if isinstance(v, float) and v.is_integer()
                    else str(v) if pd.notna(v) else None
                )
        frame.index = frame['source_row_no'] - 2
        audit = {'source_rows': len(frame), 'repeated_header_rows': headers_removed,
                 'source_last_row': row_no, 'missing_fields': ['market_value_year_open']}
        # Independent checks against saved report cells: 15 classes x 4 metrics x dates.
        controls = {}
        root = ET.fromstring(z.read(paths['全量-时序']))
        for cell in root.iter(M+'c'):
            controls[cell.get('r')] = _cell_value(cell, strings)
        checks = []
        for code in range(ord('D'), ord('X')+1):
            col = chr(code)
            date = _date_from_serial(controls[col+'2'])
            subset = frame[frame.snapshot_date.eq(date)]
            if date >= '2026-04-01':
                subset = subset[subset['分账户维度'].ne('穿透账户')]
            for start, field in [(3, '全价市值(亿)'), (20, '平均资金占用（本年以来）(亿)'),
                                 (37, '财务收益（本年以来）(亿)'), (71, '综合收益（本年以来）(亿)')]:
                totals = subset.groupby('配置计划分类')[field].sum()
                for r in range(start, start+15):
                    actual = float(totals.get(controls[f'A{r}'], 0.0))
                    expected = float(controls[f'{col}{r}'])
                    checks.append({'cell': f'{col}{r}', 'snapshot_date': date,
                                   'field': field, 'delta': actual-expected})
        audit['report_checks'] = len(checks)
        audit['report_check_max_abs_delta'] = max(abs(c['delta']) for c in checks)
        audit['report_check_failures'] = [c for c in checks if abs(c['delta']) > 1e-6]
        if audit['report_check_failures']:
            raise ValueError(f'Source report reconciliation failed: {audit["report_check_failures"][:5]}')
    return frame, audit


def import_monitor(source: Path, output_dir: Path, report_path: Path, *, apply: bool = False) -> dict:
    source = Path(source)
    source_hash = _file_hash(source)
    raw, report = extract_detail(source)
    if _file_hash(source) != source_hash:
        raise ValueError('Source workbook changed during extraction')
    existing = _load_existing_entries(output_dir)
    by_date = {e['snapshot_date']: e for e in existing}
    report.update(source_file_name=source.name, source_file_hash=source_hash, snapshots=[], applied=False)
    with staging_directory(report_path.parent) as staged:
        additions = []
        for date, partition in raw.groupby('snapshot_date', sort=True):
            if _snapshot_status(date) != 'official':
                raise ValueError(f'Monitor contains non-month-end date: {date}')
            frame = normalize_snapshot_rows(partition, date, source.name, source_hash, missing_year_open=True)
            frame['source_kind'] = 'monthly_monitor'
            entry = dict(snapshot_date=date, snapshot_month=date[:7], snapshot_status='official',
                         source_file_name=source.name, source_file_hash=source_hash, source_rows=len(frame),
                         sheet_name=SOURCE_SHEET, source_kind='monthly_monitor', source_date_column='A',
                         missing_fields=['market_value_year_open'], parquet_file=f'{date}.parquet',
                         source_row_first=int(frame.source_row_no.min()), source_row_last=int(frame.source_row_no.max()),
                         **{field: float(frame[field].sum()) for field in CONTROL_FIELDS})
            item = dict(snapshot_date=date, source_rows=len(frame), **{field: entry[field] for field in CONTROL_FIELDS})
            if date in by_date:
                old = pd.read_parquet(output_dir/by_date[date]['parquet_file'])
                item.update(action='preserved_existing', existing_rows=len(old),
                            control_deltas={field: entry[field]-float(old[field].sum()) for field in CONTROL_FIELDS})
            else:
                item['action'] = 'add'
                path = staged/entry['parquet_file']
                frame.to_parquet(path, index=False)
                restored = pd.read_parquet(path)
                pd.testing.assert_frame_equal(frame.reset_index(drop=True), restored, check_dtype=False)
                entry['parquet_file_hash'] = _file_hash(path)
                if not _parquet_frame_matches_manifest(restored, entry):
                    raise ValueError(f'Invalid staged snapshot: {date}')
                additions.append(entry)
            report['snapshots'].append(item)
        manifest = dict(manifest_version=PARQUET_MANIFEST_VERSION, created_at=datetime.now(timezone.utc).isoformat(),
                        snapshots=sorted(existing+additions, key=lambda e: e['snapshot_date']))
        if _validated_manifest_entries(manifest) is None:
            raise ValueError('Invalid staged manifest')
        report['added_snapshots'] = len(additions)
        report['added_rows'] = sum(e['source_rows'] for e in additions)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        if apply and additions:
            # Check the destination again after the potentially long source scan.
            if _load_existing_entries(output_dir) != existing:
                raise ValueError('Existing history changed during import')
            output_dir.mkdir(parents=True, exist_ok=True)
            installed = []
            try:
                for entry in additions:
                    target = output_dir/entry['parquet_file']
                    if target.exists():
                        raise FileExistsError(target)
                    (staged/entry['parquet_file']).rename(target)
                    installed.append(target)
                manifest_tmp = output_dir/'manifest.json.tmp'
                manifest_tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
                manifest_tmp.replace(output_dir/'manifest.json')
            except Exception:
                for path in installed:
                    path.unlink()
                raise
            report['applied'] = True
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output-dir', type=Path, default=snapshot_parquet_dir(DATA_DIR))
    parser.add_argument('--report', type=Path, default=ROOT/'output/monthly_history/import_report.json')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    report = import_monitor(args.source, args.output_dir, args.report, apply=args.apply)
    print(json.dumps({k: report[k] for k in ['source_rows','added_snapshots','added_rows','applied']}, ensure_ascii=False))
    print(f'Report: {args.report}')


if __name__ == '__main__':
    main()
