from __future__ import annotations

import numpy as np
import pandas as pd


INTERNAL_MANDATE = "委托资管"
RETURN_BASE_THRESHOLD = 0.0001
EXCLUDED_STRATEGY_BOOK = "流动性/其他未纳入五类"

INTERNAL_STRATEGY_BOOK_ORDER = [
    "固收-配置盘",
    "固收-交易盘",
    "非标",
    "权益-配置盘",
    "权益-交易盘",
]
EXTERNAL_STRATEGY_BOOK_ORDER = [
    "人保固收",
    "泰康固收",
    "富国权益",
    "华泰权益",
    "太平资产香港",
    "太保投资香港",
    "国寿富兰克林",
]
STRATEGY_BOOK_ORDER = INTERNAL_STRATEGY_BOOK_ORDER + EXTERNAL_STRATEGY_BOOK_ORDER
STRATEGY_BOOK_SCOPE = {
    **{label: "委内" for label in INTERNAL_STRATEGY_BOOK_ORDER},
    **{label: "委外" for label in EXTERNAL_STRATEGY_BOOK_ORDER},
}
STRATEGY_BOOK_LABEL_ORDER = [f"{STRATEGY_BOOK_SCOPE[label]}-{label}" for label in STRATEGY_BOOK_ORDER]

FIXED_ALLOCATION_CLASSES = {
    "存款",
    "同业存单",
    "政府债",
    "金融债",
    "企业债",
    "固收类保险资管产品",
}
FIXED_TRADING_CLASSES = {
    "同业存单",
    "政府债",
    "金融债",
    "企业债",
    "资产支持证券",
    "债券型基金",
    "固收类保险资管产品",
}
NONSTANDARD_CLASSES = {
    "信托计划",
    "债权计划",
    "资产支持计划",
    "持有型不动产ABS",
}
EQUITY_TRADING_CLASSES = {
    "股票",
    "股票型基金",
    "混合型基金",
    "股票型保险资管产品",
    "混合型保险资管产品",
}
OUTSOURCED_FIXED_CLASSES = {
    "同业存单",
    "政府债",
    "金融债",
    "企业债",
    "资产支持证券",
    "债券型基金",
    "固收类保险资管产品",
    "信托计划",
    "债权计划",
    "资产支持计划",
    "持有型不动产ABS",
    "公募REITS",
}
OUTSOURCED_FULL_ACCOUNT_MANDATE_BOOKS = {
    "委托华泰": "华泰权益",
    "委托太平资产香港": "太平资产香港",
    "委托太保投资香港": "太保投资香港",
    "委托国寿富兰克林": "国寿富兰克林",
}
OUTSOURCED_FULL_ACCOUNT_BOOKS = {
    "富国权益",
    *OUTSOURCED_FULL_ACCOUNT_MANDATE_BOOKS.values(),
}
CASH_LIQUIDITY_CLASSES = {
    "活期存款",
    "买入返售",
    "正回购",
    "逆回购",
    "货币类基金",
    "货币类产品",
    "其他（应收）",
    "其它",
}
PRIVATE_EQUITY_REAL_ESTATE_CLASSES = {
    "股权基金",
    "未上市企业股权",
    "股权计划",
    "不动产基金",
    "不动产直投",
}

SECTION_ORDER = {
    "存款": 0,
    "债券": 1,
    "基金": 2,
    "股票": 3,
    "流动性": 4,
    "其他": 9,
}
ITEM_ORDER = {
    "存款": 0,
    "同业存单": 1,
    "政府债": 2,
    "金融债": 3,
    "企业债": 4,
    "固收类基金及产品": 5,
    "非标": 6,
    "股票": 7,
    "股票型产品": 8,
    "公募REITS": 9,
}

RUNTIME_TEXT_COLUMNS = [
    "mandate_type",
    "asset_major_class",
    "asset_class_level_1",
    "asset_class_level_2",
    "asset_class_level_3",
    "asset_class",
    "trade_strategy",
    "manager",
    "fund_book_name",
    "group_book_name",
]


def _text_value(row: pd.Series | dict, column: str) -> str:
    value = row.get(column, "")
    if pd.isna(value):
        return ""
    return str(value).strip()


def classify_strategy_book(row: pd.Series | dict) -> str:
    mandate_type = _text_value(row, "mandate_type")
    fund_book_name = _text_value(row, "fund_book_name")
    asset_major_class = _text_value(row, "asset_major_class")
    asset_class = _text_value(row, "asset_class")
    trade_strategy = _text_value(row, "trade_strategy")
    manager = _text_value(row, "manager")

    if mandate_type == INTERNAL_MANDATE and asset_major_class == "固收":
        if trade_strategy == "配置" and asset_class in NONSTANDARD_CLASSES:
            return "非标"
        if trade_strategy == "配置" and asset_class in FIXED_ALLOCATION_CLASSES:
            return "固收-配置盘"
        if "交易" in trade_strategy and asset_class in FIXED_TRADING_CLASSES:
            return "固收-交易盘"

    if mandate_type == INTERNAL_MANDATE and asset_major_class == "权益":
        if trade_strategy == "配置" and manager == "鲍淼" and asset_class == "股票":
            return "权益-配置盘"
        if trade_strategy == "交易" and asset_class in EQUITY_TRADING_CLASSES:
            return "权益-交易盘"

    if mandate_type == "委托人保" and asset_class in OUTSOURCED_FIXED_CLASSES:
        return "人保固收"
    if mandate_type == "委托泰康" and asset_class in OUTSOURCED_FIXED_CLASSES:
        return "泰康固收"
    if "富国" in fund_book_name:
        return "富国权益"
    if mandate_type in OUTSOURCED_FULL_ACCOUNT_MANDATE_BOOKS:
        return OUTSOURCED_FULL_ACCOUNT_MANDATE_BOOKS[mandate_type]

    return EXCLUDED_STRATEGY_BOOK


def strategy_book_scope(value: object) -> str:
    return STRATEGY_BOOK_SCOPE.get(str(value).strip(), "未纳入")


def strategy_book_display_label(value: object) -> str:
    label = str(value).strip()
    scope = strategy_book_scope(label)
    if scope in {"委内", "委外"}:
        return f"{scope}-{label}"
    return label


def strategy_book_section(row: pd.Series | dict) -> str:
    strategy_book = _text_value(row, "strategy_book") or classify_strategy_book(row)
    asset_class = _text_value(row, "asset_class")
    asset_class_level_1 = _text_value(row, "asset_class_level_1")

    if strategy_book in {"固收-配置盘", "固收-交易盘", "非标", "人保固收", "泰康固收"}:
        if asset_class == "存款":
            return "存款"
        if asset_class in {"同业存单", "政府债", "金融债", "企业债", "资产支持证券", "持有型不动产ABS"}:
            return "债券"
        if asset_class in {
            "债券型基金",
            "固收类保险资管产品",
            "信托计划",
            "债权计划",
            "资产支持计划",
            "公募REITS",
        }:
            return "基金"

    if strategy_book in {"权益-配置盘", "权益-交易盘"} | OUTSOURCED_FULL_ACCOUNT_BOOKS:
        if (
            strategy_book in OUTSOURCED_FULL_ACCOUNT_BOOKS
            and (asset_class in CASH_LIQUIDITY_CLASSES or asset_class_level_1 in {"现金", "回购", "存款"})
        ):
            return "流动性"
        if asset_class == "股票":
            return "股票"
        if asset_class in {
            "股票型基金",
            "混合型基金",
            "股票型保险资管产品",
            "混合型保险资管产品",
            "单一资产管理计划（股票类产品）",
        }:
            return "基金"

    return "其他"


def strategy_book_item(row: pd.Series | dict) -> str:
    asset_class = _text_value(row, "asset_class")
    if asset_class == "资产支持证券":
        return "企业债"
    if asset_class in NONSTANDARD_CLASSES:
        return "非标"
    if asset_class in {"债券型基金", "固收类保险资管产品"}:
        return "固收类基金及产品"
    if asset_class in {
        "股票型基金",
        "混合型基金",
        "股票型保险资管产品",
        "混合型保险资管产品",
        "单一资产管理计划（股票类产品）",
    }:
        return "股票型产品"
    return asset_class or "未填报"


def exclusion_reason(row: pd.Series | dict) -> str:
    asset_major_class = _text_value(row, "asset_major_class")
    asset_class = _text_value(row, "asset_class")
    asset_class_level_1 = _text_value(row, "asset_class_level_1")
    asset_class_level_2 = _text_value(row, "asset_class_level_2")
    trade_strategy = _text_value(row, "trade_strategy")
    mandate_type = _text_value(row, "mandate_type")
    fund_book_name = _text_value(row, "fund_book_name")

    if mandate_type == "富国基金单一计划" and "富国" not in fund_book_name:
        return "富国顶层产品汇总行，已排除以避免重复计算底层持仓"

    if (
        asset_class in PRIVATE_EQUITY_REAL_ESTATE_CLASSES
        or "股权" in asset_class
        or "不动产" in asset_class
        or "股权" in asset_class_level_2
        or "不动产" in asset_class_level_2
    ):
        return "股权/不动产直投，未纳入委内/委外比较核心分类"
    if asset_class in CASH_LIQUIDITY_CLASSES or asset_class_level_1 in {"现金", "回购", "存款"}:
        return "流动性、现金、回购、应收或费用科目"
    if asset_major_class in {"", "-", "未填报", "缺省"} or trade_strategy in {"", "-", "未填报", "缺省"}:
        return "源表缺少资产大类或交易策略"
    if (
        mandate_type not in {INTERNAL_MANDATE, "委托人保", "委托泰康"}
        and mandate_type not in OUTSOURCED_FULL_ACCOUNT_MANDATE_BOOKS
        and "富国" not in fund_book_name
    ):
        return "非委内/指定委外账户"
    return "不符合委内/委外比较分类规则"


def assign_strategy_book_columns(data: pd.DataFrame) -> pd.DataFrame:
    working = data.copy()
    for column in RUNTIME_TEXT_COLUMNS:
        if column not in working.columns:
            working[column] = ""
        working[column] = working[column].fillna("").astype(str).str.strip()

    if working.empty:
        working["strategy_book"] = pd.Series(dtype=object)
        working["strategy_book_scope"] = pd.Series(dtype=object)
        working["strategy_book_display_label"] = pd.Series(dtype=object)
        working["strategy_book_section"] = pd.Series(dtype=object)
        working["strategy_book_item"] = pd.Series(dtype=object)
        working["strategy_book_exclusion_reason"] = pd.Series(dtype=object)
        return working

    working["strategy_book"] = working.apply(classify_strategy_book, axis=1)
    working["strategy_book_scope"] = working["strategy_book"].map(strategy_book_scope)
    working["strategy_book_display_label"] = working["strategy_book"].map(strategy_book_display_label)
    working["strategy_book_section"] = working.apply(strategy_book_section, axis=1)
    working["strategy_book_item"] = working.apply(strategy_book_item, axis=1)
    working["strategy_book_exclusion_reason"] = working.apply(exclusion_reason, axis=1)
    return working


def _metric_columns(comparison_mode: str) -> tuple[str, str, str]:
    if comparison_mode == "年初以来":
        return "finance_income_ytd", "comprehensive_income_ytd", "avg_capital_ytd"
    return "finance_income_mtd", "comprehensive_income_mtd", "avg_capital_mtd"


def _current_strategy_slice(data: pd.DataFrame, current_month: str) -> pd.DataFrame:
    working = data[data["snapshot_month"] == current_month].copy()
    return assign_strategy_book_columns(working)


def _aggregate_current(frame: pd.DataFrame, group_cols: list[str], comparison_mode: str) -> pd.DataFrame:
    finance_col, comprehensive_col, capital_col = _metric_columns(comparison_mode)
    for column in ["full_market_value", finance_col, comprehensive_col, capital_col]:
        if column not in frame:
            frame[column] = 0.0
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)

    if frame.empty:
        return pd.DataFrame(
            columns=group_cols
            + [
                "full_market_value_current",
                "finance_income_mtd_current",
                "comprehensive_income_mtd_current",
                "avg_capital_mtd_current",
                "finance_return_mtd",
                "comprehensive_return_mtd",
                "record_count_current",
            ]
        )

    summary = (
        frame.groupby(group_cols, dropna=False)
        .agg(
            full_market_value_current=("full_market_value", "sum"),
            finance_income_mtd_current=(finance_col, "sum"),
            comprehensive_income_mtd_current=(comprehensive_col, "sum"),
            avg_capital_mtd_current=(capital_col, "sum"),
            record_count_current=("asset_name", "size"),
        )
        .reset_index()
    )
    valid_base = summary["avg_capital_mtd_current"].abs() > RETURN_BASE_THRESHOLD
    summary["finance_return_mtd"] = np.nan
    summary["comprehensive_return_mtd"] = np.nan
    summary.loc[valid_base, "finance_return_mtd"] = (
        summary.loc[valid_base, "finance_income_mtd_current"]
        / summary.loc[valid_base, "avg_capital_mtd_current"]
    )
    summary.loc[valid_base, "comprehensive_return_mtd"] = (
        summary.loc[valid_base, "comprehensive_income_mtd_current"]
        / summary.loc[valid_base, "avg_capital_mtd_current"]
    )
    return summary


def strategy_book_summary(data: pd.DataFrame, current_month: str, comparison_mode: str) -> pd.DataFrame:
    current = _current_strategy_slice(data, current_month)
    current = current[current["strategy_book"].isin(STRATEGY_BOOK_ORDER)].copy()
    summary = _aggregate_current(current, ["strategy_book"], comparison_mode)

    if summary.empty:
        summary = pd.DataFrame({"strategy_book": STRATEGY_BOOK_ORDER})
    else:
        summary = (
            summary.set_index("strategy_book")
            .reindex(STRATEGY_BOOK_ORDER)
            .rename_axis("strategy_book")
            .reset_index()
        )

    numeric_defaults = {
        "full_market_value_current": 0.0,
        "finance_income_mtd_current": 0.0,
        "comprehensive_income_mtd_current": 0.0,
        "avg_capital_mtd_current": 0.0,
        "record_count_current": 0,
    }
    for column, default in numeric_defaults.items():
        if column not in summary.columns:
            summary[column] = default
        summary[column] = pd.to_numeric(summary[column], errors="coerce").fillna(default)

    for column in ["finance_return_mtd", "comprehensive_return_mtd"]:
        if column not in summary.columns:
            summary[column] = np.nan
    summary["strategy_book_scope"] = summary["strategy_book"].map(strategy_book_scope)
    summary["strategy_book_display_label"] = summary["strategy_book"].map(strategy_book_display_label)
    summary["_strategy_book_order"] = summary["strategy_book"].map(
        {label: index for index, label in enumerate(STRATEGY_BOOK_ORDER)}
    )
    return summary.sort_values("_strategy_book_order").drop(columns=["_strategy_book_order"])


def strategy_book_detail_summary(data: pd.DataFrame, current_month: str, comparison_mode: str) -> pd.DataFrame:
    current = _current_strategy_slice(data, current_month)
    current = current[current["strategy_book"].isin(STRATEGY_BOOK_ORDER)].copy()
    detail = _aggregate_current(
        current,
        ["strategy_book_scope", "strategy_book", "strategy_book_section", "strategy_book_item"],
        comparison_mode,
    )
    if detail.empty:
        return detail

    detail["_strategy_book_order"] = detail["strategy_book"].map(
        {label: index for index, label in enumerate(STRATEGY_BOOK_ORDER)}
    )
    detail["_section_order"] = detail["strategy_book_section"].map(SECTION_ORDER).fillna(9)
    detail["_item_order"] = detail["strategy_book_item"].map(ITEM_ORDER).fillna(99)
    return detail.sort_values(
        ["_strategy_book_order", "_section_order", "_item_order", "full_market_value_current"],
        ascending=[True, True, True, False],
    ).drop(columns=["_strategy_book_order", "_section_order", "_item_order"])


def excluded_strategy_book_detail(data: pd.DataFrame, current_month: str, comparison_mode: str) -> pd.DataFrame:
    current = _current_strategy_slice(data, current_month)
    excluded = current[current["strategy_book"] == EXCLUDED_STRATEGY_BOOK].copy()
    detail = _aggregate_current(
        excluded,
        [
            "strategy_book_exclusion_reason",
            "mandate_type",
            "fund_book_name",
            "asset_major_class",
            "trade_strategy",
            "asset_class_level_1",
            "asset_class_level_2",
            "asset_class",
        ],
        comparison_mode,
    )
    if detail.empty:
        return detail
    detail["_abs_market_value"] = detail["full_market_value_current"].abs()
    return detail.sort_values("_abs_market_value", ascending=False).drop(columns=["_abs_market_value"])
