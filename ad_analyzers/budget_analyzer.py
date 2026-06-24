import pandas as pd
import numpy as np
import streamlit as st
from data_df_store.data_store import store
from utils.date_parse import coerce_report_dates, maybe_warn_date_parse_failures


def max_consecutive_over_threshold(
    daily_df: pd.DataFrame,
    threshold: float,
    date_col: str = "日期",
    usage_col: str = "使用率",
) -> int:
    """计算使用率超过阈值的最长连续日历天数。"""
    if daily_df is None or daily_df.empty:
        return 0

    daily = daily_df.sort_values(date_col).drop_duplicates(subset=[date_col], keep="last")
    max_streak = 0
    current_streak = 0
    prev_date = None

    for _, row in daily.iterrows():
        usage = row[usage_col]
        if pd.isna(usage):
            current_streak = 0
            prev_date = row[date_col]
            continue

        if float(usage) > threshold:
            if prev_date is None or (row[date_col] - prev_date).days == 1:
                current_streak += 1
            else:
                current_streak = 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 0
        prev_date = row[date_col]

    return max_streak


# 核心函数逻辑，用于Agent和UI界面
@st.cache_data(ttl=3600)
def get_budget_analysis(
    df: pd.DataFrame,
    threshold: float = 0.9,
    consecutive_days: int = 3,
) -> dict:
    """
    纯数据分析函数，返回预算分析结果字典，不包含任何 UI 渲染。
    问题活动判定：最长连续日历天数内，使用率 > threshold 的天数 streak >= consecutive_days。
    """
    if df is None or df.empty:
        return {"problem_activities": [], "summary": [], "daily_details": {}}

    col_budget = '预算'
    col_spent = '花费'
    col_date = '日期'
    col_activity = '广告活动名称'

    needed = [col_budget, col_spent, col_date, col_activity]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        return {"problem_activities": [], "summary": [], "daily_details": {}, "error": f"缺少列: {missing}"}

    def clean_series(series):
        s = series.astype(str).str.strip()
        s = s.str.replace(r'[¥$€]', '', regex=True)
        s = s.str.replace(',', '', regex=False)
        s = s.str.replace(r'\s+', '', regex=True)
        s = s.replace('', pd.NA)
        return pd.to_numeric(s, errors='coerce')

    df_clean = df.copy()
    df_clean['预算'] = clean_series(df_clean[col_budget])
    df_clean['花费'] = clean_series(df_clean[col_spent])
    df_clean, date_failed = coerce_report_dates(df_clean, col_date)
    maybe_warn_date_parse_failures(date_failed, "预算报表")
    df_clean = df_clean.dropna(subset=['日期', '预算', '花费'])

    if df_clean.empty:
        return {"problem_activities": [], "summary": [], "daily_details": {}}

    df_clean['使用率'] = df_clean['花费'] / df_clean['预算']

    activity_stats = []
    for activity, group in df_clean.groupby(col_activity):
        streak = max_consecutive_over_threshold(group, threshold)
        stat_days = int(group['日期'].dt.normalize().nunique())
        activity_stats.append(
            {
                "广告活动名称": activity,
                "连续超标天数": streak,
                "统计天数": stat_days,
                "is_problem": streak >= consecutive_days,
            }
        )

    problem_activities = [item["广告活动名称"] for item in activity_stats if item["is_problem"]]

    if not problem_activities:
        return {
            "problem_activities": [],
            "summary": [],
            "daily_details": {},
            "config_used": {
                "budget_usage_threshold": threshold,
                "consecutive_days": consecutive_days,
            },
        }

    problem_df = df_clean[df_clean[col_activity].isin(problem_activities)]
    summary_df = problem_df.groupby(col_activity).agg(
        总预算=('预算', 'sum'),
        总花费=('花费', 'sum'),
        最高使用率=('使用率', 'max'),
        平均使用率=('使用率', 'mean'),
    ).reset_index()
    summary_df['最高使用率'] = summary_df['最高使用率'].round(4)
    summary_df['平均使用率'] = summary_df['平均使用率'].round(4)

    stats_map = {item["广告活动名称"]: item for item in activity_stats}
    summary_df['连续超标天数'] = summary_df[col_activity].map(
        lambda x: stats_map.get(x, {}).get("连续超标天数", 0)
    )
    summary_df['统计天数'] = summary_df[col_activity].map(
        lambda x: stats_map.get(x, {}).get("统计天数", 0)
    )
    summary_records = summary_df.to_dict(orient='records')

    daily_details = {}
    for act in problem_activities:
        daily = df_clean[df_clean[col_activity] == act][[col_date, '预算', '花费', '使用率']].copy()
        daily = daily.sort_values(col_date)
        daily_details[act] = daily.to_dict(orient='records')

    return {
        "problem_activities": problem_activities,
        "summary": summary_records,
        "daily_details": daily_details,
        "config_used": {
            "budget_usage_threshold": threshold,
            "consecutive_days": consecutive_days,
        },
    }


def render_budget_analysis_result(
    result: dict,
    threshold: float,
    consecutive_days: int,
    key_prefix: str = "budget",
) -> None:
    """展示预算分析结果（与 analyze_budget 相同 UI，可指定 widget key 前缀）。"""
    if result.get("error"):
        st.warning(result["error"])
        return
    if not result["problem_activities"]:
        st.success(
            f"✅ 所有广告活动正常，未发现连续 ≥ {consecutive_days} 天预算使用率超过 {threshold:.0%} 的情况。"
        )
        return

    st.warning(
        f"⚠️ 以下 {len(result['problem_activities'])} 个活动存在连续 ≥ {consecutive_days} 天"
        f"预算使用率超过 {threshold:.0%}："
    )

    summary_export_df = pd.DataFrame(result["summary"])
    st.download_button(
        label="📥 导出当前分析结果为 CSV",
        data=summary_export_df.to_csv(index=False).encode("utf-8-sig"),
        file_name="预算分析汇总.csv",
        mime="text/csv",
        key=f"{key_prefix}_summary_export",
    )

    all_activities = sorted(set(item["广告活动名称"] for item in result["summary"]))
    selected_activities = st.multiselect(
        "👇 请勾选活动查看每日明细（默认不展示以防卡顿）",
        all_activities,
        default=[],
        key=f"{key_prefix}_activity_filter",
    )

    filtered_summary = [item for item in result["summary"] if item["广告活动名称"] in selected_activities]
    if not filtered_summary:
        st.info("勾选上方活动后可查看汇总与每日明细")
        return

    summary_df = pd.DataFrame(filtered_summary)
    if "最高使用率" in summary_df.columns:
        summary_df["最高使用率"] = summary_df["最高使用率"].apply(lambda x: f"{x:.1%}")
    if "平均使用率" in summary_df.columns:
        summary_df["平均使用率"] = summary_df["平均使用率"].apply(lambda x: f"{x:.1%}")
    st.dataframe(summary_df, use_container_width=True)

    if result["daily_details"] and selected_activities:
        st.markdown("---")
        with st.expander("📅 问题活动每日预算明细（点击展开）"):
            for act in selected_activities:
                if act not in result["daily_details"]:
                    continue
                daily_records = result["daily_details"][act]
                daily_df = pd.DataFrame(daily_records)
                daily_df["预算"] = pd.to_numeric(daily_df["预算"])
                daily_df["花费"] = pd.to_numeric(daily_df["花费"])
                daily_df["使用率"] = pd.to_numeric(daily_df["使用率"])

                total_budget = daily_df["预算"].sum()
                total_spent = daily_df["花费"].sum()
                avg_usage = total_spent / total_budget if total_budget > 0 else 0

                with st.expander(
                    f"📁 {act} | 总预算: {total_budget:.2f} | 总花费: {total_spent:.2f} | 平均使用率: {avg_usage:.1%}"
                ):
                    styled = daily_df.style.apply(
                        lambda row: ["background: #ffcccc" if row["使用率"] > threshold else "" for _ in row],
                        axis=1,
                    ).format({
                        "预算": "{:.2f}",
                        "花费": "{:.2f}",
                        "使用率": "{:.1%}",
                    })
                    st.dataframe(styled, use_container_width=True)
            st.markdown("**提示**：请结合下方「预算诊断」查看是否建议加码。")


def analyze_budget(df: pd.DataFrame) -> None:
    """在 Streamlit 界面展示预算分析结果。"""
    cfg = store.get("diagnosis_config") or {}
    threshold = float(cfg.get("budget_usage_threshold", 0.9))
    consecutive_days = int(cfg.get("consecutive_days", 3))

    result = store.get("budget_analysis_result")
    if result is None:
        result = get_budget_analysis(
            df,
            threshold=threshold,
            consecutive_days=consecutive_days,
        )
        store.set("budget_analysis_result", result)

    render_budget_analysis_result(
        result,
        threshold=threshold,
        consecutive_days=consecutive_days,
        key_prefix="budget",
    )
