from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data" / "monthly_snapshots"

REQUIRED_FIELDS = [
    "资产名称",
    "资产代码",
    "交易代码",
    "分账户维度",
    "委受托维度",
    "账套编号",
    "基金账套名称",
    "分组账套名称",
    "投资经理",
    "资产分类",
    "全价市值(亿)",
    "净价市值(亿)",
    "年初市值(亿)",
    "平均资金占用（本月以来）(亿)",
    "平均资金占用（本年以来）(亿)",
    "财务收益（本月以来）(亿)",
    "综合收益（本月以来）(亿)",
    "财务收益（本年以来）(亿)",
    "综合收益（本年以来）(亿)",
]

OPTIONAL_FIELDS = [
    "久期",
]

FIELD_MAP = {
    "资产名称": "asset_name",
    "资产代码": "asset_code",
    "交易代码": "trade_code",
    "分账户维度": "account_bucket",
    "委受托维度": "mandate_type",
    "账套编号": "book_id",
    "基金账套名称": "fund_book_name",
    "分组账套名称": "group_book_name",
    "投资经理": "manager",
    "资产分类": "asset_class",
    "全价市值(亿)": "full_market_value",
    "净价市值(亿)": "clean_market_value",
    "年初市值(亿)": "market_value_year_open",
    "平均资金占用（本月以来）(亿)": "avg_capital_mtd",
    "平均资金占用（本年以来）(亿)": "avg_capital_ytd",
    "财务收益（本月以来）(亿)": "finance_income_mtd",
    "综合收益（本月以来）(亿)": "comprehensive_income_mtd",
    "财务收益（本年以来）(亿)": "finance_income_ytd",
    "综合收益（本年以来）(亿)": "comprehensive_income_ytd",
    "久期": "duration",
}

NUMERIC_COLUMNS = [
    "full_market_value",
    "clean_market_value",
    "market_value_year_open",
    "avg_capital_mtd",
    "avg_capital_ytd",
    "finance_income_mtd",
    "comprehensive_income_mtd",
    "finance_income_ytd",
    "comprehensive_income_ytd",
    "duration",
]

DISPLAY_METRICS = [
    "full_market_value_current",
    "full_market_value_prior",
    "full_market_value_delta",
    "finance_income_mtd_current",
    "comprehensive_income_mtd_current",
    "avg_capital_mtd_current",
    "finance_return_mtd",
    "comprehensive_return_mtd",
]
