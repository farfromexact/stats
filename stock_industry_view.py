"""Streamlit view for company stock industry concentration."""
import plotly.graph_objects as go
import streamlit as st

from company_stock_holdings import UNMAPPED_INDUSTRY
from stock_industry_concentration import (
    BOOKS, SCOPES, concentration_rows, concentration_distribution, industry_stock_details,
)

COLORS = dict(zip(BOOKS, ["#1c3e60", "#ae7e27", "#2d7e70", "#8c8894"]))


def render_stock_industry_concentration(data, snapshot_date):
    st.caption(
        "仅纳入已识别委内/委外的正市值直接股票，沿用持仓排名的去重与 OCI 规则；不含基金穿透及长股投股票。"
        "委外策略未填报，不推定为交易盘。行业为当前观察映射，非历史时点行业分类。"
    )
    rows = concentration_rows(data, snapshot_date)
    scope = st.radio("行业集中度范围", list(SCOPES), horizontal=True, key="industry-concentration-scope")
    dist = concentration_distribution(rows, scope)
    if dist.empty:
        st.info("当前时点和范围没有可展示的股票持仓。")
        return
    totals = dist.groupby("industry").market_value.sum().sort_values(ascending=False)
    total = totals.sum()
    known = totals.drop(UNMAPPED_INDUSTRY, errors="ignore")
    cols = st.columns(4)
    cols[0].metric("所选股票市值", f"{total:,.2f} 亿")
    for col, count in zip(cols[1:], [1, 3, 5]):
        col.metric(f"前 {count} 大行业集中度", f"{known.head(count).sum() / total:.1%}")
    unmapped = float(totals.get(UNMAPPED_INDUSTRY, 0))
    st.caption(f"行业映射覆盖率：{1 - unmapped / total:.1%}。未分类市值保留在分母和图表中，不计入前 N 大已识别行业。")
    unit = st.radio("主图显示", ["行业占所选股票市值比例", "行业市值（亿）"], horizontal=True, key="industry-concentration-unit")
    ratio = unit.startswith("行业占")
    order = totals.index.tolist()
    fig = go.Figure()
    present_books = [book for book in BOOKS if book in dist.portfolio.unique()]
    for book in present_books:
        part = dist.loc[dist.portfolio.eq(book)].set_index("industry").reindex(order).fillna(0)
        fig.add_trace(go.Bar(
            name=book, y=order, x=part.selected_share if ratio else part.market_value,
            orientation="h", marker_color=COLORS[book],
            customdata=part[["market_value", "selected_share", "company_share", "portfolio_share"]].to_numpy(),
            hovertemplate="%{y}<br>市值 %{customdata[0]:.2f} 亿<br>占所选范围 %{customdata[1]:.2%}<br>占公司股票 %{customdata[2]:.2%}<br>占本组合 %{customdata[3]:.2%}<extra>%{fullData.name}</extra>",
        ))
    fig.update_layout(barmode="stack", height=max(430, 25 * len(order)), margin=dict(l=5, r=15, t=35, b=10), legend=dict(orientation="h", y=1.1), clickmode="event+select")
    fig.update_yaxes(autorange="reversed", categoryorder="array", categoryarray=order)
    fig.update_xaxes(tickformat=".0%" if ratio else ".1f", title=unit)
    chart_cols = st.columns([1.3, 1])
    chart_cols[0].markdown("#### 行业集中度来源")
    event = chart_cols[0].plotly_chart(fig, width="stretch", key="industry-concentration-bar", on_select="rerun", selection_mode="points")

    chart_cols[1].markdown("#### 各组合内部行业占比")
    pivot = dist.pivot(index="industry", columns="portfolio", values="portfolio_share").reindex(index=order, columns=present_books).fillna(0)
    heat = go.Figure(go.Heatmap(
        z=pivot.to_numpy(), x=present_books, y=order, colorscale="Blues", zmin=0,
        text=pivot.map(lambda value: f"{value:.1%}").to_numpy(), texttemplate="%{text}",
        hovertemplate="%{y}<br>%{x}<br>占该组合股票市值 %{z:.2%}<extra></extra>",
        colorbar=dict(tickformat=".0%"),
    ))
    heat.update_layout(height=max(430, len(order) * 25), margin=dict(l=5, r=10, t=70, b=10))
    heat.update_yaxes(autorange="reversed")
    chart_cols[1].plotly_chart(heat, width="stretch", key="industry-concentration-heatmap")
    st.caption("每列以该组合股票市值为分母，合计 100%；没有持仓的组合不显示。")

    points = event.selection.points if event else []
    clicked = points[-1].get("y") if points else None
    selection_token = (snapshot_date, scope, clicked)
    if clicked in order and st.session_state.get("industry-concentration-last-click") != selection_token:
        st.session_state["industry-concentration-detail"] = clicked
    st.session_state["industry-concentration-last-click"] = selection_token
    if st.session_state.get("industry-concentration-detail") not in order:
        st.session_state["industry-concentration-detail"] = order[0]
    industry = st.selectbox("选择行业查看股票（也可点击上方柱图）", order, key="industry-concentration-detail")
    detail = industry_stock_details(rows, industry, scope).rename(columns={
        "_industry_code": "股票代码", "portfolio": "组合", "asset_name": "股票名称",
        "market_value": "市值（亿）", "industry_share": "占所选行业", "selected_share": "占所选股票范围",
    })
    st.dataframe(detail, hide_index=True, width="stretch", column_config={
        "市值（亿）": st.column_config.NumberColumn(format="%.3f"),
        "占所选行业": st.column_config.NumberColumn(format="percent"),
        "占所选股票范围": st.column_config.NumberColumn(format="percent"),
    })
    st.download_button("下载行业集中度明细 CSV", dist.to_csv(index=False).encode("utf-8-sig"), file_name=f"股票行业集中度-{snapshot_date}-{scope}.csv", key="industry-concentration-download")
