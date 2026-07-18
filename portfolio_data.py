import hashlib
import json
import re
from calendar import monthrange
from datetime import datetime
from pathlib import Path

import pandas as pd

from config import DATA_DIR, FIELD_MAP, NUMERIC_COLUMNS, OPTIONAL_FIELDS, REQUIRED_FIELDS


DATE_TOKEN = re.compile(r"(20\d{6})")
PARQUET_MANIFEST_VERSION = "snapshot-parquet-v2"
PARQUET_DIR_NAME = "snapshot_parquet"
PARQUET_MANIFEST_NAME = "manifest.json"
SNAPSHOT_STATUS_OFFICIAL = "official"
SNAPSHOT_STATUS_INTERIM = "interim"
OPTIONAL_FIELD_DEFAULTS = {
    "久期": 0.0,
    "资产大类": "",
    "资产分类一级": "",
    "资产分类二级": "",
    "资产分类三级": "",
    "交易策略": "",
}


def _snapshot_date(file_name: str) -> str | None:
    match = DATE_TOKEN.search(file_name)
    if not match:
        return None
    token = match.group(1)
    try:
        return datetime.strptime(token, "%Y%m%d").date().isoformat()
    except ValueError:
        return None


def _snapshot_month(file_name: str) -> str | None:
    snapshot_date = _snapshot_date(file_name)
    return snapshot_date[:7] if snapshot_date else None


def _snapshot_status(snapshot_date: str | None) -> str:
    if not snapshot_date:
        return SNAPSHOT_STATUS_INTERIM
    try:
        parsed = datetime.strptime(snapshot_date, "%Y-%m-%d").date()
    except ValueError:
        return SNAPSHOT_STATUS_INTERIM
    month_end = monthrange(parsed.year, parsed.month)[1]
    return SNAPSHOT_STATUS_OFFICIAL if parsed.day == month_end else SNAPSHOT_STATUS_INTERIM


def snapshot_display_label(snapshot_date: str, snapshot_status: str | None = None) -> str:
    status = snapshot_status or _snapshot_status(snapshot_date)
    suffix = "月末正式版" if status == SNAPSHOT_STATUS_OFFICIAL else "临时中间版"
    return f"{snapshot_date}（{suffix}）"


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_snapshot_files(data_dir: Path = DATA_DIR) -> list[Path]:
    if not data_dir.exists():
        return []
    return sorted(
        [
            path
            for path in data_dir.glob("*.xlsx")
            if not path.name.startswith("~$")
            and _snapshot_date(path.name) is not None
        ],
        key=lambda item: _snapshot_date(item.name) or "",
    )


def snapshot_parquet_dir(data_dir: Path = DATA_DIR) -> Path:
    return Path(data_dir).parent / PARQUET_DIR_NAME


def snapshot_parquet_manifest_path(data_dir: Path = DATA_DIR) -> Path:
    return snapshot_parquet_dir(data_dir) / PARQUET_MANIFEST_NAME


def _clean_label(series: pd.Series, fallback: str) -> pd.Series:
    values = series.fillna("").astype(str).str.strip()
    return values.mask(values.isin(["", "-", "缺省", "nan", "None"]), fallback)


def _read_wide_sheet(path: Path) -> tuple[pd.DataFrame, str, list[str]]:
    with pd.ExcelFile(path) as workbook:
        best_sheet = ""
        best_missing = REQUIRED_FIELDS
        for sheet_name in workbook.sheet_names:
            header = pd.read_excel(workbook, sheet_name=sheet_name, nrows=0)
            missing = [field for field in REQUIRED_FIELDS if field not in header.columns]
            if len(missing) < len(best_missing):
                best_sheet = sheet_name
                best_missing = missing
            if not missing:
                return pd.read_excel(workbook, sheet_name=sheet_name), sheet_name, []
    return pd.DataFrame(), best_sheet, best_missing


def _read_one(path: Path) -> tuple[pd.DataFrame | None, dict]:
    snapshot_date = _snapshot_date(path.name)
    snapshot_month = _snapshot_month(path.name)
    snapshot_status = _snapshot_status(snapshot_date)
    log = {
        "snapshot_date": snapshot_date or "",
        "snapshot_month": snapshot_month or "",
        "snapshot_status": snapshot_status,
        "source_file_name": path.name,
        "source_file_hash": _file_hash(path),
        "source_rows": 0,
        "status": "OK",
        "message": "",
        "sheet_name": "",
        "full_market_value": 0.0,
        "finance_income_mtd": 0.0,
        "comprehensive_income_mtd": 0.0,
    }
    try:
        raw, sheet_name, missing = _read_wide_sheet(path)
        log["sheet_name"] = sheet_name
    except Exception as exc:  # pragma: no cover - surfaced in Streamlit
        log["status"] = "ERROR"
        log["message"] = f"读取失败：{exc}"
        return None, log

    if missing:
        log["status"] = "ERROR"
        log["message"] = "缺少必需字段：" + "、".join(missing)
        return None, log

    source_columns = REQUIRED_FIELDS + [field for field in OPTIONAL_FIELDS if field in raw.columns]
    standard = raw[source_columns].rename(columns=FIELD_MAP).copy()
    for field in OPTIONAL_FIELDS:
        column = FIELD_MAP[field]
        if column not in standard.columns:
            standard[column] = OPTIONAL_FIELD_DEFAULTS.get(field, "")
    standard.insert(0, "source_row_no", raw.index + 2)
    standard.insert(0, "source_file_name", path.name)
    standard.insert(0, "source_file_hash", log["source_file_hash"])
    standard.insert(0, "snapshot_status", snapshot_status)
    standard.insert(0, "snapshot_month", snapshot_month)
    standard.insert(0, "snapshot_date", snapshot_date)

    for column in NUMERIC_COLUMNS:
        standard[column] = pd.to_numeric(standard[column], errors="coerce").fillna(0.0)

    standard["account_bucket"] = _clean_label(standard["account_bucket"], "未分账户/待确认")
    standard["asset_class"] = _clean_label(standard["asset_class"], "未分类/待确认")
    for column in [
        "asset_major_class",
        "asset_class_level_1",
        "asset_class_level_2",
        "asset_class_level_3",
        "trade_strategy",
    ]:
        standard[column] = _clean_label(standard[column], "未填报")
    standard["manager"] = _clean_label(standard["manager"], "未分配/待确认")
    standard["asset_name"] = _clean_label(standard["asset_name"], "未命名资产")
    standard["asset_key"] = (
        standard["asset_code"].fillna("").astype(str).str.strip()
        + "|"
        + standard["trade_code"].fillna("").astype(str).str.strip()
        + "|"
        + standard["asset_name"].fillna("").astype(str).str.strip()
        + "|"
        + standard["account_bucket"].fillna("").astype(str).str.strip()
        + "|"
        + standard["asset_class"].fillna("").astype(str).str.strip()
        + "|"
        + standard["manager"].fillna("").astype(str).str.strip()
    )

    log["source_rows"] = len(standard)
    log["full_market_value"] = float(standard["full_market_value"].sum())
    log["finance_income_mtd"] = float(standard["finance_income_mtd"].sum())
    log["comprehensive_income_mtd"] = float(standard["comprehensive_income_mtd"].sum())
    return standard, log


def _manifest_entry_to_log(entry: dict) -> dict:
    return {
        "snapshot_date": entry.get("snapshot_date", ""),
        "snapshot_month": entry.get("snapshot_month", ""),
        "snapshot_status": entry.get("snapshot_status", ""),
        "source_file_name": entry.get("source_file_name", ""),
        "source_file_hash": entry.get("source_file_hash", ""),
        "source_rows": entry.get("source_rows", 0),
        "status": "OK",
        "message": "",
        "sheet_name": entry.get("sheet_name", ""),
        "full_market_value": entry.get("full_market_value", 0.0),
        "finance_income_mtd": entry.get("finance_income_mtd", 0.0),
        "comprehensive_income_mtd": entry.get("comprehensive_income_mtd", 0.0),
    }


def _parquet_frame_matches_manifest(frame: pd.DataFrame, entry: dict) -> bool:
    if len(frame) != int(entry.get("source_rows", -1)):
        return False

    for column in ["snapshot_date", "snapshot_month", "snapshot_status"]:
        if column not in frame.columns:
            return False
        actual_values = frame[column].dropna().astype(str).unique().tolist()
        if actual_values != [str(entry.get(column, ""))]:
            return False

    for column, manifest_key in [
        ("full_market_value", "full_market_value"),
        ("finance_income_mtd", "finance_income_mtd"),
        ("comprehensive_income_mtd", "comprehensive_income_mtd"),
    ]:
        if column not in frame.columns:
            return False
        actual = float(pd.to_numeric(frame[column], errors="coerce").fillna(0.0).sum())
        expected = float(entry.get(manifest_key, 0.0))
        if abs(actual - expected) > 1e-6:
            return False
    return True


def _load_parquet_snapshots(data_dir: Path, files: list[Path]) -> tuple[pd.DataFrame, pd.DataFrame, list[str]] | None:
    manifest_path = snapshot_parquet_manifest_path(data_dir)
    if not manifest_path.exists():
        return None

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if manifest.get("manifest_version") != PARQUET_MANIFEST_VERSION:
        return None
    entries = manifest.get("snapshots")
    if not isinstance(entries, list):
        return None

    entries_by_name = {str(entry.get("source_file_name", "")): entry for entry in entries}
    if set(entries_by_name) != {path.name for path in files}:
        return None

    parquet_dir = snapshot_parquet_dir(data_dir)
    frames: list[pd.DataFrame] = []
    logs: list[dict] = []
    for path in files:
        entry = entries_by_name[path.name]
        snapshot_date = _snapshot_date(path.name)
        snapshot_status = _snapshot_status(snapshot_date)
        if entry.get("snapshot_date") != snapshot_date:
            return None
        if entry.get("snapshot_month") != _snapshot_month(path.name):
            return None
        if entry.get("snapshot_status") != snapshot_status:
            return None
        if entry.get("source_file_hash") != _file_hash(path):
            return None
        parquet_file = parquet_dir / str(entry.get("parquet_file", ""))
        if not parquet_file.exists():
            return None
        try:
            frame = pd.read_parquet(parquet_file)
        except Exception:
            return None
        if not _parquet_frame_matches_manifest(frame, entry):
            return None
        frames.append(frame)
        logs.append(_manifest_entry_to_log(entry))

    if not frames:
        return None
    return pd.concat(frames, ignore_index=True), pd.DataFrame(logs), []


def load_snapshots(
    data_dir: Path = DATA_DIR,
    prefer_parquet: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    files = discover_snapshot_files(data_dir)
    if not files:
        return pd.DataFrame(), pd.DataFrame(), [f"未在 {data_dir} 找到带 YYYYMMDD 日期的 .xlsx 月度宽表。"]

    snapshot_dates = [_snapshot_date(path.name) for path in files]
    duplicate_dates = sorted({date for date in snapshot_dates if date and snapshot_dates.count(date) > 1})
    if duplicate_dates:
        return (
            pd.DataFrame(),
            pd.DataFrame(),
            ["同一数据时点存在多个源文件，请只保留一份：" + "、".join(duplicate_dates)],
        )

    if prefer_parquet:
        parquet_result = _load_parquet_snapshots(data_dir, files)
        if parquet_result is not None:
            return parquet_result

    frames: list[pd.DataFrame] = []
    logs: list[dict] = []
    errors: list[str] = []
    for path in files:
        frame, log = _read_one(path)
        logs.append(log)
        if log["status"] != "OK":
            errors.append(f"{path.name}: {log['message']}")
        elif frame is not None:
            frames.append(frame)

    if errors:
        return pd.DataFrame(), pd.DataFrame(logs), errors

    data = pd.concat(frames, ignore_index=True)
    validation = pd.DataFrame(logs)
    return data, validation, []


def available_months(data: pd.DataFrame) -> list[str]:
    if data.empty:
        return []
    return sorted(data["snapshot_month"].dropna().unique().tolist())


def available_snapshots(data: pd.DataFrame) -> list[str]:
    if data.empty or "snapshot_date" not in data.columns:
        return []
    return sorted(data["snapshot_date"].dropna().astype(str).unique().tolist())
