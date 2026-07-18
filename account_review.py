import pandas as pd


GROUP_METRICS = [
    "full_market_value",
    "clean_market_value",
    "market_value_year_open",
    "avg_capital_mtd",
    "avg_capital_ytd",
    "finance_income_mtd",
    "comprehensive_income_mtd",
    "finance_income_ytd",
    "comprehensive_income_ytd",
]


def _snapshot_key_column(data: pd.DataFrame) -> str:
    return "snapshot_date" if "snapshot_date" in data.columns else "snapshot_month"


def _snapshot_slice(data: pd.DataFrame, snapshot: str) -> pd.DataFrame:
    return data[data[_snapshot_key_column(data)] == snapshot]


def _aggregate(data: pd.DataFrame, month: str, group_cols: list[str]) -> pd.DataFrame:
    subset = _snapshot_slice(data, month).copy()
    for metric in GROUP_METRICS:
        if metric not in subset:
            subset[metric] = 0.0
    if subset.empty:
        return pd.DataFrame(columns=group_cols + GROUP_METRICS + ["record_count"])

    return (
        subset.groupby(group_cols, dropna=False)
        .agg(
            full_market_value=("full_market_value", "sum"),
            clean_market_value=("clean_market_value", "sum"),
            market_value_year_open=("market_value_year_open", "sum"),
            avg_capital_mtd=("avg_capital_mtd", "sum"),
            avg_capital_ytd=("avg_capital_ytd", "sum"),
            finance_income_mtd=("finance_income_mtd", "sum"),
            comprehensive_income_mtd=("comprehensive_income_mtd", "sum"),
            finance_income_ytd=("finance_income_ytd", "sum"),
            comprehensive_income_ytd=("comprehensive_income_ytd", "sum"),
            record_count=("asset_name", "size"),
        )
        .reset_index()
    )


def current_vs_prior(data: pd.DataFrame, current_month: str, prior_month: str, group_cols: list[str]) -> pd.DataFrame:
    current = _aggregate(data, current_month, group_cols)
    prior = _aggregate(data, prior_month, group_cols)
    merged = current.merge(prior, on=group_cols, how="outer", suffixes=("_current", "_prior"))

    for metric in GROUP_METRICS + ["record_count"]:
        for suffix in ["current", "prior"]:
            column = f"{metric}_{suffix}"
            if column not in merged:
                merged[column] = 0.0
            merged[column] = merged[column].fillna(0.0)

    merged["full_market_value_delta"] = (
        merged["full_market_value_current"] - merged["full_market_value_prior"]
    )
    merged["clean_market_value_delta"] = (
        merged["clean_market_value_current"] - merged["clean_market_value_prior"]
    )
    merged["finance_income_mtd_delta"] = (
        merged["finance_income_mtd_current"] - merged["finance_income_mtd_prior"]
    )
    merged["comprehensive_income_mtd_delta"] = (
        merged["comprehensive_income_mtd_current"] - merged["comprehensive_income_mtd_prior"]
    )
    merged["finance_income_period"] = merged["finance_income_mtd_current"]
    merged["comprehensive_income_period"] = merged["comprehensive_income_mtd_current"]
    merged["net_full_market_value_delta"] = (
        merged["full_market_value_delta"] - merged["comprehensive_income_period"]
    )

    valid_base = merged["avg_capital_mtd_current"] > 0.0001
    merged["finance_return_mtd"] = None
    merged["comprehensive_return_mtd"] = None
    merged.loc[valid_base, "finance_return_mtd"] = (
        merged.loc[valid_base, "finance_income_mtd_current"]
        / merged.loc[valid_base, "avg_capital_mtd_current"]
    )
    merged.loc[valid_base, "comprehensive_return_mtd"] = (
        merged.loc[valid_base, "comprehensive_income_mtd_current"]
        / merged.loc[valid_base, "avg_capital_mtd_current"]
    )
    return merged


def current_vs_year_open(data: pd.DataFrame, current_month: str, group_cols: list[str]) -> pd.DataFrame:
    current = _aggregate(data, current_month, group_cols)
    current = current.rename(columns={f"{metric}": f"{metric}_current" for metric in GROUP_METRICS})
    current = current.rename(columns={"record_count": "record_count_current"})

    current["full_market_value_prior"] = current["market_value_year_open_current"]
    current["full_market_value_delta"] = (
        current["full_market_value_current"] - current["full_market_value_prior"]
    )
    current["clean_market_value_delta"] = None
    current["finance_income_mtd_current"] = current["finance_income_ytd_current"]
    current["comprehensive_income_mtd_current"] = current["comprehensive_income_ytd_current"]
    current["finance_income_period"] = current["finance_income_ytd_current"]
    current["comprehensive_income_period"] = current["comprehensive_income_ytd_current"]
    current["net_full_market_value_delta"] = (
        current["full_market_value_delta"] - current["comprehensive_income_period"]
    )
    current["avg_capital_mtd_current"] = current["avg_capital_ytd_current"]

    valid_base = current["avg_capital_ytd_current"] > 0.0001
    current["finance_return_mtd"] = None
    current["comprehensive_return_mtd"] = None
    current.loc[valid_base, "finance_return_mtd"] = (
        current.loc[valid_base, "finance_income_ytd_current"]
        / current.loc[valid_base, "avg_capital_ytd_current"]
    )
    current.loc[valid_base, "comprehensive_return_mtd"] = (
        current.loc[valid_base, "comprehensive_income_ytd_current"]
        / current.loc[valid_base, "avg_capital_ytd_current"]
    )
    return current


def comparison_summary(
    data: pd.DataFrame,
    current_month: str,
    prior_month: str,
    group_cols: list[str],
    comparison_mode: str,
) -> pd.DataFrame:
    if comparison_mode == "年初以来":
        return current_vs_year_open(data, current_month, group_cols)
    return current_vs_prior(data, current_month, prior_month, group_cols)


def filter_current(
    data: pd.DataFrame,
    current_month: str,
    account: str | None = None,
    asset_class: str | None = None,
    manager: str | None = None,
) -> pd.DataFrame:
    subset = _snapshot_slice(data, current_month).copy()
    if account and account != "全部":
        subset = subset[subset["account_bucket"] == account]
    if asset_class and asset_class != "全部":
        subset = subset[subset["asset_class"] == asset_class]
    if manager and manager != "全部":
        subset = subset[subset["manager"] == manager]
    return subset


def _asset_evidence_group_columns(extra_group_cols: list[str] | None = None) -> list[str]:
    base_cols = ["asset_key", "asset_name", "asset_code", "trade_code", "account_bucket", "asset_class", "manager"]
    cols: list[str] = []
    for column in (extra_group_cols or []) + base_cols:
        if column not in cols:
            cols.append(column)
    return cols


def _ensure_group_columns(data: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    working = data.copy()
    for column in group_cols:
        if column not in working.columns:
            working[column] = ""
    return working


def _ensure_numeric_columns(data: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    working = data.copy()
    for column in columns:
        if column not in working.columns:
            working[column] = 0.0
    return working


def _add_evidence_return_columns(evidence: pd.DataFrame) -> pd.DataFrame:
    evidence = evidence.copy()
    avg_capital = pd.to_numeric(evidence["avg_capital_mtd_current"], errors="coerce").fillna(0.0)
    finance_income = pd.to_numeric(evidence["finance_income_mtd_current"], errors="coerce").fillna(0.0)
    comprehensive_income = pd.to_numeric(
        evidence["comprehensive_income_mtd_current"],
        errors="coerce",
    ).fillna(0.0)

    valid_base = avg_capital > 0.0001
    evidence["finance_return_mtd"] = None
    evidence["comprehensive_return_mtd"] = None
    evidence.loc[valid_base, "finance_return_mtd"] = finance_income.loc[valid_base] / avg_capital.loc[valid_base]
    evidence.loc[valid_base, "comprehensive_return_mtd"] = (
        comprehensive_income.loc[valid_base] / avg_capital.loc[valid_base]
    )
    return evidence


def asset_evidence(
    data: pd.DataFrame,
    current_month: str,
    prior_month: str,
    account: str | None = None,
    asset_class: str | None = None,
    manager: str | None = None,
    extra_group_cols: list[str] | None = None,
) -> pd.DataFrame:
    subset = data.copy()
    if account and account != "全部":
        subset = subset[subset["account_bucket"] == account]
    if asset_class and asset_class != "全部":
        subset = subset[subset["asset_class"] == asset_class]
    if manager and manager != "全部":
        subset = subset[subset["manager"] == manager]

    cols = _asset_evidence_group_columns(extra_group_cols)
    subset = _ensure_group_columns(subset, cols)
    subset = _ensure_numeric_columns(
        subset,
        [
            "full_market_value",
            "avg_capital_mtd",
            "finance_income_mtd",
            "comprehensive_income_mtd",
        ],
    )
    current = (
        _snapshot_slice(subset, current_month)
        .groupby(cols, dropna=False)
        .agg(
            full_market_value_current=("full_market_value", "sum"),
            avg_capital_mtd_current=("avg_capital_mtd", "sum"),
            finance_income_mtd_current=("finance_income_mtd", "sum"),
            comprehensive_income_mtd_current=("comprehensive_income_mtd", "sum"),
            source_rows_current=("asset_name", "size"),
        )
        .reset_index()
    )
    prior = (
        _snapshot_slice(subset, prior_month)
        .groupby(cols, dropna=False)
        .agg(
            full_market_value_prior=("full_market_value", "sum"),
            finance_income_mtd_prior=("finance_income_mtd", "sum"),
            comprehensive_income_mtd_prior=("comprehensive_income_mtd", "sum"),
            source_rows_prior=("asset_name", "size"),
        )
        .reset_index()
    )

    merged = current.merge(prior, on=cols, how="outer")
    for column in [
        "full_market_value_current",
        "avg_capital_mtd_current",
        "finance_income_mtd_current",
        "comprehensive_income_mtd_current",
        "source_rows_current",
        "full_market_value_prior",
        "finance_income_mtd_prior",
        "comprehensive_income_mtd_prior",
        "source_rows_prior",
    ]:
        merged[column] = merged[column].fillna(0.0)

    merged["full_market_value_delta"] = (
        merged["full_market_value_current"] - merged["full_market_value_prior"]
    )
    merged["monthly_position_flow_delta"] = (
        merged["full_market_value_delta"] - merged["comprehensive_income_mtd_current"]
    )
    merged = _add_evidence_return_columns(merged)
    merged["change_type"] = "存续"
    merged.loc[(merged["source_rows_prior"] == 0) & (merged["source_rows_current"] > 0), "change_type"] = "新增"
    merged.loc[(merged["source_rows_prior"] > 0) & (merged["source_rows_current"] == 0), "change_type"] = "退出"
    merged.loc[
        (merged["change_type"] == "存续") & (merged["full_market_value_delta"] >= 0),
        "change_type",
    ] = "存续增加"
    merged.loc[
        (merged["change_type"] == "存续") & (merged["full_market_value_delta"] < 0),
        "change_type",
    ] = "存续减少"
    return merged


def asset_evidence_year_open(
    data: pd.DataFrame,
    current_month: str,
    account: str | None = None,
    asset_class: str | None = None,
    manager: str | None = None,
    extra_group_cols: list[str] | None = None,
    prior_month: str | None = None,
) -> pd.DataFrame:
    subset = data.copy()
    if account and account != "全部":
        subset = subset[subset["account_bucket"] == account]
    if asset_class and asset_class != "全部":
        subset = subset[subset["asset_class"] == asset_class]
    if manager and manager != "全部":
        subset = subset[subset["manager"] == manager]

    cols = _asset_evidence_group_columns(extra_group_cols)
    subset = _ensure_group_columns(subset, cols)
    subset = _ensure_numeric_columns(
        subset,
        [
            "full_market_value",
            "market_value_year_open",
            "avg_capital_ytd",
            "comprehensive_income_mtd",
            "finance_income_ytd",
            "comprehensive_income_ytd",
        ],
    )
    evidence = (
        _snapshot_slice(subset, current_month)
        .groupby(cols, dropna=False)
        .agg(
            full_market_value_current=("full_market_value", "sum"),
            full_market_value_prior=("market_value_year_open", "sum"),
            avg_capital_mtd_current=("avg_capital_ytd", "sum"),
            finance_income_mtd_current=("finance_income_ytd", "sum"),
            comprehensive_income_mtd_current=("comprehensive_income_ytd", "sum"),
            comprehensive_income_latest_month=("comprehensive_income_mtd", "sum"),
            source_rows_current=("asset_name", "size"),
        )
        .reset_index()
    )

    if prior_month:
        month_prior = (
            _snapshot_slice(subset, prior_month)
            .groupby(cols, dropna=False)
            .agg(
                full_market_value_month_prior=("full_market_value", "sum"),
                source_rows_month_prior=("asset_name", "size"),
            )
            .reset_index()
        )
        evidence = evidence.merge(month_prior, on=cols, how="left")
        evidence["full_market_value_month_prior"] = evidence["full_market_value_month_prior"].fillna(0.0)
        evidence["source_rows_month_prior"] = evidence["source_rows_month_prior"].fillna(0.0)
    else:
        evidence["full_market_value_month_prior"] = None
        evidence["source_rows_month_prior"] = None

    evidence["source_rows_prior"] = None
    evidence["full_market_value_delta"] = (
        evidence["full_market_value_current"] - evidence["full_market_value_prior"]
    )
    evidence["ytd_position_flow_delta"] = (
        evidence["full_market_value_delta"] - evidence["comprehensive_income_mtd_current"]
    )
    evidence["monthly_position_flow_delta"] = None
    if prior_month:
        evidence["monthly_position_flow_delta"] = (
            evidence["full_market_value_current"]
            - evidence["full_market_value_month_prior"]
            - evidence["comprehensive_income_latest_month"]
        )
    evidence = _add_evidence_return_columns(evidence)
    evidence["change_type"] = "较年初持平"
    evidence.loc[
        (evidence["full_market_value_prior"].abs() <= 0.0001)
        & (evidence["full_market_value_current"].abs() > 0.0001),
        "change_type",
    ] = "年初无持仓、本月有持仓"
    evidence.loc[
        (evidence["full_market_value_prior"].abs() > 0.0001)
        & (evidence["full_market_value_current"].abs() <= 0.0001),
        "change_type",
    ] = "年初有持仓、本月无持仓"
    evidence.loc[
        (evidence["change_type"] == "较年初持平") & (evidence["full_market_value_delta"] > 0.0001),
        "change_type",
    ] = "较年初增加"
    evidence.loc[
        (evidence["change_type"] == "较年初持平") & (evidence["full_market_value_delta"] < -0.0001),
        "change_type",
    ] = "较年初减少"
    return evidence
