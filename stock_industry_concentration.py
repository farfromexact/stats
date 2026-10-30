"""Stock industry concentration, reusing the ranking universe and OCI rules."""
from __future__ import annotations

import pandas as pd

from company_stock_holdings import (
    _prepare_stock_rows, load_industry_mapping, UNMAPPED_INDUSTRY,
)

BOOKS = ["委内交易盘", "委内 OCI", "委外股票", "委内其他/未识别策略"]
SCOPES = {
    "公司整体": BOOKS,
    "委内合计": [BOOKS[0], BOOKS[1], BOOKS[3]],
    "委内交易盘": [BOOKS[0]],
    "委内 OCI": [BOOKS[1]],
    "委外": [BOOKS[2]],
}


def concentration_rows(data, snapshot_date, industry_mapping=None):
    """Return stock rows once per source row; never infer trading from non-OCI."""
    parts = []
    for scope in ("委内", "委外"):
        part = _prepare_stock_rows(data, snapshot_date, holding_scope=scope, include_oci=True)
        if part.empty:
            continue
        part["portfolio"] = BOOKS[2] if scope == "委外" else BOOKS[3]
        if scope == "委内":
            strategy = part.get("trade_strategy", pd.Series("", index=part.index))
            part.loc[strategy.eq("交易"), "portfolio"] = BOOKS[0]
            part.loc[part["_is_oci"], "portfolio"] = BOOKS[1]
        parts.append(part)
    if not parts:
        return pd.DataFrame(columns=["portfolio", "industry", "full_market_value", "_industry_code", "_asset_name"])
    rows = pd.concat(parts, ignore_index=True)
    rows["_industry_code"] = rows["_industry_code"].where(rows["_industry_code"].ne(""), rows["_security_key"])
    mapping = load_industry_mapping() if industry_mapping is None else industry_mapping.copy()
    if mapping.empty:
        rows["industry"] = UNMAPPED_INDUSTRY
    else:
        mapping["code"] = mapping["code"].fillna("").astype(str).str.strip()
        mapping["industry"] = mapping["industry"].fillna("").astype(str).str.strip()
        mapping = mapping.loc[mapping.code.ne("") & mapping.industry.ne("")].drop_duplicates("code")
        rows["industry"] = rows["_industry_code"].map(mapping.set_index("code")["industry"]).fillna(UNMAPPED_INDUSTRY)
    return rows


def concentration_distribution(rows, scope="公司整体"):
    """Long form: company denominator is fixed; portfolio denominator is local."""
    if scope not in SCOPES:
        raise ValueError(f"Unknown scope: {scope}")
    cols = ["industry", "portfolio", "market_value", "company_share", "selected_share", "portfolio_share"]
    if rows.empty:
        return pd.DataFrame(columns=cols)
    selected = rows.loc[rows.portfolio.isin(SCOPES[scope])]
    if selected.empty:
        return pd.DataFrame(columns=cols)
    result = selected.groupby(["industry", "portfolio"], as_index=False).full_market_value.sum().rename(columns={"full_market_value": "market_value"})
    result["company_share"] = result.market_value / rows.full_market_value.sum()
    result["selected_share"] = result.market_value / selected.full_market_value.sum()
    result["portfolio_share"] = result.market_value / result.groupby("portfolio").market_value.transform("sum")
    return result[cols]


def industry_stock_details(rows, industry, scope="公司整体"):
    selected = rows.loc[rows.portfolio.isin(SCOPES[scope])]
    total = selected.full_market_value.sum()
    detail = selected.loc[selected.industry.eq(industry)].groupby(
        ["_industry_code", "portfolio"], as_index=False
    ).agg(asset_name=("_asset_name", "first"), market_value=("full_market_value", "sum"))
    detail["industry_share"] = detail.market_value / detail.market_value.sum()
    detail["selected_share"] = detail.market_value / total
    return detail.sort_values("market_value", ascending=False)
