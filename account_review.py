import pandas as pd


GROUP_METRICS = [
    "full_market_value",
    "clean_market_value",
    "avg_capital_mtd",
    "finance_income_mtd",
    "comprehensive_income_mtd",
    "finance_income_ytd",
    "comprehensive_income_ytd",
]


def _aggregate(data: pd.DataFrame, month: str, group_cols: list[str]) -> pd.DataFrame:
    subset = data[data["snapshot_month"] == month]
    if subset.empty:
        return pd.DataFrame(columns=group_cols + GROUP_METRICS + ["record_count"])

    return (
        subset.groupby(group_cols, dropna=False)
        .agg(
            full_market_value=("full_market_value", "sum"),
            clean_market_value=("clean_market_value", "sum"),
            avg_capital_mtd=("avg_capital_mtd", "sum"),
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
