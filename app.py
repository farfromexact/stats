import hmac
import importlib
import os
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd
import altair as alt
import streamlit as st

try:
    from streamlit.errors import StreamlitSecretNotFoundError
except ImportError:  # pragma: no cover - compatibility with older Streamlit
    StreamlitSecretNotFoundError = RuntimeError

import account_review as account_review_module
import strategy_books as strategy_books_module
from config import DATA_DIR
from portfolio_data import (
    SNAPSHOT_STATUS_INTERIM,
    SNAPSHOT_STATUS_OFFICIAL,
    available_snapshots,
    discover_snapshot_files,
    load_snapshots,
    snapshot_display_label,
)

account_review_module = importlib.reload(account_review_module)
strategy_books_module = importlib.reload(strategy_books_module)

asset_evidence = account_review_module.asset_evidence
asset_evidence_year_open = account_review_module.asset_evidence_year_open
comparison_summary = account_review_module.comparison_summary
assign_strategy_book_columns = strategy_books_module.assign_strategy_book_columns
STRATEGY_CLASSIFICATION_VERSION = strategy_books_module.STRATEGY_CLASSIFICATION_VERSION
EXTERNAL_STRATEGY_BOOK_ORDER = strategy_books_module.EXTERNAL_STRATEGY_BOOK_ORDER
OUTSOURCED_EQUITY_HOLDING_TYPE_ORDER = strategy_books_module.OUTSOURCED_EQUITY_HOLDING_TYPE_ORDER
STRATEGY_BOOK_LABEL_ORDER = strategy_books_module.STRATEGY_BOOK_LABEL_ORDER
excluded_strategy_book_detail = strategy_books_module.excluded_strategy_book_detail
outsourced_equity_holding_slice = strategy_books_module.outsourced_equity_holding_slice
strategy_book_detail_summary = strategy_books_module.strategy_book_detail_summary
strategy_book_summary = strategy_books_module.strategy_book_summary


ALL = "全部"
RETURN_BASE_THRESHOLD = 0.0001
DATA_SCHEMA_VERSION = "2026-07-18-snapshot-date-v2"
ASSET_RETURN_PLAN_PATH = DATA_DIR.parent / "asset_return_plan_2026.csv"
LOCAL_FULL_APP_MARKER_PATH = Path(__file__).resolve().parent / ".streamlit" / "local_full_app"
MAINTENANCE_MESSAGE = "多事之秋，我们秋天再见"
MAINTENANCE_SUBMESSAGE = "如有需要微信找我"
CHART_EPSILON = 1e-9
POSITIVE_COLOR = "#122256"
NEGATIVE_COLOR = "#8B2F2F"
NEUTRAL_COLOR = "#8EA0B6"
FUNDING_COLOR = "#6F7F92"
HEATMAP_NEUTRAL_COLOR = "#F7F4EF"
HEATMAP_POSITIVE_LIGHT = "#B7CCE4"
HEATMAP_NEGATIVE_LIGHT = "#E3B0AE"
FUNDING_COST_RATE = 0.0341
GUARANTEE_COST_RATE = 0.0324
EFFECTIVE_COST_RATE = 0.0326
ACCOUNT_ORDER_PREFIX = [
    "传统",
    "自有",
    "分红一",
    "分红1",
    "分红二",
    "分红2",
    "万能一",
    "万能二",
    "万能三",
    "万能四",
    "穿透账户",
]
REPO_FINANCING_ASSET_CLASSES = {"正回购"}
REVERSE_REPO_ASSET_CLASSES = {"逆回购", "买入返售"}
FUNDING_ASSET_CLASSES = REPO_FINANCING_ASSET_CLASSES | REVERSE_REPO_ASSET_CLASSES
EQUITY_THEME_KEYWORDS = ("股权", "长股投")
REAL_ESTATE_THEME_KEYWORDS = ("不动产",)

st.set_page_config(page_title="组合管理账户复盘", layout="wide")


def apply_yacht_theme() -> None:
    st.markdown(
        """
        <style>
        :root {
            --yacht-ink: #0D0707;
            --yacht-navy: #122256;
            --yacht-blue: #8EA0B6;
            --yacht-foam: #F2F1ED;
            --yacht-deck: #DCDACD;
            --rat-internal: #2F5AA8;
            --rat-external: #0F8B7B;
        }

        .stApp {
            background: var(--yacht-foam);
            color: var(--yacht-ink);
        }

        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, var(--yacht-navy) 0%, #172b63 58%, #0D0707 100%);
        }

        section[data-testid="stSidebar"] * {
            color: var(--yacht-foam);
        }

        section[data-testid="stSidebar"] div[data-baseweb="select"] * {
            color: var(--yacht-ink);
        }

        section[data-testid="stSidebar"] div[data-baseweb="select"] {
            background: var(--yacht-foam);
            border-radius: 6px;
        }

        section[data-testid="stSidebar"] input {
            color: var(--yacht-ink);
            background: var(--yacht-foam);
        }

        section[data-testid="stSidebar"] code,
        section[data-testid="stSidebar"] pre,
        section[data-testid="stSidebar"] kbd {
            color: var(--yacht-ink) !important;
            background: var(--yacht-foam) !important;
            border: 1px solid var(--yacht-blue);
            border-radius: 6px;
            white-space: normal;
            overflow-wrap: anywhere;
        }

        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] span {
            color: var(--yacht-foam);
        }

        h1, h2, h3 {
            color: var(--yacht-navy);
            letter-spacing: 0;
        }

        h1 {
            border-bottom: 3px solid var(--yacht-blue);
            padding-bottom: 0.35rem;
        }

        div[data-testid="stMetric"] {
            background: rgba(255, 255, 255, 0.72);
            border: 1px solid var(--yacht-deck);
            border-radius: 8px;
            padding: 0.85rem 1rem;
            box-shadow: 0 2px 10px rgba(13, 7, 7, 0.05);
        }

        div[data-testid="stMetric"] label {
            color: var(--yacht-navy);
        }

        div[data-testid="stMetricValue"] {
            color: var(--yacht-ink);
        }

        .filter-pills {
            display: flex;
            flex-wrap: wrap;
            gap: 0.45rem;
            margin: 0.55rem 0 1rem 0;
        }

        .filter-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.32rem 0.55rem;
            background: rgba(255, 255, 255, 0.7);
            border: 1px solid var(--yacht-deck);
            border-radius: 6px;
            color: var(--yacht-ink);
            font-size: 0.86rem;
            line-height: 1.25;
        }

        .filter-pill span {
            color: #5B6472;
            font-weight: 600;
        }

        .kpi-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(176px, 1fr));
            gap: 0.8rem;
            margin: 0.65rem 0 0.85rem 0;
        }

        .kpi-card {
            min-height: 96px;
            background: rgba(255, 255, 255, 0.78);
            border: 1px solid var(--yacht-deck);
            border-left: 4px solid var(--yacht-blue);
            border-radius: 8px;
            padding: 0.78rem 0.9rem;
            box-shadow: 0 2px 10px rgba(13, 7, 7, 0.05);
        }

        .kpi-card.kpi-card-internal {
            background: linear-gradient(180deg, rgba(47, 90, 168, 0.14) 0%, rgba(47, 90, 168, 0.08) 100%);
            border-color: rgba(47, 90, 168, 0.38);
            border-left-color: var(--rat-internal);
        }

        .kpi-card.kpi-card-external {
            background: linear-gradient(180deg, rgba(15, 139, 123, 0.14) 0%, rgba(15, 139, 123, 0.08) 100%);
            border-color: rgba(15, 139, 123, 0.36);
            border-left-color: var(--rat-external);
        }

        .kpi-label {
            color: var(--yacht-navy);
            font-size: 0.84rem;
            font-weight: 700;
            line-height: 1.25;
            margin-bottom: 0.45rem;
        }

        .kpi-value {
            color: var(--yacht-ink);
            font-size: 1.58rem;
            font-weight: 760;
            line-height: 1.16;
            overflow-wrap: anywhere;
        }

        .kpi-delta {
            display: inline-block;
            margin-top: 0.45rem;
            color: #0F6F3F;
            background: #E9F5ED;
            border-radius: 999px;
            padding: 0.12rem 0.42rem;
            font-size: 0.82rem;
            font-weight: 700;
        }

        .kpi-delta.kpi-delta-positive {
            color: var(--yacht-navy);
            background: rgba(142, 160, 182, 0.18);
        }

        .kpi-delta.kpi-delta-negative {
            color: #8B2F2F;
            background: rgba(139, 47, 47, 0.12);
        }

        .decision-summary {
            margin: 0.35rem 0 0.6rem 0;
            color: var(--yacht-ink);
            font-size: 1rem;
            line-height: 1.65;
        }

        .action-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
            gap: 0.7rem;
            margin: 0.8rem 0 1rem 0;
        }

        .action-card {
            display: block;
            min-height: 92px;
            background: rgba(255, 255, 255, 0.8);
            border: 1px solid var(--yacht-deck);
            border-radius: 8px;
            padding: 0.78rem 0.85rem;
            color: var(--yacht-ink) !important;
            text-decoration: none;
            box-shadow: 0 2px 10px rgba(13, 7, 7, 0.04);
        }

        .action-card,
        .action-card * {
            text-decoration: none !important;
        }

        .action-card:hover {
            border-color: var(--yacht-blue);
            text-decoration: none;
        }

        .action-title {
            color: var(--yacht-navy);
            font-weight: 760;
            margin-bottom: 0.28rem;
        }

        .action-copy {
            color: #475569;
            font-size: 0.88rem;
            line-height: 1.42;
        }

        .quality-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(142px, 1fr));
            gap: 0.55rem;
            margin: 0.8rem 0 0.6rem 0;
        }

        .quality-card {
            background: rgba(255, 255, 255, 0.78);
            border: 1px solid var(--yacht-deck);
            border-radius: 8px;
            padding: 0.65rem 0.75rem;
        }

        .quality-card.hot {
            border-color: #C88439;
            background: #FFF7E8;
        }

        .quality-label {
            color: #475569;
            font-size: 0.8rem;
            font-weight: 700;
            margin-bottom: 0.2rem;
        }

        .quality-value {
            color: var(--yacht-ink);
            font-size: 1.35rem;
            font-weight: 760;
            line-height: 1.12;
        }

        div[data-testid="stAlert"] {
            border-radius: 8px;
            border-color: var(--yacht-blue);
        }

        .stButton > button {
            background: var(--yacht-navy);
            color: var(--yacht-foam);
            border: 1px solid var(--yacht-navy);
            border-radius: 6px;
        }

        .stButton > button:hover {
            background: var(--yacht-ink);
            color: var(--yacht-foam);
            border-color: var(--yacht-ink);
        }

        .sidebar-nav-button {
            display: block;
            width: 100%;
            margin: 0.35rem 0;
            padding: 0.42rem 0.65rem;
            background: rgba(142, 160, 182, 0.18);
            color: var(--yacht-foam) !important;
            border: 1px solid rgba(242, 241, 237, 0.22);
            border-radius: 6px;
            text-decoration: none;
            font-weight: 600;
            font-size: 0.9rem;
        }

        .sidebar-nav-button:hover {
            background: rgba(242, 241, 237, 0.16);
            color: white !important;
            text-decoration: none;
        }

        .sidebar-nav-title {
            margin: 1rem 0 0.4rem 0;
            color: var(--yacht-foam) !important;
            font-weight: 700;
            opacity: 0.9;
        }

        div[data-testid="stDataFrame"] {
            border: 1px solid var(--yacht-deck);
            border-radius: 8px;
            overflow: hidden;
            background: white;
        }

        div[data-testid="stVegaLiteChart"] {
            background: rgba(255, 255, 255, 0.72);
            border: 1px solid var(--yacht-deck);
            border-radius: 8px;
            padding: 0.35rem;
        }

        div[data-testid="stCaptionContainer"] {
            color: #475569;
        }

        hr {
            border-color: var(--yacht-deck);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _configured_password() -> str | None:
    """Read the app password from deployment-safe config, not source code."""
    try:
        if "app_password" in st.secrets:
            return str(st.secrets["app_password"])
    except StreamlitSecretNotFoundError:
        pass
    return os.environ.get("PORTFOLIO_APP_PASSWORD")


def _truthy(value: object) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


def _secret_flag(name: str) -> str | None:
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except StreamlitSecretNotFoundError:
        return None
    return None


def maintenance_mode_enabled() -> bool:
    configured = os.environ.get("PORTFOLIO_APP_MAINTENANCE") or _secret_flag("maintenance_mode")
    if _truthy(configured):
        return _truthy(configured)
    return not LOCAL_FULL_APP_MARKER_PATH.exists()


def render_maintenance_page() -> None:
    st.markdown(
        f"""
        <style>
        div[data-testid="stSidebar"] {{
            display: none;
        }}
        section.main > div {{
            padding-top: 28vh;
        }}
        .maintenance-message {{
            color: var(--yacht-navy);
            font-size: clamp(2.8rem, 7vw, 6.5rem);
            font-weight: 800;
            line-height: 1.18;
            text-align: center;
            letter-spacing: 0;
        }}
        .maintenance-submessage {{
            margin-top: 1.2rem;
            color: var(--yacht-blue);
            font-size: clamp(1.2rem, 2.5vw, 2.2rem);
            font-weight: 700;
            line-height: 1.2;
            text-align: center;
            letter-spacing: 0;
        }}
        </style>
        <div class="maintenance-message">{html_text(MAINTENANCE_MESSAGE)}</div>
        <div class="maintenance-submessage">{html_text(MAINTENANCE_SUBMESSAGE)}</div>
        """,
        unsafe_allow_html=True,
    )


def require_login() -> None:
    expected_password = _configured_password()
    if not expected_password:
        st.error("未配置访问密码。请在 Streamlit secrets 中设置 app_password，或设置环境变量 PORTFOLIO_APP_PASSWORD。")
        st.stop()

    if st.session_state.get("authenticated"):
        return

    st.title("组合管理账户复盘")
    st.caption("请输入访问密码后继续。")
    password = st.text_input("访问密码", type="password")
    if st.button("进入"):
        if hmac.compare_digest(password, expected_password):
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("密码不正确。")
    st.stop()


DISPLAY_NAMES = {
    "snapshot_date": "数据时点",
    "snapshot_month": "快照月份",
    "snapshot_status": "快照状态",
    "source_file_name": "源文件名",
    "source_file_hash": "源文件哈希",
    "source_rows": "源表行数",
    "status": "状态",
    "message": "校验信息",
    "full_market_value": "全价市值(亿)",
    "finance_income_mtd": "本月财务收益(亿)",
    "comprehensive_income_mtd": "本月综合收益(亿)",
    "duration": "久期",
    "account_bucket": "账户",
    "mandate_type": "委受托维度",
    "fund_book_name": "基金账套名称",
    "group_book_name": "分组账套名称",
    "asset_major_class": "资产大类",
    "asset_class_level_1": "资产分类一级",
    "asset_class_level_2": "资产分类二级",
    "asset_class_level_3": "资产分类三级",
    "asset_theme": "资产主题",
    "asset_class_display": "投资品种展示",
    "asset_class": "投资品种",
    "trade_strategy": "交易策略",
    "manager": "投资经理",
    "asset_name": "资产名称",
    "asset_code": "资产代码",
    "trade_code": "交易代码",
    "change_type": "变化类型",
    "full_market_value_current": "当前时点市值(亿)",
    "full_market_value_prior": "上月市值(亿)",
    "full_market_value_delta": "较上月变化(亿)",
    "net_full_market_value_delta": "扣收益后较上月规模变化(亿)",
    "ytd_position_flow_delta": "扣综合收益后较年初加减仓(亿)",
    "monthly_position_flow_delta": "扣本月综合收益后较上月加减仓(亿)",
    "finance_income_mtd_current": "本月财务收益(亿)",
    "comprehensive_income_mtd_current": "本月综合收益(亿)",
    "finance_income_mtd_delta": "财务收益变化(亿)",
    "comprehensive_income_mtd_delta": "综合收益变化(亿)",
    "finance_income_period": "本月财务收益(亿)",
    "comprehensive_income_period": "本月综合收益(亿)",
    "avg_capital_mtd_current": "本月平均资本占用(亿)",
    "finance_return_mtd": "本月财务收益率",
    "comprehensive_return_mtd": "本月综合收益率",
    "record_count_current": "当前记录数",
    "source_rows_current": "当前源行数",
    "source_rows_prior": "上月源行数",
    "weighted_duration": "账户加权久期",
    "duration_market_value": "纳入久期计算市值(亿)",
    "duration_coverage_ratio": "久期市值覆盖率",
    "duration_asset_count": "纳入久期资产数",
    "plan_asset": "计划资产项",
    "plan_balance": "计划余额(亿)",
    "target_return_mid": "目标收益率中枢",
    "target_return_low": "目标收益率下限",
    "target_return_high": "目标收益率上限",
    "target_return_range": "目标收益率区间",
    "actual_ytd_comprehensive_return": "当前YTD综合收益率",
    "actual_annualized_comprehensive_return": "当前年化综合收益率",
    "planned_income": "年度计划综合收益(亿)",
    "actual_ytd_income": "当前YTD综合收益(亿)",
    "actual_annualized_income": "当前年化综合收益(亿)",
    "income_gap": "收益缺口/超额(亿)",
    "income_completion_rate": "收益金额完成率",
    "allocation_gap": "配置差额(亿)",
    "return_completion_status": "收益金额完成状态",
    "return_rate_status": "收益率状态",
    "return_deviation": "收益率偏离幅度",
    "mapped_asset_classes": "映射投资品种",
    "strategy_book_scope": "委内/委外",
    "strategy_book": "配置/交易分类",
    "strategy_book_display_label": "委内/委外分类",
    "strategy_book_section": "二级展示",
    "strategy_book_item": "明细展示",
    "strategy_book_exclusion_reason": "未纳入原因",
    "outsourced_equity_holding_type": "权益类型",
}

YTD_DISPLAY_OVERRIDES = {
    "full_market_value_prior": "年初市值(亿)",
    "full_market_value_delta": "较年初变化(亿)",
    "net_full_market_value_delta": "扣收益后较年初规模变化(亿)",
    "finance_income_mtd_current": "年初以来财务收益(亿)",
    "comprehensive_income_mtd_current": "年初以来综合收益(亿)",
    "finance_income_period": "年初以来财务收益(亿)",
    "comprehensive_income_period": "年初以来综合收益(亿)",
    "avg_capital_mtd_current": "本年以来平均资本占用(亿)",
    "finance_return_mtd": "年初以来财务收益率",
    "comprehensive_return_mtd": "年初以来综合收益率",
    "source_rows_prior": "年初源行数",
}

AMOUNT_COLUMNS = {
    "full_market_value",
    "finance_income_mtd",
    "comprehensive_income_mtd",
    "full_market_value_current",
    "full_market_value_prior",
    "full_market_value_delta",
    "net_full_market_value_delta",
    "ytd_position_flow_delta",
    "monthly_position_flow_delta",
    "finance_income_mtd_current",
    "comprehensive_income_mtd_current",
    "finance_income_mtd_delta",
    "comprehensive_income_mtd_delta",
    "finance_income_period",
    "comprehensive_income_period",
    "avg_capital_mtd_current",
    "duration_market_value",
    "plan_balance",
    "planned_income",
    "actual_ytd_income",
    "actual_annualized_income",
    "income_gap",
    "allocation_gap",
}
PCT_COLUMNS = {
    "finance_return_mtd",
    "comprehensive_return_mtd",
    "duration_coverage_ratio",
    "target_return_mid",
    "target_return_low",
    "target_return_high",
    "actual_ytd_comprehensive_return",
    "actual_annualized_comprehensive_return",
    "income_completion_rate",
    "return_deviation",
}
DURATION_COLUMNS = {"duration", "weighted_duration"}
COUNT_COLUMNS = {
    "record_count",
    "record_count_current",
    "source_rows",
    "source_rows_current",
    "source_rows_prior",
    "duration_asset_count",
}
RUNTIME_COLUMN_DEFAULTS = {
    "market_value_year_open": 0.0,
    "avg_capital_ytd": 0.0,
    "finance_income_ytd": 0.0,
    "comprehensive_income_ytd": 0.0,
    "asset_major_class": "",
    "asset_class_level_1": "",
    "asset_class_level_2": "",
    "asset_class_level_3": "",
    "trade_strategy": "",
}


def data_source_signature(data_dir: Path) -> tuple[tuple[str, int, int], ...]:
    parquet_dir = data_dir.parent / "snapshot_parquet"
    candidates = [
        *discover_snapshot_files(data_dir),
        *parquet_dir.glob("*.parquet"),
        parquet_dir / "manifest.json",
    ]
    signature: list[tuple[str, int, int]] = []
    for path in sorted({candidate for candidate in candidates if candidate.exists()}):
        stat = path.stat()
        signature.append((str(path.relative_to(data_dir.parent)), stat.st_size, stat.st_mtime_ns))
    return tuple(signature)


def snapshot_slice(data: pd.DataFrame, snapshot_date: str) -> pd.DataFrame:
    key = "snapshot_date" if "snapshot_date" in data.columns else "snapshot_month"
    return data[data[key] == snapshot_date]


def snapshot_status_map(data: pd.DataFrame) -> dict[str, str]:
    if data.empty or not {"snapshot_date", "snapshot_status"}.issubset(data.columns):
        return {}
    metadata = data[["snapshot_date", "snapshot_status"]].drop_duplicates("snapshot_date")
    return dict(zip(metadata["snapshot_date"].astype(str), metadata["snapshot_status"].astype(str)))


def previous_official_snapshots(data: pd.DataFrame, current_snapshot: str) -> list[str]:
    if data.empty or not {"snapshot_date", "snapshot_month", "snapshot_status"}.issubset(data.columns):
        return []
    current_rows = data[data["snapshot_date"].astype(str).eq(current_snapshot)]
    if current_rows.empty:
        return []
    current_report_month = str(current_rows["snapshot_month"].iloc[0])
    previous_report_month = str(pd.Period(current_report_month, freq="M") - 1)
    metadata = data[["snapshot_date", "snapshot_month", "snapshot_status"]].drop_duplicates("snapshot_date")
    candidates = metadata[
        metadata["snapshot_status"].eq(SNAPSHOT_STATUS_OFFICIAL)
        & metadata["snapshot_month"].astype(str).eq(previous_report_month)
    ]
    return sorted(candidates["snapshot_date"].astype(str).tolist())


@st.cache_data(show_spinner="正在读取并预处理月度宽表...")
def cached_load(
    data_dir: str,
    schema_version: str,
    classification_version: str,
    source_signature: tuple[tuple[str, int, int], ...],
):
    del schema_version, classification_version, source_signature
    data, validation, errors = load_snapshots(Path(data_dir))
    if errors or data.empty:
        return data, validation, errors
    return assign_strategy_book_columns(data), validation, errors


def missing_runtime_columns(data: pd.DataFrame) -> list[str]:
    return [column for column in RUNTIME_COLUMN_DEFAULTS if column not in data.columns]


def ensure_runtime_columns(data: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    missing = missing_runtime_columns(data)
    if not missing:
        return data, []

    data = data.copy()
    for column in missing:
        data[column] = RUNTIME_COLUMN_DEFAULTS[column]
    return data, missing


def ensure_summary_columns(summary: pd.DataFrame, comparison_mode: str) -> pd.DataFrame:
    summary = summary.copy()

    def numeric_column(column: str, default: float = 0.0) -> pd.Series:
        if column not in summary.columns:
            return pd.Series(default, index=summary.index, dtype=float)
        return pd.to_numeric(summary[column], errors="coerce").fillna(default)

    if "finance_income_period" not in summary.columns:
        if comparison_mode == "年初以来":
            summary["finance_income_period"] = numeric_column("finance_income_ytd_current")
        else:
            summary["finance_income_period"] = numeric_column("finance_income_mtd_current")

    if "comprehensive_income_period" not in summary.columns:
        if comparison_mode == "年初以来":
            summary["comprehensive_income_period"] = numeric_column("comprehensive_income_ytd_current")
        else:
            summary["comprehensive_income_period"] = numeric_column("comprehensive_income_mtd_current")

    if "net_full_market_value_delta" not in summary.columns:
        summary["net_full_market_value_delta"] = (
            numeric_column("full_market_value_delta") - numeric_column("comprehensive_income_period")
        )

    return summary


def display_names_for_mode(comparison_mode: str) -> dict[str, str]:
    names = DISPLAY_NAMES.copy()
    if comparison_mode == "年初以来":
        names.update(YTD_DISPLAY_OVERRIDES)
    return names


def clean_for_display(frame: pd.DataFrame, comparison_mode: str = "单月复盘") -> pd.DataFrame:
    display = frame.replace([np.inf, -np.inf], np.nan).copy()
    display = display.where(pd.notna(display), np.nan)
    return display.rename(columns=display_names_for_mode(comparison_mode))


def format_table(frame: pd.DataFrame, precision: str = "display", comparison_mode: str = "单月复盘"):
    display_names = display_names_for_mode(comparison_mode)
    display = clean_for_display(frame, comparison_mode)
    amount_decimals = 4 if precision == "source" else 2
    formatters = {}
    for source_col, display_col in display_names.items():
        if display_col not in display.columns:
            continue
        if source_col in AMOUNT_COLUMNS:
            formatters[display_col] = f"{{:,.{amount_decimals}f}}"
        elif source_col in PCT_COLUMNS:
            formatters[display_col] = "{:.2%}"
        elif source_col in DURATION_COLUMNS:
            formatters[display_col] = "{:,.2f}"
        elif source_col in COUNT_COLUMNS:
            formatters[display_col] = "{:,.0f}"
    return display.style.format(formatters, na_rep="—")


def amount(value: float) -> str:
    if value is None or not np.isfinite(value):
        return "—"
    return f"{value:,.2f} 亿"


def pct(value: float) -> str:
    if value is None or not np.isfinite(value):
        return "—"
    return f"{value:.2%}"


def signed_amount(value: float) -> str:
    if value is None or not np.isfinite(value):
        return "—"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:,.2f} 亿"


def html_text(value: object) -> str:
    return escape(str(value), quote=True)


def render_filter_pills(
    current_month: str,
    comparison_mode: str,
    prior_month: str,
    selected_account: str,
    selected_asset_class: str,
    selected_manager: str,
) -> None:
    current_label = snapshot_display_label(current_month)
    if comparison_mode == "年初以来":
        view_text = f"年初以来，截至 {current_label}"
    else:
        view_text = f"{current_label} 单月复盘，规模较 {snapshot_display_label(prior_month)}"
    items = [
        ("当前视角", view_text),
    ]
    items.extend(
        [
            ("账户", selected_label(selected_account)),
            ("投资品种", selected_label(selected_asset_class)),
            ("投资经理", selected_label(selected_manager)),
        ]
    )
    pills = "".join(
        f'<div class="filter-pill"><span>{html_text(label)}</span>{html_text(value)}</div>'
        for label, value in items
    )
    st.markdown(f'<div class="filter-pills">{pills}</div>', unsafe_allow_html=True)


def render_kpi_grid(items: list[dict[str, str]]) -> None:
    cards = []
    for item in items:
        delta = item.get("delta", "")
        tone = item.get("tone", "")
        tone_class = "kpi-card-internal" if tone == "internal" else "kpi-card-external" if tone == "external" else ""
        delta_tone = item.get("delta_tone", "")
        delta_tone_class = (
            " kpi-delta-positive"
            if delta_tone == "positive"
            else " kpi-delta-negative"
            if delta_tone == "negative"
            else ""
        )
        delta_html = f'<div class="kpi-delta{delta_tone_class}">{html_text(delta)}</div>' if delta else ""
        cards.append(
            '<div class="kpi-card {tone_class}"><div class="kpi-label">{label}</div>'
            '<div class="kpi-value">{value}</div>{delta}</div>'.format(
                tone_class=tone_class,
                label=html_text(item["label"]),
                value=html_text(item["value"]),
                delta=delta_html,
            )
        )
    st.markdown(f'<div class="kpi-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def metric_extreme(frame: pd.DataFrame, label_col: str, metric: str, ascending: bool) -> tuple[str, float] | None:
    if frame.empty or label_col not in frame or metric not in frame:
        return None
    working = frame.copy()
    working[metric] = _numeric_series(working, metric)
    working = working[working[metric].abs() > CHART_EPSILON]
    if working.empty:
        return None
    row = working.sort_values(metric, ascending=ascending).iloc[0]
    return str(row[label_col]), float(row[metric])


def render_decision_summary(
    current_month: str,
    prior_month: str,
    comparison_mode: str,
    current_mv: float,
    prior_mv: float,
    current_comp: float,
    asset_class_summary: pd.DataFrame,
    quality: dict[str, int],
) -> None:
    baseline = "年初" if comparison_mode == "年初以来" else snapshot_display_label(prior_month)
    period = "年初以来截至时点" if comparison_mode == "年初以来" else "本月截至时点"
    mv_delta = current_mv - prior_mv
    mv_direction = "增加" if mv_delta >= 0 else "减少"
    top_gain = metric_extreme(asset_class_summary, "asset_class", "comprehensive_income_mtd_current", False)
    top_drag = metric_extreme(asset_class_summary, "asset_class", "comprehensive_income_mtd_current", True)
    gain_text = "暂无明显收益来源"
    if top_gain is not None:
        gain_text = f"主要收益来源是 {top_gain[0]}，贡献 {amount(top_gain[1])}"
    drag_text = "未出现明显负贡献品种"
    if top_drag is not None and top_drag[1] < -CHART_EPSILON:
        drag_text = f"主要拖累是 {top_drag[0]}，贡献 {amount(top_drag[1])}"
    quality_count = sum(count for count in quality.values() if count > 0)
    quality_text = (
        f"有 {quality_count:,} 项质量提示需要核对"
        if quality_count
        else "当前未发现主要质量提示"
    )
    st.markdown(
        (
            '<p class="decision-summary">'
            f"{html_text(snapshot_display_label(current_month))} 全价市值 {html_text(amount(current_mv))}，"
            f"较 {html_text(baseline)} {html_text(mv_direction)} {html_text(amount(abs(mv_delta)))}；"
            f"{html_text(period)}综合收益 {html_text(amount(current_comp))}。"
            f"{html_text(gain_text)}；{html_text(drag_text)}；{html_text(quality_text)}。"
            "</p>"
        ),
        unsafe_allow_html=True,
    )


def render_action_cards() -> None:
    actions = [
        ("看收益来源", "先看哪些投资品种贡献了本期结果。", "#asset-class-overview"),
        ("追资产证据", "把收益贡献、拖累和规模变化落到单项资产。", "#asset-evidence"),
        ("核对数据质量", "优先处理未分配经理、异常收益率和负收益资产。", "#quality-checks"),
    ]
    cards = "".join(
        '<a class="action-card" href="{href}"><div class="action-title">{title}</div>'
        '<div class="action-copy">{copy}</div></a>'.format(
            href=html_text(href),
            title=html_text(title),
            copy=html_text(copy),
        )
        for title, copy, href in actions
    )
    st.markdown(f'<div class="action-grid">{cards}</div>', unsafe_allow_html=True)


def render_quality_signal(quality: dict[str, int]) -> None:
    cards = "".join(
        '<div class="quality-card {state}"><div class="quality-label">{label}</div>'
        '<div class="quality-value">{value}</div></div>'.format(
            state="hot" if count > 0 else "",
            label=html_text(label),
            value=html_text(f"{count:,}"),
        )
        for label, count in quality.items()
    )
    st.markdown(f'<div class="quality-grid">{cards}</div>', unsafe_allow_html=True)


def selected_label(value: str) -> str:
    return "全部" if value == ALL else value


def ordered_account_labels(labels: pd.Series | list[object], include_remaining: bool = True) -> list[str]:
    existing = [str(label) for label in labels if pd.notna(label)]
    seen: set[str] = set()
    ordered: list[str] = []

    def append(label: str) -> None:
        if label in existing and label not in seen:
            ordered.append(label)
            seen.add(label)

    for label in ACCOUNT_ORDER_PREFIX:
        append(label)

    perpetual = sorted([label for label in existing if "永续债" in label and label not in seen])
    remaining = sorted([label for label in existing if label not in seen and label not in perpetual])
    tail = remaining + perpetual if include_remaining else perpetual
    for label in tail:
        append(label)
    return ordered


def is_funding_asset_class(value: object) -> bool:
    return str(value).strip() in FUNDING_ASSET_CLASSES


def asset_class_theme(value: object) -> str:
    label = str(value).strip()
    if any(keyword in label for keyword in REAL_ESTATE_THEME_KEYWORDS):
        return "不动产"
    if any(keyword in label for keyword in EQUITY_THEME_KEYWORDS):
        return "股权"
    return "常规品种"


def enrich_asset_class_display(summary: pd.DataFrame) -> pd.DataFrame:
    enriched = summary.copy()
    if "asset_class" not in enriched:
        enriched["asset_theme"] = pd.Series(dtype=object)
        enriched["asset_class_display"] = pd.Series(dtype=object)
        return enriched

    enriched["asset_class"] = enriched["asset_class"].astype(str)
    enriched["asset_theme"] = enriched["asset_class"].map(asset_class_theme)
    enriched["asset_class_display"] = np.where(
        enriched["asset_theme"].isin(["股权", "不动产"]),
        enriched["asset_theme"] + "-" + enriched["asset_class"],
        enriched["asset_class"],
    )
    return enriched


def include_focus_asset_labels(
    summary: pd.DataFrame,
    labels: list[str],
    label_col: str = "asset_class_display",
    theme_col: str = "asset_theme",
) -> list[str]:
    ordered = list(labels)
    if summary.empty or label_col not in summary or theme_col not in summary:
        return ordered

    focus = summary[summary[theme_col].isin(["股权", "不动产"])].copy()
    if focus.empty:
        return ordered

    focus["_theme_order"] = focus[theme_col].map({"股权": 0, "不动产": 1}).fillna(9)
    if "full_market_value_current" in focus:
        focus["_focus_sort_value"] = _numeric_series(focus, "full_market_value_current").abs()
    else:
        focus["_focus_sort_value"] = 0.0
    for label in focus.sort_values(["_theme_order", "_focus_sort_value"], ascending=[True, False])[
        label_col
    ].tolist():
        text = str(label)
        if text not in ordered:
            ordered.append(text)
    return ordered


def show_block_note(text: str) -> None:
    st.caption(f"口径说明：{text}")


def reset_boolean_state_on_context(state_key: str, context: tuple[object, ...]) -> None:
    context_key = f"_{state_key}_context"
    if st.session_state.get(context_key) != context:
        st.session_state[context_key] = context
        st.session_state[state_key] = False


def income_chart_config(comparison_mode: str, title_prefix: str, title_suffix: str) -> tuple[str, str, str]:
    metric = "comprehensive_income_mtd_current"
    period = "年初以来" if comparison_mode == "年初以来" else "本月"
    return (
        metric,
        f"{title_prefix}{period}综合收益{title_suffix}",
        display_names_for_mode(comparison_mode)[metric],
    )


def section_anchor(anchor_id: str) -> None:
    st.markdown(f'<span id="{anchor_id}"></span>', unsafe_allow_html=True)


def sidebar_nav() -> None:
    st.markdown(
        """
        <div class="sidebar-nav-title">页面导航</div>
        <a class="sidebar-nav-button" href="#overview">总体表现</a>
        <a class="sidebar-nav-button" href="#charts-overview">图表总览</a>
        <a class="sidebar-nav-button" href="#asset-class-overview">投资品种图表/表格</a>
        <a class="sidebar-nav-button" href="#strategy-book-overview">委内/委外比较</a>
        <a class="sidebar-nav-button" href="#account-overview">账户层图表/表格</a>
        <a class="sidebar-nav-button" href="#duration-overview">账户久期</a>
        <a class="sidebar-nav-button" href="#account-class-breakdown">账户内品种拆解</a>
        <a class="sidebar-nav-button" href="#asset-evidence">资产证据</a>
        <a class="sidebar-nav-button" href="#quality-checks">数据质量</a>
        """,
        unsafe_allow_html=True,
    )


def quality_metrics(data: pd.DataFrame, current_month: str, comparison_mode: str) -> dict[str, int]:
    current = snapshot_slice(data, current_month)
    unassigned_manager = int((current["manager"] == "未分配/待确认").sum())
    missing_class = int((current["asset_class"] == "未分类/待确认").sum())
    capital_col = "avg_capital_ytd" if comparison_mode == "年初以来" else "avg_capital_mtd"
    finance_col = "finance_income_ytd" if comparison_mode == "年初以来" else "finance_income_mtd"
    comprehensive_col = "comprehensive_income_ytd" if comparison_mode == "年初以来" else "comprehensive_income_mtd"
    invalid_return_base = int(
        ((current[capital_col] <= RETURN_BASE_THRESHOLD)
        & ((current[finance_col] != 0) | (current[comprehensive_col] != 0))).sum()
    )
    negative_assets = int((current[comprehensive_col] < 0).sum())
    return {
        "未分配经理": unassigned_manager,
        "缺省分类": missing_class,
        "异常收益率": invalid_return_base,
        "负收益资产": negative_assets,
    }


def income_diff_breakdown(current_slice: pd.DataFrame, comparison_mode: str) -> pd.DataFrame:
    if comparison_mode == "年初以来":
        finance_col = "finance_income_ytd"
        comprehensive_col = "comprehensive_income_ytd"
        label = "年初以来"
        source_period = "本年以来"
    else:
        finance_col = "finance_income_mtd"
        comprehensive_col = "comprehensive_income_mtd"
        label = "本月"
        source_period = "本月以来"
    finance = float(current_slice[finance_col].sum())
    comprehensive = float(current_slice[comprehensive_col].sum())
    return pd.DataFrame(
        [
            {"项目": f"{label}综合收益", "金额(亿)": comprehensive, "说明": f"源表“综合收益（{source_period}）(亿)”逐行加总。"},
            {"项目": f"{label}财务收益", "金额(亿)": finance, "说明": f"源表“财务收益（{source_period}）(亿)”逐行加总。"},
            {"项目": "差异：综合收益 - 财务收益", "金额(亿)": comprehensive - finance, "说明": "用于观察公允价值、其他综合收益等非财务收益口径影响。"},
        ]
    )


def auto_summary(
    current_mv: float,
    prior_mv: float,
    finance: float,
    comprehensive: float,
    quality: dict[str, int],
    comparison_mode: str,
) -> str:
    delta = current_mv - prior_mv
    direction = "增加" if delta >= 0 else "减少"
    baseline = "年初" if comparison_mode == "年初以来" else "上月"
    period = "年初以来" if comparison_mode == "年初以来" else "本月"
    risk_items = [f"{name}{count}条" for name, count in quality.items() if count > 0]
    risk_text = "；".join(risk_items) if risk_items else "未发现主要数据质量提示"
    return (
        f"当前全价市值为 {amount(current_mv)}，较{baseline}{direction} {amount(abs(delta))}；"
        f"{period}财务收益为 {amount(finance)}，综合收益为 {amount(comprehensive)}。"
        f"数据质量提示：{risk_text}。"
    )


def render_quality_bar(quality: dict[str, int]) -> None:
    cols = st.columns(4)
    for col, (name, count) in zip(cols, quality.items()):
        col.metric(name, f"{count:,}")
    st.caption(
        "质量提示：未分配经理、缺省分类、异常收益率和负收益资产用于提示阅读风险，不代表数据错误；需要结合资产证据进一步核对。"
    )


def _numeric_series(frame: pd.DataFrame, metric: str) -> pd.Series:
    return pd.to_numeric(frame.get(metric, pd.Series(dtype=float)), errors="coerce").fillna(0.0)


def _has_chart_values(frame: pd.DataFrame, metric: str) -> bool:
    if frame.empty or metric not in frame:
        return False
    return bool((_numeric_series(frame, metric).abs() > CHART_EPSILON).any())


def top_bottom(frame: pd.DataFrame, metric: str, label_col: str, limit: int) -> pd.DataFrame:
    if frame.empty or metric not in frame or label_col not in frame:
        return pd.DataFrame(columns=frame.columns)

    working = frame.copy()
    working[metric] = _numeric_series(working, metric)
    working = working[working[metric].abs() > CHART_EPSILON]
    if working.empty:
        return working

    positive = working[working[metric] > 0].sort_values(metric, ascending=False).head(limit)
    negative = working[working[metric] < 0].sort_values(metric, ascending=True).head(limit)
    selected = pd.concat([positive, negative], ignore_index=True)
    return selected.drop_duplicates(subset=[label_col], keep="first")


def top_by_abs(frame: pd.DataFrame, metric: str, limit: int) -> pd.DataFrame:
    if frame.empty or metric not in frame:
        return pd.DataFrame(columns=frame.columns)

    working = frame.copy()
    working[metric] = _numeric_series(working, metric)
    working["_abs_metric"] = working[metric].abs()
    working = working[working["_abs_metric"] > CHART_EPSILON]
    return working.sort_values("_abs_metric", ascending=False).head(limit)


def shared_top_bottom_labels(
    frame: pd.DataFrame,
    primary_metric: str,
    secondary_metric: str,
    label_col: str,
    limit: int = 8,
    max_labels: int = 16,
) -> list[str]:
    if frame.empty or label_col not in frame:
        return []

    labels: list[str] = []

    def append_label(value: object) -> None:
        label = str(value)
        if label not in labels:
            labels.append(label)

    if primary_metric in frame:
        primary = top_bottom(frame, primary_metric, label_col, limit)
        for label in primary[label_col].tolist():
            append_label(label)

    if len(labels) >= max_labels or secondary_metric not in frame:
        return labels[:max_labels]

    secondary = top_bottom(frame, secondary_metric, label_col, limit).copy()
    if secondary.empty:
        return labels[:max_labels]

    secondary["_secondary_abs"] = _numeric_series(secondary, secondary_metric).abs()
    for label in secondary.sort_values("_secondary_abs", ascending=False)[label_col].tolist():
        append_label(label)
        if len(labels) >= max_labels:
            break

    return labels[:max_labels]


def _bar_height(row_count: int) -> int:
    return max(240, min(720, row_count * 36 + 120))


def render_bar_chart(
    frame: pd.DataFrame,
    metric: str,
    label_col: str,
    title: str,
    value_title: str,
    limit: int = 8,
    selection: str = "top_bottom",
    comparison_mode: str = "单月复盘",
    empty_message: str = "暂无可展示的图表数据。",
    label_order: list[str] | None = None,
    threshold_lines: list[dict[str, object]] | None = None,
    threshold_color_value: float | None = None,
    show_value_labels: bool = False,
) -> None:
    normalized_label_order = [str(label) for label in label_order or []]
    if normalized_label_order:
        chart_data = frame.copy()
        chart_data["_label_for_selection"] = chart_data[label_col].astype(str)
        chart_data = chart_data[chart_data["_label_for_selection"].isin(normalized_label_order)]
        order_map = {label: index for index, label in enumerate(normalized_label_order)}
        chart_data["_forced_order"] = chart_data["_label_for_selection"].map(order_map)
        chart_data = chart_data.sort_values("_forced_order")
    elif selection == "abs":
        chart_data = top_by_abs(frame, metric, limit)
    else:
        chart_data = top_bottom(frame, metric, label_col, limit)

    if not _has_chart_values(chart_data, metric):
        st.info(empty_message)
        return

    chart_data = chart_data.copy()
    chart_data["_label"] = chart_data[label_col].astype(str)
    chart_data["_value"] = _numeric_series(chart_data, metric)
    chart_data["_value_label"] = chart_data["_value"].map(
        lambda value: f"{value:.2%}" if metric in PCT_COLUMNS else f"{value:,.2f}"
    )
    chart_data["_is_funding_asset_class"] = False
    funding_label_col = "asset_class" if "asset_class" in chart_data.columns else label_col
    if label_col in {"asset_class", "asset_class_display"}:
        chart_data["_is_funding_asset_class"] = chart_data[funding_label_col].map(is_funding_asset_class)
        chart_data["_color_note"] = np.where(
            chart_data["_is_funding_asset_class"],
            "回购/融资科目：使用中性颜色",
            "按指标正负染色",
        )
    chart_data["_bar_color_group"] = np.select(
        [
            chart_data["_is_funding_asset_class"],
            chart_data["_value"] >= 0,
        ],
        [
            "回购/融资",
            "正向",
        ],
        default="负向",
    )
    color_domain = ["正向", "负向", "回购/融资"]
    color_range = [POSITIVE_COLOR, NEGATIVE_COLOR, FUNDING_COLOR]
    if threshold_color_value is not None:
        threshold = float(threshold_color_value)
        chart_data["_cost_rate_note"] = np.select(
            [
                chart_data["_is_funding_asset_class"],
                chart_data["_value"] < 0,
                chart_data["_value"] >= threshold,
            ],
            [
                "回购/融资科目",
                "低于成本率",
                "达到或超过成本率",
            ],
            default="低于成本率",
        )
        chart_data["_bar_color_group"] = np.select(
            [
                chart_data["_is_funding_asset_class"],
                chart_data["_value"] < 0,
                chart_data["_value"] >= threshold,
            ],
            [
                "回购/融资",
                "负向",
                "超过成本率",
            ],
            default="未超过成本率",
        )
        color_domain = ["超过成本率", "未超过成本率", "负向", "回购/融资"]
        color_range = [POSITIVE_COLOR, NEUTRAL_COLOR, NEGATIVE_COLOR, FUNDING_COLOR]
    if normalized_label_order:
        chart_data = chart_data.sort_values("_forced_order")
    else:
        chart_data = chart_data[chart_data["_value"].abs() > CHART_EPSILON]
        chart_data = chart_data.sort_values("_value", ascending=False)

    tooltips = [
        alt.Tooltip("_label:N", title=display_names_for_mode(comparison_mode).get(label_col, label_col)),
        alt.Tooltip("_value:Q", title=value_title, format=".2%" if metric in PCT_COLUMNS else ",.2f"),
    ]
    if label_col in {"asset_class", "asset_class_display"}:
        tooltips.append(alt.Tooltip("_color_note:N", title="颜色口径"))
    if threshold_color_value is not None and "_cost_rate_note" in chart_data.columns:
        tooltips.append(alt.Tooltip("_cost_rate_note:N", title="成本率判断"))
    for column in [
        "finance_income_mtd_current",
        "comprehensive_income_mtd_current",
        "finance_income_period",
        "comprehensive_income_period",
        "full_market_value_current",
        "full_market_value_delta",
        "net_full_market_value_delta",
        "avg_capital_mtd_current",
        "finance_return_mtd",
        "comprehensive_return_mtd",
    ]:
        if column not in chart_data.columns:
            continue
        if column == metric:
            continue
        chart_data[column] = pd.to_numeric(chart_data[column], errors="coerce")
        tooltip_title = display_names_for_mode(comparison_mode).get(column, column)
        tooltip_format = ".2%" if column in PCT_COLUMNS else ",.2f"
        tooltips.append(alt.Tooltip(f"{column}:Q", title=tooltip_title, format=tooltip_format))

    x_encoding = {
        "title": value_title,
        "axis": alt.Axis(format=".1%" if metric in PCT_COLUMNS else ",.1f"),
    }
    if show_value_labels and not chart_data.empty:
        min_value = float(chart_data["_value"].min())
        max_value = float(chart_data["_value"].max())
        domain_values = [min_value, max_value, 0.0]
        if threshold_lines:
            for threshold_line in threshold_lines:
                try:
                    domain_values.append(float(threshold_line.get("value", 0.0)))
                except (TypeError, ValueError):
                    continue
        min_domain = min(domain_values)
        max_domain = max(domain_values)
        span = max(max_domain - min_domain, max(abs(min_domain), abs(max_domain), 1.0) * 0.1)
        padding = span * 0.08
        if min_domain >= 0:
            x_encoding["scale"] = alt.Scale(domain=[0, max_domain + padding])
        elif max_domain <= 0:
            x_encoding["scale"] = alt.Scale(domain=[min_domain - padding, 0])
        else:
            x_encoding["scale"] = alt.Scale(domain=[min_domain - padding, max_domain + padding])

    y_encoding = alt.Y(
        "_label:N",
        title=None,
        sort=normalized_label_order or alt.SortField(field="_value", order="descending"),
        axis=alt.Axis(labelLimit=220),
    )

    bars = (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusEnd=2)
        .encode(
            x=alt.X("_value:Q", **x_encoding),
            y=y_encoding,
            color=alt.Color(
                "_bar_color_group:N",
                title=None,
                scale=alt.Scale(
                    domain=color_domain,
                    range=color_range,
                ),
                legend=None,
            ),
            tooltip=tooltips,
        )
    )
    zero_rule = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color="#475569", opacity=0.55).encode(x="x:Q")
    chart_layers = bars + zero_rule
    if threshold_lines:
        threshold_frame = pd.DataFrame(threshold_lines).copy()
        if not threshold_frame.empty and "value" in threshold_frame.columns:
            threshold_frame["value"] = pd.to_numeric(threshold_frame["value"], errors="coerce")
            threshold_frame = threshold_frame.dropna(subset=["value"])
            if not threshold_frame.empty:
                if "label" not in threshold_frame.columns:
                    threshold_frame["label"] = threshold_frame["value"].map(lambda value: f"{value:.2%}")
                if "color" not in threshold_frame.columns:
                    threshold_frame["color"] = "#C88439"
                threshold_frame["label"] = threshold_frame["label"].astype(str)
                threshold_frame["color"] = threshold_frame["color"].astype(str)
                threshold_rules = (
                    alt.Chart(threshold_frame)
                    .mark_rule(strokeWidth=1.1, strokeDash=[1, 8], opacity=0.32)
                    .encode(
                        x=alt.X("value:Q"),
                        color=alt.Color(
                            "label:N",
                            title=None,
                            scale=alt.Scale(
                                domain=threshold_frame["label"].tolist(),
                                range=threshold_frame["color"].tolist(),
                            ),
                            legend=alt.Legend(orient="top", symbolType="stroke"),
                        ),
                        tooltip=[
                            alt.Tooltip("label:N", title="成本率"),
                            alt.Tooltip("value:Q", title="成本率", format=".2%"),
                        ],
                    )
                )
                threshold_arrows = (
                    alt.Chart(threshold_frame)
                    .mark_text(
                        text="▼",
                        align="center",
                        baseline="bottom",
                        dy=-1,
                        color=POSITIVE_COLOR,
                        fontSize=15,
                        fontWeight=700,
                    )
                    .encode(
                        x=alt.X("value:Q"),
                        y=alt.value(4),
                        tooltip=[
                            alt.Tooltip("label:N", title="成本率"),
                            alt.Tooltip("value:Q", title="成本率", format=".2%"),
                        ],
                    )
                )
                chart_layers = chart_layers + threshold_rules + threshold_arrows
    if show_value_labels:
        positive_label_data = chart_data[chart_data["_value"] >= 0].copy()
        negative_label_data = chart_data[chart_data["_value"] < 0].copy()
        positive_value_labels = (
            alt.Chart(positive_label_data)
            .mark_text(
                align="left",
                baseline="middle",
                dx=7,
                color="#0D0707",
                fontSize=12,
                fontWeight=600,
            )
            .encode(
                x=alt.X("_value:Q", **x_encoding),
                y=y_encoding,
                text=alt.Text("_value_label:N"),
            )
        )
        negative_value_labels = (
            alt.Chart(negative_label_data)
            .mark_text(
                align="right",
                baseline="middle",
                dx=-7,
                color="#0D0707",
                fontSize=12,
                fontWeight=600,
            )
            .encode(
                x=alt.X("_value:Q", **x_encoding),
                y=y_encoding,
                text=alt.Text("_value_label:N"),
            )
        )
        chart_layers = chart_layers + positive_value_labels + negative_value_labels
    chart = (
        chart_layers
        .properties(title=title, height=_bar_height(len(chart_data)))
        .configure_view(strokeWidth=0)
        .configure_title(anchor="start", color=POSITIVE_COLOR, fontSize=15)
    )
    st.altair_chart(chart, width="stretch")


def _annualization_factor(snapshot_date: str) -> float:
    try:
        parsed = pd.Timestamp(snapshot_date)
    except (TypeError, ValueError):
        return 1.0
    days_in_year = 366 if parsed.is_leap_year else 365
    return days_in_year / max(1, parsed.dayofyear)


def _split_plan_asset_classes(value: object) -> list[str]:
    if pd.isna(value):
        return []
    return [item.strip() for item in str(value).split("|") if item.strip()]


def load_asset_return_plan(path: Path) -> tuple[pd.DataFrame, str | None]:
    required_columns = {
        "plan_asset",
        "display_order",
        "plan_balance",
        "target_return_mid",
        "target_return_low",
        "target_return_high",
        "mapped_asset_classes",
        "enabled",
    }
    if not path.exists():
        return pd.DataFrame(columns=sorted(required_columns)), f"未找到资产收益计划配置表：{path}"

    plan = pd.read_csv(path, encoding="utf-8-sig")
    missing_columns = sorted(required_columns - set(plan.columns))
    if missing_columns:
        return pd.DataFrame(columns=sorted(required_columns)), "资产收益计划配置表缺少字段：" + "、".join(missing_columns)

    plan = plan.copy()
    plan["enabled"] = plan["enabled"].astype(str).str.lower().isin({"1", "true", "yes", "y", "是"})
    plan = plan[plan["enabled"]].copy()
    for column in [
        "display_order",
        "plan_balance",
        "target_return_mid",
        "target_return_low",
        "target_return_high",
    ]:
        plan[column] = pd.to_numeric(plan[column], errors="coerce")
    plan = plan.dropna(subset=["plan_asset", "display_order", "target_return_low", "target_return_high"])
    return plan.sort_values("display_order"), None


def asset_return_completion_summary(data: pd.DataFrame, current_month: str, plan: pd.DataFrame) -> pd.DataFrame:
    if plan.empty:
        return pd.DataFrame()

    ytd_summary = ensure_summary_columns(
        comparison_summary(data, current_month, current_month, ["asset_class"], "年初以来"),
        "年初以来",
    )
    ytd_summary = ytd_summary.copy()
    ytd_summary["asset_class"] = ytd_summary["asset_class"].astype(str)
    annualization_factor = _annualization_factor(current_month)

    rows: list[dict[str, object]] = []
    for _, plan_row in plan.iterrows():
        mapped_classes = _split_plan_asset_classes(plan_row["mapped_asset_classes"])
        matched = ytd_summary[ytd_summary["asset_class"].isin(mapped_classes)]
        current_market_value = float(_numeric_series(matched, "full_market_value_current").sum())
        comprehensive_income = float(_numeric_series(matched, "comprehensive_income_mtd_current").sum())
        avg_capital = float(_numeric_series(matched, "avg_capital_mtd_current").sum())
        plan_balance = float(plan_row["plan_balance"]) if pd.notna(plan_row["plan_balance"]) else np.nan
        target_mid = float(plan_row["target_return_mid"]) if pd.notna(plan_row["target_return_mid"]) else np.nan
        planned_income = plan_balance * target_mid if np.isfinite(plan_balance) and np.isfinite(target_mid) else np.nan
        actual_ytd_income = comprehensive_income
        actual_annualized_income = comprehensive_income * annualization_factor
        income_gap = actual_ytd_income - planned_income if np.isfinite(planned_income) else np.nan
        income_completion_rate = (
            actual_ytd_income / planned_income
            if np.isfinite(planned_income) and abs(planned_income) > CHART_EPSILON
            else np.nan
        )
        allocation_gap = current_market_value - plan_balance if np.isfinite(plan_balance) else np.nan
        actual_ytd_return = np.nan
        if avg_capital > RETURN_BASE_THRESHOLD:
            actual_ytd_return = comprehensive_income / avg_capital
        actual_annualized_return = actual_ytd_return * annualization_factor if np.isfinite(actual_ytd_return) else np.nan
        target_low = float(plan_row["target_return_low"])
        target_high = float(plan_row["target_return_high"])
        if not np.isfinite(income_completion_rate):
            status = "无数据"
            status_color_group = "无数据"
        elif income_completion_rate >= 1:
            status = "完成"
            status_color_group = "完成"
        else:
            status = "未完成"
            status_color_group = "未完成"
        if not np.isfinite(actual_annualized_return):
            return_rate_status = "无数据"
            return_rate_color_group = "无数据"
            deviation = np.nan
        elif actual_annualized_return < target_low:
            return_rate_status = "低于目标"
            return_rate_color_group = "低于目标"
            deviation = actual_annualized_return - target_low
        elif actual_annualized_return > target_high:
            return_rate_status = "高于目标"
            return_rate_color_group = "高于目标"
            deviation = actual_annualized_return - target_high
        else:
            return_rate_status = "达标"
            return_rate_color_group = "达标"
            deviation = 0.0

        rows.append(
            {
                "plan_asset": str(plan_row["plan_asset"]),
                "display_order": int(plan_row["display_order"]),
                "plan_balance": plan_balance,
                "target_return_mid": target_mid,
                "target_return_low": target_low,
                "target_return_high": target_high,
                "target_return_range": f"{target_low:.1%}-{target_high:.1%}",
                "full_market_value_current": current_market_value,
                "comprehensive_income_mtd_current": comprehensive_income,
                "avg_capital_mtd_current": avg_capital,
                "actual_ytd_comprehensive_return": actual_ytd_return,
                "actual_annualized_comprehensive_return": actual_annualized_return,
                "planned_income": planned_income,
                "actual_ytd_income": actual_ytd_income,
                "actual_annualized_income": actual_annualized_income,
                "income_gap": income_gap,
                "income_completion_rate": income_completion_rate,
                "allocation_gap": allocation_gap,
                "return_completion_status": status,
                "_status_color_group": status_color_group,
                "return_rate_status": return_rate_status,
                "_return_rate_color_group": return_rate_color_group,
                "return_deviation": deviation,
                "mapped_asset_classes": "、".join(mapped_classes),
            }
        )

    return pd.DataFrame(rows).sort_values("display_order")


def render_asset_return_completion(data: pd.DataFrame, current_month: str) -> None:
    plan, plan_error = load_asset_return_plan(ASSET_RETURN_PLAN_PATH)
    if plan_error:
        st.warning(plan_error)
        return

    completion = asset_return_completion_summary(data, current_month, plan)
    if completion.empty:
        st.info("当前暂无可展示的资产收益完成情况。")
        return

    st.markdown("#### 资产收益金额完成情况")
    show_block_note(
        "本模块比较非年化收益金额，不以收益率是否达标作为主判断；当前收益金额使用年初以来综合收益额，"
        "右侧收益率图恢复上一版区间视图，点为YTD综合收益率按当前数据时点的年内已过天数年化后的结果，仅作辅助观察。"
    )

    total_planned_income = float(completion["planned_income"].sum())
    total_actual_income = float(completion["actual_ytd_income"].sum())
    total_income_gap = total_actual_income - total_planned_income
    total_completion_rate = (
        total_actual_income / total_planned_income
        if abs(total_planned_income) > CHART_EPSILON
        else np.nan
    )
    render_kpi_grid(
        [
            {"label": "年度计划综合收益", "value": amount(total_planned_income)},
            {"label": "当前YTD综合收益", "value": amount(total_actual_income)},
            {"label": "收益缺口/超额", "value": signed_amount(total_income_gap)},
            {"label": "收益金额完成率", "value": pct(total_completion_rate)},
        ]
    )

    asset_order = completion["plan_asset"].tolist()
    tooltip = [
        alt.Tooltip("plan_asset:N", title="计划资产项"),
        alt.Tooltip("planned_income:Q", title="年度计划综合收益(亿)", format=",.2f"),
        alt.Tooltip("actual_ytd_income:Q", title="当前YTD综合收益(亿)", format=",.2f"),
        alt.Tooltip("income_gap:Q", title="收益缺口/超额(亿)", format=",.2f"),
        alt.Tooltip("income_completion_rate:Q", title="收益金额完成率", format=".2%"),
        alt.Tooltip("return_completion_status:N", title="收益金额完成状态"),
        alt.Tooltip("actual_ytd_comprehensive_return:Q", title="当前YTD综合收益率", format=".2%"),
        alt.Tooltip("actual_annualized_comprehensive_return:Q", title="当前年化综合收益率", format=".2%"),
        alt.Tooltip("target_return_mid:Q", title="计划收益率中枢", format=".2%"),
        alt.Tooltip("target_return_range:N", title="目标收益率区间"),
        alt.Tooltip("target_return_low:Q", title="计划收益率下限", format=".2%"),
        alt.Tooltip("target_return_high:Q", title="计划收益率上限", format=".2%"),
        alt.Tooltip("comprehensive_income_mtd_current:Q", title="年初以来综合收益(亿)", format=",.2f"),
        alt.Tooltip("avg_capital_mtd_current:Q", title="年初以来平均资金占用(亿)", format=",.2f"),
        alt.Tooltip("full_market_value_current:Q", title="当前市值(亿)", format=",.2f"),
        alt.Tooltip("plan_balance:Q", title="计划余额(亿)", format=",.2f"),
        alt.Tooltip("allocation_gap:Q", title="配置差额(亿)", format=",.2f"),
        alt.Tooltip("mapped_asset_classes:N", title="映射投资品种"),
    ]
    planned_bars = (
        alt.Chart(completion)
        .mark_bar(size=24, color=NEUTRAL_COLOR, opacity=0.28, cornerRadiusEnd=3)
        .encode(
            x=alt.X("planned_income:Q", title="收益金额(亿)", axis=alt.Axis(format=",.0f")),
            y=alt.Y("plan_asset:N", title=None, sort=asset_order, axis=alt.Axis(labelLimit=180)),
            tooltip=tooltip,
        )
    )
    actual_bars = (
        alt.Chart(completion)
        .mark_bar(size=14, cornerRadiusEnd=3)
        .encode(
            x=alt.X("actual_ytd_income:Q", title="收益金额(亿)", axis=alt.Axis(format=",.0f")),
            y=alt.Y("plan_asset:N", sort=asset_order),
            color=alt.Color(
                "_status_color_group:N",
                title=None,
                scale=alt.Scale(
                    domain=["完成", "未完成", "无数据"],
                    range=[POSITIVE_COLOR, NEGATIVE_COLOR, NEUTRAL_COLOR],
                ),
                legend=alt.Legend(orient="top"),
            ),
            tooltip=tooltip,
        )
    )
    actual_labels = (
        alt.Chart(completion)
        .mark_text(align="left", dx=8, color="#475569", fontSize=11)
        .encode(
            x=alt.X("actual_ytd_income:Q"),
            y=alt.Y("plan_asset:N", sort=asset_order),
            text=alt.Text("actual_ytd_income:Q", format=",.1f"),
            tooltip=tooltip,
        )
    )
    zero_rule = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color="#475569", opacity=0.55).encode(x="x:Q")
    chart = (
        (planned_bars + actual_bars + actual_labels + zero_rule)
        .properties(title="计划资产项YTD收益金额完成情况", height=max(280, len(asset_order) * 42 + 80))
        .configure_view(strokeWidth=0)
        .configure_title(anchor="start", color=POSITIVE_COLOR, fontSize=15)
    )
    rate_tooltip = [
        alt.Tooltip("plan_asset:N", title="计划资产项"),
        alt.Tooltip("actual_ytd_comprehensive_return:Q", title="当前YTD综合收益率", format=".2%"),
        alt.Tooltip("actual_annualized_comprehensive_return:Q", title="当前年化综合收益率", format=".2%"),
        alt.Tooltip("target_return_mid:Q", title="计划收益率中枢", format=".2%"),
        alt.Tooltip("target_return_range:N", title="目标收益率区间"),
        alt.Tooltip("target_return_low:Q", title="计划收益率下限", format=".2%"),
        alt.Tooltip("target_return_high:Q", title="计划收益率上限", format=".2%"),
        alt.Tooltip("return_rate_status:N", title="收益率状态"),
        alt.Tooltip("return_deviation:Q", title="收益率偏离幅度", format=".2%"),
        alt.Tooltip("planned_income:Q", title="年度计划综合收益(亿)", format=",.2f"),
        alt.Tooltip("actual_ytd_income:Q", title="当前YTD综合收益(亿)", format=",.2f"),
        alt.Tooltip("income_completion_rate:Q", title="收益金额完成率", format=".2%"),
        alt.Tooltip("mapped_asset_classes:N", title="映射投资品种"),
    ]
    rate_ranges = (
        alt.Chart(completion)
        .mark_bar(size=16, color="#DCDACD", cornerRadius=4)
        .encode(
            x=alt.X("target_return_low:Q", title="收益率", axis=alt.Axis(format=".1%")),
            x2=alt.X2("target_return_high:Q"),
            y=alt.Y("plan_asset:N", title=None, sort=asset_order, axis=alt.Axis(labelLimit=180)),
            tooltip=rate_tooltip,
        )
    )
    rate_mid = (
        alt.Chart(completion)
        .mark_tick(thickness=2.5, size=28, color="#475569")
        .encode(
            x=alt.X("target_return_mid:Q"),
            y=alt.Y("plan_asset:N", sort=asset_order),
            tooltip=rate_tooltip,
        )
    )
    rate_point_data = completion.dropna(subset=["actual_annualized_comprehensive_return"]).copy()
    rate_points = (
        alt.Chart(rate_point_data)
        .mark_point(filled=True, size=95, stroke="#FFFFFF", strokeWidth=1.4)
        .encode(
            x=alt.X("actual_annualized_comprehensive_return:Q"),
            y=alt.Y("plan_asset:N", sort=asset_order),
            color=alt.Color(
                "_return_rate_color_group:N",
                title=None,
                scale=alt.Scale(
                    domain=["达标", "低于目标", "高于目标", "无数据"],
                    range=[POSITIVE_COLOR, NEGATIVE_COLOR, "#C88439", NEUTRAL_COLOR],
                ),
                legend=alt.Legend(orient="top"),
            ),
            tooltip=rate_tooltip,
        )
    )
    rate_labels = (
        alt.Chart(rate_point_data)
        .mark_text(align="left", dx=8, color="#475569", fontSize=11)
        .encode(
            x=alt.X("actual_annualized_comprehensive_return:Q"),
            y=alt.Y("plan_asset:N", sort=asset_order),
            text=alt.Text("actual_annualized_comprehensive_return:Q", format=".2%"),
            tooltip=rate_tooltip,
        )
    )
    rate_chart = (
        (rate_ranges + rate_mid + rate_points + rate_labels)
        .properties(title="计划资产项综合收益率完成情况", height=max(280, len(asset_order) * 42 + 80))
        .configure_view(strokeWidth=0)
        .configure_title(anchor="start", color=POSITIVE_COLOR, fontSize=15)
    )

    amount_chart_col, rate_chart_col = st.columns(2)
    with amount_chart_col:
        st.altair_chart(chart, width="stretch")
    with rate_chart_col:
        st.altair_chart(rate_chart, width="stretch")

    total_row = {
        "plan_asset": "合计",
        "full_market_value_current": completion["full_market_value_current"].sum(),
        "plan_balance": completion["plan_balance"].sum(),
        "allocation_gap": completion["allocation_gap"].sum(),
        "comprehensive_income_mtd_current": completion["comprehensive_income_mtd_current"].sum(),
        "planned_income": total_planned_income,
        "actual_ytd_income": total_actual_income,
        "income_gap": total_income_gap,
        "income_completion_rate": total_completion_rate,
        "actual_ytd_comprehensive_return": np.nan,
        "actual_annualized_comprehensive_return": np.nan,
        "target_return_mid": np.nan,
        "target_return_range": "",
        "return_rate_status": "",
        "return_deviation": np.nan,
        "return_completion_status": "完成" if total_completion_rate >= 1 else "未完成",
        "mapped_asset_classes": "",
    }
    table_display = pd.concat([completion, pd.DataFrame([total_row])], ignore_index=True)
    st.dataframe(
        format_table(
            table_display[
                [
                    "plan_asset",
                    "full_market_value_current",
                    "plan_balance",
                    "allocation_gap",
                    "planned_income",
                    "actual_ytd_income",
                    "income_gap",
                    "income_completion_rate",
                    "actual_ytd_comprehensive_return",
                    "actual_annualized_comprehensive_return",
                    "target_return_mid",
                    "target_return_range",
                    "return_rate_status",
                    "return_deviation",
                    "return_completion_status",
                    "mapped_asset_classes",
                ]
            ],
            comparison_mode="年初以来",
        ),
        width="stretch",
        hide_index=True,
    )


def asset_evidence_sort_options(comparison_mode: str) -> list[str]:
    if comparison_mode == "年初以来":
        return [ALL, "收益贡献", "收益拖累", "规模增加", "规模减少", "年初持仓变化"]
    return [ALL, "收益贡献", "收益拖累", "规模增加", "规模减少", "新增退出"]


def sort_asset_evidence(evidence: pd.DataFrame, sort_choice: str, comparison_mode: str) -> pd.DataFrame:
    if evidence.empty:
        return evidence
    if sort_choice == ALL:
        return evidence.sort_values("full_market_value_current", ascending=False)
    if sort_choice == "收益贡献":
        return evidence.sort_values("comprehensive_income_mtd_current", ascending=False)
    if sort_choice == "收益拖累":
        return evidence.sort_values("comprehensive_income_mtd_current", ascending=True)
    if sort_choice == "规模增加":
        return evidence.sort_values("full_market_value_delta", ascending=False)
    if sort_choice == "规模减少":
        return evidence.sort_values("full_market_value_delta", ascending=True)

    if comparison_mode == "年初以来":
        order = {
            "年初无持仓、本月有持仓": 0,
            "年初有持仓、本月无持仓": 1,
            "较年初增加": 2,
            "较年初减少": 3,
            "较年初持平": 4,
        }
    else:
        order = {"新增": 0, "退出": 1, "存续增加": 2, "存续减少": 3}
    return evidence.assign(_order=evidence["change_type"].map(order).fillna(9)).sort_values(
        ["_order", "full_market_value_delta"],
        ascending=[True, False],
    )


def asset_evidence_value_columns(comparison_mode: str) -> list[str]:
    columns = [
        "full_market_value_prior",
        "full_market_value_current",
        "avg_capital_mtd_current",
        "finance_income_mtd_current",
        "comprehensive_income_mtd_current",
    ]
    if comparison_mode == "年初以来":
        columns.extend(
            [
                "ytd_position_flow_delta",
                "full_market_value_delta",
                "monthly_position_flow_delta",
            ]
        )
    else:
        columns.extend(
            [
                "full_market_value_delta",
                "monthly_position_flow_delta",
            ]
        )
    columns.extend(["finance_return_mtd", "comprehensive_return_mtd"])
    return columns


def render_outsourced_equity_evidence(
    data: pd.DataFrame,
    current_month: str,
    prior_month: str,
    comparison_mode: str,
) -> None:
    st.markdown("#### 委外权益持仓（资产证据口径）")
    show_block_note(
        "本表先按现有委外分类扫描账户，再只保留权益资产分类；"
        "现金、存款、货币基金、债券、固收基金、应收、费用和轧差项不进入本表。"
    )

    relevant_snapshots = {current_month, prior_month}
    snapshot_key = "snapshot_date" if "snapshot_date" in data.columns else "snapshot_month"
    relevant_data = data[data[snapshot_key].isin(relevant_snapshots)]
    outsourced_equity = outsourced_equity_holding_slice(relevant_data)
    if outsourced_equity.empty:
        st.info("当前没有可展示的委外权益持仓。")
        return

    group_cols = ["strategy_book", "strategy_book_display_label", "outsourced_equity_holding_type"]
    if comparison_mode == "年初以来":
        evidence = asset_evidence_year_open(
            outsourced_equity,
            current_month,
            extra_group_cols=group_cols,
            prior_month=prior_month,
        )
    else:
        evidence = asset_evidence(
            outsourced_equity,
            current_month,
            prior_month,
            extra_group_cols=group_cols,
        )

    company_options = [ALL] + [f"委外-{label}" for label in EXTERNAL_STRATEGY_BOOK_ORDER]
    equity_type_options = [ALL] + OUTSOURCED_EQUITY_HOLDING_TYPE_ORDER
    control_cols = st.columns([0.24, 0.22, 0.54])
    with control_cols[0]:
        selected_company = st.selectbox("委外公司", company_options, key="委外权益公司")
    with control_cols[1]:
        selected_equity_type = st.selectbox("权益类型", equity_type_options, key="委外权益类型")
    with control_cols[2]:
        sort_choice = st.radio(
            "委外权益资产证据视角",
            asset_evidence_sort_options(comparison_mode),
            horizontal=True,
            key="委外权益资产证据视角",
        )

    if selected_company != ALL:
        evidence = evidence[evidence["strategy_book_display_label"].eq(selected_company)]
    if selected_equity_type != ALL:
        evidence = evidence[evidence["outsourced_equity_holding_type"].eq(selected_equity_type)]
    if evidence.empty:
        st.info("当前筛选条件下没有可展示的委外权益持仓。")
        return

    evidence = sort_asset_evidence(evidence, sort_choice, comparison_mode)
    show_all_evidence = False
    if len(evidence) > 500:
        show_all_key = "加载全部委外权益明细"
        reset_boolean_state_on_context(
            show_all_key,
            (
                current_month,
                prior_month,
                comparison_mode,
                selected_company,
                selected_equity_type,
                sort_choice,
            ),
        )
        show_all_evidence = st.toggle(
            f"加载全部委外权益明细（{len(evidence):,} 条）",
            key=show_all_key,
        )
    display_evidence = evidence if show_all_evidence else evidence.head(500)
    current_value = float(pd.to_numeric(evidence["full_market_value_current"], errors="coerce").fillna(0.0).sum())
    current_rows = int(pd.to_numeric(evidence["source_rows_current"], errors="coerce").fillna(0).sum())
    st.caption(f"当前筛选后委外权益持仓市值 {amount(current_value)}，共 {current_rows:,} 条源记录。")
    st.dataframe(
        format_table(
            display_evidence[
                [
                    "strategy_book_display_label",
                    "outsourced_equity_holding_type",
                    "change_type",
                    "asset_name",
                    "asset_code",
                    "trade_code",
                    "account_bucket",
                    "asset_class",
                    "manager",
                    *asset_evidence_value_columns(comparison_mode),
                    "source_rows_current",
                    "source_rows_prior",
                ]
            ],
            comparison_mode=comparison_mode,
        ),
        width="stretch",
        hide_index=True,
    )


def render_strategy_book_overview(
    data: pd.DataFrame,
    current_month: str,
    prior_month: str,
    comparison_mode: str,
) -> None:
    summary = strategy_book_summary(data, current_month, comparison_mode)
    detail = strategy_book_detail_summary(data, current_month, comparison_mode)

    if summary.empty or summary["record_count_current"].sum() == 0:
        st.info("当前没有可展示的委内/委外比较数据。")
        return

    render_kpi_grid(
        [
            {
                "label": str(row["strategy_book_display_label"]),
                "value": amount(float(row["full_market_value_current"])),
                "delta": pct(float(row["comprehensive_return_mtd"])),
                "delta_tone": "positive" if float(row["comprehensive_return_mtd"]) >= 0 else "negative",
                "tone": "internal" if row["strategy_book_scope"] == "委内" else "external",
            }
            for _, row in summary.iterrows()
        ]
    )

    chart_cols = st.columns(2)
    with chart_cols[0]:
        render_bar_chart(
            summary,
            "full_market_value_current",
            "strategy_book_display_label",
            "委内/委外分类市值",
            display_names_for_mode(comparison_mode)["full_market_value_current"],
            limit=len(STRATEGY_BOOK_LABEL_ORDER),
            label_order=STRATEGY_BOOK_LABEL_ORDER,
            comparison_mode=comparison_mode,
            empty_message="当前委内/委外分类暂无可展示的市值。",
            show_value_labels=True,
        )
    with chart_cols[1]:
        render_bar_chart(
            summary,
            "comprehensive_return_mtd",
            "strategy_book_display_label",
            "委内/委外分类综合收益率",
            display_names_for_mode(comparison_mode)["comprehensive_return_mtd"],
            limit=len(STRATEGY_BOOK_LABEL_ORDER),
            label_order=STRATEGY_BOOK_LABEL_ORDER,
            comparison_mode=comparison_mode,
            empty_message="当前委内/委外分类暂无可展示的收益率。",
            show_value_labels=True,
        )

    external_summary = summary[summary["strategy_book_scope"].eq("委外")].copy()
    external_label_order = [label for label in STRATEGY_BOOK_LABEL_ORDER if label.startswith("委外-")]
    if not external_summary.empty and external_summary["record_count_current"].sum() > 0:
        st.caption("委外账户单独放大展示，避免 5 亿级别账户在全量市值图中被委内大类压缩。")
        external_chart_cols = st.columns(2)
        with external_chart_cols[0]:
            render_bar_chart(
                external_summary,
                "full_market_value_current",
                "strategy_book_display_label",
                "委外账户市值（放大）",
                display_names_for_mode(comparison_mode)["full_market_value_current"],
                limit=len(external_label_order),
                label_order=external_label_order,
                comparison_mode=comparison_mode,
                empty_message="当前委外账户暂无可展示的市值。",
                show_value_labels=True,
            )
        with external_chart_cols[1]:
            render_bar_chart(
                external_summary,
                "comprehensive_income_mtd_current",
                "strategy_book_display_label",
                "委外账户综合收益额（放大）",
                display_names_for_mode(comparison_mode)["comprehensive_income_mtd_current"],
                limit=len(external_label_order),
                label_order=external_label_order,
                comparison_mode=comparison_mode,
                empty_message="当前委外账户暂无可展示的收益额。",
                show_value_labels=True,
            )

    if not detail.empty:
        st.dataframe(
            format_table(
                detail[
                    [
                        "strategy_book_scope",
                        "strategy_book",
                        "strategy_book_section",
                        "strategy_book_item",
                        "full_market_value_current",
                        "finance_income_mtd_current",
                        "comprehensive_income_mtd_current",
                        "avg_capital_mtd_current",
                        "finance_return_mtd",
                        "comprehensive_return_mtd",
                        "record_count_current",
                    ]
                ],
                comparison_mode=comparison_mode,
            ),
            width="stretch",
            hide_index=True,
        )

    render_outsourced_equity_evidence(data, current_month, prior_month, comparison_mode)

    excluded = excluded_strategy_book_detail(data, current_month, comparison_mode)
    if excluded.empty:
        return

    excluded_market_value = float(pd.to_numeric(excluded["full_market_value_current"], errors="coerce").fillna(0.0).sum())
    excluded_rows = int(pd.to_numeric(excluded["record_count_current"], errors="coerce").fillna(0).sum())
    st.caption(
        f"未纳入委内/委外比较净市值 {amount(excluded_market_value)}，共 {excluded_rows:,} 条；"
        "主要承接委内流动性、现金、买入返售、应收、费用、长股投、直投股权、不动产，"
        "以及富国顶层产品汇总行等对账项。"
    )
    reason_totals = (
        excluded.assign(
            _market_value=pd.to_numeric(excluded["full_market_value_current"], errors="coerce").fillna(0.0)
        )
        .groupby("strategy_book_exclusion_reason", dropna=False)["_market_value"]
        .sum()
        .reset_index()
    )
    if not reason_totals.empty:
        reason_totals["_abs_market_value"] = reason_totals["_market_value"].abs()
        reason_text = "；".join(
            f"{row['strategy_book_exclusion_reason']} {amount(float(row['_market_value']))}"
            for _, row in reason_totals.sort_values("_abs_market_value", ascending=False).head(4).iterrows()
        )
        st.caption(f"未纳入原因摘要：{reason_text}。")
    with st.expander("未纳入委内/委外比较对账明细", expanded=False):
        st.dataframe(
            format_table(
                excluded[
                    [
                        "strategy_book_exclusion_reason",
                        "mandate_type",
                        "fund_book_name",
                        "asset_major_class",
                        "trade_strategy",
                        "asset_class_level_1",
                        "asset_class_level_2",
                        "asset_class",
                        "full_market_value_current",
                        "finance_income_mtd_current",
                        "comprehensive_income_mtd_current",
                        "avg_capital_mtd_current",
                        "record_count_current",
                    ]
                ].head(100),
                comparison_mode=comparison_mode,
            ),
            width="stretch",
            hide_index=True,
        )


def account_duration_summary(data: pd.DataFrame, current_month: str) -> pd.DataFrame:
    columns = [
        "account_bucket",
        "weighted_duration",
        "duration_market_value",
        "duration_coverage_ratio",
        "duration_asset_count",
        "full_market_value_current",
    ]
    if data.empty or "duration" not in data.columns:
        return pd.DataFrame(columns=columns)

    current = snapshot_slice(data, current_month).copy()
    if current.empty:
        return pd.DataFrame(columns=columns)

    current["duration"] = pd.to_numeric(current["duration"], errors="coerce")
    current["full_market_value"] = pd.to_numeric(current["full_market_value"], errors="coerce").fillna(0.0)
    valid = (current["duration"] > CHART_EPSILON) & (current["full_market_value"] > CHART_EPSILON)
    current["_positive_market_value"] = current["full_market_value"].clip(lower=0.0)
    current["_duration_market_value"] = np.where(valid, current["full_market_value"], 0.0)
    current["_duration_weighted_sum"] = np.where(
        valid,
        current["duration"] * current["full_market_value"],
        0.0,
    )
    current["_duration_asset_count"] = valid.astype(int)

    summary = (
        current.groupby("account_bucket", dropna=False)
        .agg(
            full_market_value_current=("full_market_value", "sum"),
            positive_market_value=("_positive_market_value", "sum"),
            duration_market_value=("_duration_market_value", "sum"),
            duration_weighted_sum=("_duration_weighted_sum", "sum"),
            duration_asset_count=("_duration_asset_count", "sum"),
        )
        .reset_index()
    )
    summary["weighted_duration"] = np.where(
        summary["duration_market_value"].abs() > CHART_EPSILON,
        summary["duration_weighted_sum"] / summary["duration_market_value"],
        np.nan,
    )
    summary["duration_coverage_ratio"] = np.where(
        summary["positive_market_value"].abs() > CHART_EPSILON,
        summary["duration_market_value"] / summary["positive_market_value"],
        np.nan,
    )
    return summary[columns]


def render_duration_chart(duration_summary: pd.DataFrame, comparison_mode: str) -> None:
    if duration_summary.empty or "weighted_duration" not in duration_summary:
        st.info("当前源数据没有可展示的久期字段。")
        return

    chart_data = duration_summary.copy()
    chart_data["weighted_duration"] = pd.to_numeric(chart_data["weighted_duration"], errors="coerce")
    chart_data = chart_data[chart_data["weighted_duration"].notna()]
    if chart_data.empty:
        st.info("当前账户暂无可展示的有效久期。")
        return

    account_order = ordered_account_labels(chart_data["account_bucket"].tolist())
    chart_data["account_bucket"] = chart_data["account_bucket"].astype(str)
    chart_data["_duration_label"] = chart_data["weighted_duration"].map(lambda value: f"{value:,.2f}")
    max_duration = max(float(chart_data["weighted_duration"].max()), 1.0)
    tooltips = [
        alt.Tooltip("account_bucket:N", title="账户"),
        alt.Tooltip("weighted_duration:Q", title="账户加权久期", format=",.2f"),
        alt.Tooltip("duration_market_value:Q", title="纳入久期计算市值(亿)", format=",.2f"),
        alt.Tooltip("duration_coverage_ratio:Q", title="久期市值覆盖率", format=".2%"),
        alt.Tooltip(
            "full_market_value_current:Q",
            title=display_names_for_mode(comparison_mode)["full_market_value_current"],
            format=",.2f",
        ),
        alt.Tooltip("duration_asset_count:Q", title="纳入久期资产数", format=",.0f"),
    ]
    x_duration = alt.X(
        "weighted_duration:Q",
        title="账户加权久期",
        axis=alt.Axis(format=",.1f"),
        scale=alt.Scale(domain=[0, max_duration * 1.08]),
    )
    y_duration = alt.Y(
        "account_bucket:N",
        title=None,
        sort=account_order,
        axis=alt.Axis(labelLimit=180),
    )
    bars = (
        alt.Chart(chart_data)
        .mark_bar(color=POSITIVE_COLOR, cornerRadiusEnd=2)
        .encode(
            x=x_duration,
            y=y_duration,
            tooltip=tooltips,
        )
    )
    value_labels = (
        alt.Chart(chart_data)
        .mark_text(align="left", baseline="middle", dx=5, color="#475569", fontSize=11)
        .encode(
            x=x_duration,
            y=y_duration,
            text=alt.Text("_duration_label:N"),
        )
    )
    chart = (
        (bars + value_labels)
        .properties(title="账户加权久期", height=_bar_height(len(chart_data)))
        .configure_view(strokeWidth=0)
        .configure_title(anchor="start", color=POSITIVE_COLOR, fontSize=15)
    )
    st.altair_chart(chart, width="stretch")


def render_monthly_trends(data: pd.DataFrame, comparison_mode: str) -> None:
    if data.empty:
        st.info("暂无可展示的数据时点趋势。")
        return

    working = data.copy()
    working["_asset_class"] = working["asset_class"].astype(str)
    working["_repo_financing"] = np.where(
        working["_asset_class"].isin(REPO_FINANCING_ASSET_CLASSES),
        pd.to_numeric(working["full_market_value"], errors="coerce").fillna(0.0).abs(),
        0.0,
    )
    working["_reverse_repo"] = np.where(
        working["_asset_class"].isin(REVERSE_REPO_ASSET_CLASSES),
        pd.to_numeric(working["full_market_value"], errors="coerce").fillna(0.0).abs(),
        0.0,
    )

    monthly = (
        working.groupby("snapshot_date", dropna=False)
        .agg(
            full_market_value=("full_market_value", "sum"),
            finance_income_mtd=("finance_income_mtd", "sum"),
            comprehensive_income_mtd=("comprehensive_income_mtd", "sum"),
            finance_income_ytd=("finance_income_ytd", "sum"),
            comprehensive_income_ytd=("comprehensive_income_ytd", "sum"),
            repo_financing=("_repo_financing", "sum"),
            reverse_repo=("_reverse_repo", "sum"),
        )
        .reset_index()
        .sort_values("snapshot_date")
    )
    if monthly.empty:
        st.info("暂无可展示的数据时点趋势。")
        return

    monthly["net_repo_financing"] = monthly["repo_financing"] - monthly["reverse_repo"]
    monthly["repo_financing_ratio"] = (
        monthly["repo_financing"] / monthly["full_market_value"].replace(0.0, np.nan)
    )
    month_order = monthly["snapshot_date"].astype(str).tolist()
    market_min = float(monthly["full_market_value"].min())
    market_max = float(monthly["full_market_value"].max())
    market_padding = max((market_max - market_min) * 0.25, market_max * 0.004)
    market_baseline = max(0.0, market_min - market_padding)
    monthly["market_baseline"] = market_baseline

    scale_tooltip = [
        alt.Tooltip("snapshot_date:N", title="数据时点"),
        alt.Tooltip("full_market_value:Q", title="全价市值(亿)", format=",.2f"),
        alt.Tooltip("repo_financing:Q", title="正回购融资余额(亿)", format=",.2f"),
        alt.Tooltip("repo_financing_ratio:Q", title="正回购融资/全价市值", format=".2%"),
        alt.Tooltip("reverse_repo:Q", title="买入返售/逆回购余额(亿)", format=",.2f"),
        alt.Tooltip("net_repo_financing:Q", title="净回购融资余额(亿)", format=",.2f"),
    ]
    scale_bars = (
        alt.Chart(monthly)
        .mark_bar(color=POSITIVE_COLOR, cornerRadiusTopLeft=4, cornerRadiusTopRight=4, width=44)
        .encode(
            x=alt.X(
                "snapshot_date:N",
                title=None,
                sort=month_order,
                axis=alt.Axis(labelAngle=0),
            ),
            y=alt.Y(
                "full_market_value:Q",
                title="全价市值(亿)",
                scale=alt.Scale(domain=[market_baseline, market_max + market_padding]),
            ),
            y2="market_baseline:Q",
            tooltip=scale_tooltip,
        )
    )
    scale_labels = (
        alt.Chart(monthly)
        .mark_text(dy=-8, color=POSITIVE_COLOR, fontWeight=600)
        .encode(
            x=alt.X("snapshot_date:N", sort=month_order),
            y=alt.Y(
                "full_market_value:Q",
                axis=None,
                scale=alt.Scale(domain=[market_baseline, market_max + market_padding]),
            ),
            text=alt.Text("full_market_value:Q", format=",.0f"),
            tooltip=scale_tooltip,
        )
    )
    repo_line = (
        alt.Chart(monthly)
        .mark_line(color=NEGATIVE_COLOR, point=alt.OverlayMarkDef(color=NEGATIVE_COLOR, size=70), strokeWidth=2.5)
        .encode(
            x=alt.X("snapshot_date:N", title=None, sort=month_order, axis=alt.Axis(labelAngle=0)),
            y=alt.Y(
                "repo_financing:Q",
                title=None,
                axis=alt.Axis(labels=False, ticks=False, domain=False, title=None),
                scale=alt.Scale(zero=False),
            ),
            tooltip=scale_tooltip,
        )
    )
    repo_labels = (
        alt.Chart(monthly)
        .mark_text(dy=-12, color=NEGATIVE_COLOR, fontWeight=600)
        .encode(
            x=alt.X("snapshot_date:N", sort=month_order),
            y=alt.Y(
                "repo_financing:Q",
                axis=None,
                scale=alt.Scale(zero=False),
            ),
            text=alt.Text("repo_financing:Q", format=",.0f"),
            tooltip=scale_tooltip,
        )
    )
    scale_chart = (
        alt.layer(scale_bars, scale_labels, repo_line, repo_labels)
        .resolve_scale(y="independent")
        .properties(title="规模与正回购融资余额", height=300)
        .configure_view(strokeWidth=0)
        .configure_title(anchor="start", color=POSITIVE_COLOR, fontSize=15)
    )

    mtd_label_finance = "当月财务收益"
    mtd_label_comprehensive = "当月综合收益"
    ytd_label_finance = "年初以来财务收益"
    ytd_label_comprehensive = "年初以来综合收益"
    income_bar_long = monthly.melt(
        id_vars=["snapshot_date"],
        value_vars=["finance_income_mtd", "comprehensive_income_mtd"],
        var_name="income_type",
        value_name="income_value",
    )
    income_bar_long["income_type"] = income_bar_long["income_type"].map(
        {
            "finance_income_mtd": mtd_label_finance,
            "comprehensive_income_mtd": mtd_label_comprehensive,
        }
    )
    income_point_long = monthly.melt(
        id_vars=["snapshot_date"],
        value_vars=["finance_income_ytd", "comprehensive_income_ytd"],
        var_name="income_type",
        value_name="income_value",
    )
    income_point_long["income_type"] = income_point_long["income_type"].map(
        {
            "finance_income_ytd": ytd_label_finance,
            "comprehensive_income_ytd": ytd_label_comprehensive,
        }
    )
    income_point_long["offset_type"] = income_point_long["income_type"].map(
        {
            ytd_label_finance: mtd_label_finance,
            ytd_label_comprehensive: mtd_label_comprehensive,
        }
    )
    income_domain = [
        mtd_label_finance,
        mtd_label_comprehensive,
        ytd_label_finance,
        ytd_label_comprehensive,
    ]
    income_colors = [NEUTRAL_COLOR, POSITIVE_COLOR, "#C88439", "#0F6F3F"]
    income_tooltip = [
        alt.Tooltip("snapshot_date:N", title="数据时点"),
        alt.Tooltip("income_type:N", title="收益口径"),
        alt.Tooltip("income_value:Q", title="收益(亿)", format=",.2f"),
    ]
    income_bars = (
        alt.Chart(income_bar_long)
        .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=alt.X("snapshot_date:N", title=None, sort=month_order, axis=alt.Axis(labelAngle=0)),
            xOffset=alt.XOffset("income_type:N", sort=[mtd_label_finance, mtd_label_comprehensive]),
            y=alt.Y("income_value:Q", title="收益(亿)"),
            color=alt.Color(
                "income_type:N",
                title=None,
                scale=alt.Scale(domain=income_domain, range=income_colors),
                legend=alt.Legend(orient="top", columns=2),
            ),
            tooltip=income_tooltip,
        )
    )
    income_lines = (
        alt.Chart(income_point_long)
        .mark_line(strokeWidth=2.4, opacity=0.9)
        .encode(
            x=alt.X("snapshot_date:N", title=None, sort=month_order, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("income_value:Q", title="收益(亿)"),
            color=alt.Color(
                "income_type:N",
                title=None,
                scale=alt.Scale(domain=income_domain, range=income_colors),
                legend=alt.Legend(orient="top", columns=2),
            ),
            detail=alt.Detail("income_type:N"),
            tooltip=income_tooltip,
        )
    )
    income_points = (
        alt.Chart(income_point_long)
        .mark_point(filled=True, size=100, stroke="white", strokeWidth=1.4)
        .encode(
            x=alt.X("snapshot_date:N", title=None, sort=month_order, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("income_value:Q", title="收益(亿)"),
            color=alt.Color(
                "income_type:N",
                title=None,
                scale=alt.Scale(domain=income_domain, range=income_colors),
                legend=alt.Legend(orient="top", columns=2),
            ),
            tooltip=income_tooltip,
        )
    )
    zero_rule = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color="#475569", opacity=0.45).encode(y="y:Q")
    income_chart = (
        (income_bars + income_lines + income_points + zero_rule)
        .properties(title="收益趋势：当月截至数据时点 + 年初以来累计趋势", height=300)
        .configure_view(strokeWidth=0)
        .configure_title(anchor="start", color=POSITIVE_COLOR, fontSize=15)
    )

    trend_cols = st.columns([0.9, 1.1])
    trend_cols[0].altair_chart(scale_chart, width="stretch")
    trend_cols[1].altair_chart(income_chart, width="stretch")


def render_heatmap(class_summary: pd.DataFrame, selected_account: str, comparison_mode: str) -> None:
    metric = "comprehensive_income_mtd_current"
    value_title = display_names_for_mode(comparison_mode)[metric]
    return_metric = "comprehensive_return_mtd"
    return_title = display_names_for_mode(comparison_mode)[return_metric]
    if selected_account != ALL:
        render_bar_chart(
            class_summary,
            metric,
            "asset_class",
            f"{selected_label(selected_account)}：投资品种综合收益贡献",
            value_title,
            limit=12,
            selection="abs",
            comparison_mode=comparison_mode,
            empty_message="当前账户暂无可展示的投资品种收益贡献。",
        )
        return

    if not _has_chart_values(class_summary, metric):
        st.info("暂无可展示的账户 × 投资品种收益热力图。")
        return

    working = class_summary.copy()
    working[metric] = _numeric_series(working, metric)
    working = working[working[metric].abs() > CHART_EPSILON]
    account_order = (
        working.groupby("account_bucket")[metric]
        .sum()
        .abs()
        .sort_values(ascending=False)
        .head(10)
        .index.astype(str)
        .tolist()
    )
    class_order = (
        working.groupby("asset_class")[metric]
        .sum()
        .abs()
        .sort_values(ascending=False)
        .head(12)
        .index.astype(str)
        .tolist()
    )
    chart_data = working[
        working["account_bucket"].astype(str).isin(account_order)
        & working["asset_class"].astype(str).isin(class_order)
    ].copy()
    chart_data["account_bucket"] = chart_data["account_bucket"].astype(str)
    chart_data["asset_class"] = chart_data["asset_class"].astype(str)
    chart_data["_is_funding_asset_class"] = chart_data["asset_class"].map(is_funding_asset_class)
    chart_data[return_metric] = pd.to_numeric(chart_data[return_metric], errors="coerce")
    chart_data["_color_note"] = np.where(
        chart_data["_is_funding_asset_class"],
        "回购/融资科目：使用中性颜色",
        "按排名强度染色，真实值见 tooltip",
    )
    chart_data["full_market_value_current"] = pd.to_numeric(
        chart_data["full_market_value_current"],
        errors="coerce",
    )
    chart_data["_amount_value"] = pd.to_numeric(chart_data[metric], errors="coerce")
    chart_data["_return_value"] = pd.to_numeric(chart_data[return_metric], errors="coerce")

    def absolute_rank_percentile(value_col: str) -> pd.Series:
        values = pd.to_numeric(chart_data[value_col], errors="coerce")
        valid = (
            ~chart_data["_is_funding_asset_class"]
            & values.notna()
            & (values.abs() > CHART_EPSILON)
        )
        ranks = pd.Series(np.nan, index=chart_data.index, dtype=float)
        ranks.loc[valid] = values.loc[valid].abs().rank(method="average", pct=True)
        return ranks

    amount_rank = absolute_rank_percentile("_amount_value")
    return_rank = absolute_rank_percentile("_return_value")
    amount_sign = np.sign(chart_data["_amount_value"].fillna(0.0))
    return_sign = np.sign(chart_data["_return_value"].fillna(0.0))
    amount_weight = np.sqrt(amount_rank.fillna(0.0))
    chart_data["_amount_rank_score"] = amount_sign * amount_rank
    chart_data["_return_weighted_score"] = return_sign * return_rank * amount_weight

    heatmap_height = max(300, min(620, len(class_order) * 34 + 80))

    def heatmap_chart(score_col: str, title: str, legend_title: str):
        return (
            alt.Chart(chart_data)
            .mark_rect(stroke="#E5E1D8", strokeWidth=0.55)
            .encode(
                x=alt.X(
                    "account_bucket:N",
                    title="账户",
                    sort=account_order,
                    axis=alt.Axis(labelAngle=-35, labelLimit=120),
                ),
                y=alt.Y(
                    "asset_class:N",
                    title="投资品种",
                    sort=class_order,
                    axis=alt.Axis(labelLimit=150),
                ),
                color=alt.condition(
                    "datum._is_funding_asset_class",
                    alt.value(FUNDING_COLOR),
                    alt.Color(
                        f"{score_col}:Q",
                        title=legend_title,
                        scale=alt.Scale(
                            domain=[-1, -0.25, 0, 0.25, 1],
                            range=[
                                NEGATIVE_COLOR,
                                HEATMAP_NEGATIVE_LIGHT,
                                HEATMAP_NEUTRAL_COLOR,
                                HEATMAP_POSITIVE_LIGHT,
                                POSITIVE_COLOR,
                            ],
                        ),
                    ),
                ),
                tooltip=[
                    alt.Tooltip("account_bucket:N", title="账户"),
                    alt.Tooltip("asset_class:N", title="投资品种"),
                    alt.Tooltip(f"{metric}:Q", title=value_title, format=",.2f"),
                    alt.Tooltip(f"{return_metric}:Q", title=return_title, format=".2%"),
                    alt.Tooltip("_amount_rank_score:Q", title="金额排名强度", format=".2f"),
                    alt.Tooltip("_return_weighted_score:Q", title="收益率加权排名强度", format=".2f"),
                    alt.Tooltip("_color_note:N", title="颜色口径"),
                    alt.Tooltip("full_market_value_current:Q", title="当前全价市值(亿)", format=",.2f"),
                ],
            )
            .properties(title=title, height=heatmap_height)
            .configure_view(strokeWidth=0)
            .configure_title(anchor="start", color=POSITIVE_COLOR, fontSize=15)
        )

    return_chart = heatmap_chart(
        "_return_weighted_score",
        "账户 × 投资品种综合收益率热力图",
        "收益率加权排名强度",
    )
    amount_chart = heatmap_chart(
        "_amount_rank_score",
        "账户 × 投资品种综合收益金额热力图",
        "金额贡献排名强度",
    )
    st.altair_chart(return_chart, width="stretch")
    st.altair_chart(amount_chart, width="stretch")
    st.caption("颜色说明：两张热力图共用账户和投资品种排序；颜色按排名强度展示，正数使用浅蓝到深蓝，负数使用浅红到深红，精确值以 tooltip 和下方表格为准；正回购、逆回购按回购/融资科目处理，使用中性灰蓝色。")


def main() -> None:
    apply_yacht_theme()
    if maintenance_mode_enabled():
        render_maintenance_page()
        return

    require_login()

    st.title("组合管理账户复盘")
    st.caption("看组合规模、收益贡献、数据质量，并追到资产证据。")

    source_signature = data_source_signature(DATA_DIR)
    data, validation, errors = cached_load(
        str(DATA_DIR),
        DATA_SCHEMA_VERSION,
        STRATEGY_CLASSIFICATION_VERSION,
        source_signature,
    )
    runtime_missing_columns = missing_runtime_columns(data)
    if runtime_missing_columns and not st.session_state.get("runtime_schema_cache_refresh_attempted"):
        st.session_state["runtime_schema_cache_refresh_attempted"] = True
        cached_load.clear()
        st.rerun()
    data, runtime_missing_columns = ensure_runtime_columns(data)
    with st.sidebar:
        st.header("数据与筛选")
        with st.expander("数据源", expanded=False):
            st.write(f"数据目录：`{DATA_DIR}`")
        if st.button("刷新数据"):
            cached_load.clear()
            st.rerun()
        sidebar_nav()

    if errors:
        st.error("数据校验未通过，已停止分析。")
        for error in errors:
            st.write(f"- {error}")
        if not validation.empty:
            st.dataframe(format_table(validation, precision="source"), width="stretch", hide_index=True)
        st.stop()

    if runtime_missing_columns:
        st.warning(
            "源表或部署缓存仍缺少部分运行字段，已临时补空以避免页面中断；"
            "委内/委外比较等新模块可能无法完整展示。请点击左侧“刷新数据”重新读取源文件。缺失字段："
            + "、".join(runtime_missing_columns)
        )

    snapshots = available_snapshots(data)
    if not snapshots:
        st.error("至少需要一个带完整日期的数据快照才能做账户复盘。")
        st.stop()

    status_by_snapshot = snapshot_status_map(data)
    default_current = snapshots[-1]

    if st.session_state.get("reset_filters"):
        st.session_state["账户"] = ALL
        st.session_state["投资品种"] = ALL
        st.session_state["投资经理"] = ALL
        st.session_state["加载全部资产证据"] = False
        st.session_state["加载全部委外权益明细"] = False
        st.session_state["reset_filters"] = False

    with st.sidebar:
        current_month = st.selectbox(
            "数据时点",
            snapshots,
            index=snapshots.index(default_current),
            format_func=lambda value: snapshot_display_label(value, status_by_snapshot.get(value)),
        )
        comparison_mode = st.selectbox("分析视角", ["年初以来", "单月复盘"], index=0)
        prior_candidates = previous_official_snapshots(data, current_month)
        if comparison_mode == "单月复盘" and not prior_candidates:
            st.error("缺少上一自然月的月末正式快照，不能做单月复盘规模变化。")
            st.stop()
        if comparison_mode == "单月复盘":
            prior_month = prior_candidates[-1]
            st.caption(
                f"单月复盘使用上一自然月正式快照 {snapshot_display_label(prior_month)} 作为规模变化基准。"
            )
        else:
            prior_month = prior_candidates[-1] if prior_candidates else ""
            st.caption("年初以来口径使用源表年初市值、本年以来收益、本年以来平均资金占用。")
        if st.button("重置局部筛选"):
            st.session_state["reset_filters"] = True
            st.rerun()

    current_snapshot_status = status_by_snapshot.get(current_month, SNAPSHOT_STATUS_INTERIM)
    if current_snapshot_status == SNAPSHOT_STATUS_INTERIM:
        st.warning(
            f"当前展示的是 {snapshot_display_label(current_month, current_snapshot_status)}，并非当月月末正式版本；"
            "所有指标仅截至该数据时点，后续月末数据可能调整。"
        )

    account_summary = ensure_summary_columns(
        comparison_summary(data, current_month, prior_month, ["account_bucket"], comparison_mode),
        comparison_mode,
    )
    account_options = [ALL] + sorted(account_summary["account_bucket"].astype(str).tolist())
    if st.session_state.get("账户") not in account_options:
        st.session_state["账户"] = ALL
    selected_account = st.session_state.get("账户", ALL)

    current_options_slice = snapshot_slice(data, current_month)
    account_filtered_options = current_options_slice
    if selected_account != ALL:
        account_filtered_options = account_filtered_options[account_filtered_options["account_bucket"] == selected_account]
    asset_options = [ALL] + sorted(account_filtered_options["asset_class"].dropna().astype(str).unique().tolist())
    if st.session_state.get("投资品种") not in asset_options:
        st.session_state["投资品种"] = ALL
    selected_asset_class = st.session_state.get("投资品种", ALL)

    manager_options_frame = account_filtered_options
    if selected_asset_class != ALL:
        manager_options_frame = manager_options_frame[manager_options_frame["asset_class"] == selected_asset_class]
    manager_options = [ALL] + sorted(manager_options_frame["manager"].dropna().astype(str).unique().tolist())
    if st.session_state.get("投资经理") not in manager_options:
        st.session_state["投资经理"] = ALL
    selected_manager = st.session_state.get("投资经理", ALL)

    render_filter_pills(
        current_month,
        comparison_mode,
        prior_month,
        selected_account,
        selected_asset_class,
        selected_manager,
    )

    current_slice = snapshot_slice(data, current_month)
    prior_slice = snapshot_slice(data, prior_month)
    current_mv = float(current_slice["full_market_value"].sum())
    if comparison_mode == "年初以来":
        prior_mv = float(current_slice["market_value_year_open"].sum())
        current_fin = float(current_slice["finance_income_ytd"].sum())
        current_comp = float(current_slice["comprehensive_income_ytd"].sum())
        current_capital = float(current_slice["avg_capital_ytd"].sum())
        period_label = "年初以来截至时点" if current_snapshot_status == SNAPSHOT_STATUS_INTERIM else "年初以来"
        baseline_label = "年初"
        capital_label = "本年以来平均资金占用"
    else:
        prior_mv = float(prior_slice["full_market_value"].sum())
        current_fin = float(current_slice["finance_income_mtd"].sum())
        current_comp = float(current_slice["comprehensive_income_mtd"].sum())
        current_capital = float(current_slice["avg_capital_mtd"].sum())
        period_label = "本月截至时点" if current_snapshot_status == SNAPSHOT_STATUS_INTERIM else "本月"
        baseline_label = "上月"
        capital_label = "本月平均资金占用"
    quality = quality_metrics(data, current_month, comparison_mode)
    asset_class_summary = enrich_asset_class_display(
        ensure_summary_columns(
            comparison_summary(data, current_month, prior_month, ["asset_class"], comparison_mode),
            comparison_mode,
        )
    )

    section_anchor("overview")
    st.subheader("总体表现")
    render_decision_summary(
        current_month,
        prior_month,
        comparison_mode,
        current_mv,
        prior_mv,
        current_comp,
        asset_class_summary,
        quality,
    )
    render_kpi_grid(
        [
            {"label": "时点市值", "value": amount(current_mv), "delta": signed_amount(current_mv - prior_mv)},
            {"label": f"{period_label}财务收益", "value": amount(current_fin)},
            {"label": f"{period_label}综合收益", "value": amount(current_comp)},
            {"label": capital_label, "value": amount(current_capital)},
            {"label": "快照行数", "value": f"{len(current_slice):,}"},
        ]
    )
    render_action_cards()
    render_quality_signal(quality)
    show_block_note(
        f"顶部指标均为当前数据时点全组合源表逐行加总；市值变化 = 时点市值 - {baseline_label}市值；收益与资金占用采用{period_label}口径。"
    )

    section_anchor("charts-overview")
    st.subheader("图表总览")
    show_block_note("左图用柱展示各数据时点全组合规模、用红色点线展示正回购融资余额；右图用柱展示当月截至对应时点的收益，用折线+点展示年初以来累计收益。")
    render_monthly_trends(data, comparison_mode)

    st.divider()

    section_anchor("asset-class-overview")
    st.subheader("投资品种总览：规模变化与收益贡献")
    scale_income_label = "年初以来综合收益" if comparison_mode == "年初以来" else "本月综合收益"
    scale_baseline_label = "年初市值" if comparison_mode == "年初以来" else "上月市值"
    show_block_note(
        f"本表不分账户，直接按投资品种汇总；股权/不动产相关品种用资产主题标明并强制纳入图表；右侧净规模变化 = 时点市值 - {scale_baseline_label} - {scale_income_label}，用于近似识别真实增减仓或资金进出。"
    )
    asset_class_display = asset_class_summary.sort_values("comprehensive_income_mtd_current", ascending=False)
    asset_income_metric, asset_income_title, asset_income_value_title = income_chart_config(
        comparison_mode,
        "投资品种",
        " Top/Bottom",
    )
    asset_scale_metric = "net_full_market_value_delta"
    asset_chart_labels = include_focus_asset_labels(
        asset_class_summary,
        shared_top_bottom_labels(
            asset_class_summary,
            asset_income_metric,
            asset_scale_metric,
            "asset_class_display",
        ),
    )
    asset_chart_cols = st.columns(2)
    with asset_chart_cols[0]:
        render_bar_chart(
            asset_class_summary,
            asset_income_metric,
            "asset_class_display",
            asset_income_title,
            asset_income_value_title,
            comparison_mode=comparison_mode,
            empty_message="当前投资品种暂无可展示的收益贡献。",
            label_order=asset_chart_labels,
            show_value_labels=True,
        )
    with asset_chart_cols[1]:
        render_bar_chart(
            asset_class_summary,
            asset_scale_metric,
            "asset_class_display",
            "投资品种净规模变化 Top/Bottom",
            display_names_for_mode(comparison_mode)[asset_scale_metric],
            comparison_mode=comparison_mode,
            empty_message="当前投资品种暂无可展示的规模变化。",
            label_order=asset_chart_labels,
            show_value_labels=True,
        )
    st.dataframe(
        format_table(
            asset_class_display[
                [
                    "asset_theme",
                    "asset_class",
                    "full_market_value_current",
                    "full_market_value_prior",
                    "full_market_value_delta",
                    "net_full_market_value_delta",
                    "finance_income_mtd_current",
                    "comprehensive_income_mtd_current",
                    "avg_capital_mtd_current",
                    "finance_return_mtd",
                    "comprehensive_return_mtd",
                    "record_count_current",
                ]
            ],
            comparison_mode=comparison_mode,
        ),
        width="stretch",
        hide_index=True,
    )
    render_asset_return_completion(data, current_month)

    st.divider()

    section_anchor("strategy-book-overview")
    st.subheader("委内/委外比较")
    show_block_note(
        "本模块复刻管理透视表口径：委内展示委托资管下的固收配置盘、固收交易盘、非标、权益配置盘、权益交易盘；"
        "委外并列展示人保/泰康/中信建投/中邮证券固收，富国/华泰/华夏基金/国泰海通/大成基金/广发基金权益，"
        "以及太平资产香港、太保投资香港、国寿富兰克林。"
        "单一委外计划按数据时点在顶层汇总行与底层持仓中选择有规模的一层，避免重复计算；"
        "指定委外账户按账户全量纳入，包含现金、应收、费用等调节项；"
        "富国顶层产品行只作为对账提示，避免重复计算底层持仓；"
        "卡片胶囊数字为综合收益率。"
    )
    render_strategy_book_overview(data, current_month, prior_month, comparison_mode)

    st.divider()

    section_anchor("account-overview")
    st.subheader("账户层：规模变化与收益贡献")
    show_block_note(
        f"本表用于回答哪个账户收益效率更高；左图展示综合收益率，右图展示财务收益率；tooltip 保留收益额、规模变化和资金占用；收益率 = {period_label}收益 / {capital_label}。"
    )
    account_display = account_summary.sort_values("full_market_value_delta", ascending=False)
    account_chart_labels = ordered_account_labels(account_summary["account_bucket"].tolist(), include_remaining=False)

    account_chart_cols = st.columns(2)
    with account_chart_cols[0]:
        render_bar_chart(
            account_summary,
            "comprehensive_return_mtd",
            "account_bucket",
            "账户综合收益率",
            display_names_for_mode(comparison_mode)["comprehensive_return_mtd"],
            limit=12,
            selection="abs",
            comparison_mode=comparison_mode,
            empty_message="当前账户暂无可展示的综合收益率。",
            label_order=account_chart_labels,
            threshold_lines=[
                {"label": "资金成本率 3.41%", "value": FUNDING_COST_RATE, "color": "#C88439"},
            ],
            threshold_color_value=FUNDING_COST_RATE,
            show_value_labels=True,
        )
    with account_chart_cols[1]:
        render_bar_chart(
            account_summary,
            "finance_return_mtd",
            "account_bucket",
            "账户财务收益率",
            display_names_for_mode(comparison_mode)["finance_return_mtd"],
            limit=12,
            selection="abs",
            comparison_mode=comparison_mode,
            empty_message="当前账户暂无可展示的财务收益率。",
            label_order=account_chart_labels,
            threshold_lines=[
                {"label": "有效成本率 3.26%", "value": EFFECTIVE_COST_RATE, "color": "#0F6F3F"},
            ],
            threshold_color_value=EFFECTIVE_COST_RATE,
            show_value_labels=True,
        )
    st.caption(
        "比较说明：以下三项为公司整体成本率，并非按账户拆分后的成本率。"
        "综合收益率 vs 资金成本率 3.41% 看监管 ALM 缺口；"
        "风险调整收益率 vs 保证成本率 3.24% 看最低承诺覆盖能力；"
        "会计收益率 vs 有效成本率 3.26% 看 IFRS17 账户利润压力。"
    )
    st.dataframe(
        format_table(
            account_display[
                [
                    "account_bucket",
                    "full_market_value_current",
                    "full_market_value_prior",
                    "full_market_value_delta",
                    "finance_income_mtd_current",
                    "comprehensive_income_mtd_current",
                    "avg_capital_mtd_current",
                    "finance_return_mtd",
                    "comprehensive_return_mtd",
                    "record_count_current",
                ]
            ],
            comparison_mode=comparison_mode,
        ),
        width="stretch",
        hide_index=True,
    )

    section_anchor("duration-overview")
    st.subheader("账户久期：市值加权久期")
    show_block_note(
        "账户久期按金融市场惯例使用全价市值加权：Σ(资产久期 × 全价市值) / Σ(有有效久期资产全价市值)；"
        "仅纳入久期大于 0 且全价市值大于 0 的资产，并展示久期市值覆盖率。"
    )
    duration_summary = account_duration_summary(data, current_month)
    duration_order = ordered_account_labels(duration_summary["account_bucket"].tolist())
    duration_display = duration_summary.copy()
    duration_display["_account_order"] = pd.Categorical(
        duration_display["account_bucket"].astype(str),
        categories=duration_order,
        ordered=True,
    )
    duration_display = duration_display.sort_values("_account_order")
    render_duration_chart(duration_summary, comparison_mode)
    if not duration_display.empty:
        st.dataframe(
            format_table(
                duration_display[
                    [
                        "account_bucket",
                        "weighted_duration",
                        "duration_market_value",
                        "duration_coverage_ratio",
                        "duration_asset_count",
                        "full_market_value_current",
                    ]
                ],
                comparison_mode=comparison_mode,
            ),
            width="stretch",
            hide_index=True,
        )

    section_anchor("mandate-overview")
    st.subheader("委受托维度：规模变化与收益贡献")
    show_block_note(
        f"本表用于回答不同委受托关系下的规模、收益贡献和变化情况；当前采用{comparison_mode}口径，不参与左侧筛选链路。"
    )
    mandate_summary = ensure_summary_columns(
        comparison_summary(data, current_month, prior_month, ["mandate_type"], comparison_mode),
        comparison_mode,
    )
    mandate_display = mandate_summary.sort_values("full_market_value_delta", ascending=False)
    st.dataframe(
        format_table(
            mandate_display[
                [
                    "mandate_type",
                    "full_market_value_current",
                    "full_market_value_prior",
                    "full_market_value_delta",
                    "finance_income_mtd_current",
                    "comprehensive_income_mtd_current",
                    "avg_capital_mtd_current",
                    "finance_return_mtd",
                    "comprehensive_return_mtd",
                    "record_count_current",
                ]
            ],
            comparison_mode=comparison_mode,
        ),
        width="stretch",
        hide_index=True,
    )

    section_anchor("account-class-breakdown")
    st.subheader("账户内品种拆解")
    show_block_note(f"本表用于回答选定账户的钱投向哪些品种，以及这些品种在{comparison_mode}口径下分别贡献或拖累了多少收益。")
    account_control_col, _ = st.columns([0.28, 0.72])
    with account_control_col:
        selected_account = st.selectbox("账户", account_options, key="账户")
    class_summary = ensure_summary_columns(
        comparison_summary(data, current_month, prior_month, ["account_bucket", "asset_class"], comparison_mode),
        comparison_mode,
    )
    if selected_account != ALL:
        class_summary = class_summary[class_summary["account_bucket"] == selected_account]
    class_display = class_summary.sort_values("comprehensive_income_mtd_current", ascending=False)
    render_heatmap(class_summary, selected_account, comparison_mode)
    st.dataframe(
        format_table(
            class_display[
                [
                    "account_bucket",
                    "asset_class",
                    "full_market_value_current",
                    "full_market_value_prior",
                    "full_market_value_delta",
                    "finance_income_mtd_current",
                    "comprehensive_income_mtd_current",
                    "avg_capital_mtd_current",
                    "comprehensive_return_mtd",
                    "record_count_current",
                ]
            ],
            comparison_mode=comparison_mode,
        ),
        width="stretch",
        hide_index=True,
    )

    section_anchor("manager-breakdown")
    st.subheader("品种内经理拆解")
    show_block_note(
        f"本表用于回答选定品种下，结果由哪些投资经理贡献或拖累；投资经理筛选会同步收窄本表和资产证据，当前采用{comparison_mode}口径。"
    )
    if st.session_state.get("经理展示口径") not in ["合并账户", "拆分账户"]:
        st.session_state["经理展示口径"] = "合并账户"
    manager_scope_cols = st.columns([0.22, 0.26, 0.26, 0.26])
    with manager_scope_cols[0]:
        manager_view_mode = st.radio(
            "经理展示口径",
            ["合并账户", "拆分账户"],
            horizontal=True,
            key="经理展示口径",
        )

    account_filtered_options = current_options_slice
    if manager_view_mode == "拆分账户" and selected_account != ALL:
        account_filtered_options = account_filtered_options[account_filtered_options["account_bucket"] == selected_account]
    asset_options = [ALL] + sorted(account_filtered_options["asset_class"].dropna().astype(str).unique().tolist())
    if st.session_state.get("投资品种") not in asset_options:
        st.session_state["投资品种"] = ALL
    selected_asset_class = st.session_state.get("投资品种", ALL)
    manager_options_frame = account_filtered_options
    if selected_asset_class != ALL:
        manager_options_frame = manager_options_frame[manager_options_frame["asset_class"] == selected_asset_class]
    manager_options = [ALL] + sorted(manager_options_frame["manager"].dropna().astype(str).unique().tolist())
    if st.session_state.get("投资经理") not in manager_options:
        st.session_state["投资经理"] = ALL
    with manager_scope_cols[1]:
        selected_asset_class = st.selectbox("投资品种", asset_options, key="投资品种")
    manager_options_frame = account_filtered_options
    if selected_asset_class != ALL:
        manager_options_frame = manager_options_frame[manager_options_frame["asset_class"] == selected_asset_class]
    manager_options = [ALL] + sorted(manager_options_frame["manager"].dropna().astype(str).unique().tolist())
    if st.session_state.get("投资经理") not in manager_options:
        st.session_state["投资经理"] = ALL
    with manager_scope_cols[2]:
        selected_manager = st.selectbox("投资经理", manager_options, key="投资经理")
    manager_group_cols = (
        ["asset_class", "manager"]
        if manager_view_mode == "合并账户"
        else ["account_bucket", "asset_class", "manager"]
    )
    manager_summary = ensure_summary_columns(
        comparison_summary(
            data,
            current_month,
            prior_month,
            manager_group_cols,
            comparison_mode,
        ),
        comparison_mode,
    )
    if manager_view_mode == "拆分账户" and selected_account != ALL:
        manager_summary = manager_summary[manager_summary["account_bucket"] == selected_account]
    if selected_asset_class != ALL:
        manager_summary = manager_summary[manager_summary["asset_class"] == selected_asset_class]
    if selected_manager != ALL:
        manager_summary = manager_summary[manager_summary["manager"] == selected_manager]
    manager_display = manager_summary.sort_values("comprehensive_income_mtd_current", ascending=False)
    manager_display_columns = [
        "asset_class",
        "manager",
        "full_market_value_current",
        "full_market_value_prior",
        "full_market_value_delta",
        "finance_income_mtd_current",
        "comprehensive_income_mtd_current",
        "avg_capital_mtd_current",
        "comprehensive_return_mtd",
        "record_count_current",
    ]
    if manager_view_mode == "拆分账户":
        manager_display_columns = ["account_bucket"] + manager_display_columns
    manager_table = manager_display[manager_display_columns].reset_index(drop=True)
    st.dataframe(
        format_table(
            manager_table,
            comparison_mode=comparison_mode,
        ),
        width="stretch",
        hide_index=True,
        key=f"manager-breakdown-table-{manager_view_mode}",
    )

    section_anchor("asset-evidence")
    st.subheader("资产证据")
    evidence_account = selected_account if manager_view_mode == "拆分账户" else ALL
    if comparison_mode == "年初以来":
        show_block_note(
            "本表用于把账户、品种、经理的结果追溯到资产明细；变化类型基于源表年初市值与当前市值判断，不等同于逐月交易明细。"
        )
        evidence = asset_evidence_year_open(
            data,
            current_month,
            evidence_account,
            selected_asset_class,
            selected_manager,
            prior_month=prior_month,
        )
        evidence_options = asset_evidence_sort_options(comparison_mode)
    else:
        show_block_note(
            f"本表用于把账户、品种、经理的结果追溯到资产明细；变化类型按当前数据时点和上一月正式快照 {snapshot_display_label(prior_month)} 是否出现及市值变化判断。"
        )
        evidence = asset_evidence(
            data,
            current_month,
            prior_month,
            evidence_account,
            selected_asset_class,
            selected_manager,
        )
        evidence_options = asset_evidence_sort_options(comparison_mode)
    sort_choice = st.radio(
        "资产证据视角",
        evidence_options,
        horizontal=True,
    )
    evidence = sort_asset_evidence(evidence, sort_choice, comparison_mode)
    show_all_evidence = False
    if len(evidence) > 500:
        show_all_key = "加载全部资产证据"
        reset_boolean_state_on_context(
            show_all_key,
            (
                current_month,
                prior_month,
                comparison_mode,
                manager_view_mode,
                evidence_account,
                selected_asset_class,
                selected_manager,
                sort_choice,
            ),
        )
        show_all_evidence = st.toggle(
            f"加载全部资产证据（{len(evidence):,} 条）",
            key=show_all_key,
        )
        if not show_all_evidence:
            st.caption("为提升刷新速度，默认展示当前排序下前 500 条；汇总指标仍按全部资产计算。")
    display_evidence = evidence if show_all_evidence else evidence.head(500)

    st.dataframe(
        format_table(
            display_evidence[
                [
                    "change_type",
                    "asset_name",
                    "manager",
                    *asset_evidence_value_columns(comparison_mode),
                    "asset_code",
                    "trade_code",
                    "account_bucket",
                    "asset_class",
                    "source_rows_current",
                    "source_rows_prior",
                ]
            ],
            comparison_mode=comparison_mode,
        ),
        width="stretch",
        hide_index=True,
    )

    st.divider()

    section_anchor("quality-checks")
    st.subheader("数据质量提示")
    show_block_note("本提示用于提醒阅读者哪些数据需要谨慎解释，不改变源表数值，也不参与收益贡献计算。")
    render_quality_bar(quality)

    st.subheader("财务收益与综合收益差异")
    show_block_note(f"本表用于回答财务收益和综合收益差在哪里；金额为当前数据时点源表逐行加总，采用{period_label}口径。")
    diff_table = income_diff_breakdown(current_slice, comparison_mode)
    st.dataframe(
        diff_table.style.format({"金额(亿)": "{:,.2f}"}, na_rep="—"),
        width="stretch",
        hide_index=True,
    )

    with st.expander("源数据核对"):
        st.caption("源数据核对页保留 4 位小数，便于和原始宽表汇总结果复核。")
        st.dataframe(format_table(validation, precision="source"), width="stretch", hide_index=True)


if __name__ == "__main__":
    main()
