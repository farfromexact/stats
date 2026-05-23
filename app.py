from pathlib import Path
import hmac
import os

import numpy as np
import pandas as pd
import streamlit as st

from account_review import asset_evidence, current_vs_prior
from config import DATA_DIR
from portfolio_data import available_months, load_snapshots


ALL = "全部"
RETURN_BASE_THRESHOLD = 0.0001

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

        section[data-testid="stSidebar"] input {
            color: var(--yacht-ink);
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

        div[data-testid="stDataFrame"] {
            border: 1px solid var(--yacht-deck);
            border-radius: 8px;
            overflow: hidden;
            background: white;
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
    if "app_password" in st.secrets:
        return str(st.secrets["app_password"])
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
    "asset_class": "投资品种",
    "manager": "投资经理",
    "asset_name": "资产名称",
    "asset_code": "资产代码",
    "trade_code": "交易代码",
    "change_type": "变化类型",
    "full_market_value_current": "当前全价市值(亿)",
    "full_market_value_prior": "对比全价市值(亿)",
    "full_market_value_delta": "全价市值变化(亿)",
    "finance_income_mtd_current": "当前本月财务收益(亿)",
    "comprehensive_income_mtd_current": "当前本月综合收益(亿)",
    "avg_capital_mtd_current": "当前平均资金占用(亿)",
    "finance_return_mtd": "本月财务收益率",
    "comprehensive_return_mtd": "本月综合收益率",
    "record_count_current": "当前记录数",
    "source_rows_current": "当前源行数",
    "source_rows_prior": "对比源行数",
}

AMOUNT_COLUMNS = {
    "full_market_value",
    "finance_income_mtd",
    "comprehensive_income_mtd",
    "full_market_value_current",
    "full_market_value_prior",
    "full_market_value_delta",
    "finance_income_mtd_current",
    "comprehensive_income_mtd_current",
    "avg_capital_mtd_current",
}
PCT_COLUMNS = {"finance_return_mtd", "comprehensive_return_mtd"}


@st.cache_data(show_spinner="正在读取月度宽表...")
def cached_load(data_dir: str):
    return load_snapshots(Path(data_dir))


def clean_for_display(frame: pd.DataFrame) -> pd.DataFrame:
    display = frame.replace([np.inf, -np.inf], np.nan).copy()
    return display.rename(columns=DISPLAY_NAMES)


def format_table(frame: pd.DataFrame, precision: str = "display"):
    display = clean_for_display(frame)
    amount_decimals = 4 if precision == "source" else 2
    formatters = {}
    for source_col, display_col in DISPLAY_NAMES.items():
        if display_col not in display.columns:
            continue
        if source_col in AMOUNT_COLUMNS:
            formatters[display_col] = f"{{:,.{amount_decimals}f}}"
        elif source_col in PCT_COLUMNS:
            formatters[display_col] = "{:.2%}"
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


def selected_label(value: str) -> str:
    return "全部" if value == ALL else value


def show_block_note(text: str) -> None:
    st.caption(f"口径说明：{text}")


def quality_metrics(data: pd.DataFrame, current_month: str) -> dict[str, int]:
    current = data[data["snapshot_month"] == current_month]
    unassigned_manager = int((current["manager"] == "未分配/待确认").sum())
    missing_class = int((current["asset_class"] == "未分类/待确认").sum())
    invalid_return_base = int(
        ((current["avg_capital_mtd"] <= RETURN_BASE_THRESHOLD)
        & ((current["finance_income_mtd"] != 0) | (current["comprehensive_income_mtd"] != 0))).sum()
    )
    negative_assets = int((current["comprehensive_income_mtd"] < 0).sum())
    return {
        "未分配经理": unassigned_manager,
        "缺省分类": missing_class,
        "异常收益率": invalid_return_base,
        "负收益资产": negative_assets,
    }


def income_diff_breakdown(current_slice: pd.DataFrame) -> pd.DataFrame:
    finance = float(current_slice["finance_income_mtd"].sum())
    comprehensive = float(current_slice["comprehensive_income_mtd"].sum())
    return pd.DataFrame(
        [
            {"项目": "本月综合收益", "金额(亿)": comprehensive, "说明": "源表“综合收益（本月以来）(亿)”逐行加总。"},
            {"项目": "本月财务收益", "金额(亿)": finance, "说明": "源表“财务收益（本月以来）(亿)”逐行加总。"},
            {"项目": "差异：综合收益 - 财务收益", "金额(亿)": comprehensive - finance, "说明": "用于观察公允价值、其他综合收益等非财务收益口径影响。"},
        ]
    )


def auto_summary(current_mv: float, prior_mv: float, finance: float, comprehensive: float, quality: dict[str, int]) -> str:
    delta = current_mv - prior_mv
    direction = "增加" if delta >= 0 else "减少"
    risk_items = [f"{name}{count}条" for name, count in quality.items() if count > 0]
    risk_text = "；".join(risk_items) if risk_items else "未发现主要数据质量提示"
    return (
        f"本月全价市值为 {amount(current_mv)}，较对比月{direction} {amount(abs(delta))}；"
        f"本月财务收益为 {amount(finance)}，综合收益为 {amount(comprehensive)}。"
        f"数据质量提示：{risk_text}。"
    )


def render_quality_bar(quality: dict[str, int]) -> None:
    cols = st.columns(4)
    for col, (name, count) in zip(cols, quality.items()):
        col.metric(name, f"{count:,}")
    st.caption(
        "质量提示：未分配经理、缺省分类、异常收益率和负收益资产用于提示阅读风险，不代表数据错误；需要结合资产证据进一步核对。"
    )


def main() -> None:
    apply_yacht_theme()
    require_login()

    st.title("组合管理账户复盘")
    st.caption("第一阶段：固定文件夹读取月度宽表，围绕账户 -> 投资品种 -> 投资经理 -> 资产做筛选下钻。")

    data, validation, errors = cached_load(str(DATA_DIR))
    with st.sidebar:
        st.header("数据与筛选")
        st.write(f"数据目录：`{DATA_DIR}`")
        if st.button("刷新数据"):
            st.cache_data.clear()
            st.rerun()

    if errors:
        st.error("数据校验未通过，已停止分析。")
        for error in errors:
            st.write(f"- {error}")
        if not validation.empty:
            st.dataframe(format_table(validation, precision="source"), use_container_width=True, hide_index=True)
        st.stop()

    months = available_months(data)
    if len(months) < 2:
        st.error("至少需要两个带月份的快照文件才能做账户复盘环比分析。")
        st.stop()

    default_current = months[-1]
    default_prior = months[-2]

    if st.session_state.get("reset_filters"):
        st.session_state["账户"] = ALL
        st.session_state["投资品种"] = ALL
        st.session_state["投资经理"] = ALL
        st.session_state["reset_filters"] = False

    with st.sidebar:
        current_month = st.selectbox("当前月份", months, index=months.index(default_current))
        prior_candidates = [month for month in months if month < current_month]
        if not prior_candidates:
            st.error("当前月份之前没有可对比月份。")
            st.stop()
        prior_month = st.selectbox("对比月份", prior_candidates, index=len(prior_candidates) - 1)

    account_summary = current_vs_prior(data, current_month, prior_month, ["account_bucket"])
    account_options = [ALL] + sorted(account_summary["account_bucket"].astype(str).tolist())

    with st.sidebar:
        selected_account = st.selectbox("账户", account_options, key="账户")

    filtered_for_options = data[data["snapshot_month"] == current_month]
    if selected_account != ALL:
        filtered_for_options = filtered_for_options[filtered_for_options["account_bucket"] == selected_account]
    asset_options = [ALL] + sorted(filtered_for_options["asset_class"].dropna().astype(str).unique().tolist())
    if st.session_state.get("投资品种") not in asset_options:
        st.session_state["投资品种"] = ALL
    with st.sidebar:
        selected_asset_class = st.selectbox("投资品种", asset_options, key="投资品种")

    manager_options_frame = filtered_for_options
    if selected_asset_class != ALL:
        manager_options_frame = manager_options_frame[manager_options_frame["asset_class"] == selected_asset_class]
    manager_options = [ALL] + sorted(manager_options_frame["manager"].dropna().astype(str).unique().tolist())
    if st.session_state.get("投资经理") not in manager_options:
        st.session_state["投资经理"] = ALL
    with st.sidebar:
        selected_manager = st.selectbox("投资经理", manager_options, key="投资经理")
        if st.button("重置筛选"):
            st.session_state["reset_filters"] = True
            st.rerun()

    st.info(
        f"当前筛选：当前月份 {current_month}；对比月份 {prior_month}；"
        f"账户 {selected_label(selected_account)}；投资品种 {selected_label(selected_asset_class)}；"
        f"投资经理 {selected_label(selected_manager)}。"
    )

    current_slice = data[data["snapshot_month"] == current_month]
    prior_slice = data[data["snapshot_month"] == prior_month]
    current_mv = float(current_slice["full_market_value"].sum())
    prior_mv = float(prior_slice["full_market_value"].sum())
    current_fin = float(current_slice["finance_income_mtd"].sum())
    current_comp = float(current_slice["comprehensive_income_mtd"].sum())
    current_capital = float(current_slice["avg_capital_mtd"].sum())
    quality = quality_metrics(data, current_month)

    st.subheader("数据质量提示")
    show_block_note("本提示用于提醒阅读者哪些数据需要谨慎解释，不改变源表数值，也不参与收益贡献计算。")
    render_quality_bar(quality)

    st.subheader("本月总体表现")
    show_block_note(
        "顶部指标均为当前月份全组合源表逐行加总；市值变化 = 当前月份全价市值 - 对比月份全价市值。"
    )
    top_cols = st.columns(5)
    top_cols[0].metric("当前全价市值", amount(current_mv), signed_amount(current_mv - prior_mv))
    top_cols[1].metric("本月财务收益", amount(current_fin))
    top_cols[2].metric("本月综合收益", amount(current_comp))
    top_cols[3].metric("平均资金占用", amount(current_capital))
    top_cols[4].metric("快照行数", f"{len(current_slice):,}")
    st.write(auto_summary(current_mv, prior_mv, current_fin, current_comp, quality))

    st.subheader("财务收益与综合收益差异")
    show_block_note("本表用于回答财务收益和综合收益差在哪里；金额为当前月份源表逐行加总。")
    diff_table = income_diff_breakdown(current_slice)
    st.dataframe(
        diff_table.style.format({"金额(亿)": "{:,.2f}"}, na_rep="—"),
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    st.subheader("账户层：规模变化与收益贡献")
    show_block_note(
        "本表用于回答哪个账户规模增加或减少、哪个账户贡献收益；收益率 = 本月收益 / 本月平均资金占用，资金占用无效时显示为“—”。"
    )
    account_display = account_summary.sort_values("full_market_value_delta", ascending=False)
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
                    "finance_return_mtd",
                    "comprehensive_return_mtd",
                    "record_count_current",
                ]
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("账户内品种拆解")
    show_block_note("本表用于回答选定账户的钱投向哪些品种，以及这些品种分别贡献或拖累了多少收益。")
    class_summary = current_vs_prior(data, current_month, prior_month, ["account_bucket", "asset_class"])
    if selected_account != ALL:
        class_summary = class_summary[class_summary["account_bucket"] == selected_account]
    class_display = class_summary.sort_values("comprehensive_income_mtd_current", ascending=False)
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
                    "comprehensive_return_mtd",
                    "record_count_current",
                ]
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("品种内经理拆解")
    show_block_note("本表用于回答选定账户和品种下，结果由哪些投资经理贡献或拖累。")
    manager_summary = current_vs_prior(data, current_month, prior_month, ["account_bucket", "asset_class", "manager"])
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
                    "comprehensive_return_mtd",
                    "record_count_current",
                ]
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("资产证据")
    show_block_note(
        "本表用于把账户、品种、经理的结果追溯到资产明细；变化类型按当前月和对比月是否出现及市值变化判断。"
    )
    evidence = asset_evidence(
        data,
        current_month,
        prior_month,
        selected_account,
        selected_asset_class,
        selected_manager,
    )
    sort_choice = st.radio(
        "资产证据视角",
        ["收益贡献", "收益拖累", "规模增加", "规模减少", "新增退出"],
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
            ].head(500)
        ),
        use_container_width=True,
        hide_index=True,
    )

    with st.expander("源数据核对"):
        st.caption("源数据核对页保留 4 位小数，便于和原始宽表汇总结果复核。")
        st.dataframe(format_table(validation, precision="source"), use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
