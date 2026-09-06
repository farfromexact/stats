"""Peer comparisons of observed investment exposure, separate from subject detail."""

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from outsourced_funding import adjust_outsourced_funding_capital


PEER_GROUPS = {
    "权益": ["权益委外", "委内股票", "委内权益产品"],
    "固收": ["固收委外", "委内固收产品", "委内固收直投"],
}
PRODUCT_CLASSES = {
    "债券型基金", "股票型基金", "混合型基金", "固收类保险资管产品",
    "股票型保险资管产品", "混合型保险资管产品", "信托计划", "债权计划",
    "资产支持计划", "持有型不动产ABS", "资产支持证券（非标）", "股权基金",
    "股权计划", "单一资产管理计划（股票类产品）", "公募REITS",
}
CASH_CLASSES = {"活期存款", "买入返售", "货币类基金", "货币类产品"}
DIRECT_CLASSES = {"存款", "股票", "长股投股票", "政府债", "金融债", "企业债", "同业存单", "资产支持证券", "未上市企业股权"}


def position_peer_history(rows, current_snapshot, board, include_interim=False):
    """Official month ends plus the latest subsequent interim, bounded by the selected date.

    include_interim is retained for older callers; the latest interim is now automatic.
    """
    working = rows.loc[
        rows["attribution_in_scope"]
        & rows["attribution_board"].eq(board)
        & rows["snapshot_date"].astype(str).le(str(current_snapshot))
    ].copy()
    working = adjust_outsourced_funding_capital(working)
    if working.empty:
        return pd.DataFrame(), pd.DataFrame()
    values = pd.to_numeric(working["full_market_value"], errors="coerce").fillna(0)
    positive = values.clip(lower=0)
    asset_class = working["asset_class"].fillna("").astype(str)
    working["product_value"] = positive.where(asset_class.isin(PRODUCT_CLASSES), 0)
    working["direct_value"] = positive.where(asset_class.isin(DIRECT_CLASSES), 0)
    working["cash_value"] = positive.where(asset_class.isin(CASH_CLASSES), 0)
    working["investment_value"] = working["product_value"] + working["direct_value"]
    working["other_positive_value"] = positive.where(
        ~asset_class.isin(PRODUCT_CLASSES | DIRECT_CLASSES | CASH_CLASSES), 0
    )
    working["financing_value"] = (-values).clip(lower=0).where(asset_class.eq("正回购"), 0)
    external, product, direct = (
        ("权益委外", "委内权益产品", "委内股票") if board == "权益"
        else ("固收委外", "委内固收产品", "委内固收直投")
    )
    working["peer_group"] = np.select(
        [working["attribution_scope"].eq("委外"), asset_class.isin(PRODUCT_CLASSES), asset_class.isin(DIRECT_CLASSES)],
        [external, product, direct], default="",
    )
    entity_keys = ["snapshot_date", "attribution_entity_id"]
    metadata = rows.loc[
        rows["snapshot_date"].astype(str).le(str(current_snapshot)),
        ["snapshot_date", "snapshot_month", "snapshot_status"],
    ].drop_duplicates()
    # Shared cash/income adjustments belong to a group only when that entity
    # has one investment group at this exact date. Never copy them across groups.
    core = working[working["peer_group"].ne("") & working["investment_value"].gt(0.0001)]
    memberships = core.groupby(entity_keys)["peer_group"].agg(["first", "nunique"])
    sole_group = memberships["first"].where(memberships["nunique"].eq(1)).rename("_sole_group")
    working = working.merge(sole_group, on=entity_keys, how="left", validate="many_to_one")
    working["peer_group"] = working["peer_group"].where(working["peer_group"].ne(""), working["_sole_group"].fillna(""))
    financial_columns = [f"{field}_{period}" for period in ["mtd", "ytd"] for field in ["comprehensive_income", "avg_capital"]]
    for column in financial_columns:
        working[column] = pd.to_numeric(working[column], errors="coerce") if column in working else np.nan
    cash = working.groupby(entity_keys, as_index=False)[["cash_value", "other_positive_value", "financing_value"]].sum()
    observed = working[working["peer_group"].ne("")].groupby(
        entity_keys + ["attribution_entity_name", "peer_group"], as_index=False, dropna=False
    )[["investment_value", "product_value", "direct_value", *financial_columns]].sum(min_count=1)
    for period in ["mtd", "ytd"]:
        observed[f"comprehensive_return_{period}"] = observed[f"comprehensive_income_{period}"].div(
            observed[f"avg_capital_{period}"].where(observed[f"avg_capital_{period}"].gt(0.0001))
        )
    active_groups = observed[observed["investment_value"] > 0.0001].groupby(entity_keys)["peer_group"].nunique().rename("active_groups").reset_index()
    observed = observed.merge(cash, on=entity_keys, validate="many_to_one").merge(active_groups, on=entity_keys, how="left", validate="many_to_one")
    observed["cash_value"] = observed["cash_value"].where(observed["active_groups"].eq(1))
    denominator = observed["investment_value"] + observed["cash_value"]
    observed["investment_share"] = observed["investment_value"].div(denominator.where(denominator > 0.0001))
    current = observed[observed["snapshot_date"].eq(current_snapshot) & observed["investment_value"].gt(0.0001)].copy()
    current["mixed_assets"] = current["active_groups"].gt(1)
    current = current.sort_values(["investment_value", "attribution_entity_name"], ascending=[False, True])
    official = metadata[metadata["snapshot_status"].eq("official")]
    official = official.sort_values("snapshot_date").groupby("snapshot_month", dropna=False).tail(1)
    dates = sorted(official["snapshot_date"].unique())
    interim = metadata[metadata["snapshot_status"].eq("interim")]
    if not interim.empty:
        latest_interim = str(interim["snapshot_date"].max())
        if not dates or latest_interim > dates[-1]:
            dates.append(latest_interim)
    if current.empty or not dates:
        return pd.DataFrame(), current
    grid = current[["attribution_entity_id", "attribution_entity_name", "peer_group"]].merge(pd.DataFrame({"snapshot_date": dates}), how="cross")
    merge_keys = ["attribution_entity_id", "peer_group", "snapshot_date"]
    history = grid.merge(observed.drop(columns=["attribution_entity_name"]), how="left", on=merge_keys, validate="one_to_one")
    history = history.sort_values(["peer_group", "attribution_entity_id", "snapshot_date"])
    history["market_value_change"] = history.groupby(["peer_group", "attribution_entity_id"], sort=False)["investment_value"].diff()
    history["baseline_snapshot_date"] = history["snapshot_date"].map(dict(zip(dates, [None, *dates[:-1]])))
    history["prior_investment_value"] = history.groupby(["peer_group", "attribution_entity_id"], sort=False)["investment_value"].shift()
    history["share_change_pp"] = history.groupby(["peer_group", "attribution_entity_id"], sort=False)["investment_share"].diff() * 100
    return history, current


def render_peer_income_trend(selected, order, period, view_choice):
    is_return = view_choice == "综合收益率"
    metric = f"comprehensive_{'return' if is_return else 'income'}_{period}"
    label = f"{period.upper()}{view_choice}"
    st.markdown(f"##### {label}趋势 · 同组比较")
    if selected[metric].notna().sum() == 0:
        st.info("本组暂无可展示的收益趋势数据。")
        return
    plot_data = selected.sort_values(["attribution_entity_id", "snapshot_date"]).copy()
    # A missing observation must break a line instead of joining across the gap.
    plot_data["_gap"] = plot_data[metric].isna().groupby(plot_data["attribution_entity_id"]).cumsum()
    plot_data["_segment"] = plot_data["attribution_entity_id"].astype(str) + "::" + plot_data["_gap"].astype(str)
    focus = alt.selection_point(fields=["attribution_entity_name"], bind="legend")
    chart = alt.Chart(plot_data).mark_line(point=alt.OverlayMarkDef(size=65), strokeWidth=2.5).encode(
        x=alt.X("snapshot_date:T", title=None, axis=alt.Axis(format="%Y-%m-%d", labelAngle=-35, values=sorted(plot_data["snapshot_date"].unique()))),
        y=alt.Y(f"{metric}:Q", title=label + ("（对称对数刻度）" if is_return else "(亿，对称对数刻度)"), scale=alt.Scale(type="symlog", constant=0.01 if is_return else 1), axis=alt.Axis(format=".1%" if is_return else ",.1f")),
        color=alt.Color("attribution_entity_name:N", title=None, sort=order, scale=alt.Scale(
            domain=order,
            range=["#1B3A5C", "#2F7A6B", "#B78021", "#8056A3", "#B54A50", "#297A9B", "#626E2F", "#A65D2A", "#89576A", "#4C63A6", "#4E8172", "#6F6254"],
        ), legend=alt.Legend(orient="top", columns=4, labelLimit=220)),
        detail="_segment:N",
        opacity=alt.condition(focus, alt.value(1), alt.value(.15)),
        tooltip=[
            alt.Tooltip("attribution_entity_name:N", title="主体"),
            alt.Tooltip("_date_label:N", title="数据时点"),
            alt.Tooltip(f"comprehensive_income_{period}:Q", title=f"{period.upper()}综合收益额(亿)", format="+,.2f"),
            alt.Tooltip(f"comprehensive_return_{period}:Q", title=f"{period.upper()}综合收益率", format=".2%"),
            alt.Tooltip(f"avg_capital_{period}:Q", title="同期平均资金占用(亿)", format=",.4f"),
        ],
    ).add_params(focus).properties(height=350).configure_view(strokeWidth=0)
    st.altair_chart(chart, width="stretch")
    st.caption(
        "默认显示本组全部主体；点击图例可高亮。纵轴压缩极端值，悬停保留实际收益和分母。"
        + ("各点为当月累计收益，临时点为月内截至当日，不能当作完整月份收益。" if period == "mtd" else "各点为年初至该时点累计收益。")
    )


def render_position_peer_comparison(rows, current_snapshot, board, include_interim, key_suffix, period="ytd", view_choice="综合收益额"):
    st.markdown("#### 同类主体 · 趋势与规模变化")
    history, peers = position_peer_history(rows, current_snapshot, board)
    if peers.empty:
        st.info("当前板块暂无可按投资持仓分组的主体。")
        return
    group = st.radio(
        "比较分组", PEER_GROUPS[board], horizontal=True, key=f"manager-position-peer-{key_suffix}",
        format_func=lambda name: f"{name}（{int(peers['peer_group'].eq(name).sum())}）",
    )
    members = peers[peers["peer_group"].eq(group)]
    if members.empty:
        st.info(f"当前{board}板块没有{group}主体。")
        return
    if history.empty:
        st.info("当前范围没有可展示的趋势时点。")
        return
    selected = history[history["peer_group"].eq(group) & history["attribution_entity_id"].isin(members["attribution_entity_id"])].copy()
    dates = sorted(selected["snapshot_date"].unique())
    order = members["attribution_entity_name"].tolist()
    selected["_date_label"] = selected["snapshot_date"].astype(str)
    interim_dates = set(rows.loc[rows["snapshot_status"].eq("interim"), "snapshot_date"].astype(str))
    selected.loc[selected["snapshot_date"].isin(interim_dates), "_date_label"] += " *"
    st.caption(f"{group}共 {len(members)} 个主体，全部同组比较；历史采用月末正式版，自动追加所选时点以内最新的后续临时版（*）。")
    render_peer_income_trend(selected, order, period, view_choice)
    st.markdown("##### 较上期规模变化")
    latest = selected[selected["snapshot_date"].eq(dates[-1])].copy()
    baseline = latest["baseline_snapshot_date"].iloc[0]
    if pd.notna(baseline):
        st.caption(f"最新列：{dates[-1]}{' 临时中间版' if dates[-1] in interim_dates else ' 月末正式版'} − {baseline} 月末正式版。历史各列均对比上一可用正式月末；— 表示缺少可比记录。")
    else:
        st.caption("尚无更早的正式月末基准，规模变化留空；不将缺失记录视为零。")
    metric = "market_value_change"
    tooltip = [
        alt.Tooltip("attribution_entity_name:N", title="主体"),
        alt.Tooltip("_date_label:N", title="数据时点"),
        alt.Tooltip("baseline_snapshot_date:N", title="对比正式月末"),
        alt.Tooltip("market_value_change:Q", title="较上期规模变化(亿)", format="+,.2f"),
        alt.Tooltip("investment_value:Q", title="本期投资持仓市值(亿)", format=",.2f"),
        alt.Tooltip("prior_investment_value:Q", title="对比期投资持仓市值(亿)", format=",.2f"),
    ]
    largest = max(float(selected[metric].abs().max()) if selected[metric].notna().any() else 0, .01)
    color_scale = alt.Scale(type="symlog", constant=1, domain=[-largest, 0, largest], range=["#963F3D", "#F4F3EE", "#2F7A6B"])
    darkness = np.log1p(selected[metric].abs()) / np.log1p(largest)
    selected["_value_label"] = selected[metric].map(lambda v: f"{v:+.2f}" if pd.notna(v) else "—")
    selected["_label_color"] = np.where(darkness > .55, "#FFFFFF", "#1B3A5C")
    base = alt.Chart(selected).encode(
        x=alt.X("_date_label:N", title=None, sort=sorted(selected["_date_label"].unique()), axis=alt.Axis(labelAngle=-45, labelOverlap=False, labelLimit=160)),
        y=alt.Y("attribution_entity_name:N", title=None, sort=order, axis=alt.Axis(labelLimit=260)),
    )
    cells = base.mark_rect(stroke="#FFFFFF", strokeWidth=2).encode(
        color=alt.Color(f"{metric}:Q", title="规模变化(亿)", scale=color_scale, legend=alt.Legend(format="+,.2f")), tooltip=tooltip,
    )
    labels = base.mark_text(fontSize=11).encode(text="_value_label:N", color=alt.Color("_label_color:N", scale=None, legend=None), tooltip=tooltip)
    chart = (cells + labels).resolve_scale(color="independent").properties(height=max(140, len(members) * 34)).configure_view(strokeWidth=0)
    st.altair_chart(chart, width="stretch")
    st.caption("规模为本组投资资产正市值，不含活期存款、货币类及买入返售。变化包含价格和归属调整，不等同于净买卖；颜色压缩极端值，数字为实际金额。")
    table = latest.set_index("attribution_entity_name").reindex(order).reset_index()[["attribution_entity_name", "baseline_snapshot_date", "prior_investment_value", "investment_value", "market_value_change"]].rename(columns={
        "attribution_entity_name": "主体", "baseline_snapshot_date": "对比正式月末", "prior_investment_value": "对比期规模(亿)",
        "investment_value": "本期规模(亿)", "market_value_change": "规模变化(亿)",
    })
    st.dataframe(table.style.format({"对比期规模(亿)": "{:,.2f}", "本期规模(亿)": "{:,.2f}", "规模变化(亿)": "{:+,.2f}"}, na_rep="—"), hide_index=True, width="stretch")
    with st.expander("分组口径与完整数据"):
        st.caption("委外按受托方；委内按股票、权益产品、固收产品、固收直投分别计算。跨组主体仅统计对应资产；未能分配的共享现金收益及调节项不向各组摊派。产品包含基金、资管及非标计划，不做内部穿透。")
        export = selected.drop(columns=["_date_label", "_value_label", "_label_color"])
        export = export.rename(columns={"snapshot_date": "数据时点", "attribution_entity_name": "主体", "peer_group": "分组", "baseline_snapshot_date": "对比正式月末", "investment_value": "本期规模(亿)", "prior_investment_value": "对比期规模(亿)", "market_value_change": "规模变化(亿)"})
        st.download_button("下载本组趋势与规模变化 CSV", export.to_csv(index=False).encode("utf-8-sig"), file_name=f"{board}-{group}-趋势与规模变化.csv", mime="text/csv", key=f"manager-position-download-{key_suffix}")
