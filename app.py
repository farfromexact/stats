import hmac
import importlib
import os
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd
import altair as alt
import plotly.graph_objects as go
import streamlit as st

try:
    from streamlit.errors import StreamlitSecretNotFoundError
except ImportError:  # pragma: no cover - compatibility with older Streamlit
    StreamlitSecretNotFoundError = RuntimeError

import account_review as account_review_module
import manager_attribution as manager_attribution_module
import strategy_books as strategy_books_module
from manager_position_views import render_position_peer_comparison
from outsourced_funding import FUNDING_NOTE, adjust_outsourced_funding_capital, funding_capital_audit
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
manager_attribution_module = importlib.reload(manager_attribution_module)
strategy_books_module = importlib.reload(strategy_books_module)

asset_evidence = account_review_module.asset_evidence
asset_evidence_year_open = account_review_module.asset_evidence_year_open
comparison_summary = account_review_module.comparison_summary
ATTRIBUTION_BOARD_EQUITY = manager_attribution_module.ATTRIBUTION_BOARD_EQUITY
ATTRIBUTION_BOARD_FIXED = manager_attribution_module.ATTRIBUTION_BOARD_FIXED
build_manager_attribution_rows = manager_attribution_module.build_manager_attribution_rows
default_manager_entities = manager_attribution_module.default_manager_entities
holding_position_change_status = manager_attribution_module.holding_position_change_status
manager_asset_detail = manager_attribution_module.manager_asset_detail
manager_exited_holdings = manager_attribution_module.manager_exited_holdings
manager_holding_map = manager_attribution_module.manager_holding_map
manager_attribution_change_summary = manager_attribution_module.manager_attribution_change_summary
manager_attribution_coverage_summary = manager_attribution_module.manager_attribution_coverage_summary
manager_attribution_summary = manager_attribution_module.manager_attribution_summary
manager_attribution_timeseries = manager_attribution_module.manager_attribution_timeseries
rank_manager_timeseries = manager_attribution_module.rank_manager_timeseries
assign_strategy_book_columns = strategy_books_module.assign_strategy_book_columns
STRATEGY_CLASSIFICATION_VERSION = strategy_books_module.STRATEGY_CLASSIFICATION_VERSION
EQUITY_DASHBOARD_LABEL_ORDER = strategy_books_module.EQUITY_DASHBOARD_LABEL_ORDER
EXTERNAL_STRATEGY_BOOK_ORDER = strategy_books_module.EXTERNAL_STRATEGY_BOOK_ORDER
OUTSOURCED_EQUITY_HOLDING_TYPE_ORDER = strategy_books_module.OUTSOURCED_EQUITY_HOLDING_TYPE_ORDER
MANAGER_DISPLAY_COLUMN = strategy_books_module.MANAGER_DISPLAY_COLUMN
STRATEGY_BOOK_LABEL_ORDER = strategy_books_module.STRATEGY_BOOK_LABEL_ORDER
equity_dashboard_summary = strategy_books_module.equity_dashboard_summary
excluded_strategy_book_detail = strategy_books_module.excluded_strategy_book_detail
outsourced_equity_holding_slice = strategy_books_module.outsourced_equity_holding_slice
strategy_book_detail_summary = strategy_books_module.strategy_book_detail_summary
strategy_book_summary = strategy_books_module.strategy_book_summary


ALL = "全部"
RETURN_BASE_THRESHOLD = 0.0001
DATA_SCHEMA_VERSION = "2026-07-31-parquet-only-v5"
YEAR_TO_DATE_MODE = "年初以来"
MONTH_REVIEW_MODE = "单月复盘"
SNAPSHOT_COMPARISON_MODE = "时点对比"
COMPARISON_MODE_OPTIONS = [YEAR_TO_DATE_MODE, MONTH_REVIEW_MODE, SNAPSHOT_COMPARISON_MODE]
ASSET_RETURN_PLAN_PATH = DATA_DIR.parent / "asset_return_plan_2026.csv"
MAINTENANCE_MESSAGE = "多事之秋，我们秋天再见"
MAINTENANCE_SUBMESSAGE = "如有需要微信找我"
CHART_EPSILON = 1e-9
# Columbia / BioShock Infinite palette: sky navy, brass, parchment, refined crimson.
POSITIVE_COLOR = "#1B3A5C"
NEGATIVE_COLOR = "#8C3A3A"
NEUTRAL_COLOR = "#8BA9BF"
FUNDING_COLOR = "#6E7F92"
HEATMAP_NEUTRAL_COLOR = "#F7F1E3"
HEATMAP_POSITIVE_LIGHT = "#B7D0E4"
HEATMAP_NEGATIVE_LIGHT = "#E3B6B0"
MANAGER_ATTRIBUTION_COLORS = [
    "#1B3A5C",
    "#2F7A6B",
    "#C08A2D",
    "#7B5EA7",
    "#3F7CAC",
    "#8C3A3A",
]
MANAGER_ATTRIBUTION_MAX_COMPARISONS = 5
MANAGER_ATTRIBUTION_PERIODS = {
    YEAR_TO_DATE_MODE: {
        "income": "comprehensive_income_ytd",
        "return": "comprehensive_return_ytd",
        "short_label": "YTD",
    },
    MONTH_REVIEW_MODE: {
        "income": "comprehensive_income_mtd",
        "return": "comprehensive_return_mtd",
        "short_label": "MTD",
    },
}
MANAGER_ATTRIBUTION_VIEW_OPTIONS = ["综合收益额", "综合收益率"]
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

st.set_page_config(page_title="组合管理账户复盘 · Columbia", layout="wide")


def apply_columbia_theme() -> None:
    """Apply a restrained Columbia-inspired shell around the operating dashboard."""
    st.html(
        """
        <style>
        :root {
            --columbia-ink: #1C2433;
            --columbia-navy: #1B3A5C;
            --columbia-sky: #6FA8C9;
            --columbia-sky-soft: #A8D0E4;
            --columbia-brass: #C9A84C;
            --columbia-brass-deep: #A8882E;
            --columbia-brass-soft: #E8D48B;
            --columbia-parchment: #F7F1E3;
            --columbia-cream: #FFFBF3;
            --columbia-border: #D9CDB5;
            --columbia-muted: #5C6B7A;
            --columbia-crimson: #8C3A3A;
            --columbia-foam: #FBF6EC;
            --rat-internal: #3D6F9A;
            --rat-external: #2F7A6B;
        }

        html, body, [class*="css"] {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
        }

        .stApp {
            background: #F4F3EE;
            color: var(--columbia-ink);
        }

        .stApp::before {
            display: none;
        }

        section.main > div {
            position: relative;
            z-index: 1;
        }

        section[data-testid="stSidebar"] {
            background:
                linear-gradient(180deg, #142844 0%, #1B3A5C 42%, #0F1F33 100%);
            border-right: 1px solid rgba(201, 168, 76, 0.35);
        }

        section[data-testid="stSidebar"] * {
            color: var(--columbia-foam);
        }

        section[data-testid="stSidebar"] div[data-baseweb="select"] * {
            color: var(--columbia-ink);
        }

        section[data-testid="stSidebar"] div[data-baseweb="select"] {
            background: var(--columbia-cream);
            border-radius: 4px;
            border: 1px solid rgba(201, 168, 76, 0.45);
        }

        section[data-testid="stSidebar"] input {
            color: var(--columbia-ink);
            background: var(--columbia-cream);
        }

        section[data-testid="stSidebar"] code,
        section[data-testid="stSidebar"] pre,
        section[data-testid="stSidebar"] kbd {
            color: var(--columbia-ink) !important;
            background: var(--columbia-cream) !important;
            border: 1px solid rgba(201, 168, 76, 0.45);
            border-radius: 4px;
            white-space: normal;
            overflow-wrap: anywhere;
        }

        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] span {
            color: var(--columbia-foam);
        }

        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3 {
            color: var(--columbia-brass-soft) !important;
            font-family: inherit;
            letter-spacing: 0;
            border-bottom: none !important;
        }

        h1, h2, h3 {
            color: var(--columbia-navy);
            font-family: inherit;
            letter-spacing: 0;
            font-weight: 700;
        }

        h1 {
            border-bottom: 2px solid var(--columbia-sky-soft);
            padding-bottom: 0.38rem;
        }

        h2 {
            border-left: 3px solid var(--columbia-brass);
            padding-left: 0.65rem;
            margin-top: 0.4rem;
        }

        h3 {
            color: #2A4A6B;
        }

        div[data-testid="stMetric"] {
            background: rgba(255, 255, 255, 0.78);
            border: 1px solid var(--columbia-border);
            border-radius: 6px;
            padding: 0.85rem 1rem;
            box-shadow: 0 2px 10px rgba(27, 58, 92, 0.05);
        }

        div[data-testid="stMetric"] label {
            color: var(--columbia-navy);
            font-family: inherit;
            letter-spacing: 0;
        }

        div[data-testid="stMetricValue"] {
            color: var(--columbia-ink);
        }

        .hero-banner {
            margin: 0.15rem 0 0.9rem 0;
            padding: 0.25rem 0 0.72rem 0.85rem;
            background: transparent;
            border: none;
            border-left: 3px solid var(--columbia-brass);
        }

        .hero-banner::before,
        .hero-banner::after {
            display: none;
        }

        .hero-banner::before { left: 0.7rem; }
        .hero-banner::after { right: 0.7rem; }

        .hero-kicker {
            font-family: inherit;
            font-size: 0.72rem;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            color: var(--columbia-brass-deep);
            margin-bottom: 0.2rem;
            text-align: left;
        }

        .hero-title {
            font-family: inherit;
            font-size: 1.8rem;
            font-weight: 700;
            color: var(--columbia-navy);
            text-align: left;
            letter-spacing: 0;
            line-height: 1.25;
            margin: 0;
        }

        .hero-subtitle {
            margin-top: 0.28rem;
            text-align: left;
            color: var(--columbia-muted);
            font-size: 0.9rem;
            line-height: 1.4;
        }

        .filter-pills {
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            margin: 0.55rem 0 1rem 0;
        }

        .filter-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.34rem 0.62rem;
            background: rgba(255, 255, 255, 0.72);
            border: 1px solid var(--columbia-border);
            border-radius: 5px;
            color: var(--columbia-ink);
            font-size: 0.86rem;
            line-height: 1.25;
        }

        .filter-pill span {
            color: var(--columbia-muted);
            font-weight: 700;
            font-family: inherit;
            font-size: 0.78rem;
            letter-spacing: 0;
        }

        .kpi-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(176px, 1fr));
            gap: 0.85rem;
            margin: 0.65rem 0 0.85rem 0;
        }

        .kpi-grid.kpi-grid-attribution {
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
        }

        .kpi-card {
            min-height: 96px;
            background: rgba(255, 255, 255, 0.8);
            border: 1px solid var(--columbia-border);
            border-left: 4px solid var(--columbia-brass);
            border-radius: 6px;
            padding: 0.82rem 0.95rem;
            box-shadow: 0 2px 10px rgba(27, 58, 92, 0.05);
            transition: border-color 0.15s ease, box-shadow 0.15s ease;
        }

        .kpi-card:hover {
            border-color: rgba(201, 168, 76, 0.65);
            box-shadow: 0 6px 18px rgba(27, 58, 92, 0.09);
        }

        .kpi-card.kpi-card-internal {
            background: linear-gradient(180deg, rgba(61, 111, 154, 0.14) 0%, rgba(61, 111, 154, 0.06) 100%);
            border-color: rgba(61, 111, 154, 0.35);
            border-left-color: var(--rat-internal);
        }

        .kpi-card.kpi-card-external {
            background: linear-gradient(180deg, rgba(47, 122, 107, 0.14) 0%, rgba(47, 122, 107, 0.06) 100%);
            border-color: rgba(47, 122, 107, 0.34);
            border-left-color: var(--rat-external);
        }

        .kpi-card.kpi-card-positive {
            background: linear-gradient(180deg, rgba(47, 122, 107, 0.13) 0%, rgba(47, 122, 107, 0.04) 100%);
            border-color: rgba(47, 122, 107, 0.32);
            border-left-color: #2F7A6B;
        }

        .kpi-card.kpi-card-negative {
            background: linear-gradient(180deg, rgba(140, 58, 58, 0.12) 0%, rgba(140, 58, 58, 0.035) 100%);
            border-color: rgba(140, 58, 58, 0.28);
            border-left-color: var(--columbia-crimson);
        }

        .kpi-label {
            color: var(--columbia-navy);
            font-size: 0.8rem;
            font-weight: 600;
            font-family: inherit;
            letter-spacing: 0;
            line-height: 1.3;
            margin-bottom: 0.45rem;
        }

        .kpi-value {
            color: var(--columbia-ink);
            font-size: 1.58rem;
            font-weight: 700;
            font-family: inherit;
            line-height: 1.16;
            overflow-wrap: anywhere;
        }

        .kpi-delta {
            display: inline-block;
            margin-top: 0.45rem;
            color: #1F6B4A;
            background: rgba(31, 107, 74, 0.1);
            border-radius: 999px;
            padding: 0.12rem 0.48rem;
            font-size: 0.82rem;
            font-weight: 700;
        }

        .kpi-delta.kpi-delta-positive {
            color: var(--columbia-navy);
            background: rgba(111, 168, 201, 0.2);
        }

        .kpi-delta.kpi-delta-negative {
            color: var(--columbia-crimson);
            background: rgba(140, 58, 58, 0.12);
        }

        .attribution-coverage {
            margin: 0.45rem 0 0.9rem 0;
            padding: 0.75rem 0.9rem 0.7rem 0.9rem;
            background: rgba(255, 255, 255, 0.68);
            border: 1px solid var(--columbia-border);
            border-radius: 6px;
        }

        .attribution-coverage-head {
            display: flex;
            justify-content: space-between;
            gap: 1rem;
            color: var(--columbia-navy);
            font-size: 0.86rem;
            font-weight: 700;
        }

        .attribution-coverage-head strong {
            font-size: 1rem;
        }

        .attribution-coverage-track {
            height: 6px;
            margin: 0.55rem 0 0.5rem 0;
            overflow: hidden;
            background: rgba(140, 58, 58, 0.14);
            border-radius: 999px;
        }

        .attribution-coverage-fill {
            height: 100%;
            background: linear-gradient(90deg, #2F7A6B 0%, #6FA8C9 100%);
            border-radius: inherit;
        }

        .attribution-coverage-meta {
            display: flex;
            flex-wrap: wrap;
            gap: 0.35rem 1rem;
            color: var(--columbia-muted);
            font-size: 0.78rem;
            line-height: 1.45;
        }

        .decision-summary {
            margin: 0.35rem 0 0.75rem 0;
            padding: 0.35rem 0 0.35rem 0.85rem;
            color: var(--columbia-ink);
            font-size: 1.02rem;
            line-height: 1.7;
            font-family: inherit;
            background: transparent;
            border-left: 2px solid var(--columbia-brass);
            border-radius: 0;
        }

        .action-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
            gap: 0.75rem;
            margin: 0.8rem 0 1rem 0;
        }

        .action-card {
            display: block;
            min-height: 96px;
            background: rgba(255, 255, 255, 0.8);
            border: 1px solid var(--columbia-border);
            border-radius: 6px;
            padding: 0.85rem 0.9rem;
            color: var(--columbia-ink) !important;
            text-decoration: none;
            box-shadow: 0 3px 12px rgba(27, 58, 92, 0.05);
            transition: transform 0.12s ease, border-color 0.12s ease, box-shadow 0.12s ease;
        }

        .action-card,
        .action-card * {
            text-decoration: none !important;
        }

        .action-card:hover {
            border-color: var(--columbia-brass);
            box-shadow: 0 8px 20px rgba(27, 58, 92, 0.1);
            transform: translateY(-1px);
            text-decoration: none;
        }

        .action-title {
            color: var(--columbia-navy);
            font-family: inherit;
            font-weight: 700;
            letter-spacing: 0;
            margin-bottom: 0.32rem;
        }

        .action-copy {
            color: var(--columbia-muted);
            font-size: 0.88rem;
            line-height: 1.45;
        }

        .quality-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(142px, 1fr));
            gap: 0.55rem;
            margin: 0.8rem 0 0.6rem 0;
        }

        .quality-card {
            background: rgba(255, 255, 255, 0.78);
            border: 1px solid var(--columbia-border);
            border-radius: 6px;
            padding: 0.65rem 0.75rem;
        }

        .quality-card.hot {
            border-color: var(--columbia-brass-deep);
            background: linear-gradient(180deg, #FFF6E0 0%, #F8E8C4 100%);
            box-shadow: inset 0 0 0 1px rgba(201, 168, 76, 0.25);
        }

        .quality-label {
            color: var(--columbia-muted);
            font-size: 0.78rem;
            font-weight: 700;
            font-family: inherit;
            letter-spacing: 0;
            margin-bottom: 0.2rem;
        }

        .quality-value {
            color: var(--columbia-ink);
            font-size: 1.35rem;
            font-weight: 700;
            font-family: inherit;
            line-height: 1.12;
        }

        div[data-testid="stAlert"] {
            border-radius: 6px;
            border-color: rgba(201, 168, 76, 0.55);
            background: rgba(255, 251, 243, 0.85);
        }

        .stButton > button {
            background: var(--columbia-navy);
            color: var(--columbia-foam);
            border: 1px solid var(--columbia-navy);
            border-radius: 4px;
            font-family: inherit;
            letter-spacing: 0;
            font-weight: 600;
            box-shadow: none;
        }

        .stButton > button:hover {
            background: linear-gradient(180deg, #3A5F88 0%, #243F63 100%);
            color: #FFF8E7;
            border-color: var(--columbia-brass);
        }

        .stButton > button:focus {
            box-shadow: 0 0 0 2px rgba(201, 168, 76, 0.35);
        }

        .sidebar-nav-button {
            display: block;
            width: 100%;
            margin: 0.32rem 0;
            padding: 0.45rem 0.7rem;
            background: rgba(168, 208, 228, 0.1);
            color: var(--columbia-foam) !important;
            border: 1px solid rgba(201, 168, 76, 0.22);
            border-left: 2px solid rgba(201, 168, 76, 0.55);
            border-radius: 4px;
            text-decoration: none;
            font-weight: 600;
            font-size: 0.88rem;
            transition: background 0.12s ease, border-color 0.12s ease;
        }

        .sidebar-nav-button:hover {
            background: rgba(201, 168, 76, 0.18);
            border-color: rgba(201, 168, 76, 0.5);
            color: #FFF8E7 !important;
            text-decoration: none;
        }

        .sidebar-nav-title {
            margin: 1rem 0 0.45rem 0;
            color: var(--columbia-brass-soft) !important;
            font-family: inherit;
            font-weight: 600;
            letter-spacing: 0;
            text-transform: none;
            font-size: 0.78rem;
            opacity: 0.95;
        }

        div[data-testid="stDataFrame"] {
            border: 1px solid var(--columbia-border);
            border-radius: 6px;
            overflow: hidden;
            background: var(--columbia-cream);
            box-shadow: 0 3px 12px rgba(27, 58, 92, 0.04);
        }

        div[data-testid="stVegaLiteChart"] {
            background: rgba(255, 255, 255, 0.76);
            border: 1px solid var(--columbia-border);
            border-radius: 6px;
            padding: 0.45rem;
            box-shadow: 0 3px 12px rgba(27, 58, 92, 0.04);
        }

        div[data-testid="stCaptionContainer"] {
            color: var(--columbia-muted);
            font-family: inherit;
        }

        hr {
            border-color: var(--columbia-border);
            background: none;
        }

        </style>
        """,
    )


def render_hero_banner(title: str, subtitle: str, kicker: str = "Columbia · Portfolio Review") -> None:
    st.markdown(
        f"""
        <div class="hero-banner">
            <div class="hero-kicker">{html_text(kicker)}</div>
            <div class="hero-title">{html_text(title)}</div>
            <div class="hero-subtitle">{html_text(subtitle)}</div>
        </div>
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
    return _truthy(configured)


def render_maintenance_page() -> None:
    st.markdown(
        f"""
        <style>
        div[data-testid="stSidebar"] {{
            display: none;
        }}
        section.main > div {{
            padding-top: 24vh;
        }}
        .maintenance-message {{
            color: var(--columbia-navy, #1B3A5C);
            font-family: inherit;
            font-size: clamp(2.4rem, 6.5vw, 5.5rem);
            font-weight: 700;
            line-height: 1.2;
            text-align: center;
            letter-spacing: 0;
            border-bottom: 2px solid var(--columbia-brass, #C9A84C);
            padding-bottom: 0.55rem;
        }}
        .maintenance-submessage {{
            margin-top: 1.35rem;
            color: var(--columbia-brass-deep, #A8882E);
            font-family: inherit;
            font-size: clamp(1.15rem, 2.3vw, 1.9rem);
            font-weight: 600;
            line-height: 1.3;
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

    render_hero_banner(
        "组合管理账户复盘",
        "请输入访问密码后继续。",
        kicker="Columbia / Authorized Entry",
    )
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
    "manager_display": "投资经理/受托机构",
    "asset_name": "资产名称",
    "asset_code": "资产代码",
    "trade_code": "交易代码",
    "change_type": "变化类型",
    "full_market_value_current": "当前时点市值(亿)",
    "full_market_value_prior": "上月市值(亿)",
    "prior_full_market_value": "上月末市值(亿)",
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
    "equity_scope": "范围",
    "equity_group_display_label": "比较项",
    "attribution_board": "归因板块",
    "attribution_scope": "委内/委外",
    "attribution_entity_name": "投资经理/受托机构",
    "avg_capital_mtd": "本月平均资本占用(亿)",
    "avg_capital_ytd": "年初以来平均资本占用(亿)",
    "comprehensive_income_ytd": "年初以来综合收益(亿)",
    "comprehensive_return_ytd": "年初以来综合收益率",
    "market_value_share": "当前市值占比",
    "asset_count": "资产数量",
    "row_count": "源表行数",
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

SNAPSHOT_COMPARISON_DISPLAY_OVERRIDES = {
    "full_market_value_prior": "对比时点市值(亿)",
    "full_market_value_delta": "较对比时点变化(亿)",
    "net_full_market_value_delta": "扣收益后较对比时点规模变化(亿)",
    "monthly_position_flow_delta": "扣本月综合收益后较对比时点加减仓(亿)",
    "source_rows_prior": "对比时点源行数",
}

AMOUNT_COLUMNS = {
    "full_market_value",
    "finance_income_mtd",
    "comprehensive_income_mtd",
    "comprehensive_income_ytd",
    "avg_capital_mtd",
    "avg_capital_ytd",
    "full_market_value_current",
    "full_market_value_prior",
    "prior_full_market_value",
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
    "comprehensive_return_ytd",
    "market_value_share",
}
DURATION_COLUMNS = {"duration", "weighted_duration"}
COUNT_COLUMNS = {
    "record_count",
    "record_count_current",
    "source_rows",
    "source_rows_current",
    "source_rows_prior",
    "duration_asset_count",
    "asset_count",
    "row_count",
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


def selectable_comparison_snapshots(snapshots: list[str], current_snapshot: str) -> list[str]:
    """Return valid baseline choices while preventing a snapshot from comparing with itself."""
    return [snapshot for snapshot in snapshots if snapshot != current_snapshot]


def default_comparison_snapshot(snapshots: list[str], current_snapshot: str) -> str:
    options = selectable_comparison_snapshots(snapshots, current_snapshot)
    if not options:
        return ""
    earlier = [snapshot for snapshot in options if snapshot < current_snapshot]
    return earlier[-1] if earlier else options[0]


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
    if comparison_mode == YEAR_TO_DATE_MODE:
        names.update(YTD_DISPLAY_OVERRIDES)
    elif comparison_mode == SNAPSHOT_COMPARISON_MODE:
        names.update(SNAPSHOT_COMPARISON_DISPLAY_OVERRIDES)
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
) -> None:
    current_label = snapshot_display_label(current_month)
    if comparison_mode == YEAR_TO_DATE_MODE:
        view_text = f"年初以来，截至 {current_label}"
    elif comparison_mode == SNAPSHOT_COMPARISON_MODE:
        view_text = f"{current_label} 对比 {snapshot_display_label(prior_month)}"
    else:
        view_text = f"{current_label} 单月复盘，规模较 {snapshot_display_label(prior_month)}"
    items = [
        ("当前视角", view_text),
        ("账户", selected_label(selected_account)),
    ]
    pills = "".join(
        f'<div class="filter-pill"><span>{html_text(label)}</span>{html_text(value)}</div>'
        for label, value in items
    )
    st.markdown(f'<div class="filter-pills">{pills}</div>', unsafe_allow_html=True)


def render_kpi_grid(
    items: list[dict[str, str]],
    grid_class: str = "",
) -> None:
    cards = []
    for item in items:
        delta = item.get("delta", "")
        tone = item.get("tone", "")
        tone_class = {
            "internal": "kpi-card-internal",
            "external": "kpi-card-external",
            "positive": "kpi-card-positive",
            "negative": "kpi-card-negative",
        }.get(tone, "")
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
    class_name = f"kpi-grid {grid_class}".strip()
    st.markdown(
        f'<div class="{html_text(class_name)}">{"".join(cards)}</div>',
        unsafe_allow_html=True,
    )


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
    if comparison_mode == YEAR_TO_DATE_MODE:
        baseline = "年初"
        period = "年初以来截至时点"
    elif comparison_mode == SNAPSHOT_COMPARISON_MODE:
        baseline = f"对比时点 {snapshot_display_label(prior_month)}"
        period = "当前时点本月截至"
    else:
        baseline = snapshot_display_label(prior_month)
        period = "本月截至时点"
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
        ("看经理归因", "从全体贡献继续穿透到经理或受托方的资产明细。", "#manager-attribution"),
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
    period = "年初以来" if comparison_mode == YEAR_TO_DATE_MODE else "本月"
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
        <a class="sidebar-nav-button" href="#equity-dashboard">股票专项看板</a>
        <a class="sidebar-nav-button" href="#strategy-book-overview">委内/委外比较</a>
        <a class="sidebar-nav-button" href="#manager-attribution">经理/受托归因</a>
        <a class="sidebar-nav-button" href="#account-overview">账户层图表/表格</a>
        <a class="sidebar-nav-button" href="#duration-overview">账户久期</a>
        <a class="sidebar-nav-button" href="#account-class-breakdown">账户内品种拆解</a>
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
    if comparison_mode == YEAR_TO_DATE_MODE:
        finance_col = "finance_income_ytd"
        comprehensive_col = "comprehensive_income_ytd"
        label = "年初以来"
        source_period = "本年以来"
    elif comparison_mode == SNAPSHOT_COMPARISON_MODE:
        finance_col = "finance_income_mtd"
        comprehensive_col = "comprehensive_income_mtd"
        label = "当前时点本月"
        source_period = "本月以来"
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
    if comparison_mode == YEAR_TO_DATE_MODE:
        baseline = "年初"
        period = "年初以来"
    elif comparison_mode == SNAPSHOT_COMPARISON_MODE:
        baseline = "对比时点"
        period = "当前时点本月"
    else:
        baseline = "上月"
        period = "本月"
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
        "质量提示：未分配经理、缺省分类、异常收益率和负收益资产用于提示阅读风险，不代表数据错误；需要结合对应模块的资产明细进一步核对。"
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
                    threshold_frame["color"] = "#C9A84C"
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


def render_equity_dashboard_bar_chart(
    frame: pd.DataFrame,
    metric: str,
    title: str,
    value_title: str,
    comparison_mode: str,
) -> None:
    chart_data = frame.copy()
    chart_data["_label"] = chart_data["equity_group_display_label"].astype(str)
    chart_data["_value"] = pd.to_numeric(chart_data[metric], errors="coerce")
    chart_data["_value_missing"] = chart_data["_value"].isna()
    chart_data["_plot_value"] = chart_data["_value"].fillna(0.0)
    chart_data["_value_label"] = chart_data["_plot_value"].map(
        lambda value: f"{value:.2%}" if metric in PCT_COLUMNS else f"{value:,.2f}"
    )
    chart_data.loc[chart_data["_value_missing"], "_value_label"] = "—"
    chart_data["_bar_color_group"] = np.where(chart_data["_plot_value"] < 0, "负向", "正向")

    valid_values = chart_data.loc[~chart_data["_value_missing"], "_plot_value"]
    min_value = min(float(valid_values.min()) if not valid_values.empty else 0.0, 0.0)
    max_value = max(float(valid_values.max()) if not valid_values.empty else 0.0, 0.0)
    minimum_span = 0.01 if metric in PCT_COLUMNS else 1.0
    span = max(max_value - min_value, abs(min_value), abs(max_value), minimum_span)
    padding = span * 0.08
    if min_value >= 0:
        domain = [0.0, max_value + padding]
    elif max_value <= 0:
        domain = [min_value - padding, 0.0]
    else:
        domain = [min_value - padding, max_value + padding]

    x_encoding = {
        "title": value_title,
        "axis": alt.Axis(format=".1%" if metric in PCT_COLUMNS else ",.1f"),
        "scale": alt.Scale(domain=domain),
    }
    y_encoding = alt.Y(
        "_label:N",
        title=None,
        sort=EQUITY_DASHBOARD_LABEL_ORDER,
        axis=alt.Axis(labelLimit=220),
    )
    tooltips = [
        alt.Tooltip("equity_scope:N", title="范围"),
        alt.Tooltip("_label:N", title="比较项"),
        alt.Tooltip("_value:Q", title=value_title, format=".2%" if metric in PCT_COLUMNS else ",.2f"),
    ]
    for column in [
        "full_market_value_current",
        "finance_income_mtd_current",
        "comprehensive_income_mtd_current",
        "avg_capital_mtd_current",
        "finance_return_mtd",
        "comprehensive_return_mtd",
    ]:
        if column == metric or column not in chart_data.columns:
            continue
        chart_data[column] = pd.to_numeric(chart_data[column], errors="coerce")
        tooltips.append(
            alt.Tooltip(
                f"{column}:Q",
                title=display_names_for_mode(comparison_mode).get(column, column),
                format=".2%" if column in PCT_COLUMNS else ",.2f",
            )
        )

    valid_chart_data = chart_data[~chart_data["_value_missing"]].copy()
    bars = (
        alt.Chart(valid_chart_data)
        .mark_bar(cornerRadiusEnd=2)
        .encode(
            x=alt.X("_plot_value:Q", **x_encoding),
            y=y_encoding,
            color=alt.Color(
                "_bar_color_group:N",
                title=None,
                scale=alt.Scale(
                    domain=["正向", "负向"],
                    range=[POSITIVE_COLOR, NEGATIVE_COLOR],
                ),
                legend=None,
            ),
            tooltip=tooltips,
        )
    )
    zero_rule = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(
        color="#475569",
        opacity=0.55,
    ).encode(x="x:Q")
    positive_value_labels = (
        alt.Chart(valid_chart_data[valid_chart_data["_plot_value"] >= 0])
        .mark_text(
            align="left",
            baseline="middle",
            dx=7,
            color="#0D0707",
            fontSize=12,
            fontWeight=600,
        )
        .encode(
            x=alt.X("_plot_value:Q", **x_encoding),
            y=y_encoding,
            text=alt.Text("_value_label:N"),
        )
    )
    negative_value_labels = (
        alt.Chart(valid_chart_data[valid_chart_data["_plot_value"] < 0])
        .mark_text(
            align="right",
            baseline="middle",
            dx=-7,
            color="#0D0707",
            fontSize=12,
            fontWeight=600,
        )
        .encode(
            x=alt.X("_plot_value:Q", **x_encoding),
            y=y_encoding,
            text=alt.Text("_value_label:N"),
        )
    )
    missing_value_labels = (
        alt.Chart(chart_data[chart_data["_value_missing"]])
        .mark_text(
            align="left",
            baseline="middle",
            dx=7,
            color="#5C6B7A",
            fontSize=12,
            fontWeight=600,
        )
        .encode(
            x=alt.X("_plot_value:Q", **x_encoding),
            y=y_encoding,
            text=alt.Text("_value_label:N"),
            tooltip=[
                alt.Tooltip("equity_scope:N", title="范围"),
                alt.Tooltip("_label:N", title="比较项"),
                alt.Tooltip("_value_label:N", title=value_title),
            ],
        )
    )
    chart = (
        (bars + zero_rule + positive_value_labels + negative_value_labels + missing_value_labels)
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
                    range=[POSITIVE_COLOR, NEGATIVE_COLOR, "#C9A84C", NEUTRAL_COLOR],
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
    if comparison_mode == YEAR_TO_DATE_MODE:
        outsourced_equity = adjust_outsourced_funding_capital(outsourced_equity)
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
    control_cols = st.columns(2)
    with control_cols[0]:
        selected_company = st.selectbox("委外公司", company_options, key="委外权益公司")
    with control_cols[1]:
        selected_equity_type = st.selectbox("权益类型", equity_type_options, key="委外权益类型")
    sort_choice = ALL

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
                    MANAGER_DISPLAY_COLUMN,
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


def render_equity_dashboard(
    data: pd.DataFrame,
    current_month: str,
    comparison_mode: str,
) -> None:
    summary = equity_dashboard_summary(data, current_month, comparison_mode)
    if comparison_mode == YEAR_TO_DATE_MODE:
        st.caption("六家境内权益委外收益率采用放款期平均占用估算，详见下方委内/委外比较中的原值对照。")
        income_title = "年初以来综合收益额"
    elif comparison_mode == SNAPSHOT_COMPARISON_MODE:
        income_title = "当前时点本月综合收益额"
    else:
        income_title = "本月综合收益额"

    chart_cols = st.columns(2)
    with chart_cols[0]:
        render_equity_dashboard_bar_chart(
            summary,
            "comprehensive_income_mtd_current",
            f"股票专项：{income_title}",
            display_names_for_mode(comparison_mode)["comprehensive_income_mtd_current"],
            comparison_mode,
        )
    with chart_cols[1]:
        render_equity_dashboard_bar_chart(
            summary,
            "comprehensive_return_mtd",
            "股票专项：综合收益率",
            display_names_for_mode(comparison_mode)["comprehensive_return_mtd"],
            comparison_mode,
        )

    st.dataframe(
        format_table(
            summary[
                [
                    "equity_scope",
                    "equity_group_display_label",
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


def render_outsourced_funding_note(data, snapshot_date):
    st.caption("六家境内权益委外的YTD收益率已按估算放款期修正平均资金占用，原始YTD收益额不变。")
    with st.expander("六家权益委外：放款期估算口径与原值对照"):
        st.caption(FUNDING_NOTE)
        current = data[data["snapshot_date"].astype(str).eq(str(snapshot_date))]
        if "attribution_in_scope" not in current:
            current = build_manager_attribution_rows(current)
        audit = funding_capital_audit(current, snapshot_date).rename(columns={
            "strategy_book": "委外账户", "funding_start_estimate": "估算放款日",
            "source_avg_capital_ytd": "源表YTD平均占用(亿)", "avg_capital_ytd": "放款期平均占用估算(亿)",
            "comprehensive_income_ytd": "YTD综合收益(亿)", "source_return": "源口径收益率", "funding_return": "修正收益率(估算)",
        })
        if not audit.empty:
            st.dataframe(audit.style.format({
                "源表YTD平均占用(亿)": "{:.4f}", "放款期平均占用估算(亿)": "{:.4f}",
                "YTD综合收益(亿)": "{:+.4f}", "源口径收益率": "{:.2%}", "修正收益率(估算)": "{:.2%}",
            }, na_rep="—"), hide_index=True, width="stretch")


def render_strategy_book_overview(
    data: pd.DataFrame,
    current_month: str,
    prior_month: str,
    comparison_mode: str,
) -> None:
    summary = strategy_book_summary(data, current_month, comparison_mode)
    detail = strategy_book_detail_summary(data, current_month, comparison_mode)
    if comparison_mode == YEAR_TO_DATE_MODE:
        render_outsourced_funding_note(data, current_month)

    if summary.empty or summary["record_count_current"].sum() == 0:
        st.info("当前没有可展示的委内/委外比较数据。")
        return

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
    income_colors = [NEUTRAL_COLOR, POSITIVE_COLOR, "#C9A84C", "#2F6B4F"]
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


def manager_attribution_metric_config(
    period_choice: str,
    view_choice: str,
) -> tuple[str, str, str, str]:
    period = MANAGER_ATTRIBUTION_PERIODS.get(
        period_choice,
        MANAGER_ATTRIBUTION_PERIODS[YEAR_TO_DATE_MODE],
    )
    metric_kind = "return" if view_choice == "综合收益率" else "income"
    metric = str(period[metric_kind])
    short_label = str(period["short_label"])
    if metric_kind == "return":
        return metric, f"{short_label}综合收益率", f"{short_label}综合收益率", ".1%"
    return metric, f"{short_label}综合收益额", f"{short_label}综合收益额(亿)", ",.1f"


def manager_attribution_period_for_mode(comparison_mode: str) -> str:
    """Map the global sidebar time view to the manager attribution metric period."""
    return YEAR_TO_DATE_MODE if comparison_mode == YEAR_TO_DATE_MODE else MONTH_REVIEW_MODE


def _manager_extreme(
    frame: pd.DataFrame,
    metric: str,
    direction: str,
) -> pd.Series | None:
    if frame.empty or metric not in frame.columns:
        return None
    working = frame.copy()
    working[metric] = pd.to_numeric(working[metric], errors="coerce")
    if direction == "positive":
        working = working[working[metric] > CHART_EPSILON]
        working = working.sort_values(metric, ascending=False)
    else:
        working = working[working[metric] < -CHART_EPSILON]
        working = working.sort_values(metric, ascending=True)
    return None if working.empty else working.iloc[0]


def _manager_focus_rows(
    frame: pd.DataFrame,
    metric: str,
    limit: int = 14,
) -> pd.DataFrame:
    if frame.empty or metric not in frame.columns:
        return frame.iloc[0:0].copy()
    working = frame.copy()
    working[metric] = pd.to_numeric(working[metric], errors="coerce")
    working = working.dropna(subset=[metric])
    working = working[working[metric].abs() > CHART_EPSILON]
    if len(working) <= limit:
        return working.sort_values(metric, ascending=False).reset_index(drop=True)

    positive_limit = limit // 2
    negative_limit = limit - positive_limit
    positive = working[working[metric] > 0].nlargest(positive_limit, metric)
    negative = working[working[metric] < 0].nsmallest(negative_limit, metric)
    selected_ids = set(
        pd.concat([positive, negative], ignore_index=True)["attribution_entity_id"]
        .astype(str)
        .tolist()
    )
    remaining = limit - len(selected_ids)
    if remaining > 0:
        extras = (
            working[
                ~working["attribution_entity_id"].astype(str).isin(selected_ids)
            ]
            .assign(_abs_metric=lambda data: data[metric].abs())
            .nlargest(remaining, "_abs_metric")
            .drop(columns="_abs_metric")
        )
        focus = pd.concat([positive, negative, extras], ignore_index=True)
    else:
        focus = pd.concat([positive, negative], ignore_index=True)
    return (
        focus.drop_duplicates("attribution_entity_id")
        .sort_values(metric, ascending=False)
        .reset_index(drop=True)
    )


def render_manager_attribution_coverage(
    coverage: dict[str, float],
    current_snapshot: str,
) -> None:
    coverage_ratio = float(coverage.get("market_value_coverage", np.nan))
    net_coverage = float(coverage.get("net_market_value_coverage", np.nan))
    row_coverage = float(coverage.get("row_coverage", np.nan))
    bar_ratio = min(max(coverage_ratio, 0.0), 1.0) if np.isfinite(coverage_ratio) else 0.0
    ratio_label = pct(coverage_ratio)
    st.markdown(
        f"""
        <div class="attribution-coverage">
            <div class="attribution-coverage-head">
                <span>归因完整性 · {html_text(snapshot_display_label(current_snapshot))}</span>
                <strong>{html_text(ratio_label)}</strong>
            </div>
            <div class="attribution-coverage-track">
                <div class="attribution-coverage-fill" style="width:{bar_ratio * 100:.2f}%"></div>
            </div>
            <div class="attribution-coverage-meta">
                <span>按绝对市值计算，避免正负调节项互相抵消</span>
                <span>签名净额归属比 {html_text(pct(net_coverage))}（受正负调节影响可超 100%）</span>
                <span>行覆盖 {html_text(pct(row_coverage))}</span>
                <span>未归属绝对市值 {html_text(amount(float(coverage.get('unattributed_absolute_market_value', 0.0))))} / 净额 {html_text(amount(float(coverage.get('unattributed_market_value', 0.0))))}</span>
                <span>层级去重 {html_text(amount(float(coverage.get('excluded_market_value', 0.0))))} / {int(coverage.get('excluded_row_count', 0)):,} 行</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_manager_attribution_overview(
    summary: pd.DataFrame,
    changes: pd.DataFrame,
    period_choice: str,
) -> None:
    period = MANAGER_ATTRIBUTION_PERIODS[period_choice]
    income_metric = str(period["income"])
    short_label = str(period["short_label"])
    contributor = _manager_extreme(summary, income_metric, "positive")
    detractor = _manager_extreme(summary, income_metric, "negative")
    increase = _manager_extreme(changes, "estimated_flow", "positive")
    decrease = _manager_extreme(changes, "estimated_flow", "negative")
    income_values = pd.to_numeric(summary[income_metric], errors="coerce").fillna(0.0)
    total_income = float(income_values.sum())
    positive_count = int((income_values > CHART_EPSILON).sum())
    negative_count = int((income_values < -CHART_EPSILON).sum())
    current_market_delta = np.nan
    if not changes.empty and "full_market_value_delta" in changes.columns:
        current_market_delta = float(
            pd.to_numeric(changes["full_market_value_delta"], errors="coerce")
            .fillna(0.0)
            .sum()
        )
    market_card_delta = f"{len(summary):,} 个主体"
    if np.isfinite(current_market_delta):
        market_card_delta += f" · 较基准 {signed_amount(current_market_delta)}"

    def extreme_card(
        row: pd.Series | None,
        *,
        label: str,
        metric: str,
        empty_value: str,
        tone: str,
    ) -> dict[str, str]:
        if row is None:
            return {"label": label, "value": empty_value, "delta": "当前口径无记录"}
        scope = str(row.get("attribution_scope", "")).strip()
        delta = signed_amount(float(row[metric]))
        if scope:
            delta = f"{delta} · {scope}"
        return {
            "label": label,
            "value": str(row["attribution_entity_name"]),
            "delta": delta,
            "delta_tone": tone,
            "tone": tone,
        }

    cards: list[dict[str, str]] = [
        {
            "label": "当前归因市值",
            "value": amount(float(summary["full_market_value"].sum())),
            "delta": market_card_delta,
        },
        {
            "label": f"{short_label}综合收益",
            "value": signed_amount(total_income),
            "delta": f"{positive_count} 个贡献 / {negative_count} 个拖累",
            "delta_tone": "positive" if total_income >= 0 else "negative",
            "tone": "positive" if total_income >= 0 else "negative",
        },
        extreme_card(
            contributor,
            label="贡献第一",
            metric=income_metric,
            empty_value="本期无正贡献",
            tone="positive",
        ),
        extreme_card(
            detractor,
            label="拖累第一",
            metric=income_metric,
            empty_value="本期无负贡献",
            tone="negative",
        ),
        extreme_card(
            increase,
            label="估算净增配最大",
            metric="estimated_flow",
            empty_value="本期无净增配" if not changes.empty else "暂无可比时点",
            tone="positive",
        ),
        extreme_card(
            decrease,
            label="估算净减配最大",
            metric="estimated_flow",
            empty_value="本期无净减配" if not changes.empty else "暂无可比时点",
            tone="negative",
        ),
    ]
    render_kpi_grid(cards, grid_class="kpi-grid-attribution")
    if not changes.empty:
        prior_snapshot = str(changes["prior_snapshot_date"].iloc[0])
        st.caption(
            f"估算净配置变化 = 当前市值 − {prior_snapshot} 月末市值 − 当前MTD综合收益；"
            "用于复盘资金方向，不等同于交易流水。"
        )


def render_manager_contribution_ranking(
    summary: pd.DataFrame,
    period_choice: str,
    view_choice: str = "综合收益额",
    title_prefix: str = "",
) -> None:
    period = MANAGER_ATTRIBUTION_PERIODS[period_choice]
    income_metric = str(period["income"])
    return_metric = str(period["return"])
    short_label = str(period["short_label"])
    metric, metric_label, value_title, axis_format = manager_attribution_metric_config(
        period_choice,
        view_choice,
    )
    is_return_view = view_choice == "综合收益率"
    metric_text = "综合收益率" if is_return_view else "综合收益额"
    secondary_metric = income_metric if is_return_view else return_metric
    secondary_title = (
        f"{short_label}综合收益额(亿)"
        if is_return_view
        else f"{short_label}综合收益率"
    )
    secondary_format = ",.2f" if is_return_view else ".2%"
    chart_data = summary.copy()
    chart_data[metric] = pd.to_numeric(chart_data[metric], errors="coerce")
    chart_data = chart_data.dropna(subset=[metric]).reset_index(drop=True)
    st.markdown(f"#### {title_prefix}{short_label}{metric_text}贡献 / 拖累全景")
    if chart_data.empty:
        st.info(f"当前口径暂无可供展示的{metric_text}贡献。")
        return

    chart_data = chart_data.copy()
    chart_data[income_metric] = pd.to_numeric(chart_data[income_metric], errors="coerce")
    chart_data[return_metric] = pd.to_numeric(chart_data[return_metric], errors="coerce")
    chart_data["full_market_value"] = pd.to_numeric(
        chart_data["full_market_value"], errors="coerce"
    )
    chart_data["_entity_label"] = (
        chart_data["attribution_entity_name"].astype(str)
        + " · "
        + chart_data["attribution_scope"].astype(str)
    )
    chart_data["_value"] = pd.to_numeric(chart_data[metric], errors="coerce")
    chart_data = chart_data.sort_values(
        ["_value", "_entity_label"], ascending=[False, True], kind="stable"
    )
    entity_order = chart_data["_entity_label"].tolist()
    chart_data["_value_label"] = chart_data["_value"].map(
        lambda value: f"{value:+.2%}" if is_return_view else f"{value:+,.2f}"
    )
    chart_data["_direction"] = np.where(chart_data["_value"] >= 0, "贡献", "拖累")
    full_ranks = pd.to_numeric(summary[metric], errors="coerce").rank(
        method="min",
        ascending=False,
    )
    rank_map = dict(zip(summary["attribution_entity_id"].astype(str), full_ranks))
    chart_data["_board_rank"] = chart_data["attribution_entity_id"].astype(str).map(rank_map)
    chart_data["_rank_label"] = chart_data["_board_rank"].map(
        lambda value: f"第 {int(value)} / {full_ranks.count()} 名" if pd.notna(value) else "无排名"
    )
    # Keep a fixed transition per unit so changing the period does not change
    # the compression rule. Pad in display space to leave room for end labels.
    scale_constant = 0.01 if is_return_view else 1.0
    bounds = np.array([
        min(float(chart_data["_value"].min()), 0.0),
        max(float(chart_data["_value"].max()), 0.0),
    ])
    display_bounds = np.sign(bounds) * np.log1p(np.abs(bounds) / scale_constant)
    display_span = max(float(display_bounds[1] - display_bounds[0]), 1.0)
    padded_bounds = display_bounds + np.array([-0.12, 0.12]) * display_span
    domain = (
        np.sign(padded_bounds) * scale_constant * np.expm1(np.abs(padded_bounds))
    ).tolist()
    x_scale = alt.Scale(type="symlog", constant=scale_constant, domain=domain)
    y_encoding = alt.Y(
        "_entity_label:N",
        title=None,
        # All layers share one order, including the positive/negative label subsets.
        sort=entity_order,
        scale=alt.Scale(domain=entity_order),
        axis=alt.Axis(labelLimit=250),
    )
    x_encoding = alt.X(
        "_value:Q",
        title=value_title,
        scale=x_scale,
        axis=alt.Axis(format=axis_format),
    )
    tooltips = [
        alt.Tooltip("_entity_label:N", title="归因主体"),
        alt.Tooltip("_value:Q", title=value_title, format=",.2f" if not is_return_view else ".2%"),
        alt.Tooltip(secondary_metric + ":Q", title=secondary_title, format=secondary_format),
        alt.Tooltip("full_market_value:Q", title="当前市值(亿)", format=",.2f"),
        alt.Tooltip("_rank_label:N", title="全板块排名"),
    ]
    capital_metric = "avg_capital_ytd" if period_choice == YEAR_TO_DATE_MODE else "avg_capital_mtd"
    if is_return_view and capital_metric in chart_data.columns:
        tooltips.insert(
            3,
            alt.Tooltip(f"{capital_metric}:Q", title=f"{short_label}平均资金占用(亿)", format=",.4f"),
        )
    bars = (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusEnd=3)
        .encode(
            x=x_encoding,
            y=y_encoding,
            color=alt.Color(
                "_direction:N",
                title=None,
                scale=alt.Scale(
                    domain=["贡献", "拖累"],
                    range=["#2F7A6B", NEGATIVE_COLOR],
                ),
                legend=None,
            ),
            tooltip=tooltips,
        )
    )
    zero_rule = alt.Chart(pd.DataFrame({"x": [0.0]})).mark_rule(
        color="#64748B",
        opacity=0.65,
    ).encode(x=alt.X("x:Q", scale=x_scale))
    positive_labels = (
        alt.Chart(chart_data[chart_data["_value"] >= 0])
        .mark_text(align="left", baseline="middle", dx=7, fontSize=11, fontWeight=600)
        .encode(x=x_encoding, y=y_encoding, text="_value_label:N")
    )
    negative_labels = (
        alt.Chart(chart_data[chart_data["_value"] < 0])
        .mark_text(align="right", baseline="middle", dx=-7, fontSize=11, fontWeight=600)
        .encode(x=x_encoding, y=y_encoding, text="_value_label:N")
    )
    chart = (
        (bars + zero_rule + positive_labels + negative_labels)
        .properties(height=max(320, len(chart_data) * 26))
        .configure_view(strokeWidth=0)
    )
    st.altair_chart(chart, width="stretch")
    st.caption(
        f"已展示 {len(chart_data)} / {len(summary)} 个主体（含零收益主体）；"
        f"自上而下按{metric_text}从高到低排列，同值按主体名称排序；"
        "横轴采用对称对数刻度，大值经过压缩，条形长度不代表收益倍数；"
        "刻度、标签和悬停数字均为实际值。"
        f"绿色为贡献、红色为拖累，排名基于全部{len(summary)}个主体。"
        + ("收益率 = 同期综合收益额 / 平均资金占用，较小的分母可能放大比例。" if is_return_view else "")
    )


def render_manager_comparison_ranking(
    changes: pd.DataFrame,
    current_snapshot: str,
    prior_snapshot: str,
) -> None:
    """Show the manager-level scale change against the selected snapshot."""
    required = {
        "attribution_entity_name",
        "attribution_scope",
        "current_full_market_value",
        "prior_full_market_value",
        "full_market_value_delta",
        "estimated_flow",
    }
    if changes.empty or not prior_snapshot or not required.issubset(changes.columns):
        return

    chart_data = changes.copy()
    for column in required - {"attribution_entity_name", "attribution_scope"}:
        chart_data[column] = pd.to_numeric(chart_data[column], errors="coerce")
    chart_data = chart_data.dropna(subset=["full_market_value_delta"]).reset_index(drop=True)
    if chart_data.empty:
        return
    chart_data["_entity_label"] = (
        chart_data["attribution_entity_name"].astype(str)
        + " · "
        + chart_data["attribution_scope"].astype(str)
    )
    chart_data["_value"] = chart_data["full_market_value_delta"]
    chart_data["_value_label"] = chart_data["_value"].map(lambda value: f"{value:+,.2f}")
    chart_data["_direction"] = np.where(chart_data["_value"] >= 0, "增加", "减少")
    value_span = max(
        float(chart_data["_value"].max() - chart_data["_value"].min()),
        float(chart_data["_value"].abs().max()),
        1.0,
    )
    domain = [
        min(float(chart_data["_value"].min()), 0.0) - value_span * 0.12,
        max(float(chart_data["_value"].max()), 0.0) + value_span * 0.12,
    ]
    y_encoding = alt.Y(
        "_entity_label:N",
        title=None,
        sort=alt.SortField(field="_value", order="descending"),
        axis=alt.Axis(labelLimit=250),
    )
    x_encoding = alt.X(
        "_value:Q",
        title="较对比时点市值变化(亿)",
        scale=alt.Scale(domain=domain),
        axis=alt.Axis(format=",.1f"),
    )
    bars = (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusEnd=3)
        .encode(
            x=x_encoding,
            y=y_encoding,
            color=alt.Color(
                "_direction:N",
                title=None,
                scale=alt.Scale(
                    domain=["增加", "减少"],
                    range=["#2F7A6B", NEGATIVE_COLOR],
                ),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("_entity_label:N", title="归因主体"),
                alt.Tooltip("_value:Q", title="较对比时点市值变化(亿)", format=",.2f"),
                alt.Tooltip("current_full_market_value:Q", title="当前市值(亿)", format=",.2f"),
                alt.Tooltip("prior_full_market_value:Q", title="对比时点市值(亿)", format=",.2f"),
                alt.Tooltip("estimated_flow:Q", title="估算净配置变化(亿)", format=",.2f"),
            ],
        )
    )
    zero_rule = alt.Chart(pd.DataFrame({"x": [0.0]})).mark_rule(
        color="#64748B",
        opacity=0.65,
    ).encode(x="x:Q")
    positive_labels = (
        alt.Chart(chart_data[chart_data["_value"] >= 0])
        .mark_text(align="left", baseline="middle", dx=7, fontSize=11, fontWeight=600)
        .encode(x=x_encoding, y=y_encoding, text="_value_label:N")
    )
    negative_labels = (
        alt.Chart(chart_data[chart_data["_value"] < 0])
        .mark_text(align="right", baseline="middle", dx=-7, fontSize=11, fontWeight=600)
        .encode(x=x_encoding, y=y_encoding, text="_value_label:N")
    )
    chart = (
        (bars + zero_rule + positive_labels + negative_labels)
        .properties(height=max(320, len(chart_data) * 26))
        .configure_view(strokeWidth=0)
    )
    st.markdown("#### 较对比时点市值变化全景")
    st.altair_chart(chart, width="stretch")
    st.caption(
        f"当前时点 {snapshot_display_label(current_snapshot)} 对比 "
        f"{snapshot_display_label(prior_snapshot)}；绿色为市值增加，红色为市值减少。"
    )


def render_manager_comparison_table(
    changes: pd.DataFrame,
    current_snapshot: str,
    prior_snapshot: str,
    table_key: str,
) -> None:
    """Show the manager-level current-vs-baseline values for snapshot comparison."""
    if changes.empty or not prior_snapshot:
        return

    working = changes.copy()
    required = {
        "attribution_entity_name",
        "attribution_scope",
        "current_full_market_value",
        "prior_full_market_value",
        "full_market_value_delta",
        "estimated_flow",
    }
    if not required.issubset(working.columns):
        return
    for column in required - {"attribution_entity_name", "attribution_scope"}:
        working[column] = pd.to_numeric(working[column], errors="coerce")
    working["_abs_delta"] = working["full_market_value_delta"].abs()
    working = working.sort_values("_abs_delta", ascending=False).drop(columns="_abs_delta")
    display = working.rename(
        columns={
            "attribution_entity_name": "投资经理/受托机构",
            "attribution_scope": "委内/委外",
            "current_full_market_value": "当前市值(亿)",
            "prior_full_market_value": "对比时点市值(亿)",
            "full_market_value_delta": "较对比时点变化(亿)",
            "estimated_flow": "估算净配置变化(亿)",
        }
    )[
        [
            "投资经理/受托机构",
            "委内/委外",
            "当前市值(亿)",
            "对比时点市值(亿)",
            "较对比时点变化(亿)",
            "估算净配置变化(亿)",
        ]
    ]
    styled = display.style.format(
        {
            "当前市值(亿)": "{:,.2f}",
            "对比时点市值(亿)": "{:,.2f}",
            "较对比时点变化(亿)": "{:+,.2f}",
            "估算净配置变化(亿)": "{:+,.2f}",
        },
        na_rep="—",
    )
    st.markdown("#### 较对比数据时点变化")
    st.caption(
        f"当前时点 {snapshot_display_label(current_snapshot)} 对比 "
        f"{snapshot_display_label(prior_snapshot)}；按市值变化排序，估算净配置变化已扣除当前时点本月综合收益。"
    )
    st.dataframe(styled, width="stretch", hide_index=True, key=table_key)


def render_manager_asset_contribution_chart(
    asset_detail: pd.DataFrame,
    period_choice: str,
) -> None:
    period = MANAGER_ATTRIBUTION_PERIODS[period_choice]
    income_metric = str(period["income"])
    return_metric = str(period["return"])
    short_label = str(period["short_label"])
    st.markdown("#### 资产收益贡献 / 拖累")
    if asset_detail.empty or income_metric not in asset_detail.columns:
        st.info("当前主体暂无资产收益贡献可供展示。")
        return

    working = asset_detail.copy()
    working[income_metric] = pd.to_numeric(working[income_metric], errors="coerce")
    working[return_metric] = pd.to_numeric(working[return_metric], errors="coerce")
    working = working.dropna(subset=[income_metric])
    working = working[working[income_metric].abs() > CHART_EPSILON]
    if working.empty:
        st.info("当前主体暂无非零资产收益贡献。")
        return
    working["attribution_entity_id"] = working["asset_key"].astype(str)
    chart_data = _manager_focus_rows(working, income_metric, limit=12)
    duplicate_names = chart_data["asset_name"].astype(str).duplicated(keep=False)
    chart_data["_asset_label"] = chart_data["asset_name"].astype(str)
    chart_data.loc[duplicate_names, "_asset_label"] = (
        chart_data.loc[duplicate_names, "asset_name"].astype(str)
        + " · "
        + chart_data.loc[duplicate_names, "account_bucket"].astype(str)
    )
    chart_data["_value"] = pd.to_numeric(chart_data[income_metric], errors="coerce")
    chart_data["_value_label"] = chart_data["_value"].map(lambda value: f"{value:+,.2f}")
    chart_data["_direction"] = np.where(chart_data["_value"] >= 0, "贡献", "拖累")
    y_encoding = alt.Y(
        "_asset_label:N",
        title=None,
        sort=alt.SortField(field="_value", order="descending"),
        axis=alt.Axis(labelLimit=260),
    )
    bars = (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusEnd=3)
        .encode(
            x=alt.X("_value:Q", title=f"{short_label}综合收益额(亿)", axis=alt.Axis(format=",.1f")),
            y=y_encoding,
            color=alt.Color(
                "_direction:N",
                scale=alt.Scale(domain=["贡献", "拖累"], range=["#2F7A6B", NEGATIVE_COLOR]),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("asset_name:N", title="资产名称"),
                alt.Tooltip("asset_class:N", title="投资品种"),
                alt.Tooltip("account_bucket:N", title="账户"),
                alt.Tooltip("_value:Q", title=f"{short_label}综合收益额(亿)", format=",.2f"),
                alt.Tooltip(f"{return_metric}:Q", title=f"{short_label}综合收益率", format=".2%"),
                alt.Tooltip("full_market_value:Q", title="当前市值(亿)", format=",.2f"),
            ],
        )
    )
    zero_rule = alt.Chart(pd.DataFrame({"x": [0.0]})).mark_rule(
        color="#64748B",
        opacity=0.65,
    ).encode(x="x:Q")
    chart = (bars + zero_rule).properties(height=max(300, len(chart_data) * 30)).configure_view(strokeWidth=0)
    st.altair_chart(chart, width="stretch")
    st.caption("本图按收益额直接展示资产贡献与拖累；持仓规模结构在下方单独呈现。")


def manager_attribution_entity_labels(summary: pd.DataFrame) -> dict[str, str]:
    if summary.empty:
        return {}
    return {
        str(row["attribution_entity_id"]): (
            f"{row['attribution_entity_name']} · {row['attribution_scope']}"
        )
        for _, row in summary.iterrows()
    }


def render_manager_attribution_timeseries_chart(
    timeseries: pd.DataFrame,
    selected_entities: list[str],
    entity_labels: dict[str, str],
    primary_entity: str,
    metric: str,
    metric_label: str,
    value_title: str,
    axis_format: str,
    chart_key: str,
) -> None:
    ranked_data = rank_manager_timeseries(
        timeseries,
        selected_entities,
        metric,
    )
    chart_data = ranked_data.dropna(subset=[metric]).copy()
    if chart_data.empty:
        st.info("所选主体在当前时点范围内暂无可展示的趋势数据。")
        return

    chart_data["_snapshot_label"] = chart_data["snapshot_date"].astype(str)
    interim = chart_data["snapshot_status"].eq(SNAPSHOT_STATUS_INTERIM)
    chart_data.loc[interim, "_snapshot_label"] += "（临时）"
    chart_data = chart_data.sort_values("snapshot_date")
    chart_data["_rank_label"] = chart_data.apply(
        lambda row: (
            f"全板块第 {int(row['board_rank'])} / {int(row['board_count'])} 名"
            if pd.notna(row["board_rank"]) and pd.notna(row["board_count"])
            else "全板块无排名"
        ),
        axis=1,
    )
    if metric.startswith("comprehensive_return"):
        chart_data["_value_label"] = chart_data[metric].map(pct)
    else:
        chart_data["_value_label"] = chart_data[metric].map(amount)

    snapshot_metadata = timeseries[
        ["snapshot_date", "snapshot_status"]
    ].drop_duplicates("snapshot_date").copy()
    snapshot_metadata["snapshot_date"] = snapshot_metadata["snapshot_date"].astype(str)
    snapshot_metadata["_snapshot_label"] = snapshot_metadata["snapshot_date"]
    snapshot_labels = snapshot_metadata.set_index("snapshot_date")["_snapshot_label"].to_dict()
    interim_dates = set(
        timeseries.loc[
            timeseries["snapshot_status"].eq(SNAPSHOT_STATUS_INTERIM),
            "snapshot_date",
        ].astype(str)
    )
    for snapshot_date in interim_dates:
        snapshot_labels[snapshot_date] = f"{snapshot_date}（临时）"
    all_snapshot_dates = sorted(timeseries["snapshot_date"].astype(str).unique().tolist())
    hover_anchor = float(chart_data[metric].median())
    figure = go.Figure()
    for entity_index, entity_id in enumerate(selected_entities):
        entity_data = chart_data[
            chart_data["attribution_entity_id"].astype(str).eq(str(entity_id))
        ].sort_values("snapshot_date")
        label = entity_labels.get(str(entity_id), str(entity_id))
        is_primary = str(entity_id) == str(primary_entity)
        trace_label = f"{label}（观察）" if is_primary else label
        color = MANAGER_ATTRIBUTION_COLORS[
            entity_index % len(MANAGER_ATTRIBUTION_COLORS)
        ]
        figure.add_trace(
            go.Scatter(
                x=pd.to_datetime(entity_data["snapshot_date"], errors="coerce"),
                y=entity_data[metric],
                mode="lines+markers",
                name=trace_label,
                connectgaps=False,
                line={
                    "color": color,
                    "width": 3.6 if is_primary else 2.1,
                    "dash": "solid",
                },
                marker={
                    "size": 9 if is_primary else 7,
                    "color": color,
                    "line": {"color": "#FFFFFF", "width": 1.2},
                },
                hoverinfo="skip",
            )
        )

        hover_rows = pd.DataFrame({"snapshot_date": all_snapshot_dates})
        hover_rows = hover_rows.merge(
            entity_data[
                ["snapshot_date", "_rank_label", "_value_label"]
            ].assign(snapshot_date=lambda frame: frame["snapshot_date"].astype(str)),
            how="left",
            on="snapshot_date",
        )
        hover_rows["_entity_label"] = trace_label
        hover_rows["_rank_label"] = hover_rows["_rank_label"].fillna("无排名")
        hover_rows["_value_label"] = hover_rows["_value_label"].fillna("无数据")
        hover_rows["_snapshot_label"] = hover_rows["snapshot_date"].map(snapshot_labels)
        figure.add_trace(
            go.Scatter(
                x=pd.to_datetime(hover_rows["snapshot_date"], errors="coerce"),
                y=[hover_anchor] * len(hover_rows),
                mode="markers",
                name=label,
                showlegend=False,
                marker={"size": 16, "color": "rgba(0,0,0,0)"},
                customdata=hover_rows[
                    ["_entity_label", "_rank_label", "_value_label", "_snapshot_label"]
                ].to_numpy(),
                hovertemplate=(
                    "<b>%{customdata[0]}</b>｜%{customdata[1]}｜%{customdata[2]}"
                    "<extra></extra>"
                ),
            )
        )

    date_axis_values = pd.to_datetime(
        sorted(chart_data["snapshot_date"].astype(str).unique().tolist())
    ).tolist()
    st.markdown(f"##### {metric_label}趋势")
    figure.update_layout(
        height=430,
        margin={"t": 66, "r": 22, "b": 62, "l": 70},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Microsoft YaHei, Arial, sans-serif", "color": "#4B5563"},
        hovermode="x unified",
        hoverdistance=-1,
        hoverlabel={
            "bgcolor": "#FFFBF3",
            "bordercolor": "#C7B27A",
            "font": {"color": "#0D1B2A", "size": 13},
            "namelength": -1,
        },
        legend={
            "orientation": "h",
            "x": 0,
            "y": 1.08,
            "xanchor": "left",
            "yanchor": "bottom",
            "font": {"size": 12},
        },
        xaxis={
            "title": None,
            "tickmode": "array",
            "tickvals": date_axis_values,
            "tickformat": "%Y-%m-%d",
            "tickangle": -20,
            "showgrid": False,
            "showspikes": True,
            "spikemode": "across",
            "spikesnap": "cursor",
            "spikecolor": "#94A3B8",
            "spikethickness": 1,
        },
        yaxis={
            "title": value_title,
            "tickformat": axis_format,
            "rangemode": "normal" if metric.startswith("comprehensive_return") else "tozero",
            "gridcolor": "#E3E8ED",
            "zerolinecolor": "#94A3B8",
            "zerolinewidth": 1,
        },
    )
    st.plotly_chart(
        figure,
        width="stretch",
        config={"displayModeBar": False, "scrollZoom": False},
        key=chart_key,
    )
    st.caption("悬浮任一数据时点，可同时查看观察主体与比较主体的指标值；排名均按该时点全板块主体计算。")


def render_manager_holding_treemap(
    holdings: pd.DataFrame,
    asset_detail: pd.DataFrame,
    chart_key: str,
    period_choice: str = YEAR_TO_DATE_MODE,
) -> None:
    st.markdown("#### 持仓规模结构")
    if holdings.empty:
        st.info("当前主体暂无正市值持仓可供展示，完整记录仍保留在下方资产明细中。")
        return
    prior_snapshot_date = str(holdings["prior_snapshot_date"].iloc[0] or "")
    prior_available = bool(prior_snapshot_date)
    if prior_available:
        st.caption(
            f"面积代表当前市值，百分比为正市值持仓占比；较 {prior_snapshot_date} 月末："
            "↑ 估算加仓，↓ 估算减仓，NEW 新建仓，→ 基本持平。"
            "加减仓按市值变化扣除本月综合收益估算，并非交易流水。"
        )
    else:
        st.caption("面积代表当前市值，百分比为正市值持仓占比；暂无上一月末正式版，因此不显示仓位变化标记。")

    palette = [
        "#1B3A5C",
        "#2F7A6B",
        "#B07A27",
        "#6B5791",
        "#3F70A3",
        "#8C3A3A",
        "#397A87",
        "#755744",
        "#536574",
    ]
    class_order = holdings.groupby("asset_class", dropna=False)["full_market_value"].sum().sort_values(ascending=False).index.tolist()
    color_map = {asset_class: palette[index % len(palette)] for index, asset_class in enumerate(class_order)}
    period_config = MANAGER_ATTRIBUTION_PERIODS[period_choice]
    income_metric = str(period_config["income"])
    return_metric = str(period_config["return"])
    capital_metric = "avg_capital_ytd" if period_choice == YEAR_TO_DATE_MODE else "avg_capital_mtd"
    period_label = str(period_config["short_label"])

    class_summary = (
        holdings.groupby("asset_class", dropna=False)
        .agg(
            full_market_value=("full_market_value", "sum"),
            market_value_share=("market_value_share", "sum"),
            prior_full_market_value=("prior_full_market_value", "sum"),
            monthly_position_flow_delta=("monthly_position_flow_delta", "sum"),
            period_income=(income_metric, "sum"),
            period_capital=(capital_metric, "sum"),
            holding_count=("holding_count", "sum"),
        )
        .reindex(class_order)
        .reset_index()
    )
    class_summary["period_return"] = np.where(
        class_summary["period_capital"] > RETURN_BASE_THRESHOLD,
        class_summary["period_income"] / class_summary["period_capital"],
        np.nan,
    )
    if not prior_available:
        class_summary["prior_full_market_value"] = np.nan
        class_summary["monthly_position_flow_delta"] = np.nan
    class_summary["position_change_status"] = class_summary.apply(
        lambda row: holding_position_change_status(
            float(row["full_market_value"]),
            float(row["prior_full_market_value"]),
            float(row["monthly_position_flow_delta"]),
            prior_available,
        ),
        axis=1,
    )

    labels: list[str] = []
    node_ids: list[str] = []
    parents: list[str] = []
    values: list[float] = []
    colors: list[str] = []
    hover_data: list[list[str]] = []

    def add_node(
        *,
        label: str,
        node_id: str,
        parent: str,
        asset_class: str,
        market_value: float,
        market_value_share: float,
        period_income: float,
        period_return: float,
        prior_market_value: float,
        position_flow_delta: float,
        position_change_status: str,
        note: str,
    ) -> None:
        badge = {
            "new": "NEW",
            "increase": "↑",
            "decrease": "↓",
            "flat": "→",
            "unavailable": "",
        }.get(position_change_status, "")
        if position_change_status == "new":
            change_description = "NEW 新建仓"
        elif position_change_status == "increase":
            change_description = f"↑ 估算加仓 {signed_amount(position_flow_delta)}"
        elif position_change_status == "decrease":
            change_description = f"↓ 估算减仓 {signed_amount(position_flow_delta)}"
        elif position_change_status == "flat":
            change_description = "→ 基本持平"
        else:
            change_description = "暂无上一月末正式版"
        labels.append(label)
        node_ids.append(node_id)
        parents.append(parent)
        values.append(market_value)
        colors.append(color_map[asset_class])
        hover_data.append(
            [
                asset_class,
                amount(market_value),
                pct(market_value_share),
                signed_amount(period_income),
                pct(period_return),
                note,
                badge,
                prior_snapshot_date or "—",
                amount(prior_market_value) if prior_available else "—",
                change_description,
            ]
        )

    for class_index, class_row in class_summary.iterrows():
        asset_class = str(class_row["asset_class"])
        class_id = f"asset-class-{class_index}"
        class_count = int(class_row["holding_count"])
        add_node(
            label=asset_class,
            node_id=class_id,
            parent="",
            asset_class=asset_class,
            market_value=float(class_row["full_market_value"]),
            market_value_share=float(class_row["market_value_share"]),
            period_income=float(class_row["period_income"]),
            period_return=float(class_row["period_return"]),
            prior_market_value=float(class_row["prior_full_market_value"]),
            position_flow_delta=float(class_row["monthly_position_flow_delta"]),
            position_change_status=str(class_row["position_change_status"]),
            note=f"共 {class_count:,} 项持仓",
        )
        class_holdings = holdings[holdings["asset_class"].astype(str).eq(asset_class)]
        for holding_index, holding in class_holdings.iterrows():
            holding_count = int(holding["holding_count"])
            note = "单项资产" if holding["holding_kind"] == "单项资产" else f"合并 {holding_count:,} 项长尾持仓"
            add_node(
                label=str(holding["holding_label"]),
                node_id=f"holding-{class_index}-{holding_index}",
                parent=class_id,
                asset_class=asset_class,
                market_value=float(holding["full_market_value"]),
                market_value_share=float(holding["market_value_share"]),
                period_income=float(holding[income_metric]),
                period_return=float(holding[return_metric]),
                prior_market_value=float(holding["prior_full_market_value"]),
                position_flow_delta=float(holding["monthly_position_flow_delta"]),
                position_change_status=str(holding["position_change_status"]),
                note=note,
            )

    figure = go.Figure(
        go.Treemap(
            labels=labels,
            ids=node_ids,
            parents=parents,
            values=values,
            branchvalues="total",
            customdata=hover_data,
            marker={"colors": colors, "line": {"color": "#FFFBF3", "width": 2}},
            texttemplate="<b>%{label}</b><br>%{customdata[2]} %{customdata[6]}",
            hovertemplate=(
                "<b>%{label}</b><br>"
                "投资品种：%{customdata[0]}<br>"
                "当前市值：%{customdata[1]}<br>"
                "正市值持仓占比：%{customdata[2]}<br>"
                f"{period_label} 综合收益：%{{customdata[3]}}<br>"
                f"{period_label} 综合收益率：%{{customdata[4]}}<br>"
                "上月末时点：%{customdata[7]}<br>"
                "上月末市值：%{customdata[8]}<br>"
                "仓位变化：%{customdata[9]}<br>"
                "%{customdata[5]}"
                "<extra></extra>"
            ),
            tiling={"packing": "squarify", "pad": 2},
            pathbar={"visible": False},
        )
    )
    figure.update_layout(
        height=520,
        margin={"t": 8, "r": 8, "b": 8, "l": 8},
        paper_bgcolor="rgba(0,0,0,0)",
        font={"family": "Microsoft YaHei, Arial, sans-serif", "color": "#FFFFFF", "size": 13},
        uniformtext={"minsize": 10, "mode": "hide"},
    )
    st.plotly_chart(
        figure,
        width="stretch",
        config={"displayModeBar": False, "scrollZoom": False},
        key=chart_key,
    )

    if not asset_detail.empty:
        market_values = pd.to_numeric(asset_detail["full_market_value"], errors="coerce").fillna(0.0)
        omitted = asset_detail[market_values <= RETURN_BASE_THRESHOLD]
        if not omitted.empty:
            st.caption(
                f"另有 {len(omitted):,} 条零值或负值调节记录未占用地图面积"
                f"（合计 {float(market_values.loc[omitted.index].sum()):,.2f} 亿），仍保留在下方资产明细中。"
            )


def render_manager_exited_holdings(
    exited_holdings: pd.DataFrame,
    prior_snapshot: str,
    table_key: str,
) -> None:
    if exited_holdings.empty:
        return
    st.markdown("#### 本月完全退出资产")
    st.caption(
        f"以下资产在当前时点市值已归零，因此不进入持仓面积图；"
        f"仍按 {prior_snapshot} 月末市值保留在减持复盘中。"
    )
    if len(exited_holdings) > 50:
        st.caption(f"完全退出资产共 {len(exited_holdings):,} 项，按估算减配幅度展示前 50 项。")
    st.dataframe(
        format_table(
            exited_holdings.head(50)[
                [
                    "asset_name",
                    "asset_class",
                    "account_bucket",
                    "prior_full_market_value",
                    "full_market_value_delta",
                    "monthly_position_flow_delta",
                ]
            ],
            comparison_mode=SNAPSHOT_COMPARISON_MODE,
        ),
        width="stretch",
        hide_index=True,
        key=table_key,
    )


def render_manager_attribution_tab(
    attribution_rows: pd.DataFrame,
    current_snapshot: str,
    prior_snapshot: str,
    board: str,
    period_choice: str,
    trend_view: str,
    include_interim: bool,
    comparison_mode: str = MONTH_REVIEW_MODE,
) -> None:
    summary = manager_attribution_summary(attribution_rows, current_snapshot, board)
    if summary.empty:
        st.info(f"当前时点暂无{board}经理或受托方可供归因。")
        return

    period = MANAGER_ATTRIBUTION_PERIODS[period_choice]
    income_metric = str(period["income"])
    return_metric = str(period["return"])
    short_label = str(period["short_label"])
    capital_metric = "avg_capital_ytd" if period_choice == YEAR_TO_DATE_MODE else "avg_capital_mtd"
    changes = manager_attribution_change_summary(
        attribution_rows,
        current_snapshot,
        prior_snapshot,
        board,
    )
    render_manager_attribution_overview(summary, changes, period_choice)
    if comparison_mode == SNAPSHOT_COMPARISON_MODE:
        st.caption(
            "时点对比模式下，全景图按当前时点相对对比时点的市值变化展示；收益额/率选择继续用于下方主体趋势与资产详情。"
        )
        render_manager_comparison_ranking(changes, current_snapshot, prior_snapshot)
    else:
        render_manager_contribution_ranking(summary, period_choice, trend_view)
    if comparison_mode == SNAPSHOT_COMPARISON_MODE:
        render_manager_comparison_table(
            changes,
            current_snapshot,
            prior_snapshot,
            table_key=f"manager-attribution-comparison-{board}",
        )

    entity_labels = manager_attribution_entity_labels(summary)
    entity_options = summary["attribution_entity_id"].astype(str).tolist()
    state_suffix = "fixed" if board == ATTRIBUTION_BOARD_FIXED else "equity"
    primary_key = f"manager-attribution-primary-{state_suffix}"
    render_position_peer_comparison(
        attribution_rows, current_snapshot, board, include_interim, state_suffix,
        period="ytd" if period_choice == YEAR_TO_DATE_MODE else "mtd",
        view_choice=trend_view,
    )

    st.markdown("#### 单一主体观察")
    income_values = pd.to_numeric(summary[income_metric], errors="coerce")
    default_primary = (
        str(summary.loc[income_values.abs().idxmax(), "attribution_entity_id"])
        if income_values.notna().any() else entity_options[0]
    )
    if st.session_state.get(primary_key) not in entity_labels:
        st.session_state[primary_key] = default_primary
    primary_entity = st.selectbox(
        "选择观察主体",
        entity_options,
        key=primary_key,
        format_func=lambda value: entity_labels.get(value, value),
        help="仅控制下方主体详情、资产收益贡献、持仓结构与资产明细。",
    )

    detail_summary = summary[summary["attribution_entity_id"].eq(primary_entity)].iloc[0]
    tone = "external" if detail_summary["attribution_scope"] == "委外" else "internal"
    full_rank = pd.to_numeric(summary[income_metric], errors="coerce").rank(
        method="min",
        ascending=False,
    )
    detail_index = detail_summary.name
    rank_value = full_rank.loc[detail_index] if detail_index in full_rank.index else np.nan
    rank_label = f"#{int(rank_value)} / {int(full_rank.count())}" if pd.notna(rank_value) else "—"
    change_row = changes[changes["attribution_entity_id"].eq(primary_entity)]
    estimated_flow = float(change_row["estimated_flow"].iloc[0]) if not change_row.empty else np.nan
    period_income = float(detail_summary[income_metric])
    period_return = float(detail_summary[return_metric])
    st.markdown(f"#### 主体详情｜{entity_labels.get(primary_entity, primary_entity)}")
    render_kpi_grid(
        [
            {"label": "当前市值", "value": amount(float(detail_summary["full_market_value"])), "tone": tone},
            {
                "label": f"{short_label}综合收益",
                "value": signed_amount(period_income),
                "tone": "positive" if period_income >= 0 else "negative",
            },
            {
                "label": f"{short_label}综合收益率",
                "value": pct(period_return),
                "delta": f"资金占用 {amount(float(detail_summary[capital_metric]))}",
                "tone": tone,
            },
            {"label": "全板块贡献排名", "value": rank_label, "delta": "按综合收益额", "tone": tone},
            {
                "label": "估算净配置变化",
                "value": signed_amount(estimated_flow),
                "delta": f"较 {prior_snapshot} 月末" if prior_snapshot else "暂无月末基准",
                "delta_tone": (
                    "positive"
                    if np.isfinite(estimated_flow) and estimated_flow >= 0
                    else "negative"
                    if np.isfinite(estimated_flow)
                    else ""
                ),
                "tone": (
                    "positive"
                    if np.isfinite(estimated_flow) and estimated_flow >= 0
                    else "negative"
                    if np.isfinite(estimated_flow)
                    else tone
                ),
            },
            {"label": "资产数量", "value": f"{int(detail_summary['asset_count']):,}", "tone": tone},
        ],
        grid_class="kpi-grid-attribution",
    )
    if np.isfinite(period_return) and abs(period_return) > 1.0:
        st.warning(
            f"该主体{short_label}收益率为 {pct(period_return)}，受较小资金占用分母或特殊调节项影响；"
            "横向评价请优先结合收益额、当前市值与资产明细。"
        )

    asset_detail = manager_asset_detail(
        attribution_rows,
        current_snapshot,
        board,
        primary_entity,
    )
    render_manager_asset_contribution_chart(asset_detail, period_choice)
    holdings = manager_holding_map(
        attribution_rows,
        current_snapshot,
        board,
        primary_entity,
        max_assets=20,
        prior_snapshot_date=prior_snapshot,
    )
    render_manager_holding_treemap(
        holdings,
        asset_detail,
        chart_key=f"manager-attribution-holding-map-{state_suffix}",
        period_choice=period_choice,
    )
    exited_holdings = manager_exited_holdings(
        attribution_rows,
        current_snapshot,
        board,
        primary_entity,
        prior_snapshot_date=prior_snapshot,
    )
    render_manager_exited_holdings(
        exited_holdings,
        prior_snapshot,
        table_key=f"manager-attribution-exited-holdings-{state_suffix}",
    )

    st.markdown("#### 资产明细")
    if len(asset_detail) > 500:
        st.caption(f"资产明细共 {len(asset_detail):,} 条，按当前市值排序展示前 500 条。")
    detail_metric_columns = (
        ["comprehensive_income_ytd", "avg_capital_ytd", "comprehensive_return_ytd"]
        if period_choice == YEAR_TO_DATE_MODE
        else ["comprehensive_income_mtd", "avg_capital_mtd", "comprehensive_return_mtd"]
    )
    st.dataframe(
        format_table(
            asset_detail.head(500)[
                [
                    "asset_name",
                    "asset_class",
                    "account_bucket",
                    "full_market_value",
                    *detail_metric_columns,
                    "asset_code",
                    "trade_code",
                    "source_rows",
                ]
            ],
            comparison_mode=period_choice,
        ),
        width="stretch",
        hide_index=True,
        key=f"manager-attribution-assets-{state_suffix}",
    )


def render_manager_attribution_dashboard(
    data: pd.DataFrame,
    current_snapshot: str,
    comparison_mode: str = MONTH_REVIEW_MODE,
    baseline_snapshot: str | None = None,
) -> None:
    board = st.radio(
        "选择归因板块",
        [ATTRIBUTION_BOARD_FIXED, ATTRIBUTION_BOARD_EQUITY],
        format_func=lambda value: f"{value}归因",
        horizontal=True,
        key="manager-attribution-board",
    )
    attribution_rows = build_manager_attribution_rows(data)
    if board == ATTRIBUTION_BOARD_EQUITY and comparison_mode == YEAR_TO_DATE_MODE:
        render_outsourced_funding_note(attribution_rows, current_snapshot)
    if baseline_snapshot is None:
        prior_candidates = previous_official_snapshots(data, current_snapshot)
        prior_snapshot = prior_candidates[-1] if prior_candidates else ""
    else:
        prior_snapshot = str(baseline_snapshot)
    if comparison_mode == SNAPSHOT_COMPARISON_MODE and prior_snapshot:
        baseline_note = (
            f"规模、配置变化和资产明细以当前时点 {snapshot_display_label(current_snapshot)} "
            f"对比 {snapshot_display_label(prior_snapshot)}；收益指标跟随左侧时点视角，使用当前时点本月口径。"
        )
    elif comparison_mode == YEAR_TO_DATE_MODE:
        baseline_note = (
            f"规模、配置变化和资产明细沿用 "
            f"{snapshot_display_label(prior_snapshot) if prior_snapshot else '上一正式时点'} "
            "作为变化基准；收益指标跟随左侧年初以来视角。"
        )
    else:
        baseline_note = (
            f"规模、配置变化和资产明细以 {snapshot_display_label(prior_snapshot) if prior_snapshot else '上一正式时点'} "
            "为基准；收益指标跟随左侧单月复盘视角。"
        )
    show_block_note(
        "先看全体贡献/拖累，再按同类分组比较仓位管理；下方单独选择观察主体查看资产收益归因与持仓结构；"
        f"本模块跟随左侧分析视角，{baseline_note}"
    )
    period_choice = manager_attribution_period_for_mode(comparison_mode)
    trend_view = st.radio(
        "收益趋势 / 全景指标",
        MANAGER_ATTRIBUTION_VIEW_OPTIONS,
        horizontal=True,
        key="manager-attribution-trend-view",
    )
    include_interim = True  # Latest interim is appended automatically to month ends.
    coverage = manager_attribution_coverage_summary(attribution_rows, current_snapshot)
    render_manager_attribution_coverage(coverage, current_snapshot)
    render_manager_attribution_tab(
        attribution_rows,
        current_snapshot,
        prior_snapshot,
        board,
        period_choice,
        trend_view,
        include_interim,
        comparison_mode,
    )


def main() -> None:
    apply_columbia_theme()
    if maintenance_mode_enabled():
        render_maintenance_page()
        return

    require_login()

    render_hero_banner(
        "组合管理账户复盘",
        "看组合规模、收益贡献、数据质量，并追到资产明细。",
        kicker="Columbia / Portfolio Review",
    )

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
        st.session_state["加载全部委外权益明细"] = False
        st.session_state["reset_filters"] = False

    with st.sidebar:
        current_month = st.selectbox(
            "数据时点",
            snapshots,
            index=snapshots.index(default_current),
            format_func=lambda value: snapshot_display_label(value, status_by_snapshot.get(value)),
        )
        comparison_mode = st.selectbox("分析视角", COMPARISON_MODE_OPTIONS, index=0, key="分析视角")
        prior_candidates = previous_official_snapshots(data, current_month)
        if comparison_mode == MONTH_REVIEW_MODE and not prior_candidates:
            st.error("缺少上一自然月的月末正式快照，不能做单月复盘规模变化。")
            st.stop()
        if comparison_mode == MONTH_REVIEW_MODE:
            prior_month = prior_candidates[-1]
            st.caption(
                f"单月复盘使用上一自然月正式快照 {snapshot_display_label(prior_month)} 作为规模变化基准。"
            )
        elif comparison_mode == SNAPSHOT_COMPARISON_MODE:
            comparison_options = selectable_comparison_snapshots(snapshots, current_month)
            if not comparison_options:
                st.error("至少需要两个不同的数据时点才能进行时点对比。")
                st.stop()
            comparison_default = default_comparison_snapshot(snapshots, current_month)
            if st.session_state.get("对比数据时点") not in comparison_options:
                st.session_state["对比数据时点"] = comparison_default
            prior_month = st.selectbox(
                "对比数据时点",
                comparison_options,
                format_func=lambda value: snapshot_display_label(value, status_by_snapshot.get(value)),
                key="对比数据时点",
            )
            st.caption(
                f"当前时点 {snapshot_display_label(current_month)} 对比 {snapshot_display_label(prior_month)}；"
                "规模、账户和资产变化均以该对比时点为基准，收益指标仍采用当前时点的本月以来口径。"
            )
        else:
            prior_month = prior_candidates[-1] if prior_candidates else ""
            st.caption("年初以来口径使用源表年初市值、本年以来收益、本年以来平均资金占用。")
        if st.button("重置账户筛选"):
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

    render_filter_pills(
        current_month,
        comparison_mode,
        prior_month,
        selected_account,
    )

    current_slice = snapshot_slice(data, current_month)
    prior_slice = snapshot_slice(data, prior_month)
    current_mv = float(current_slice["full_market_value"].sum())
    if comparison_mode == YEAR_TO_DATE_MODE:
        prior_mv = float(current_slice["market_value_year_open"].sum())
        current_fin = float(current_slice["finance_income_ytd"].sum())
        current_comp = float(current_slice["comprehensive_income_ytd"].sum())
        current_capital = float(current_slice["avg_capital_ytd"].sum())
        period_label = "年初以来截至时点" if current_snapshot_status == SNAPSHOT_STATUS_INTERIM else "年初以来"
        baseline_label = "年初"
        capital_label = "本年以来平均资金占用"
    elif comparison_mode == SNAPSHOT_COMPARISON_MODE:
        prior_mv = float(prior_slice["full_market_value"].sum())
        current_fin = float(current_slice["finance_income_mtd"].sum())
        current_comp = float(current_slice["comprehensive_income_mtd"].sum())
        current_capital = float(current_slice["avg_capital_mtd"].sum())
        period_label = "当前时点本月截至" if current_snapshot_status == SNAPSHOT_STATUS_INTERIM else "当前时点本月"
        baseline_label = "对比时点"
        capital_label = "当前时点本月平均资金占用"
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
    if comparison_mode == YEAR_TO_DATE_MODE:
        scale_income_label = "年初以来综合收益"
        scale_baseline_label = "年初市值"
    elif comparison_mode == SNAPSHOT_COMPARISON_MODE:
        scale_income_label = "当前时点本月综合收益"
        scale_baseline_label = "对比时点市值"
    else:
        scale_income_label = "本月综合收益"
        scale_baseline_label = "上月市值"
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

    section_anchor("equity-dashboard")
    st.subheader("股票专项看板：委内/委外权益收益对比")
    show_block_note(
        "本模块只跟随数据时点和分析视角，不受下方账户筛选影响；"
        "委内固定展示股票、四类权益产品合计和鲍淼配置盘 OCI 股票，长股投股票不纳入；"
        "委外按公司汇总全部权益资产并排除现金、固收、应收和费用项目；"
        "无持仓公司保留零值，平均资金占用不足时收益率显示为 —。"
    )
    render_equity_dashboard(data, current_month, comparison_mode)

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
    )
    render_strategy_book_overview(data, current_month, prior_month, comparison_mode)

    st.divider()

    section_anchor("manager-attribution")
    st.subheader("投资经理 / 受托方归因")
    render_manager_attribution_dashboard(data, current_month, comparison_mode, prior_month)

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
                {"label": "资金成本率 3.41%", "value": FUNDING_COST_RATE, "color": "#C9A84C"},
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
                {"label": "有效成本率 3.26%", "value": EFFECTIVE_COST_RATE, "color": "#2F6B4F"},
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
