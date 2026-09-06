"""Estimated funded-period capital for the six domestic outsourced equity accounts.

Dates are user-approved month-start estimates, not transaction records. Source
YTD income stays unchanged; this is not an IRR or a time-weighted return.
"""

import pandas as pd


FUNDING_STARTS = {
    "华泰权益": "2026-04-01",
    "富国权益": "2026-04-01",
    "华夏基金权益": "2026-07-01",
    "国泰海通权益": "2026-07-01",
    "广发基金权益": "2026-07-01",
    "大成基金权益": "2026-07-01",
}
FUNDING_NOTE = (
    "六家境内权益委外的YTD收益率按放款期间折算平均资金占用（估算，非年化）："
    "华泰、富国暂按2026-04-01，其余华夏、国泰海通、广发、大成暂按2026-07-01。"
    "调整后平均占用 = 源表YTD平均占用 × 年内已过天数 ÷ 放款后天数（均含当日）；"
    "收益额沿用源表YTD值，放款前不展示收益率。"
    "大成、广发各2亿未放款仅作说明，不加入分母，也不从源表占用中重复扣减。"
)


def adjust_outsourced_funding_capital(data: pd.DataFrame) -> pd.DataFrame:
    """Adjust a private reporting copy, idempotently; preserve the source column."""
    if not {"strategy_book", "snapshot_date", "avg_capital_ytd"}.issubset(data.columns):
        return data.copy()
    result = data.copy()
    source_column = "source_avg_capital_ytd"
    if source_column not in result:
        result[source_column] = pd.to_numeric(result["avg_capital_ytd"], errors="coerce")
    source = pd.to_numeric(result[source_column], errors="coerce")
    dates = pd.to_datetime(result["snapshot_date"], errors="coerce")
    starts = pd.to_datetime(result["strategy_book"].map(FUNDING_STARTS), errors="coerce")
    applies = starts.notna()
    if "strategy_book_scope" in result:
        applies &= result["strategy_book_scope"].eq("委外")
    year_start = pd.to_datetime(dates.dt.year.astype("Int64").astype(str) + "-01-01", errors="coerce")
    effective_start = starts.where(starts.ge(year_start), year_start)
    funded_days = (dates - effective_start).dt.days + 1
    valid = applies & dates.notna() & funded_days.gt(0)
    factor = dates.dt.dayofyear.div(funded_days.where(valid))
    result.loc[applies, "avg_capital_ytd"] = (source * factor).where(valid)
    result["funding_start_estimate"] = starts.dt.strftime("%Y-%m-%d").where(applies)
    result["funding_capital_factor"] = factor.where(applies, 1.0)
    result["funding_capital_adjusted"] = applies
    return result


def funding_capital_audit(rows: pd.DataFrame, snapshot_date: str) -> pd.DataFrame:
    adjusted = adjust_outsourced_funding_capital(rows)
    if "funding_capital_adjusted" not in adjusted:
        return pd.DataFrame()
    selected = adjusted[adjusted["snapshot_date"].eq(snapshot_date) & adjusted["funding_capital_adjusted"]].copy()
    if "attribution_in_scope" in selected:
        selected = selected[selected["attribution_in_scope"]]
    if selected.empty:
        return pd.DataFrame()
    report = selected.groupby(["strategy_book", "funding_start_estimate"], as_index=False)[
        ["source_avg_capital_ytd", "avg_capital_ytd", "comprehensive_income_ytd"]
    ].sum(min_count=1)
    for capital, column in [("source_avg_capital_ytd", "source_return"), ("avg_capital_ytd", "funding_return")]:
        report[column] = report["comprehensive_income_ytd"].div(report[capital].where(report[capital].gt(0.0001)))
    return report
