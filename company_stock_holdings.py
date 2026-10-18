"""Company-wide stock holding ranking.

The dashboard already has manager/account-level views.  This module keeps the
company-wide security aggregation separate so a stock is counted once across
all managers and accounts, while allowing the caller to select the recognised
internal or outsourced stock universe.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from strategy_books import INTERNAL_MANDATE, ensure_strategy_book_columns


RETURN_BASE_THRESHOLD = 0.0001
YTD_MODE = "年初以来"
INTERNAL_SCOPE = "委内"
OUTSOURCED_SCOPE = "委外"
OCI_MANAGER = "鲍淼"
OCI_TRADE_STRATEGY = "配置"
OCI_ASSET_MAJOR_CLASS = "权益"
HIERARCHY_EXCLUSION_PATTERN = r"避免重复计算|已改用顶层产品汇总行"
UNMAPPED_INDUSTRY = "未分类/境外股"
DEFAULT_INDUSTRY_MAPPING_PATH = Path(__file__).resolve().parent / "data" / "industry_mapping.parquet"

RANKING_COLUMNS = [
    "rank",
    "stock_label",
    "asset_name",
    "asset_code",
    "trade_code",
    "full_market_value_current",
    "cost_basis_period",
    "market_value_share",
    "non_outsourced_market_value_current",
    "outsourced_market_value_current",
    "comprehensive_income_period",
    "loss_amount_period",
    "profit_amount_period",
    "avg_capital_mtd_current",
    "comprehensive_return_mtd",
    "source_rows_current",
]

INDUSTRY_DISTRIBUTION_COLUMNS = [
    "rank",
    "industry",
    "industry_mapping_method",
    "full_market_value_current",
    "cost_basis_period",
    "market_value_share",
    "non_outsourced_market_value_current",
    "outsourced_market_value_current",
    "stock_count",
    "source_rows_current",
    "comprehensive_income_period",
    "loss_amount_period",
    "profit_amount_period",
    "avg_capital_mtd_current",
    "comprehensive_return_mtd",
]


def _empty_result() -> pd.DataFrame:
    return pd.DataFrame(columns=RANKING_COLUMNS)


def _empty_industry_result() -> pd.DataFrame:
    return pd.DataFrame(columns=INDUSTRY_DISTRIBUTION_COLUMNS)


def _clean_text(series: pd.Series, fallback: str = "") -> pd.Series:
    values = series.fillna("").astype(str).str.strip()
    return values.mask(values.isin({"", "-", "nan", "None"}), fallback)


def _first_nonempty(values: pd.Series, fallback: str = "") -> str:
    for value in values:
        text = "" if pd.isna(value) else str(value).strip()
        if text and text not in {"-", "nan", "None"}:
            return text
    return fallback


def _text_column(frame: pd.DataFrame, column: str, fallback: str = "") -> pd.Series:
    if column not in frame:
        return pd.Series(fallback, index=frame.index, dtype=object)
    return _clean_text(frame[column], fallback=fallback)


def _numeric_column(frame: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column not in frame:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").fillna(default)


def normalize_security_code(asset_code: object, trade_code: object = "") -> str:
    """Convert source security identifiers to the reference-repo code format."""
    code = "" if pd.isna(asset_code) else str(asset_code).strip()
    trade = "" if pd.isna(trade_code) else str(trade_code).strip()
    for source, target in (
        (".STK.SHSC", ".HK"),
        (".STK.SZSC", ".HK"),
        (".STK.NASDAQ", ".US"),
        (".STK.XNYS", ".US"),
        (".STK.SZ", ".SZ"),
        (".STK.SH", ".SH"),
        (".STK.HK", ".HK"),
    ):
        if source in code:
            return code.replace(source, target)
    if code:
        return code
    for suffix, market in (("MH", ".HK"), ("SZ", ".SZ"), ("SH", ".SH")):
        if trade.endswith(suffix):
            return trade[: -len(suffix)] + market
    return trade


def _prepare_stock_rows(
    data: pd.DataFrame,
    snapshot_date: str,
    *,
    holding_scope: str,
    include_oci: bool,
) -> pd.DataFrame:
    if data.empty:
        return pd.DataFrame()

    working = ensure_strategy_book_columns(data)
    current = _snapshot_slice(working, snapshot_date)
    if current.empty or "asset_class" not in current.columns:
        return pd.DataFrame()

    current = current[_text_column(current, "asset_class").eq("股票")].copy()
    if current.empty:
        return pd.DataFrame()

    exclusion_reason = _text_column(current, "strategy_book_exclusion_reason")
    current = current[
        ~exclusion_reason.str.contains(HIERARCHY_EXCLUSION_PATTERN, regex=True, na=False)
    ].copy()
    if current.empty:
        return pd.DataFrame()

    current["full_market_value"] = _numeric_column(current, "full_market_value")
    current = current[current["full_market_value"] > RETURN_BASE_THRESHOLD].copy()
    if current.empty:
        return pd.DataFrame()

    current["_asset_code"] = _text_column(current, "asset_code")
    current["_trade_code"] = _text_column(current, "trade_code")
    current["_asset_name"] = _text_column(current, "asset_name", fallback="未命名股票")
    current["_security_key"] = np.select(
        [current["_asset_code"].ne(""), current["_trade_code"].ne("")],
        ["asset_code::" + current["_asset_code"], "trade_code::" + current["_trade_code"]],
        default="name::" + current["_asset_name"],
    )
    current["_industry_code"] = [
        normalize_security_code(asset_code, trade_code)
        for asset_code, trade_code in zip(current["_asset_code"], current["_trade_code"])
    ]
    current["_is_outsourced"] = _text_column(current, "strategy_book_scope").eq(OUTSOURCED_SCOPE)
    current["_is_oci"] = (
        _text_column(current, "mandate_type").eq(INTERNAL_MANDATE)
        & _text_column(current, "asset_major_class").eq(OCI_ASSET_MAJOR_CLASS)
        & _text_column(current, "asset_class").eq("股票")
        & _text_column(current, "manager").eq(OCI_MANAGER)
        & _text_column(current, "trade_strategy").eq(OCI_TRADE_STRATEGY)
    )
    if holding_scope not in {INTERNAL_SCOPE, OUTSOURCED_SCOPE}:
        raise ValueError(f"holding_scope must be {INTERNAL_SCOPE!r} or {OUTSOURCED_SCOPE!r}")
    current = current[
        _text_column(current, "strategy_book_scope").eq(holding_scope)
    ].copy()
    if not include_oci:
        current = current[~current["_is_oci"]].copy()
    return current


def _attach_period_columns(current: pd.DataFrame, comparison_mode: str) -> pd.DataFrame:
    working = current.copy()
    income_column = "comprehensive_income_ytd" if comparison_mode == YTD_MODE else "comprehensive_income_mtd"
    capital_column = "avg_capital_ytd" if comparison_mode == YTD_MODE else "avg_capital_mtd"
    working["_period_income"] = _numeric_column(working, income_column)
    working["_period_capital"] = _numeric_column(working, capital_column)
    working["_non_outsourced_market_value"] = np.where(
        working["_is_outsourced"], 0.0, working["full_market_value"]
    )
    working["_outsourced_market_value"] = np.where(
        working["_is_outsourced"], working["full_market_value"], 0.0
    )
    return working


def load_industry_mapping(path: str | Path = DEFAULT_INDUSTRY_MAPPING_PATH) -> pd.DataFrame:
    """Load the compact industry snapshot copied from the reference workflow."""
    mapping_path = Path(path)
    if not mapping_path.exists():
        return pd.DataFrame(columns=["code", "industry", "mapping_method", "observed_date"])
    mapping = pd.read_parquet(mapping_path).copy()
    if "code" not in mapping.columns:
        if "thscode" in mapping.columns:
            mapping = mapping.rename(columns={"thscode": "code"})
        else:
            return pd.DataFrame(columns=["code", "industry", "mapping_method", "observed_date"])
    if "industry" not in mapping.columns:
        for candidate in ["analysis_industry", "sw1_name"]:
            if candidate in mapping.columns:
                mapping = mapping.rename(columns={candidate: "industry"})
                break
    if "industry" not in mapping.columns:
        return pd.DataFrame(columns=["code", "industry", "mapping_method", "observed_date"])
    mapping["code"] = _clean_text(mapping["code"])
    mapping["industry"] = _clean_text(mapping["industry"])
    if "mapping_method" not in mapping.columns:
        mapping["mapping_method"] = "申万一级"
    if "observed_date" not in mapping.columns:
        mapping["observed_date"] = ""
    mapping = mapping[
        ["code", "industry", "mapping_method", "observed_date"]
    ].query("code != '' and industry != ''")
    return mapping.drop_duplicates("code", keep="first").reset_index(drop=True)


def _snapshot_slice(data: pd.DataFrame, snapshot_date: str) -> pd.DataFrame:
    key = "snapshot_date" if "snapshot_date" in data.columns else "snapshot_month"
    return data[data[key].astype(str).eq(str(snapshot_date))].copy()


def company_stock_holding_ranking(
    data: pd.DataFrame,
    snapshot_date: str,
    *,
    holding_scope: str = INTERNAL_SCOPE,
    include_oci: bool = False,
    comparison_mode: str = "单月复盘",
) -> pd.DataFrame:
    """Aggregate positive-value stock holdings across managers and accounts.

    ``holding_scope`` selects either the recognised ``委内`` or ``委外`` stock
    universe.  Unclassified rows are not silently assigned to either scope.
    ``include_oci`` follows the existing equity dashboard's exact OCI scope:
    internal stock rows for manager ``鲍淼`` with ``配置`` strategy.
    Existing single-plan hierarchy exclusions are respected to avoid counting
    a top-level product and its underlying holdings together.
    """

    current = _prepare_stock_rows(
        data,
        snapshot_date,
        holding_scope=holding_scope,
        include_oci=include_oci,
    )
    if current.empty:
        return _empty_result()

    current = _attach_period_columns(current, comparison_mode)

    ranking = (
        current.groupby("_security_key", dropna=False)
        .agg(
            asset_name=("_asset_name", _first_nonempty),
            asset_code=("_asset_code", _first_nonempty),
            trade_code=("_trade_code", _first_nonempty),
            full_market_value_current=("full_market_value", "sum"),
            non_outsourced_market_value_current=("_non_outsourced_market_value", "sum"),
            outsourced_market_value_current=("_outsourced_market_value", "sum"),
            comprehensive_income_period=("_period_income", "sum"),
            avg_capital_mtd_current=("_period_capital", "sum"),
            source_rows_current=("_security_key", "size"),
        )
        .reset_index()
    )
    ranking["comprehensive_return_mtd"] = np.nan
    valid_capital = ranking["avg_capital_mtd_current"] > RETURN_BASE_THRESHOLD
    ranking.loc[valid_capital, "comprehensive_return_mtd"] = (
        ranking.loc[valid_capital, "comprehensive_income_period"]
        / ranking.loc[valid_capital, "avg_capital_mtd_current"]
    )
    ranking["cost_basis_period"] = (
        ranking["full_market_value_current"] - ranking["comprehensive_income_period"]
    ).clip(lower=0.0)
    ranking["loss_amount_period"] = np.nan
    loss_mask = ranking["comprehensive_income_period"] < -RETURN_BASE_THRESHOLD
    ranking.loc[loss_mask, "loss_amount_period"] = -ranking.loc[
        loss_mask, "comprehensive_income_period"
    ]
    ranking["profit_amount_period"] = np.nan
    profit_mask = ranking["comprehensive_income_period"] > RETURN_BASE_THRESHOLD
    ranking.loc[profit_mask, "profit_amount_period"] = ranking.loc[
        profit_mask, "comprehensive_income_period"
    ]

    total_market_value = float(ranking["full_market_value_current"].sum())
    ranking["market_value_share"] = np.nan
    if total_market_value > RETURN_BASE_THRESHOLD:
        ranking["market_value_share"] = ranking["full_market_value_current"] / total_market_value

    ranking["stock_label"] = ranking.apply(
        lambda row: (
            f"{row['asset_name']}（{row['trade_code'] or row['asset_code']}）"
            if (row["trade_code"] or row["asset_code"])
            else str(row["asset_name"])
        ),
        axis=1,
    )
    ranking = ranking.sort_values(
        ["full_market_value_current", "asset_name", "asset_code", "trade_code"],
        ascending=[False, True, True, True],
        kind="mergesort",
    ).reset_index(drop=True)
    ranking["rank"] = np.arange(1, len(ranking) + 1, dtype=int)
    return ranking[RANKING_COLUMNS]


def company_stock_industry_distribution(
    data: pd.DataFrame,
    snapshot_date: str,
    *,
    holding_scope: str = INTERNAL_SCOPE,
    include_oci: bool = False,
    comparison_mode: str = "单月复盘",
    industry_mapping: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Aggregate the selected stock universe by observed SW1 industry.

    A-share codes use the observed 2026-10-16 SW1 snapshot from the reference
    workflow.  If a code has no available mapping, it is kept in
    ``未分类/境外股`` so the industry percentages still reconcile to the stock
    universe instead of silently dropping Hong Kong or overseas holdings.
    """
    current = _prepare_stock_rows(
        data,
        snapshot_date,
        holding_scope=holding_scope,
        include_oci=include_oci,
    )
    if current.empty:
        return _empty_industry_result()

    current = _attach_period_columns(current, comparison_mode)
    mapping = load_industry_mapping() if industry_mapping is None else industry_mapping.copy()
    if mapping.empty:
        current["_industry"] = UNMAPPED_INDUSTRY
        current["_mapping_method"] = "未映射"
    else:
        mapping = mapping.copy()
        mapping["code"] = _clean_text(mapping["code"])
        mapping["industry"] = _clean_text(mapping["industry"])
        if "mapping_method" not in mapping.columns:
            mapping["mapping_method"] = "申万一级"
        lookup = mapping[["code", "industry", "mapping_method"]].drop_duplicates("code", keep="first")
        current = current.merge(
            lookup,
            how="left",
            left_on="_industry_code",
            right_on="code",
        )
        current["_industry"] = current["industry"].where(
            current["industry"].notna() & current["industry"].astype(str).str.strip().ne(""),
            UNMAPPED_INDUSTRY,
        )
        current["_mapping_method"] = current["mapping_method"].where(
            current["_industry"].ne(UNMAPPED_INDUSTRY),
            "未映射",
        )

    distribution = (
        current.groupby("_industry", dropna=False)
        .agg(
            industry_mapping_method=("_mapping_method", _first_nonempty),
            full_market_value_current=("full_market_value", "sum"),
            non_outsourced_market_value_current=("_non_outsourced_market_value", "sum"),
            outsourced_market_value_current=("_outsourced_market_value", "sum"),
            stock_count=("_security_key", "nunique"),
            source_rows_current=("_security_key", "size"),
            comprehensive_income_period=("_period_income", "sum"),
            avg_capital_mtd_current=("_period_capital", "sum"),
        )
        .reset_index()
        .rename(columns={"_industry": "industry"})
    )
    distribution["comprehensive_return_mtd"] = np.nan
    valid_capital = distribution["avg_capital_mtd_current"] > RETURN_BASE_THRESHOLD
    distribution.loc[valid_capital, "comprehensive_return_mtd"] = (
        distribution.loc[valid_capital, "comprehensive_income_period"]
        / distribution.loc[valid_capital, "avg_capital_mtd_current"]
    )
    distribution["cost_basis_period"] = (
        distribution["full_market_value_current"] - distribution["comprehensive_income_period"]
    ).clip(lower=0.0)
    distribution["loss_amount_period"] = np.nan
    loss_mask = distribution["comprehensive_income_period"] < -RETURN_BASE_THRESHOLD
    distribution.loc[loss_mask, "loss_amount_period"] = -distribution.loc[
        loss_mask, "comprehensive_income_period"
    ]
    distribution["profit_amount_period"] = np.nan
    profit_mask = distribution["comprehensive_income_period"] > RETURN_BASE_THRESHOLD
    distribution.loc[profit_mask, "profit_amount_period"] = distribution.loc[
        profit_mask, "comprehensive_income_period"
    ]
    total_market_value = float(distribution["full_market_value_current"].sum())
    distribution["market_value_share"] = np.nan
    if total_market_value > RETURN_BASE_THRESHOLD:
        distribution["market_value_share"] = (
            distribution["full_market_value_current"] / total_market_value
        )
    distribution = distribution.sort_values(
        ["full_market_value_current", "industry"],
        ascending=[False, True],
        kind="mergesort",
    ).reset_index(drop=True)
    distribution["rank"] = np.arange(1, len(distribution) + 1, dtype=int)
    return distribution[INDUSTRY_DISTRIBUTION_COLUMNS]
