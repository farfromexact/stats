import hashlib
import re
from pathlib import Path

import pandas as pd

from config import DATA_DIR, FIELD_MAP, NUMERIC_COLUMNS, OPTIONAL_FIELDS, REQUIRED_FIELDS


DATE_TOKEN = re.compile(r"(20\d{6})")
OPTIONAL_FIELD_DEFAULTS = {
    "久期": 0.0,
    "资产大类": "",
    "资产分类一级": "",
    "资产分类二级": "",
    "资产分类三级": "",
    "交易策略": "",
}


def _snapshot_month(file_name: str) -> str | None:
    match = DATE_TOKEN.search(file_name)
    if not match:
        return None
    token = match.group(1)
    return f"{token[:4]}-{token[4:6]}"


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
            and _snapshot_month(path.name) is not None
        ],
        key=lambda item: _snapshot_month(item.name) or "",
    )


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
    snapshot = _snapshot_month(path.name)
    log = {
        "snapshot_month": snapshot or "",
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
    standard.insert(0, "snapshot_month", snapshot)

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


def load_snapshots(data_dir: Path = DATA_DIR) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    files = discover_snapshot_files(data_dir)
    if not files:
        return pd.DataFrame(), pd.DataFrame(), [f"未在 {data_dir} 找到带 YYYYMMDD 日期的 .xlsx 月度宽表。"]

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
