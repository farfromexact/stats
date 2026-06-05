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


def _aggregate(data: pd.DataFrame, month: str, group_cols: list[str]) -> pd.DataFrame:
    subset = data[data["snapshot_month"] == month].copy()
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
    merged["finance_income_period"] = (
        merged["finance_income_ytd_current"] - merged["finance_income_ytd_prior"]
    )
    merged["comprehensive_income_period"] = (
        merged["comprehensive_income_ytd_current"] - merged["comprehensive_income_ytd_prior"]
    )
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
    subset = data[data["snapshot_month"] == current_month].copy()
    if account and account != "全部":
        subset = subset[subset["account_bucket"] == account]
    if asset_class and asset_class != "全部":
        subset = subset[subset["asset_class"] == asset_class]
    if manager and manager != "全部":
        subset = subset[subset["manager"] == manager]
    return subset


def asset_evidence(
    data: pd.DataFrame,
    current_month: str,
    prior_month: str,
    account: str | None = None,
    asset_class: str | None = None,
    manager: str | None = None,
) -> pd.DataFrame:
    subset = data.copy()
    if account and account != "全部":
        subset = subset[subset["account_bucket"] == account]
    if asset_class and asset_class != "全部":
        subset = subset[subset["asset_class"] == asset_class]
    if manager and manager != "全部":
        subset = subset[subset["manager"] == manager]

    cols = ["asset_key", "asset_name", "asset_code", "trade_code", "account_bucket", "asset_class", "manager"]
    current = (
        subset[subset["snapshot_month"] == current_month]
        .groupby(cols, dropna=False)
        .agg(
            full_market_value_current=("full_market_value", "sum"),
            finance_income_mtd_current=("finance_income_mtd", "sum"),
            comprehensive_income_mtd_current=("comprehensive_income_mtd", "sum"),
            source_rows_current=("asset_name", "size"),
        )
        .reset_index()
    )
    prior = (
        subset[subset["snapshot_month"] == prior_month]
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
) -> pd.DataFrame:
    subset = data[data["snapshot_month"] == current_month].copy()
    if account and account != "全部":
        subset = subset[subset["account_bucket"] == account]
    if asset_class and asset_class != "全部":
        subset = subset[subset["asset_class"] == asset_class]
    if manager and manager != "全部":
        subset = subset[subset["manager"] == manager]

    cols = ["asset_key", "asset_name", "asset_code", "trade_code", "account_bucket", "asset_class", "manager"]
    evidence = (
        subset.groupby(cols, dropna=False)
        .agg(
            full_market_value_current=("full_market_value", "sum"),
            full_market_value_prior=("market_value_year_open", "sum"),
            finance_income_mtd_current=("finance_income_ytd", "sum"),
            comprehensive_income_mtd_current=("comprehensive_income_ytd", "sum"),
            source_rows_current=("asset_name", "size"),
        )
        .reset_index()
    )
    evidence["source_rows_prior"] = None
    evidence["full_market_value_delta"] = (
        evidence["full_market_value_current"] - evidence["full_market_value_prior"]
    )
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
