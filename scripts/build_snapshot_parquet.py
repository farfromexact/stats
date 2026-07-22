from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import DATA_DIR
from portfolio_data import (
    PARQUET_MANIFEST_VERSION,
    _file_hash,
    _parquet_frame_matches_manifest,
    _read_one,
    _snapshot_date,
    _validated_manifest_entries,
    discover_snapshot_files,
    snapshot_parquet_dir,
)


def _load_existing_entries(output_dir: Path) -> list[dict]:
    manifest_path = output_dir / "manifest.json"
    if not manifest_path.exists():
        return []

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Existing parquet manifest is unreadable: {manifest_path}") from exc

    entries = _validated_manifest_entries(manifest)
    if entries is None:
        raise RuntimeError(f"Existing parquet manifest is invalid or outdated: {manifest_path}")

    for entry in entries:
        parquet_path = output_dir / str(entry["parquet_file"])
        try:
            if _file_hash(parquet_path) != entry["parquet_file_hash"]:
                raise RuntimeError(f"Existing parquet hash mismatch: {parquet_path.name}")
            frame = pd.read_parquet(parquet_path)
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Existing parquet is unreadable: {parquet_path.name}") from exc
        if not _parquet_frame_matches_manifest(frame, entry):
            raise RuntimeError(f"Existing parquet does not match its manifest: {parquet_path.name}")
    return entries


def build_snapshot_parquet(data_dir: Path = DATA_DIR, output_dir: Path | None = None) -> Path:
    data_dir = Path(data_dir)
    output_dir = Path(output_dir) if output_dir is not None else snapshot_parquet_dir(data_dir)
    files = discover_snapshot_files(data_dir)
    if not files:
        raise RuntimeError(f"No YYYYMMDD .xlsx snapshots found in {data_dir}.")

    output_dir.mkdir(parents=True, exist_ok=True)
    existing_entries = _load_existing_entries(output_dir)
    entries_by_date = {str(entry["snapshot_date"]): entry for entry in existing_entries}
    frames_to_write: dict[str, object] = {}
    written_snapshot_dates: set[str] = set()
    for path in files:
        snapshot_date = _snapshot_date(path.name)
        if snapshot_date is None:
            raise RuntimeError(f"Invalid snapshot date in {path.name}")
        if snapshot_date in written_snapshot_dates:
            raise RuntimeError(f"Duplicate snapshot date {snapshot_date}: {path.name}")
        written_snapshot_dates.add(snapshot_date)

        existing_entry = entries_by_date.get(snapshot_date)
        source_hash = _file_hash(path)
        if (
            existing_entry is not None
            and existing_entry.get("source_file_name") == path.name
            and existing_entry.get("source_file_hash") == source_hash
        ):
            continue

        frame, log = _read_one(path)
        if log["status"] != "OK" or frame is None:
            raise RuntimeError(f"{path.name}: {log['message']}")
        if int(log["source_rows"]) <= 0:
            raise RuntimeError(f"{path.name}: snapshot contains no data rows")

        parquet_name = f"{snapshot_date}.parquet"
        frames_to_write[parquet_name] = frame
        entries_by_date[snapshot_date] = {
            "snapshot_date": snapshot_date,
            "snapshot_month": log["snapshot_month"],
            "snapshot_status": log["snapshot_status"],
            "source_file_name": log["source_file_name"],
            "source_file_hash": log["source_file_hash"],
            "source_rows": int(log["source_rows"]),
            "sheet_name": log["sheet_name"],
            "full_market_value": float(log["full_market_value"]),
            "finance_income_mtd": float(log["finance_income_mtd"]),
            "comprehensive_income_mtd": float(log["comprehensive_income_mtd"]),
            "parquet_file": parquet_name,
        }

    for parquet_name, frame in frames_to_write.items():
        frame.to_parquet(output_dir / parquet_name, index=False)

    entries = sorted(entries_by_date.values(), key=lambda entry: str(entry["snapshot_date"]))
    for entry in entries:
        parquet_file = output_dir / str(entry["parquet_file"])
        entry["parquet_file_hash"] = _file_hash(parquet_file)

    expected_parquet_files = {str(entry["parquet_file"]) for entry in entries}
    for old_file in output_dir.glob("*.parquet"):
        if old_file.name not in expected_parquet_files:
            old_file.unlink()

    manifest = {
        "manifest_version": PARQUET_MANIFEST_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "snapshots": entries,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build committed parquet snapshots from source Excel files.")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    manifest_path = build_snapshot_parquet(args.data_dir, args.output_dir)
    print(f"Wrote {manifest_path}")


if __name__ == "__main__":
    main()
