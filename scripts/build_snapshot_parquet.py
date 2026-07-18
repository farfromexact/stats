from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import DATA_DIR
from portfolio_data import (
    PARQUET_MANIFEST_VERSION,
    _read_one,
    discover_snapshot_files,
    snapshot_parquet_dir,
)


def build_snapshot_parquet(data_dir: Path = DATA_DIR, output_dir: Path | None = None) -> Path:
    data_dir = Path(data_dir)
    output_dir = Path(output_dir) if output_dir is not None else snapshot_parquet_dir(data_dir)
    files = discover_snapshot_files(data_dir)
    if not files:
        raise RuntimeError(f"No YYYYMMDD .xlsx snapshots found in {data_dir}.")

    entries: list[dict] = []
    frames_to_write: list[tuple[str, object]] = []
    written_snapshot_dates: set[str] = set()
    for path in files:
        frame, log = _read_one(path)
        if log["status"] != "OK" or frame is None:
            raise RuntimeError(f"{path.name}: {log['message']}")

        snapshot_date = str(log["snapshot_date"])
        if snapshot_date in written_snapshot_dates:
            raise RuntimeError(f"Duplicate snapshot date {snapshot_date}: {path.name}")
        written_snapshot_dates.add(snapshot_date)

        parquet_name = f"{snapshot_date}.parquet"
        frames_to_write.append((parquet_name, frame))
        entries.append(
            {
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
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    for old_file in output_dir.glob("*.parquet"):
        old_file.unlink()
    for parquet_name, frame in frames_to_write:
        frame.to_parquet(output_dir / parquet_name, index=False)

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
