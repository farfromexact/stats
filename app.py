import hmac
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

from account_review import asset_evidence, asset_evidence_year_open, comparison_summary
from config import DATA_DIR
from portfolio_data import available_months, load_snapshots


ALL = "全部"
RETURN_BASE_THRESHOLD = 0.0001
DATA_SCHEMA_VERSION = "2026-06-02-may-snapshot-v1"
CHART_EPSILON = 1e-9
POSITIVE_COLOR = "#122256"
NEGATIVE_COLOR = "#8B2F2F"
NEUTRAL_COLOR = "#8EA0B6"
FUNDING_COLOR = "#6F7F92"
HIGHLIGHT_COLOR = "#C88439"
CORE_ACCOUNT_LABELS = {"传统", "自有", "自由", "分红一", "分红1", "分红二", "分红2"}
REPO_FINANCING_ASSET_CLASSES = {"正回购"}
REVERSE_REPO_ASSET_CLASSES = {"逆回购", "买入返售"}
FUNDING_ASSET_CLASSES = REPO_FINANCING_ASSET_CLASSES | REVERSE_REPO_ASSET_CLASSES

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
    "snapshot_month": "快照月份",
    "source_file_name": "源文件名",
    "source_file_hash": "源文件哈希",
    "source_rows": "源表行数",
    "status": "状态",
    "message": "校验信息",
    "full_market_value": "全价市值(亿)",
    "finance_income_mtd": "本月财务收益(亿)",
    "comprehensive_income_mtd": "本月综合收益(亿)",
    "account_bucket": "账户",
    "mandate_type": "委受托维度",
    "asset_class": "投资品种",
    "manager": "投资经理",
    "asset_name": "资产名称",
    "asset_code": "资产代码",
    "trade_code": "交易代码",
    "change_type": "变化类型",
    "full_market_value_current": "报告月市值(亿)",
    "full_market_value_prior": "上月市值(亿)",
    "full_market_value_delta": "较上月变化(亿)",
    "net_full_market_value_delta": "扣收益后较上月规模变化(亿)",
    "finance_income_mtd_current": "本月财务收益(亿)",
    "comprehensive_income_mtd_current": "本月综合收益(亿)",
    "finance_income_mtd_delta": "财务收益变化(亿)",
    "comprehensive_income_mtd_delta": "综合收益变化(亿)",
    "finance_income_period": "本月财务收益(亿)",
    "comprehensive_income_period": "本月综合收益(亿)",
    "avg_capital_mtd_current": "本月平均资金占用(亿)",
    "finance_return_mtd": "本月财务收益率",
    "comprehensive_return_mtd": "本月综合收益率",
    "record_count_current": "当前记录数",
    "source_rows_current": "当前源行数",
    "source_rows_prior": "上月源行数",
}

YTD_DISPLAY_OVERRIDES = {
    "full_market_value_prior": "年初市值(亿)",
    "full_market_value_delta": "较年初变化(亿)",
    "net_full_market_value_delta": "扣收益后较年初规模变化(亿)",
    "finance_income_mtd_current": "年初以来财务收益(亿)",
    "comprehensive_income_mtd_current": "年初以来综合收益(亿)",
    "finance_income_period": "年初以来财务收益(亿)",
    "comprehensive_income_period": "年初以来综合收益(亿)",
    "avg_capital_mtd_current": "本年以来平均资金占用(亿)",
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
    "finance_income_mtd_current",
    "comprehensive_income_mtd_current",
    "finance_income_mtd_delta",
    "comprehensive_income_mtd_delta",
    "finance_income_period",
    "comprehensive_income_period",
    "avg_capital_mtd_current",
}
PCT_COLUMNS = {"finance_return_mtd", "comprehensive_return_mtd"}
COUNT_COLUMNS = {
    "record_count",
    "record_count_current",
    "source_rows",
    "source_rows_current",
    "source_rows_prior",
}


@st.cache_data(show_spinner="正在读取月度宽表...")
def cached_load(data_dir: str, schema_version: str):
    return load_snapshots(Path(data_dir))


def ensure_runtime_columns(data: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    required_runtime_columns = {
        "market_value_year_open": 0.0,
        "avg_capital_ytd": 0.0,
        "finance_income_ytd": 0.0,
        "comprehensive_income_ytd": 0.0,
    }
    missing = [column for column in required_runtime_columns if column not in data.columns]
    if not missing:
        return data, []

    data = data.copy()
    for column in missing:
        data[column] = required_runtime_columns[column]
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
    if comparison_mode == "年初以来":
        view_text = f"年初以来，截至 {current_month}"
    else:
        view_text = f"{current_month} 单月复盘，规模较 {prior_month}"
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
        delta_html = f'<div class="kpi-delta">{html_text(delta)}</div>' if delta else ""
        cards.append(
            '<div class="kpi-card"><div class="kpi-label">{label}</div>'
            '<div class="kpi-value">{value}</div>{delta}</div>'.format(
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
    baseline = "年初" if comparison_mode == "年初以来" else prior_month
    period = "年初以来" if comparison_mode == "年初以来" else "本月"
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
            f"{html_text(current_month)} 全价市值 {html_text(amount(current_mv))}，"
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


def is_funding_asset_class(value: object) -> bool:
    return str(value).strip() in FUNDING_ASSET_CLASSES


def show_block_note(text: str) -> None:
    st.caption(f"口径说明：{text}")


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
        <a class="sidebar-nav-button" href="#account-overview">账户层图表/表格</a>
        <a class="sidebar-nav-button" href="#account-class-breakdown">账户内品种拆解</a>
        <a class="sidebar-nav-button" href="#asset-evidence">资产证据</a>
        <a class="sidebar-nav-button" href="#quality-checks">数据质量</a>
        """,
        unsafe_allow_html=True,
    )


def quality_metrics(data: pd.DataFrame, current_month: str, comparison_mode: str) -> dict[str, int]:
    current = data[data["snapshot_month"] == current_month]
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
    highlight_labels: set[str] | None = None,
) -> None:
    normalized_label_order = [str(label) for label in label_order or []]
    normalized_highlight_labels = {str(label) for label in highlight_labels or set()}
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
    chart_data["_is_highlighted"] = chart_data["_label"].isin(normalized_highlight_labels)
    chart_data["_is_funding_asset_class"] = False
    if label_col == "asset_class":
        chart_data["_is_funding_asset_class"] = chart_data[label_col].map(is_funding_asset_class)
        chart_data["_color_note"] = np.where(
            chart_data["_is_funding_asset_class"],
            "回购/融资科目：使用中性颜色",
            "按指标正负染色",
        )
    chart_data["_bar_color_group"] = np.select(
        [
            chart_data["_is_funding_asset_class"],
            chart_data["_is_highlighted"],
            chart_data["_value"] >= 0,
        ],
        [
            "回购/融资",
            "核心账户",
            "正向",
        ],
        default="负向",
    )
    if normalized_label_order:
        chart_data = chart_data.sort_values("_forced_order")
    else:
        chart_data = chart_data[chart_data["_value"].abs() > CHART_EPSILON]
        chart_data = chart_data.sort_values("_value", ascending=False)

    tooltips = [
        alt.Tooltip("_label:N", title=display_names_for_mode(comparison_mode).get(label_col, label_col)),
        alt.Tooltip("_value:Q", title=value_title, format=".2%" if metric in PCT_COLUMNS else ",.2f"),
    ]
    if label_col == "asset_class":
        tooltips.append(alt.Tooltip("_color_note:N", title="颜色口径"))
    if normalized_highlight_labels:
        chart_data["_highlight_note"] = np.where(chart_data["_is_highlighted"], "核心账户", "其他账户")
        tooltips.append(alt.Tooltip("_highlight_note:N", title="账户标记"))
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

    bars = (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusEnd=2)
        .encode(
            x=alt.X(
                "_value:Q",
                title=value_title,
                axis=alt.Axis(format=".1%" if metric in PCT_COLUMNS else ",.1f"),
            ),
            y=alt.Y(
                "_label:N",
                title=None,
                sort=normalized_label_order or alt.SortField(field="_value", order="descending"),
                axis=alt.Axis(labelLimit=220),
            ),
            color=alt.Color(
                "_bar_color_group:N",
                title=None,
                scale=alt.Scale(
                    domain=["正向", "负向", "回购/融资", "核心账户"],
                    range=[POSITIVE_COLOR, NEGATIVE_COLOR, FUNDING_COLOR, HIGHLIGHT_COLOR],
                ),
                legend=None,
            ),
            tooltip=tooltips,
        )
    )
    zero_rule = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color="#475569", opacity=0.55).encode(x="x:Q")
    chart = (
        (bars + zero_rule)
        .properties(title=title, height=_bar_height(len(chart_data)))
        .configure_view(strokeWidth=0)
        .configure_title(anchor="start", color=POSITIVE_COLOR, fontSize=15)
    )
    st.altair_chart(chart, width="stretch")


def render_monthly_trends(data: pd.DataFrame, comparison_mode: str) -> None:
    if data.empty:
        st.info("暂无可展示的月份趋势数据。")
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
        working.groupby("snapshot_month", dropna=False)
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
        .sort_values("snapshot_month")
    )
    if monthly.empty:
        st.info("暂无可展示的月份趋势数据。")
        return

    monthly["net_repo_financing"] = monthly["repo_financing"] - monthly["reverse_repo"]
    monthly["repo_financing_ratio"] = (
        monthly["repo_financing"] / monthly["full_market_value"].replace(0.0, np.nan)
    )
    month_order = monthly["snapshot_month"].astype(str).tolist()
    market_min = float(monthly["full_market_value"].min())
    market_max = float(monthly["full_market_value"].max())
    market_padding = max((market_max - market_min) * 0.25, market_max * 0.004)
    market_baseline = max(0.0, market_min - market_padding)
    monthly["market_baseline"] = market_baseline

    scale_tooltip = [
        alt.Tooltip("snapshot_month:N", title="月份"),
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
                "snapshot_month:N",
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
            x=alt.X("snapshot_month:N", sort=month_order),
            y=alt.Y(
                "full_market_value:Q",
                axis=None,
                scale=alt.Scale(domain=[market_baseline, market_max + market_padding]),
            ),
            text=alt.Text("full_market_value:Q", format=",.0f"),
        )
    )
    repo_line = (
        alt.Chart(monthly)
        .mark_line(color=NEGATIVE_COLOR, point=alt.OverlayMarkDef(color=NEGATIVE_COLOR, size=70), strokeWidth=2.5)
        .encode(
            x=alt.X("snapshot_month:N", title=None, sort=month_order, axis=alt.Axis(labelAngle=0)),
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
            x=alt.X("snapshot_month:N", sort=month_order),
            y=alt.Y(
                "repo_financing:Q",
                axis=None,
                scale=alt.Scale(zero=False),
            ),
            text=alt.Text("repo_financing:Q", format=",.0f"),
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
        id_vars=["snapshot_month"],
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
        id_vars=["snapshot_month"],
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
        alt.Tooltip("snapshot_month:N", title="月份"),
        alt.Tooltip("income_type:N", title="收益口径"),
        alt.Tooltip("income_value:Q", title="收益(亿)", format=",.2f"),
    ]
    income_bars = (
        alt.Chart(income_bar_long)
        .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=alt.X("snapshot_month:N", title=None, sort=month_order, axis=alt.Axis(labelAngle=0)),
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
            x=alt.X("snapshot_month:N", title=None, sort=month_order, axis=alt.Axis(labelAngle=0)),
            xOffset=alt.XOffset("offset_type:N", sort=[mtd_label_finance, mtd_label_comprehensive]),
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
            x=alt.X("snapshot_month:N", title=None, sort=month_order, axis=alt.Axis(labelAngle=0)),
            xOffset=alt.XOffset("offset_type:N", sort=[mtd_label_finance, mtd_label_comprehensive]),
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
        .properties(title="收益趋势：当月30天 + 年初以来累计趋势", height=300)
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
                        scale=alt.Scale(domain=[-1, 0, 1], range=[NEGATIVE_COLOR, "#F2F1ED", POSITIVE_COLOR]),
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
    st.caption("颜色说明：两张热力图共用账户和投资品种排序；颜色按排名强度展示，精确值以 tooltip 和下方表格为准；正回购、逆回购按回购/融资科目处理，使用中性灰蓝色。")


def main() -> None:
    apply_yacht_theme()
    require_login()

    st.title("组合管理账户复盘")
    st.caption("看组合规模、收益贡献、数据质量，并追到资产证据。")

    data, validation, errors = cached_load(str(DATA_DIR), DATA_SCHEMA_VERSION)
    data, runtime_missing_columns = ensure_runtime_columns(data)
    with st.sidebar:
        st.header("数据与筛选")
        with st.expander("数据源", expanded=False):
            st.write(f"数据目录：`{DATA_DIR}`")
        if st.button("刷新数据"):
            st.cache_data.clear()
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
            "当前缓存或源表缺少年初以来口径字段，已临时补空以避免页面中断；"
            "请点击左侧“刷新数据”重新读取源文件。缺失字段："
            + "、".join(runtime_missing_columns)
        )

    months = available_months(data)
    if not months:
        st.error("至少需要一个带月份的快照文件才能做账户复盘。")
        st.stop()

    default_current = months[-1]
    default_prior = months[-2] if len(months) > 1 else months[-1]

    if st.session_state.get("reset_filters"):
        st.session_state["账户"] = ALL
        st.session_state["投资品种"] = ALL
        st.session_state["投资经理"] = ALL
        st.session_state["reset_filters"] = False

    with st.sidebar:
        current_month = st.selectbox("报告月份", months, index=months.index(default_current))
        comparison_mode = st.selectbox("分析视角", ["年初以来", "单月复盘"], index=0)
        prior_candidates = [month for month in months if month < current_month]
        if comparison_mode == "单月复盘" and not prior_candidates:
            st.error("该报告月份之前没有上一可用月份，不能做单月复盘规模变化。")
            st.stop()
        if comparison_mode == "单月复盘":
            prior_month = prior_candidates[-1]
            st.caption(f"单月复盘自动使用上一可用月份 {prior_month} 作为规模变化基准。")
        else:
            prior_month = prior_candidates[-1] if prior_candidates else default_prior
            st.caption("年初以来口径使用源表年初市值、本年以来收益、本年以来平均资金占用。")
        if st.button("重置局部筛选"):
            st.session_state["reset_filters"] = True
            st.rerun()

    account_summary = ensure_summary_columns(
        comparison_summary(data, current_month, prior_month, ["account_bucket"], comparison_mode),
        comparison_mode,
    )
    account_options = [ALL] + sorted(account_summary["account_bucket"].astype(str).tolist())
    if st.session_state.get("账户") not in account_options:
        st.session_state["账户"] = ALL
    selected_account = st.session_state.get("账户", ALL)

    current_options_slice = data[data["snapshot_month"] == current_month]
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

    current_slice = data[data["snapshot_month"] == current_month]
    prior_slice = data[data["snapshot_month"] == prior_month]
    current_mv = float(current_slice["full_market_value"].sum())
    if comparison_mode == "年初以来":
        prior_mv = float(current_slice["market_value_year_open"].sum())
        current_fin = float(current_slice["finance_income_ytd"].sum())
        current_comp = float(current_slice["comprehensive_income_ytd"].sum())
        current_capital = float(current_slice["avg_capital_ytd"].sum())
        period_label = "年初以来"
        baseline_label = "年初"
        capital_label = "本年以来平均资金占用"
    else:
        prior_mv = float(prior_slice["full_market_value"].sum())
        current_fin = float(current_slice["finance_income_mtd"].sum())
        current_comp = float(current_slice["comprehensive_income_mtd"].sum())
        current_capital = float(current_slice["avg_capital_mtd"].sum())
        period_label = "本月"
        baseline_label = "上月"
        capital_label = "本月平均资金占用"
    quality = quality_metrics(data, current_month, comparison_mode)
    asset_class_summary = ensure_summary_columns(
        comparison_summary(data, current_month, prior_month, ["asset_class"], comparison_mode),
        comparison_mode,
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
            {"label": "报告月市值", "value": amount(current_mv), "delta": signed_amount(current_mv - prior_mv)},
            {"label": f"{period_label}财务收益", "value": amount(current_fin)},
            {"label": f"{period_label}综合收益", "value": amount(current_comp)},
            {"label": capital_label, "value": amount(current_capital)},
            {"label": "快照行数", "value": f"{len(current_slice):,}"},
        ]
    )
    render_action_cards()
    render_quality_signal(quality)
    show_block_note(
        f"顶部指标均为报告月份全组合源表逐行加总；市值变化 = 报告月市值 - {baseline_label}市值；收益与资金占用采用{period_label}口径。"
    )

    section_anchor("charts-overview")
    st.subheader("图表总览")
    show_block_note("左图用柱展示全组合规模、用红色点线展示正回购融资余额；右图用柱展示当月30天收益，用彩色点展示对应口径的年初以来累计收益。")
    render_monthly_trends(data, comparison_mode)

    st.divider()

    section_anchor("asset-class-overview")
    st.subheader("投资品种总览：规模变化与收益贡献")
    scale_income_label = "年初以来综合收益" if comparison_mode == "年初以来" else "本月综合收益"
    scale_baseline_label = "年初市值" if comparison_mode == "年初以来" else "上月市值"
    show_block_note(
        f"本表不分账户，直接按投资品种汇总；右侧净规模变化 = 报告月市值 - {scale_baseline_label} - {scale_income_label}，用于近似识别真实增减仓或资金进出。"
    )
    asset_class_display = asset_class_summary.sort_values("comprehensive_income_mtd_current", ascending=False)
    asset_income_metric, asset_income_title, asset_income_value_title = income_chart_config(
        comparison_mode,
        "投资品种",
        " Top/Bottom",
    )
    asset_scale_metric = "net_full_market_value_delta"
    asset_chart_labels = shared_top_bottom_labels(
        asset_class_summary,
        asset_income_metric,
        asset_scale_metric,
        "asset_class",
    )
    asset_chart_cols = st.columns(2)
    with asset_chart_cols[0]:
        render_bar_chart(
            asset_class_summary,
            asset_income_metric,
            "asset_class",
            asset_income_title,
            asset_income_value_title,
            comparison_mode=comparison_mode,
            empty_message="当前投资品种暂无可展示的收益贡献。",
            label_order=asset_chart_labels,
        )
    with asset_chart_cols[1]:
        render_bar_chart(
            asset_class_summary,
            asset_scale_metric,
            "asset_class",
            "投资品种净规模变化 Top/Bottom",
            display_names_for_mode(comparison_mode)[asset_scale_metric],
            comparison_mode=comparison_mode,
            empty_message="当前投资品种暂无可展示的规模变化。",
            label_order=asset_chart_labels,
        )
    st.dataframe(
        format_table(
            asset_class_display[
                [
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

    section_anchor("account-overview")
    st.subheader("账户层：规模变化与收益贡献")
    show_block_note(
        f"本表用于回答哪个账户收益效率更高；左图展示综合收益率，右图展示财务收益率；tooltip 保留收益额、规模变化和资金占用；收益率 = {period_label}收益 / {capital_label}。"
    )
    account_display = account_summary.sort_values("full_market_value_delta", ascending=False)
    existing_accounts = set(account_summary["account_bucket"].astype(str).tolist())
    account_highlights = CORE_ACCOUNT_LABELS & existing_accounts
    account_chart_labels = top_by_abs(account_summary, "comprehensive_return_mtd", 12)[
        "account_bucket"
    ].astype(str).tolist()
    for label in ["传统", "自有", "自由", "分红一", "分红1", "分红二", "分红2"]:
        if label in existing_accounts and label not in account_chart_labels:
            account_chart_labels.append(label)

    account_chart_cols = st.columns(2)
    with account_chart_cols[0]:
        render_bar_chart(
            account_summary,
            "comprehensive_return_mtd",
            "account_bucket",
            "账户综合收益率排行",
            display_names_for_mode(comparison_mode)["comprehensive_return_mtd"],
            limit=12,
            selection="abs",
            comparison_mode=comparison_mode,
            empty_message="当前账户暂无可展示的综合收益率。",
            label_order=account_chart_labels,
            highlight_labels=account_highlights,
        )
    with account_chart_cols[1]:
        render_bar_chart(
            account_summary,
            "finance_return_mtd",
            "account_bucket",
            "账户财务收益率排行",
            display_names_for_mode(comparison_mode)["finance_return_mtd"],
            limit=12,
            selection="abs",
            comparison_mode=comparison_mode,
            empty_message="当前账户暂无可展示的财务收益率。",
            label_order=account_chart_labels,
            highlight_labels=account_highlights,
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
    show_block_note(f"本表用于回答选定账户和品种下，结果由哪些投资经理贡献或拖累；当前采用{comparison_mode}口径。")
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
    manager_control_cols = st.columns([0.28, 0.28, 0.44])
    with manager_control_cols[0]:
        selected_asset_class = st.selectbox("投资品种", asset_options, key="投资品种")
    manager_options_frame = account_filtered_options
    if selected_asset_class != ALL:
        manager_options_frame = manager_options_frame[manager_options_frame["asset_class"] == selected_asset_class]
    manager_options = [ALL] + sorted(manager_options_frame["manager"].dropna().astype(str).unique().tolist())
    if st.session_state.get("投资经理") not in manager_options:
        st.session_state["投资经理"] = ALL
    with manager_control_cols[1]:
        selected_manager = st.selectbox("投资经理", manager_options, key="投资经理")
    manager_summary = ensure_summary_columns(
        comparison_summary(
            data,
            current_month,
            prior_month,
            ["account_bucket", "asset_class", "manager"],
            comparison_mode,
        ),
        comparison_mode,
    )
    if selected_account != ALL:
        manager_summary = manager_summary[manager_summary["account_bucket"] == selected_account]
    if selected_asset_class != ALL:
        manager_summary = manager_summary[manager_summary["asset_class"] == selected_asset_class]
    manager_display = manager_summary.sort_values("comprehensive_income_mtd_current", ascending=False)
    st.dataframe(
        format_table(
            manager_display[
                [
                    "account_bucket",
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
            ],
            comparison_mode=comparison_mode,
        ),
        width="stretch",
        hide_index=True,
    )

    section_anchor("asset-evidence")
    st.subheader("资产证据")
    if comparison_mode == "年初以来":
        show_block_note(
            "本表用于把账户、品种、经理的结果追溯到资产明细；变化类型基于源表年初市值与当前市值判断，不等同于逐月交易明细。"
        )
        evidence = asset_evidence_year_open(
            data,
            current_month,
            selected_account,
            selected_asset_class,
            selected_manager,
        )
        evidence_options = ["收益贡献", "收益拖累", "规模增加", "规模减少", "年初持仓变化"]
    else:
        show_block_note(
            f"本表用于把账户、品种、经理的结果追溯到资产明细；变化类型按报告月份和上一可用月份 {prior_month} 是否出现及市值变化判断。"
        )
        evidence = asset_evidence(
            data,
            current_month,
            prior_month,
            selected_account,
            selected_asset_class,
            selected_manager,
        )
        evidence_options = ["收益贡献", "收益拖累", "规模增加", "规模减少", "新增退出"]
    sort_choice = st.radio(
        "资产证据视角",
        evidence_options,
        horizontal=True,
    )
    if sort_choice == "收益贡献":
        evidence = evidence.sort_values("comprehensive_income_mtd_current", ascending=False)
    elif sort_choice == "收益拖累":
        evidence = evidence.sort_values("comprehensive_income_mtd_current", ascending=True)
    elif sort_choice == "规模增加":
        evidence = evidence.sort_values("full_market_value_delta", ascending=False)
    elif sort_choice == "规模减少":
        evidence = evidence.sort_values("full_market_value_delta", ascending=True)
    else:
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
        evidence = evidence.assign(_order=evidence["change_type"].map(order).fillna(9)).sort_values(
            ["_order", "full_market_value_delta"],
            ascending=[True, False],
        )

    st.dataframe(
        format_table(
            evidence[
                [
                    "change_type",
                    "asset_name",
                    "asset_code",
                    "trade_code",
                    "account_bucket",
                    "asset_class",
                    "manager",
                    "full_market_value_current",
                    "full_market_value_prior",
                    "full_market_value_delta",
                    "finance_income_mtd_current",
                    "comprehensive_income_mtd_current",
                    "source_rows_current",
                    "source_rows_prior",
                ]
            ].head(500),
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
    show_block_note(f"本表用于回答财务收益和综合收益差在哪里；金额为报告月份源表逐行加总，采用{period_label}口径。")
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
