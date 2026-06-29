"""广告位报表清洗、汇总分析与 Streamlit 展示。

输出结构（get_placement_analysis）
---------------------------------
- summary: 按 (活动, 放置) 聚合展示量/点击/订单/花费/ACOS
- daily_details: 每个 (活动, 放置) 的按日明细
- top/worst_placements_by_activity: 每活动 ACOS 最低/最高放置（供 Agent 摘要）
"""
import pandas as pd
import numpy as np
import streamlit as st
from data_df_store.data_store import store
from utils.date_parse import coerce_report_dates, maybe_warn_date_parse_failures


def _fmt_int_display(val) -> str:
    """展示用整数格式（历史库 float 汇总后避免长小数）。"""
    if pd.isna(val):
        return "-"
    try:
        return f"{int(round(float(val))):,}"
    except (TypeError, ValueError):
        return str(val)


def clean_placement_data(df: pd.DataFrame) -> pd.DataFrame:
    """清洗广告位报表，转换数值列并计算点击率。

    Args:
        df (pd.DataFrame): 原始广告位报表 DataFrame。

    Returns:
        pd.DataFrame: 清洗后的 DataFrame。

    Raises:
        None
    """
    df_clean = df.copy()
    df_clean, date_failed = coerce_report_dates(df_clean, "日期")
    maybe_warn_date_parse_failures(date_failed, "广告位报表")

    def to_float(series):
        """将 Series 清洗并转换为浮点数。

        Args:
            series: 待转换的 pandas Series。

        Returns:
            pd.Series: 转换后的数值 Series。

        Raises:
            None
        """
        s = series.astype(str).str.strip()
        s = s.str.replace(r'[¥$€]', '', regex=True)
        s = s.str.replace(',', '', regex=False)
        s = s.str.replace(r'\s+', '', regex=True)
        s = s.replace('', pd.NA)
        return pd.to_numeric(s, errors='coerce')

    def to_percent_float(series):
        """将百分比字符串 Series 转换为 0-1 范围的浮点数。

        Args:
            series: 含百分号的 pandas Series。

        Returns:
            pd.Series: 转换后的小数 Series。

        Raises:
            None
        """
        s = series.astype(str).str.replace('%', '', regex=False).str.strip()
        s = s.replace('', pd.NA)
        return pd.to_numeric(s, errors='coerce') / 100

    # 转换花费、销售额、CPC
    df_clean['花费_数值'] = to_float(df_clean['花费'])
    df_clean['7天总销售额_数值'] = to_float(df_clean['7天总销售额'])
    df_clean['单次点击成本 (CPC)_数值'] = to_float(df_clean['单次点击成本 (CPC)']).fillna(0)
    df_clean['ACOS_数值'] = to_percent_float(df_clean['广告投入产出比 (ACOS) 总计'])

    # 转换展示量、点击量（确保数值）
    df_clean['展示量'] = pd.to_numeric(df_clean['展示量'], errors='coerce')
    df_clean['点击量'] = pd.to_numeric(df_clean['点击量'], errors='coerce')

    orders_col = '7天总订单数(#)' if '7天总订单数(#)' in df_clean.columns else '7天总订单数'
    if orders_col in df_clean.columns:
        df_clean['7天总订单数'] = pd.to_numeric(df_clean[orders_col], errors='coerce').fillna(0)
    else:
        df_clean['7天总订单数'] = 0

    df_clean['转化率'] = np.where(
        df_clean['点击量'] > 0,
        df_clean['7天总订单数'] / df_clean['点击量'],
        np.nan,
    )

    # 计算点击率
    df_clean['点击率'] = df_clean['点击量'] / df_clean['展示量']
    # 移动列
    click_pos = df_clean.columns.get_loc('点击量')
    ctr_col = df_clean.pop('点击率')
    df_clean.insert(click_pos + 1, '点击率', ctr_col)

    # 保留必要列（增加日期）
    keep_cols = ['日期', '广告活动名称', '放置', '展示量', '点击量', '点击率',
                 '7天总订单数', '转化率',
                 '单次点击成本 (CPC)_数值', '花费_数值', '7天总销售额_数值', 'ACOS_数值']
    # 只保留存在的列
    keep_cols = [c for c in keep_cols if c in df_clean.columns]
    df_clean = df_clean[keep_cols]
    return df_clean

@st.cache_data(ttl=3600)
def get_placement_analysis(df_clean: pd.DataFrame) -> dict:
    """汇总广告位数据：按 (活动, 放置) 求和后再算整体 CTR/CVR/ACOS（非 ACOS 平均）。"""
    if df_clean is None or df_clean.empty:
        return {"summary": [], "top_placements": [], "worst_placements": [], "daily_details": {}}

    required_cols = [
        '日期', '广告活动名称', '放置', '展示量', '点击量', '7天总订单数',
        '花费_数值', '7天总销售额_数值', 'ACOS_数值', '点击率',
    ]
    missing = [c for c in required_cols if c not in df_clean.columns]

    if missing:
        return {"summary": [], "top_placements": [], "worst_placements": [], "daily_details": {},
                "error": f"缺少列: {missing}"}

    summary_df = df_clean.groupby(['广告活动名称', '放置']).agg(
        总展示量=('展示量', 'sum'),
        总点击量=('点击量', 'sum'),
        总订单数=('7天总订单数', 'sum'),
        总花费=('花费_数值', 'sum'),
        总销售额=('7天总销售额_数值', 'sum')
    ).reset_index()

    # 计算整体点击率、转化率与整体ACOS
    summary_df['整体点击率'] = summary_df['总点击量'] / summary_df['总展示量']
    summary_df['整体转化率'] = np.where(
        summary_df['总点击量'] > 0,
        summary_df['总订单数'] / summary_df['总点击量'],
        np.nan,
    )
    # 整体 ACOS = 总花费 / 总销售额（先聚合再除，避免对日 ACOS 做平均）
    summary_df['整体ACOS'] = summary_df['总花费'] / summary_df['总销售额']
    summary_df['整体ACOS'] = summary_df['整体ACOS'].replace([np.inf, -np.inf], np.nan)

    # 已经计算好 summary_df，包含每个 (广告活动名称, 放置) 的 总花费、总销售额、整体ACOS
    # 注意整体ACOS计算：总花费/总销售额
    # 为每个广告活动，找出最佳和最差的放置
    top_by_activity = []
    worst_by_activity = []
    for activity, group in summary_df.groupby('广告活动名称'):
        # 按整体ACOS排序
        group_sorted = group.sort_values('整体ACOS')
        # 最佳两个（ACOS最低）
        best = group_sorted.head(1)
        # 最差两个（ACOS最高）
        worst = group_sorted.tail(1)
        for _, row in best.iterrows():
            top_by_activity.append({
                '广告活动名称': activity,
                '放置': row['放置'],
                '整体ACOS': row['整体ACOS']
            })
        for _, row in worst.iterrows():
            worst_by_activity.append({
                '广告活动名称': activity,
                '放置': row['放置'],
                '整体ACOS': row['整体ACOS']
            })

    # 每日明细（排除日期无法解析的行）
    daily_details = {}
    df_dated = df_clean.dropna(subset=['日期']) if '日期' in df_clean.columns else df_clean
    for (act, placement), group in df_dated.groupby(['广告活动名称', '放置']):
        daily = group[
            ['日期', '展示量', '点击量', '7天总订单数', '花费_数值', '7天总销售额_数值', '点击率', 'ACOS_数值']
        ].copy()
        daily = daily.sort_values('日期')
        daily.rename(columns={
            '7天总订单数': '订单数',
            '花费_数值': '花费',
            '7天总销售额_数值': '销售额',
            'ACOS_数值': 'ACOS',
        }, inplace=True)
        daily_details[(act, placement)] = daily.to_dict(orient='records')

    return {
        "summary": summary_df.to_dict(orient='records'),
        "top_placements_by_activity": top_by_activity,  # 每个活动的最佳放置
        "worst_placements_by_activity": worst_by_activity,  # 每个活动的最差放置
        "daily_details": daily_details
    }


def render_placement_analysis_result(result: dict, *, key_prefix: str = "placement") -> None:
    """展示汇总表、每活动最佳/最差放置、以及筛选后的每日明细。"""
    if result.get("error"):
        st.warning(result["error"])
        return
    if not result["summary"]:
        st.info("没有有效的广告位数据")
        return

    all_activities = sorted(set(item["广告活动名称"] for item in result["summary"]))
    all_placements = sorted(set(item["放置"] for item in result["summary"]))
    col1, col2 = st.columns(2)
    with col1:
        selected_activities = st.multiselect(
            "👇 选择广告活动",
            all_activities,
            default=[],
            placeholder="点击选择活动...",
            key=f"{key_prefix}_activity_filter",
        )
    with col2:
        selected_placements = st.multiselect(
            "👇 选择广告位类型",
            all_placements,
            default=[],
            placeholder="点击选择广告位...",
            key=f"{key_prefix}_filter",
        )
    if not selected_activities or not selected_placements:
        st.caption("💡 请同时选择「广告活动」和「广告位」以查看汇总及每日明细。")

    filtered_summary = [
        item
        for item in result["summary"]
        if item["广告活动名称"] in selected_activities and item["放置"] in selected_placements
    ]
    if not filtered_summary:
        st.info("没有符合筛选条件的数据")
        return

    summary_df = pd.DataFrame(filtered_summary)
    summary_df.rename(
        columns={
            "总展示量": "展示量",
            "总点击量": "点击量",
            "总订单数": "订单数",
            "整体点击率": "点击率(整体)",
            "整体ACOS": "ACOS(整体)",
        },
        inplace=True,
    )
    for col in ("展示量", "点击量", "订单数"):
        if col in summary_df.columns:
            summary_df[col] = summary_df[col].apply(_fmt_int_display)
    if "点击率(整体)" in summary_df.columns:
        summary_df["点击率(整体)"] = summary_df["点击率(整体)"].apply(
            lambda x: f"{x:.1%}" if pd.notna(x) else "-"
        )
    if "ACOS(整体)" in summary_df.columns:
        summary_df["ACOS(整体)"] = summary_df["ACOS(整体)"].apply(
            lambda x: f"{x:.1%}" if pd.notna(x) else "-"
        )

    display_cols = [
        "广告活动名称", "放置", "展示量", "点击量", "订单数",
        "总花费", "总销售额", "点击率(整体)", "ACOS(整体)",
    ]
    available_cols = [c for c in display_cols if c in summary_df.columns]
    st.dataframe(summary_df[available_cols], use_container_width=True)

    filtered_summary_df = pd.DataFrame(filtered_summary)
    top_by_activity = []
    worst_by_activity = []
    for act, group in filtered_summary_df.groupby("广告活动名称"):
        group_sorted = group.sort_values("整体ACOS")
        best = group_sorted.head(1)
        worst = group_sorted.tail(1)
        for _, row in best.iterrows():
            top_by_activity.append(
                {"广告活动名称": act, "放置": row["放置"], "整体ACOS": row["整体ACOS"]}
            )
        for _, row in worst.iterrows():
            worst_by_activity.append(
                {"广告活动名称": act, "放置": row["放置"], "整体ACOS": row["整体ACOS"]}
            )

    if top_by_activity:
        st.success("✅ 各广告活动表现最佳的广告位（ACOS最低）：")
        top_df = pd.DataFrame(top_by_activity)
        top_df["整体ACOS"] = top_df["整体ACOS"].apply(lambda x: f"{x:.1%}" if pd.notna(x) else "-")
        st.dataframe(top_df, use_container_width=True)

    if worst_by_activity:
        st.error("⚠️ 各广告活动表现最差的广告位（ACOS最高）：")
        worst_df = pd.DataFrame(worst_by_activity)
        worst_df["整体ACOS"] = worst_df["整体ACOS"].apply(lambda x: f"{x:.1%}" if pd.notna(x) else "-")
        st.dataframe(worst_df, use_container_width=True)

    if result["daily_details"] and selected_activities and selected_placements:
        st.markdown("---")
        with st.expander("📅 各广告活动+广告位每日明细（点击展开）"):
            for act, place in [(a, p) for a in selected_activities for p in selected_placements]:
                if (act, place) not in result["daily_details"]:
                    continue
                daily_records = result["daily_details"][(act, place)]
                daily_df = pd.DataFrame(daily_records)
                total_spend = daily_df["花费"].sum()
                total_sales = daily_df["销售额"].sum()
                avg_acos = total_spend / total_sales if total_sales > 0 else 0
                with st.expander(
                    f"📁 {act} - {place} | 总花费: {total_spend:.2f} | "
                    f"总销售额: {total_sales:.2f} | ACOS: {avg_acos:.1%}"
                ):
                    display_daily = daily_df.copy()
                    for col in ("展示量", "点击量", "订单数"):
                        if col in display_daily.columns:
                            display_daily[col] = display_daily[col].apply(_fmt_int_display)
                    display_daily["点击率"] = display_daily["点击率"].apply(
                        lambda x: f"{x:.1%}" if pd.notna(x) else "-"
                    )
                    display_daily["ACOS"] = display_daily["ACOS"].apply(
                        lambda x: f"{x:.1%}" if pd.notna(x) else "-"
                    )
                    daily_cols = ["日期", "展示量", "点击量", "订单数", "花费", "销售额", "点击率", "ACOS"]
                    available_daily = [c for c in daily_cols if c in display_daily.columns]
                    st.dataframe(display_daily[available_daily], use_container_width=True)
            st.markdown("**建议**：关注ACOS异常偏高的日期和广告位组合，调整出价或否定词。")


def analyze_placement(df_clean: pd.DataFrame) -> None:
    """Streamlit UI 展示广告位分析结果（输入必须是清洗后的中文列名DataFrame）"""
    result = store.get("placement_analysis_result")
    if result is None:
        result = get_placement_analysis(df_clean)
        store.set("placement_analysis_result", result)
    st.subheader("📈 广告位效果分析")
    render_placement_analysis_result(result, key_prefix="placement")



    
