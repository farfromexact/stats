from __future__ import annotations

import re

import numpy as np
import pandas as pd

from outsourced_funding import adjust_outsourced_funding_capital

from strategy_books import (
    OUTSOURCED_FIXED_BOOKS,
    OUTSOURCED_FULL_ACCOUNT_BOOKS,
    ensure_strategy_book_columns,
)


ATTRIBUTION_BOARD_FIXED = "固收"
ATTRIBUTION_BOARD_EQUITY = "权益"
ATTRIBUTION_BOARD_UNATTRIBUTED = "未归属"
ATTRIBUTION_BOARD_OPTIONS = [ATTRIBUTION_BOARD_FIXED, ATTRIBUTION_BOARD_EQUITY]
ATTRIBUTION_SCOPE_UNATTRIBUTED = "未归属"
RETURN_BASE_THRESHOLD = 0.0001
POSITION_CHANGE_ABSOLUTE_THRESHOLD = 0.001
POSITION_CHANGE_RELATIVE_THRESHOLD = 0.001

FIXED_STRATEGY_BOOKS = {
    "固收-配置盘",
    "固收-交易盘",
    "非标",
    *OUTSOURCED_FIXED_BOOKS,
}
EQUITY_STRATEGY_BOOKS = {
    "权益-配置盘",
    "权益-交易盘",
    *OUTSOURCED_FULL_ACCOUNT_BOOKS,
}

ATTRIBUTION_NUMERIC_COLUMNS = [
    "full_market_value",
    "avg_capital_mtd",
    "avg_capital_ytd",
    "finance_income_mtd",
    "finance_income_ytd",
    "comprehensive_income_mtd",
    "comprehensive_income_ytd",
]
ATTRIBUTION_TEXT_COLUMNS = [
    "snapshot_date",
    "snapshot_month",
    "snapshot_status",
    "manager_display",
    "asset_key",
    "asset_name",
    "asset_code",
    "trade_code",
    "account_bucket",
    "asset_class",
]
HIERARCHY_EXCLUSION_PATTERN = "避免重复计算|已改用顶层产品汇总行"
JOINT_MANAGER_PATTERN = re.compile(r"[,，、;；]+")
UNASSIGNED_MANAGER_LABELS = {"", "未分配/待确认"}


def holding_position_change_status(
    current_market_value: float,
    prior_market_value: float,
    position_flow_delta: float,
    prior_snapshot_available: bool,
) -> str:
    """Classify an estimated holding change without treating missing history as zero."""
    if not prior_snapshot_available:
        return "unavailable"
    if current_market_value > RETURN_BASE_THRESHOLD and prior_market_value <= RETURN_BASE_THRESHOLD:
        return "new"
    threshold = max(
        POSITION_CHANGE_ABSOLUTE_THRESHOLD,
        abs(prior_market_value) * POSITION_CHANGE_RELATIVE_THRESHOLD,
    )
    if position_flow_delta > threshold:
        return "increase"
    if position_flow_delta < -threshold:
        return "decrease"
    return "flat"


def _strategy_book_board(value: object) -> str | None:
    label = "" if pd.isna(value) else str(value).strip()
    if label in FIXED_STRATEGY_BOOKS:
        return ATTRIBUTION_BOARD_FIXED
    if label in EQUITY_STRATEGY_BOOKS:
        return ATTRIBUTION_BOARD_EQUITY
    return None


def _ensure_runtime_columns(data: pd.DataFrame) -> pd.DataFrame:
    working = data.copy()
    for column in ATTRIBUTION_TEXT_COLUMNS:
        if column not in working.columns:
            working[column] = ""
        working[column] = working[column].fillna("").astype(str).str.strip()
    for column in ATTRIBUTION_NUMERIC_COLUMNS:
        if column not in working.columns:
            working[column] = 0.0
        working[column] = pd.to_numeric(working[column], errors="coerce").fillna(0.0)
    return working


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    result = pd.Series(np.nan, index=numerator.index, dtype=float)
    valid = denominator > RETURN_BASE_THRESHOLD
    result.loc[valid] = numerator.loc[valid] / denominator.loc[valid]
    return result


def _snapshot_key(data: pd.DataFrame) -> pd.Series:
    if "snapshot_date" in data.columns and data["snapshot_date"].astype(str).str.strip().ne("").any():
        return data["snapshot_date"].fillna("").astype(str)
    if "snapshot_month" in data.columns:
        return data["snapshot_month"].fillna("").astype(str)
    return pd.Series("__all__", index=data.index, dtype=object)


def _joint_manager_parts(label: str) -> list[str]:
    return [part.strip() for part in JOINT_MANAGER_PATTERN.split(label) if part.strip()]


def _mapping_for_core_rows(
    core: pd.DataFrame,
) -> dict[tuple[str, str], tuple[str, str]]:
    mapping: dict[tuple[str, str], tuple[str, str]] = {}
    if core.empty:
        return mapping

    for (snapshot_key, manager_label), group in core.groupby(
        ["_attribution_snapshot_key", "manager_display"],
        dropna=False,
    ):
        boards = sorted(set(group["attribution_board"].dropna().astype(str)))
        scopes = sorted(set(group["attribution_scope"].dropna().astype(str)))
        if len(boards) == 1 and len(scopes) == 1:
            mapping[(str(snapshot_key), str(manager_label))] = (boards[0], scopes[0])
    return mapping


def _infer_adjustment_assignment(
    snapshot_key: str,
    manager_label: str,
    direct_mapping: dict[tuple[str, str], tuple[str, str]],
) -> tuple[str, str, str]:
    direct = direct_mapping.get((snapshot_key, manager_label))
    if direct:
        return direct[0], direct[1], "按同一主体归回调节项"

    parts = _joint_manager_parts(manager_label)
    if len(parts) < 2:
        return (
            ATTRIBUTION_BOARD_UNATTRIBUTED,
            ATTRIBUTION_SCOPE_UNATTRIBUTED,
            "无法确认主体所属板块",
        )

    assignments = [direct_mapping.get((snapshot_key, part)) for part in parts]
    known_assignments = [assignment for assignment in assignments if assignment is not None]
    if len(known_assignments) == len(parts) and len(set(known_assignments)) == 1:
        board, scope = known_assignments[0]
        return board, scope, "按联合署名成员归回调节项"
    if len({assignment[0] for assignment in known_assignments}) > 1:
        return (
            ATTRIBUTION_BOARD_UNATTRIBUTED,
            ATTRIBUTION_SCOPE_UNATTRIBUTED,
            "跨板块联合署名",
        )
    return (
        ATTRIBUTION_BOARD_UNATTRIBUTED,
        ATTRIBUTION_SCOPE_UNATTRIBUTED,
        "联合署名成员无法全部确认",
    )


def build_manager_attribution_rows(data: pd.DataFrame) -> pd.DataFrame:
    """Attach manager/trustee attribution fields without mutating source data."""
    working = _ensure_runtime_columns(ensure_strategy_book_columns(data))
    working["_attribution_snapshot_key"] = _snapshot_key(working)
    working["attribution_board"] = working["strategy_book"].map(_strategy_book_board)
    working["attribution_scope"] = np.where(
        working["attribution_board"].notna(),
        working["strategy_book_scope"],
        None,
    )
    exclusion_reason = working["strategy_book_exclusion_reason"].fillna("").astype(str)
    working["attribution_in_scope"] = ~exclusion_reason.str.contains(
        HIERARCHY_EXCLUSION_PATTERN,
        regex=True,
        na=False,
    )
    working["attribution_reason"] = np.where(
        working["attribution_board"].notna(),
        "核心策略分类",
        "",
    )

    unassigned_manager = working["manager_display"].isin(UNASSIGNED_MANAGER_LABELS)
    working.loc[unassigned_manager, "attribution_board"] = None
    working.loc[unassigned_manager, "attribution_scope"] = None
    working.loc[unassigned_manager, "attribution_reason"] = "未分配主体"

    hierarchy_excluded = ~working["attribution_in_scope"]
    working.loc[hierarchy_excluded, "attribution_board"] = ATTRIBUTION_BOARD_UNATTRIBUTED
    working.loc[hierarchy_excluded, "attribution_scope"] = ATTRIBUTION_SCOPE_UNATTRIBUTED
    working.loc[hierarchy_excluded, "attribution_reason"] = "上下层重复数据排除"

    core = working[
        working["attribution_in_scope"]
        & working["attribution_board"].isin(ATTRIBUTION_BOARD_OPTIONS)
        & ~working["manager_display"].isin(UNASSIGNED_MANAGER_LABELS)
    ].copy()
    direct_mapping = _mapping_for_core_rows(core)

    adjustment_mask = (
        working["attribution_in_scope"]
        & working["attribution_board"].isna()
    )
    adjustment_keys = list(
        zip(
            working.loc[adjustment_mask, "_attribution_snapshot_key"].astype(str),
            working.loc[adjustment_mask, "manager_display"].astype(str),
        )
    )
    assignment_cache: dict[tuple[str, str], tuple[str, str, str]] = {}
    for snapshot_key, manager_label in dict.fromkeys(adjustment_keys):
        manager_label = manager_label.strip()
        if manager_label in UNASSIGNED_MANAGER_LABELS:
            assignment = (
                ATTRIBUTION_BOARD_UNATTRIBUTED,
                ATTRIBUTION_SCOPE_UNATTRIBUTED,
                "未分配主体",
            )
        else:
            assignment = _infer_adjustment_assignment(
                snapshot_key,
                manager_label,
                direct_mapping,
            )
        assignment_cache[(snapshot_key, manager_label)] = assignment

    adjustment_assignments = [
        assignment_cache[(snapshot_key, manager_label.strip())]
        for snapshot_key, manager_label in adjustment_keys
    ]
    if adjustment_assignments:
        working.loc[adjustment_mask, "attribution_board"] = [
            assignment[0] for assignment in adjustment_assignments
        ]
        working.loc[adjustment_mask, "attribution_scope"] = [
            assignment[1] for assignment in adjustment_assignments
        ]
        working.loc[adjustment_mask, "attribution_reason"] = [
            assignment[2] for assignment in adjustment_assignments
        ]

    working["attribution_board"] = working["attribution_board"].fillna(
        ATTRIBUTION_BOARD_UNATTRIBUTED
    )
    working["attribution_scope"] = working["attribution_scope"].fillna(
        ATTRIBUTION_SCOPE_UNATTRIBUTED
    )
    working["attribution_entity_name"] = working["manager_display"].replace(
        "", "未分配/待确认"
    )
    working["attribution_entity_id"] = (
        working["attribution_scope"].astype(str)
        + "::"
        + working["attribution_entity_name"].astype(str)
    )
    working["_asset_identity"] = working["asset_key"].where(
        working["asset_key"].ne(""),
        working["asset_name"],
    )
    return adjust_outsourced_funding_capital(working.drop(columns=["_attribution_snapshot_key"]))


def _ensure_attribution_rows(data: pd.DataFrame) -> pd.DataFrame:
    required = {
        "attribution_board",
        "attribution_scope",
        "attribution_entity_id",
        "attribution_entity_name",
        "attribution_in_scope",
        "_asset_identity",
    }
    if required.issubset(data.columns):
        return data
    return build_manager_attribution_rows(data)


def _exact_snapshot(data: pd.DataFrame, snapshot_date: str) -> pd.DataFrame:
    key = "snapshot_date" if "snapshot_date" in data.columns else "snapshot_month"
    return data[data[key].astype(str).eq(str(snapshot_date))].copy()


def _aggregate_entities(data: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    if data.empty:
        return pd.DataFrame(
            columns=[
                *group_cols,
                "full_market_value",
                "avg_capital_mtd",
                "avg_capital_ytd",
                "comprehensive_income_mtd",
                "comprehensive_income_ytd",
                "comprehensive_return_mtd",
                "comprehensive_return_ytd",
                "asset_count",
                "row_count",
            ]
        )
    summary = (
        data.groupby(group_cols, dropna=False)
        .agg(
            full_market_value=("full_market_value", "sum"),
            avg_capital_mtd=("avg_capital_mtd", "sum"),
            avg_capital_ytd=("avg_capital_ytd", "sum"),
            comprehensive_income_mtd=("comprehensive_income_mtd", "sum"),
            comprehensive_income_ytd=("comprehensive_income_ytd", "sum"),
            asset_count=("_asset_identity", "nunique"),
            row_count=("asset_name", "size"),
        )
        .reset_index()
    )
    summary["comprehensive_return_mtd"] = _safe_ratio(
        summary["comprehensive_income_mtd"],
        summary["avg_capital_mtd"],
    )
    summary["comprehensive_return_ytd"] = _safe_ratio(
        summary["comprehensive_income_ytd"],
        summary["avg_capital_ytd"],
    )
    return summary


def manager_attribution_summary(
    data: pd.DataFrame,
    snapshot_date: str,
    board: str,
) -> pd.DataFrame:
    working = _ensure_attribution_rows(data)
    current = _exact_snapshot(working, snapshot_date)
    current = current[
        current["attribution_in_scope"]
        & current["attribution_board"].eq(board)
    ]
    summary = _aggregate_entities(
        current,
        [
            "attribution_board",
            "attribution_scope",
            "attribution_entity_id",
            "attribution_entity_name",
        ],
    )
    return summary.sort_values("full_market_value", ascending=False).reset_index(drop=True)


def manager_attribution_change_summary(
    data: pd.DataFrame,
    current_snapshot: str,
    prior_snapshot: str | None,
    board: str,
) -> pd.DataFrame:
    """Estimate entity-level capital flows between two snapshots.

    The estimate removes current-period comprehensive income from the market-value
    change. It is a reconciliation aid, not transaction-level cash-flow data.
    """
    columns = [
        "attribution_board",
        "attribution_scope",
        "attribution_entity_id",
        "attribution_entity_name",
        "current_full_market_value",
        "prior_full_market_value",
        "full_market_value_delta",
        "comprehensive_income_mtd",
        "estimated_flow",
        "prior_snapshot_date",
    ]
    if not prior_snapshot:
        return pd.DataFrame(columns=columns)

    current = manager_attribution_summary(data, current_snapshot, board).rename(
        columns={"full_market_value": "current_full_market_value"}
    )
    prior = manager_attribution_summary(data, str(prior_snapshot), board).rename(
        columns={"full_market_value": "prior_full_market_value"}
    )
    if current.empty and prior.empty:
        return pd.DataFrame(columns=columns)

    identity_columns = [
        "attribution_board",
        "attribution_scope",
        "attribution_entity_id",
        "attribution_entity_name",
    ]
    current_columns = [
        *identity_columns,
        "current_full_market_value",
        "comprehensive_income_mtd",
    ]
    prior_columns = [
        *identity_columns,
        "prior_full_market_value",
    ]
    changes = current[current_columns].merge(
        prior[prior_columns],
        how="outer",
        on=identity_columns,
    )
    for column in [
        "current_full_market_value",
        "prior_full_market_value",
        "comprehensive_income_mtd",
    ]:
        changes[column] = pd.to_numeric(changes[column], errors="coerce").fillna(0.0)
    changes["full_market_value_delta"] = (
        changes["current_full_market_value"] - changes["prior_full_market_value"]
    )
    changes["estimated_flow"] = (
        changes["full_market_value_delta"] - changes["comprehensive_income_mtd"]
    )
    changes["prior_snapshot_date"] = str(prior_snapshot)
    return (
        changes[columns]
        .sort_values("estimated_flow", ascending=False)
        .reset_index(drop=True)
    )


def default_manager_entities(summary: pd.DataFrame, limit: int = 5) -> list[str]:
    if summary.empty or "attribution_entity_id" not in summary.columns:
        return []
    working = summary.copy()
    working["full_market_value"] = pd.to_numeric(
        working.get("full_market_value", 0.0),
        errors="coerce",
    ).fillna(0.0)
    return (
        working.sort_values("full_market_value", ascending=False)
        .drop_duplicates("attribution_entity_id")
        .head(limit)["attribution_entity_id"]
        .astype(str)
        .tolist()
    )


def manager_attribution_timeseries(
    data: pd.DataFrame,
    current_snapshot: str,
    board: str,
    include_interim: bool = False,
) -> pd.DataFrame:
    working = _ensure_attribution_rows(data)
    working = working[
        working["attribution_in_scope"]
        & working["attribution_board"].eq(board)
    ].copy()
    if working.empty:
        return _aggregate_entities(working, ["snapshot_date"])

    snapshot_dates = pd.to_datetime(working["snapshot_date"], errors="coerce")
    current_date = pd.to_datetime(current_snapshot, errors="coerce")
    if pd.notna(current_date):
        working = working[snapshot_dates <= current_date].copy()

    metadata = working[["snapshot_date", "snapshot_month", "snapshot_status"]].drop_duplicates()
    if not include_interim:
        metadata = metadata[metadata["snapshot_status"].eq("official")].copy()
        metadata = (
            metadata.sort_values("snapshot_date")
            .groupby("snapshot_month", as_index=False, dropna=False)
            .tail(1)
        )
    allowed_dates = set(metadata["snapshot_date"].astype(str))
    working = working[working["snapshot_date"].astype(str).isin(allowed_dates)]

    return _aggregate_entities(
        working,
        [
            "snapshot_date",
            "snapshot_month",
            "snapshot_status",
            "attribution_board",
            "attribution_scope",
            "attribution_entity_id",
            "attribution_entity_name",
        ],
    ).sort_values(["snapshot_date", "full_market_value"], ascending=[True, False]).reset_index(drop=True)


def rank_manager_timeseries(
    timeseries: pd.DataFrame,
    selected_entities: list[str],
    metric: str,
) -> pd.DataFrame:
    """Return selected entities while ranking them against the full board."""
    working = timeseries.copy()
    if working.empty or metric not in working.columns:
        output = working[
            working.get("attribution_entity_id", pd.Series(dtype=object))
            .astype(str)
            .isin([str(entity_id) for entity_id in selected_entities])
        ].copy()
        output["board_rank"] = pd.Series(dtype="Int64")
        output["board_count"] = pd.Series(dtype="Int64")
        return output

    working[metric] = pd.to_numeric(working[metric], errors="coerce")
    rank_group_columns = ["snapshot_date"]
    if "attribution_board" in working.columns:
        rank_group_columns.append("attribution_board")
    grouped_metric = working.groupby(rank_group_columns, dropna=False)[metric]
    working["board_rank"] = grouped_metric.rank(
        method="min",
        ascending=False,
    ).astype("Int64")
    working["board_count"] = grouped_metric.transform("count").astype("Int64")
    return working[
        working["attribution_entity_id"].astype(str).isin(
            [str(entity_id) for entity_id in selected_entities]
        )
    ].copy()


def rank_selected_manager_timeseries(
    timeseries: pd.DataFrame,
    selected_entities: list[str],
    metric: str,
) -> pd.DataFrame:
    """Backward-compatible wrapper for board-wide ranking."""
    return rank_manager_timeseries(timeseries, selected_entities, metric)


def manager_asset_class_attribution(
    data: pd.DataFrame,
    snapshot_date: str,
    board: str,
    entity_id: str,
) -> pd.DataFrame:
    working = _ensure_attribution_rows(data)
    current = _exact_snapshot(working, snapshot_date)
    current = current[
        current["attribution_in_scope"]
        & current["attribution_board"].eq(board)
        & current["attribution_entity_id"].eq(entity_id)
    ].copy()
    if current.empty:
        return pd.DataFrame(
            columns=[
                "asset_class",
                "full_market_value",
                "market_value_share",
                "comprehensive_income_ytd",
                "avg_capital_ytd",
                "comprehensive_return_ytd",
                "asset_count",
                "row_count",
            ]
        )
    current["asset_class"] = current["asset_class"].replace("", "未分类/待确认")
    summary = (
        current.groupby("asset_class", dropna=False)
        .agg(
            full_market_value=("full_market_value", "sum"),
            comprehensive_income_ytd=("comprehensive_income_ytd", "sum"),
            avg_capital_ytd=("avg_capital_ytd", "sum"),
            asset_count=("_asset_identity", "nunique"),
            row_count=("asset_name", "size"),
        )
        .reset_index()
    )
    summary["comprehensive_return_ytd"] = _safe_ratio(
        summary["comprehensive_income_ytd"],
        summary["avg_capital_ytd"],
    )
    total_market_value = float(summary["full_market_value"].sum())
    summary["market_value_share"] = np.nan
    if abs(total_market_value) > RETURN_BASE_THRESHOLD:
        summary["market_value_share"] = summary["full_market_value"] / total_market_value
    return summary.sort_values("full_market_value", ascending=False).reset_index(drop=True)


def manager_asset_detail(
    data: pd.DataFrame,
    snapshot_date: str,
    board: str,
    entity_id: str,
) -> pd.DataFrame:
    working = _ensure_attribution_rows(data)
    current = _exact_snapshot(working, snapshot_date)
    current = current[
        current["attribution_in_scope"]
        & current["attribution_board"].eq(board)
        & current["attribution_entity_id"].eq(entity_id)
    ].copy()
    group_cols = [
        "asset_key",
        "asset_name",
        "asset_code",
        "trade_code",
        "account_bucket",
        "asset_class",
    ]
    if current.empty:
        return pd.DataFrame(
            columns=[
                *group_cols,
                "full_market_value",
                "comprehensive_income_mtd",
                "comprehensive_income_ytd",
                "avg_capital_mtd",
                "avg_capital_ytd",
                "comprehensive_return_mtd",
                "comprehensive_return_ytd",
                "source_rows",
            ]
        )
    detail = (
        current.groupby(group_cols, dropna=False)
        .agg(
            full_market_value=("full_market_value", "sum"),
            comprehensive_income_mtd=("comprehensive_income_mtd", "sum"),
            comprehensive_income_ytd=("comprehensive_income_ytd", "sum"),
            avg_capital_mtd=("avg_capital_mtd", "sum"),
            avg_capital_ytd=("avg_capital_ytd", "sum"),
            source_rows=("asset_name", "size"),
        )
        .reset_index()
    )
    detail["comprehensive_return_mtd"] = _safe_ratio(
        detail["comprehensive_income_mtd"],
        detail["avg_capital_mtd"],
    )
    detail["comprehensive_return_ytd"] = _safe_ratio(
        detail["comprehensive_income_ytd"],
        detail["avg_capital_ytd"],
    )
    return detail.sort_values("full_market_value", ascending=False).reset_index(drop=True)


def _holding_snapshot_summary(detail: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "_holding_identity",
        "account_bucket",
        "asset_code",
        "trade_code",
        "asset_class",
        "asset_name",
        "full_market_value",
        "comprehensive_income_mtd",
        "comprehensive_income_ytd",
        "avg_capital_mtd",
        "avg_capital_ytd",
        "source_rows",
    ]
    if detail.empty:
        return pd.DataFrame(columns=columns)

    working = detail.copy()
    for column in ["account_bucket", "asset_code", "trade_code"]:
        working[column] = working[column].fillna("").astype(str).str.strip()
    working["asset_name"] = (
        working["asset_name"]
        .fillna("")
        .astype(str)
        .str.strip()
        .replace("", "未命名资产")
    )
    working["asset_class"] = (
        working["asset_class"]
        .fillna("")
        .astype(str)
        .str.strip()
        .replace("", "未分类/待确认")
    )
    security_identity = np.where(
        working["asset_code"].ne(""),
        "asset::" + working["asset_code"],
        np.where(
            working["trade_code"].ne(""),
            "trade::" + working["trade_code"],
            "name::" + working["asset_name"],
        ),
    )
    working["_holding_identity"] = (
        working["account_bucket"].replace("", "未分账户/待确认")
        + "||"
        + pd.Series(security_identity, index=working.index, dtype=object)
    )
    return (
        working.groupby("_holding_identity", dropna=False)
        .agg(
            account_bucket=("account_bucket", "first"),
            asset_code=("asset_code", "first"),
            trade_code=("trade_code", "first"),
            asset_class=("asset_class", "first"),
            asset_name=("asset_name", "first"),
            full_market_value=("full_market_value", "sum"),
            comprehensive_income_mtd=("comprehensive_income_mtd", "sum"),
            comprehensive_income_ytd=("comprehensive_income_ytd", "sum"),
            avg_capital_mtd=("avg_capital_mtd", "sum"),
            avg_capital_ytd=("avg_capital_ytd", "sum"),
            source_rows=("source_rows", "sum"),
        )
        .reset_index()
    )


def _manager_holding_change_rows(
    data: pd.DataFrame,
    snapshot_date: str,
    board: str,
    entity_id: str,
    prior_snapshot_date: str | None,
) -> pd.DataFrame:
    """Match current and prior holdings while retaining prior-only exits."""
    current = _holding_snapshot_summary(
        manager_asset_detail(data, snapshot_date, board, entity_id)
    )
    prior_available = bool(prior_snapshot_date)
    if not prior_available:
        current["prior_full_market_value"] = np.nan
        current["source_rows_prior"] = np.nan
        current["full_market_value_delta"] = np.nan
        current["monthly_position_flow_delta"] = np.nan
        current["is_exited"] = False
        current["flow_status"] = "unavailable"
        return current

    prior = _holding_snapshot_summary(
        manager_asset_detail(
            data,
            str(prior_snapshot_date),
            board,
            entity_id,
        )
    )[
        [
            "_holding_identity",
            "account_bucket",
            "asset_code",
            "trade_code",
            "asset_class",
            "asset_name",
            "full_market_value",
            "source_rows",
        ]
    ].rename(
        columns={
            "account_bucket": "account_bucket_prior",
            "asset_code": "asset_code_prior",
            "trade_code": "trade_code_prior",
            "asset_class": "asset_class_prior",
            "asset_name": "asset_name_prior",
            "full_market_value": "prior_full_market_value",
            "source_rows": "source_rows_prior",
        }
    )
    holdings = current.merge(
        prior,
        how="outer",
        on="_holding_identity",
    )
    for column in [
        "account_bucket",
        "asset_code",
        "trade_code",
        "asset_class",
        "asset_name",
    ]:
        holdings[column] = holdings[column].fillna(holdings[f"{column}_prior"])
    holdings = holdings.drop(
        columns=[
            "account_bucket_prior",
            "asset_code_prior",
            "trade_code_prior",
            "asset_class_prior",
            "asset_name_prior",
        ]
    )
    for column in [
        "full_market_value",
        "comprehensive_income_mtd",
        "comprehensive_income_ytd",
        "avg_capital_mtd",
        "avg_capital_ytd",
        "source_rows",
        "prior_full_market_value",
        "source_rows_prior",
    ]:
        holdings[column] = pd.to_numeric(holdings[column], errors="coerce").fillna(0.0)
    holdings["full_market_value_delta"] = (
        holdings["full_market_value"] - holdings["prior_full_market_value"]
    )
    holdings["monthly_position_flow_delta"] = (
        holdings["full_market_value_delta"]
        - holdings["comprehensive_income_mtd"]
    )
    holdings["is_exited"] = (
        (holdings["full_market_value"] <= RETURN_BASE_THRESHOLD)
        & (holdings["prior_full_market_value"] > RETURN_BASE_THRESHOLD)
    )
    holdings["flow_status"] = holdings.apply(
        lambda row: (
            "exited"
            if bool(row["is_exited"])
            else holding_position_change_status(
                float(row["full_market_value"]),
                float(row["prior_full_market_value"]),
                float(row["monthly_position_flow_delta"]),
                True,
            )
        ),
        axis=1,
    )
    return holdings


def manager_exited_holdings(
    data: pd.DataFrame,
    snapshot_date: str,
    board: str,
    entity_id: str,
    prior_snapshot_date: str | None,
) -> pd.DataFrame:
    """Return prior-only or zero-current holdings for a separate exit view."""
    columns = [
        "account_bucket",
        "asset_code",
        "trade_code",
        "asset_class",
        "asset_name",
        "full_market_value",
        "prior_snapshot_date",
        "prior_full_market_value",
        "full_market_value_delta",
        "monthly_position_flow_delta",
        "is_exited",
        "flow_status",
        "source_rows",
        "source_rows_prior",
    ]
    changes = _manager_holding_change_rows(
        data,
        snapshot_date,
        board,
        entity_id,
        prior_snapshot_date,
    )
    if changes.empty or not prior_snapshot_date:
        return pd.DataFrame(columns=columns)
    exited = changes[changes["is_exited"]].copy()
    exited["prior_snapshot_date"] = str(prior_snapshot_date)
    return (
        exited[columns]
        .sort_values("monthly_position_flow_delta", ascending=True)
        .reset_index(drop=True)
    )


def manager_holding_map(
    data: pd.DataFrame,
    snapshot_date: str,
    board: str,
    entity_id: str,
    max_assets: int = 20,
    prior_snapshot_date: str | None = None,
) -> pd.DataFrame:
    """Return treemap holdings with estimated changes from the prior month-end snapshot."""
    output_columns = [
        "asset_class",
        "holding_label",
        "holding_kind",
        "holding_count",
        "full_market_value",
        "market_value_share",
        "prior_snapshot_date",
        "prior_full_market_value",
        "full_market_value_delta",
        "monthly_position_flow_delta",
        "position_change_status",
        "position_change_badge",
        "comprehensive_income_mtd",
        "comprehensive_income_ytd",
        "avg_capital_mtd",
        "avg_capital_ytd",
        "comprehensive_return_mtd",
        "comprehensive_return_ytd",
        "source_rows",
        "source_rows_prior",
    ]
    prior_available = bool(prior_snapshot_date)
    holdings = _manager_holding_change_rows(
        data,
        snapshot_date,
        board,
        entity_id,
        prior_snapshot_date,
    )

    holdings = holdings[holdings["full_market_value"] > RETURN_BASE_THRESHOLD].copy()
    if holdings.empty:
        return pd.DataFrame(columns=output_columns)

    holdings = holdings.sort_values("full_market_value", ascending=False).reset_index(drop=True)
    max_assets = max(1, int(max_assets))
    leading = holdings.head(max_assets).copy()
    leading["holding_label"] = leading["asset_name"]
    leading["holding_kind"] = "单项资产"
    leading["holding_count"] = 1

    tail = holdings.iloc[max_assets:].copy()
    if tail.empty:
        display = leading
    else:
        tail_summary = (
            tail.groupby("asset_class", dropna=False)
            .agg(
                full_market_value=("full_market_value", "sum"),
                prior_full_market_value=("prior_full_market_value", "sum"),
                full_market_value_delta=("full_market_value_delta", "sum"),
                monthly_position_flow_delta=("monthly_position_flow_delta", "sum"),
                comprehensive_income_mtd=("comprehensive_income_mtd", "sum"),
                comprehensive_income_ytd=("comprehensive_income_ytd", "sum"),
                avg_capital_mtd=("avg_capital_mtd", "sum"),
                avg_capital_ytd=("avg_capital_ytd", "sum"),
                source_rows=("source_rows", "sum"),
                source_rows_prior=("source_rows_prior", "sum"),
                holding_count=("asset_name", "size"),
            )
            .reset_index()
        )
        tail_summary["holding_label"] = tail_summary.apply(
            lambda row: f"其他{row['asset_class']}持仓（{int(row['holding_count'])}项）",
            axis=1,
        )
        tail_summary["holding_kind"] = "长尾合并"
        display = pd.concat([leading, tail_summary], ignore_index=True, sort=False)

    if not prior_available:
        for column in [
            "prior_full_market_value",
            "full_market_value_delta",
            "monthly_position_flow_delta",
            "source_rows_prior",
        ]:
            display[column] = np.nan
    display["prior_snapshot_date"] = str(prior_snapshot_date or "")
    display["position_change_status"] = display.apply(
        lambda row: holding_position_change_status(
            float(row["full_market_value"]),
            float(row["prior_full_market_value"]),
            float(row["monthly_position_flow_delta"]),
            prior_available,
        ),
        axis=1,
    )
    display["position_change_badge"] = display["position_change_status"].map(
        {
            "new": "NEW",
            "increase": "↑",
            "decrease": "↓",
            "flat": "→",
            "unavailable": "",
        }
    )
    display["comprehensive_return_mtd"] = _safe_ratio(
        display["comprehensive_income_mtd"],
        display["avg_capital_mtd"],
    )
    display["comprehensive_return_ytd"] = _safe_ratio(
        display["comprehensive_income_ytd"],
        display["avg_capital_ytd"],
    )
    positive_market_value = float(display["full_market_value"].sum())
    display["market_value_share"] = display["full_market_value"] / positive_market_value
    return (
        display[output_columns]
        .sort_values("full_market_value", ascending=False)
        .reset_index(drop=True)
    )


def manager_attribution_reconciliation(
    data: pd.DataFrame,
    snapshot_date: str,
) -> pd.DataFrame:
    working = _ensure_attribution_rows(data)
    current = _exact_snapshot(working, snapshot_date)
    current = current[current["attribution_in_scope"]].copy()
    if current.empty:
        return pd.DataFrame(
            columns=[
                "attribution_board",
                "full_market_value",
                "comprehensive_income_mtd",
                "comprehensive_income_ytd",
                "row_count",
            ]
        )
    return (
        current.groupby("attribution_board", dropna=False)
        .agg(
            full_market_value=("full_market_value", "sum"),
            comprehensive_income_mtd=("comprehensive_income_mtd", "sum"),
            comprehensive_income_ytd=("comprehensive_income_ytd", "sum"),
            row_count=("asset_name", "size"),
        )
        .reset_index()
        .sort_values("attribution_board")
        .reset_index(drop=True)
    )


def manager_attribution_coverage_summary(
    data: pd.DataFrame,
    snapshot_date: str,
) -> dict[str, float]:
    """Summarize visible attribution coverage and excluded hierarchy rows."""
    working = _ensure_attribution_rows(data)
    current = _exact_snapshot(working, snapshot_date)
    included = current[current["attribution_in_scope"]].copy()
    attributed_mask = included["attribution_board"].isin(ATTRIBUTION_BOARD_OPTIONS)
    attributed = included[attributed_mask]
    unattributed = included[~attributed_mask]
    excluded = current[~current["attribution_in_scope"]]

    total_market_value = float(included["full_market_value"].sum())
    attributed_market_value = float(attributed["full_market_value"].sum())
    total_absolute_market_value = float(included["full_market_value"].abs().sum())
    attributed_absolute_market_value = float(
        attributed["full_market_value"].abs().sum()
    )
    total_rows = float(len(included))
    attributed_rows = float(len(attributed))
    market_value_coverage = (
        attributed_absolute_market_value / total_absolute_market_value
        if total_absolute_market_value > RETURN_BASE_THRESHOLD
        else np.nan
    )
    net_market_value_coverage = (
        attributed_market_value / total_market_value
        if abs(total_market_value) > RETURN_BASE_THRESHOLD
        else np.nan
    )
    row_coverage = attributed_rows / total_rows if total_rows else np.nan
    return {
        "market_value_coverage": float(market_value_coverage),
        "net_market_value_coverage": float(net_market_value_coverage),
        "row_coverage": float(row_coverage),
        "attributed_market_value": attributed_market_value,
        "attributed_absolute_market_value": attributed_absolute_market_value,
        "unattributed_market_value": float(unattributed["full_market_value"].sum()),
        "unattributed_absolute_market_value": float(
            unattributed["full_market_value"].abs().sum()
        ),
        "total_market_value": total_market_value,
        "total_absolute_market_value": total_absolute_market_value,
        "attributed_row_count": attributed_rows,
        "unattributed_row_count": float(len(unattributed)),
        "total_row_count": total_rows,
        "excluded_market_value": float(excluded["full_market_value"].sum()),
        "excluded_row_count": float(len(excluded)),
    }


def hierarchy_exclusion_summary(
    data: pd.DataFrame,
    snapshot_date: str,
) -> dict[str, float]:
    working = _ensure_attribution_rows(data)
    current = _exact_snapshot(working, snapshot_date)
    excluded = current[~current["attribution_in_scope"]]
    return {
        "row_count": float(len(excluded)),
        "full_market_value": float(excluded["full_market_value"].sum()),
        "comprehensive_income_ytd": float(excluded["comprehensive_income_ytd"].sum()),
    }
