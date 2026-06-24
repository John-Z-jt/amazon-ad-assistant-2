# ad_analyzers/search_analyzer.py
import pandas as pd
import numpy as np
import streamlit as st
from typing import Dict, Any
from data_df_store.data_store import store
from utils.date_parse import coerce_report_dates, maybe_warn_date_parse_failures

# ---------- 通用清洗函数 ----------
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

def _ensure_match_type_column(df_clean: pd.DataFrame) -> pd.DataFrame:
    if "匹配类型" not in df_clean.columns:
        df_clean["匹配类型"] = "—"
    else:
        df_clean["匹配类型"] = (
            df_clean["匹配类型"].astype(str).str.strip().replace({"": "—", "nan": "—", "None": "—"})
        )
    return df_clean


SEARCH_GROUP_KEYS = ["广告活动名称", "广告组名称", "投放", "匹配类型", "客户搜索词"]


def clean_search_report(df: pd.DataFrame) -> pd.DataFrame:
    """清洗搜索词报表"""
    df_clean = df.copy()
    df_clean, date_failed = coerce_report_dates(df_clean, "日期")
    maybe_warn_date_parse_failures(date_failed, "搜索词报表")

    df_clean['展示量'] = pd.to_numeric(df_clean['展示量'], errors='coerce')
    df_clean['点击量'] = pd.to_numeric(df_clean['点击量'], errors='coerce')
    df_clean['7天总订单数(#)'] = pd.to_numeric(df_clean['7天总订单数(#)'], errors='coerce')

    df_clean['花费_数值'] = to_float(df_clean['花费'])
    df_clean['7天总销售额_数值'] = to_float(df_clean['7天总销售额'])
    df_clean['单次点击成本 (CPC)_数值'] = to_float(df_clean['单次点击成本 (CPC)']).fillna(0)

    if '广告投入产出比 (ACOS) 总计' in df_clean.columns:
        df_clean['ACOS_数值'] = to_percent_float(df_clean['广告投入产出比 (ACOS) 总计'])
    else:
        df_clean['ACOS_数值'] = np.nan

    df_clean['点击率'] = df_clean['点击量'] / df_clean['展示量']
    df_clean['转化率'] = df_clean['7天总订单数(#)'] / df_clean['点击量']

    df_clean = _ensure_match_type_column(df_clean)

    keep_cols = ['日期', '广告活动名称', '广告组名称', '投放', '匹配类型', '客户搜索词', '展示量', '点击量', '点击率', '转化率',
                 '花费_数值', '7天总销售额_数值', '7天总订单数(#)', '单次点击成本 (CPC)_数值', 'ACOS_数值']
    keep_cols = [c for c in keep_cols if c in df_clean.columns]
    df_clean = df_clean[keep_cols]
    df_clean = df_clean.dropna(subset=['花费_数值', '7天总销售额_数值'], how='all')
    return df_clean

@st.cache_data(ttl=3600)
def get_search_analysis(df_clean: pd.DataFrame) -> Dict[str, Any]:
    """
    按广告活动、广告组、投放、匹配类型、客户搜索词分组聚合，返回汇总和每日明细
    """
    if df_clean is None or df_clean.empty:
        return {"summary": [], "daily_details": {}}

    df_clean = _ensure_match_type_column(df_clean.copy())

    required = ['广告活动名称', '广告组名称', '投放', '客户搜索词', '展示量', '点击量', '花费_数值', '7天总销售额_数值', '7天总订单数(#)']
    missing = [c for c in required if c not in df_clean.columns]
    if missing:
        return {"summary": [], "daily_details": {}, "error": f"缺少列: {missing}"}

    summary_df = df_clean.groupby(SEARCH_GROUP_KEYS).agg(
        总展示量=('展示量', 'sum'),
        总点击量=('点击量', 'sum'),
        总花费=('花费_数值', 'sum'),
        总销售额=('7天总销售额_数值', 'sum'),
        总订单数=('7天总订单数(#)', 'sum')
    ).reset_index()

    summary_df['平均CPC'] = summary_df['总花费'] / summary_df['总点击量']
    summary_df['总点击率'] = summary_df['总点击量'] / summary_df['总展示量']
    summary_df['总转化率'] = summary_df['总订单数'] / summary_df['总点击量']
    summary_df['总ACOS'] = summary_df['总花费'] / summary_df['总销售额']
    summary_df.replace([np.inf, -np.inf], np.nan, inplace=True)

    daily_details = {}
    if '日期' in df_clean.columns:
        df_clean = df_clean.dropna(subset=['日期'])
        for (act, adg, kw, match_type, term), group in df_clean.groupby(SEARCH_GROUP_KEYS):
            daily = group[['日期', '花费_数值', '7天总销售额_数值', '点击量', '展示量', '7天总订单数(#)', '单次点击成本 (CPC)_数值']].copy()
            daily = daily.sort_values('日期')
            daily.rename(columns={
                '花费_数值': '花费',
                '7天总销售额_数值': '销售额',
                '点击量': '点击量',
                '展示量': '展示量',
                '7天总订单数(#)': '订单数',
                '单次点击成本 (CPC)_数值': 'CPC'
            }, inplace=True)
            daily['点击率'] = daily['点击量'] / daily['展示量']
            daily['转化率'] = daily['订单数'] / daily['点击量']
            daily['ACOS'] = daily['花费'] / daily['销售额']
            daily_details[(act, adg, kw, match_type, term)] = daily.to_dict(orient='records')

    return {
        "summary": summary_df.to_dict(orient='records'),
        "daily_details": daily_details
    }


def render_search_analysis_result(result: dict, *, key_prefix: str = "search") -> None:
    """展示搜索词分析结果（五级联动，可指定 widget key 前缀；供历史查询等复用）。"""
    if result.get("error"):
        st.warning(result["error"])
        return
    if not result["summary"]:
        st.info("没有有效的搜索词数据")
        return

    summary_df = pd.DataFrame(result["summary"])

    all_activities = sorted(summary_df["广告活动名称"].unique())
    selected_activities = st.multiselect(
        "选择广告活动查看每日明细",
        all_activities,
        default=[],
        key=f"{key_prefix}_act",
    )

    if selected_activities:
        filtered_by_act = summary_df[summary_df["广告活动名称"].isin(selected_activities)]
        all_adgroups = sorted(filtered_by_act["广告组名称"].unique())
    else:
        all_adgroups = []
    selected_adgroups = st.multiselect(
        "选择广告组查看每日明细",
        all_adgroups,
        default=[],
        key=f"{key_prefix}_adg",
    )

    if selected_adgroups:
        filtered_by_adg = summary_df[
            summary_df["广告活动名称"].isin(selected_activities)
            & summary_df["广告组名称"].isin(selected_adgroups)
        ]
        all_targets = sorted(filtered_by_adg["投放"].unique())
    else:
        all_targets = []
    selected_targets = st.multiselect(
        "选择投放词查看每日明细",
        all_targets,
        default=[],
        key=f"{key_prefix}_target",
    )

    if selected_targets:
        filtered_by_target = summary_df[
            summary_df["广告活动名称"].isin(selected_activities)
            & summary_df["广告组名称"].isin(selected_adgroups)
            & summary_df["投放"].isin(selected_targets)
        ]
        all_match_types = sorted(filtered_by_target["匹配类型"].unique())
    else:
        all_match_types = []
    selected_match_types = st.multiselect(
        "选择匹配类型查看每日明细",
        all_match_types,
        default=[],
        key=f"{key_prefix}_match_type",
    )

    if selected_match_types:
        filtered_by_mt = summary_df[
            summary_df["广告活动名称"].isin(selected_activities)
            & summary_df["广告组名称"].isin(selected_adgroups)
            & summary_df["投放"].isin(selected_targets)
            & summary_df["匹配类型"].isin(selected_match_types)
        ]
        all_terms = sorted(filtered_by_mt["客户搜索词"].unique())
    else:
        all_terms = []
    selected_terms = st.multiselect(
        "选择客户搜索词查看每日明细",
        all_terms,
        default=[],
        key=f"{key_prefix}_term",
    )

    mask = pd.Series(True, index=summary_df.index)
    if selected_activities:
        mask &= summary_df["广告活动名称"].isin(selected_activities)
    if selected_adgroups:
        mask &= summary_df["广告组名称"].isin(selected_adgroups)
    if selected_targets:
        mask &= summary_df["投放"].isin(selected_targets)
    if selected_match_types:
        mask &= summary_df["匹配类型"].isin(selected_match_types)
    if selected_terms:
        mask &= summary_df["客户搜索词"].isin(selected_terms)

    filtered_df = summary_df[mask]
    if filtered_df.empty:
        st.info("没有符合筛选条件的数据")
        return

    display_df = filtered_df.copy()
    for col in ["总点击率", "总转化率", "总ACOS"]:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(lambda x: f"{x:.1%}" if pd.notna(x) else "-")
    if "平均CPC" in display_df.columns:
        display_df["平均CPC"] = display_df["平均CPC"].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "-")
    st.dataframe(display_df, use_container_width=True)

    if (
        result["daily_details"]
        and selected_activities
        and selected_adgroups
        and selected_targets
        and selected_match_types
        and selected_terms
    ):
        st.markdown("---")
        with st.expander("📅 各搜索词每日明细（点击展开）"):
            for act in selected_activities:
                for adg in selected_adgroups:
                    for target in selected_targets:
                        for match_type in selected_match_types:
                            for term in selected_terms:
                                detail_key = (act, adg, target, match_type, term)
                                if detail_key not in result["daily_details"]:
                                    continue
                                daily_records = result["daily_details"][detail_key]
                                daily_df = pd.DataFrame(daily_records)
                                total_spend = daily_df["花费"].sum()
                                total_sales = daily_df["销售额"].sum()
                                total_orders = daily_df["订单数"].sum()
                                avg_acos = total_spend / total_sales if total_sales > 0 else 0
                                with st.expander(
                                    f"📁 {act} / {adg} / {target} / {match_type} / {term} | "
                                    f"花费: {total_spend:.2f} | 销售额: {total_sales:.2f} | "
                                    f"订单: {int(total_orders)} | ACOS: {avg_acos:.1%}"
                                ):
                                    display_daily = daily_df.copy()
                                    for col in ["点击率", "转化率", "ACOS"]:
                                        if col in display_daily.columns:
                                            display_daily[col] = display_daily[col].apply(
                                                lambda x: f"{x:.1%}" if pd.notna(x) else "-"
                                            )
                                    if "CPC" in display_daily.columns:
                                        display_daily["CPC"] = display_daily["CPC"].apply(
                                            lambda x: f"{x:.2f}" if pd.notna(x) else "-"
                                        )
                                    st.dataframe(display_daily, use_container_width=True)


def analyze_search(df_clean: pd.DataFrame) -> None:
        """搜索词分析：两个Tab，每个Tab内有筛选器，每行带明细按钮"""
        result = store.get("search_analysis_result")
        if result is None:
            result = get_search_analysis(df_clean)
            store.set("search_analysis_result", result)
        if result.get("error"):
            st.warning(result["error"])
            return
        if not result["summary"]:
            st.info("没有有效的搜索词数据")
            return

        # 初始化 session_state 变量（明细状态）
        if 'show_neg_detail' not in st.session_state:
            st.session_state.show_neg_detail = False
        if 'selected_neg_comb' not in st.session_state:
            st.session_state.selected_neg_comb = None
        if 'show_pot_detail' not in st.session_state:
            st.session_state.show_pot_detail = False
        if 'selected_pot_comb' not in st.session_state:
            st.session_state.selected_pot_comb = None

        summary_list = result["summary"]
        daily_details = result["daily_details"]
        df_all_raw = pd.DataFrame(summary_list)

        # ---------- 1. 否定词候选（按广告活动分组阈值）----------
        df_all = df_all_raw.copy()
        # 计算每个广告活动的平均点击量和平均花费（transform 保持行数）
        df_all['mean_clicks'] = df_all.groupby('广告活动名称')['总点击量'].transform('mean')
        df_all['mean_spend'] = df_all.groupby('广告活动名称')['总花费'].transform('mean')

        negation_df = df_all[
            (df_all['总订单数'] == 0) &
            (df_all['总点击量'] > 0.4 * df_all['mean_clicks']) &
            (df_all['总花费'] > 0.4 * df_all['mean_spend'])
            ].copy()
        negation_df = negation_df.drop(columns=['mean_clicks', 'mean_spend'])
        negation_df = negation_df.sort_values('总花费', ascending=False)

        # 2. 高潜力拓词候选：有订单、客户搜索词≠投放词、且点击量>2
        potential_df = df_all_raw[
            (df_all_raw['总订单数'] > 0) &
            (df_all_raw['客户搜索词'] != df_all_raw['投放']) &
            (df_all_raw['总点击量'] > 2)
            ].copy()
        potential_df = potential_df.sort_values('总订单数', ascending=False)

        tab_neg, tab_pot = st.tabs(["🚫 否定词候选", "🌟 高潜力拓词候选"])

        def _daily_detail_key(comb: tuple) -> tuple | None:
            if len(comb) == 5:
                return comb
            if len(comb) == 4:
                return (comb[0], comb[1], comb[2], "—", comb[3])
            return None

        # ---------- 辅助函数：渲染带筛选器的表格 ----------
        def render_search_table(df: pd.DataFrame, title: str, detail_type: str):
            """渲染带筛选与分页的搜索词分析表格。

            Args:
                df (pd.DataFrame): 待展示的搜索词数据。
                title (str): 表格标题。
                detail_type (str): 明细类型标识，用于 session_state 键名。

            Returns:
                None

            Raises:
                None
            """
            if df.empty:
                st.success(f"✅ 没有{title}")
                return

            st.subheader(title)

            # 模式选择：明确区分“活动级分析”和“跨活动分析”
            mode = st.radio(
                "选择分析模式",
                ["🎯 定位问题（限定在某个活动/广告组内）", "⚡ 诊断内部竞争（跨所有活动查看同一搜索词）"],
                horizontal=True,
                key=f"{detail_type}_mode"
            )

            # ----- 模式1：🎯 定位问题（五级联动）-----
            selected_targets: list = []
            selected_match_types: list = []
            if mode == "🎯 定位问题（限定在某个活动/广告组内）":
                st.caption("💡 活动 → 广告组 → 投放 → 匹配类型 → 客户搜索词。")
                all_activities = sorted(df['广告活动名称'].unique())
                selected_activity = st.selectbox(
                    "选择广告活动",
                    ["全部"] + all_activities,
                    key=f"{detail_type}_activity"
                )
                if selected_activity != "全部":
                    adgroups = sorted(df[df['广告活动名称'] == selected_activity]['广告组名称'].unique())
                    selected_adgroups = st.multiselect(
                        "选择广告组（可多选）",
                        adgroups,
                        default=[],
                        key=f"{detail_type}_adgroup"
                    )
                else:
                    selected_adgroups = []
                    st.info("请先选择广告活动以启用下级筛选")

                range_df = df.copy()
                if selected_activity != "全部":
                    range_df = range_df[range_df['广告活动名称'] == selected_activity]
                if selected_adgroups:
                    range_df = range_df[range_df['广告组名称'].isin(selected_adgroups)]

                if selected_activity != "全部" and selected_adgroups:
                    all_targets = sorted(range_df['投放'].unique())
                    selected_targets = st.multiselect(
                        "选择投放词（可多选）",
                        all_targets,
                        default=[],
                        key=f"{detail_type}_target",
                    )
                    if selected_targets:
                        range_df = range_df[range_df['投放'].isin(selected_targets)]
                        all_match_types = sorted(range_df['匹配类型'].unique())
                        selected_match_types = st.multiselect(
                            "选择匹配类型（可多选）",
                            all_match_types,
                            default=[],
                            key=f"{detail_type}_match_type",
                        )
                        if selected_match_types:
                            range_df = range_df[range_df['匹配类型'].isin(selected_match_types)]
                all_terms = sorted(range_df['客户搜索词'].unique()) if selected_activity != "全部" else []
            else:
                # 模式2：跨活动分析（只按客户搜索词）
                st.caption("💡 跨活动分析将忽略活动/广告组/投放/匹配类型，只按客户搜索词查看。")
                selected_activity = "全部"
                selected_adgroups = []
                all_terms = sorted(df['客户搜索词'].unique())

            # ----- 客户搜索词筛选（两种模式共用）-----
            st.markdown("### 🔍 按客户搜索词筛选")
            term_options = ["全部"] + all_terms if all_terms else ["全部"]
            if mode == "🎯 定位问题（限定在某个活动/广告组内）" and selected_activity == "全部":
                st.info("定位模式下请先选择广告活动以加载客户搜索词列表。")
            selected_term = st.selectbox(
                "选择客户搜索词",
                term_options,
                key=f"{detail_type}_term"
            )

            # ----- 应用筛选 -----
            filtered_df = df.copy()
            if mode == "🎯 定位问题（限定在某个活动/广告组内）":
                if selected_activity != "全部":
                    filtered_df = filtered_df[filtered_df['广告活动名称'] == selected_activity]
                if selected_adgroups:
                    filtered_df = filtered_df[filtered_df['广告组名称'].isin(selected_adgroups)]
                if selected_targets:
                    filtered_df = filtered_df[filtered_df['投放'].isin(selected_targets)]
                if selected_match_types:
                    filtered_df = filtered_df[filtered_df['匹配类型'].isin(selected_match_types)]
            if selected_term != "全部":
                filtered_df = filtered_df[filtered_df['客户搜索词'] == selected_term]

            if filtered_df.empty:
                st.info("没有符合筛选条件的数据")
                return

            # ----- 分页显示（默认10条）-----
            DISPLAY_LIMIT = 10
            limit_key = f"{detail_type}_display_limit"
            if limit_key not in st.session_state:
                st.session_state[limit_key] = DISPLAY_LIMIT

            show_df = filtered_df.head(st.session_state[limit_key]).reset_index(drop=True)

            # 显示每条记录 + 明细按钮
            for idx, row in show_df.iterrows():
                cols = st.columns([6, 1])
                match_type = row.get('匹配类型', '—')
                with cols[0]:
                    st.markdown(
                        f"**{row['客户搜索词']}**  |  活动: {row['广告活动名称']}  |  "
                        f"广告组: {row['广告组名称']}  |  触发词: {row['投放']}  |  匹配: {match_type}"
                    )
                    st.markdown(f"花费: {row['总花费']:.2f}  |  点击量: {row['总点击量']}  |  订单: {row['总订单数']}  |  CPC: {row['平均CPC']:.2f}")
                with cols[1]:
                    btn_key = (
                        f"{detail_type}_detail_{idx}_{row['广告活动名称']}_{row['广告组名称']}_"
                        f"{row['投放']}_{match_type}_{row['客户搜索词']}"
                    )[:80]
                    if st.button("📊 明细", key=btn_key):
                        st.session_state[f"selected_{detail_type}_comb"] = (
                            row['广告活动名称'],
                            row['广告组名称'],
                            row['投放'],
                            match_type,
                            row['客户搜索词'],
                        )
                        st.session_state[f"show_{detail_type}_detail"] = True
                # 添加分隔线（除了最后一条）
                if idx < len(show_df) - 1:
                    st.markdown("---")

            # 控制显示数量的按钮区域
            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.session_state[limit_key] < len(filtered_df):
                    if st.button(f"加载更多（当前显示{st.session_state[limit_key]}条，共{len(filtered_df)}条）",
                                 key=f"load_more_{detail_type}"):
                        st.session_state[limit_key] += DISPLAY_LIMIT
                        st.rerun()
            with col_btn2:
                if st.session_state[limit_key] > DISPLAY_LIMIT:
                    if st.button("显示更少（重置为10条）", key=f"reset_limit_{detail_type}"):
                        st.session_state[limit_key] = DISPLAY_LIMIT
                        st.rerun()

            # ----- 显示每日明细（如果已选中）-----
            if st.session_state.get(f"show_{detail_type}_detail", False) and st.session_state.get(
                    f"selected_{detail_type}_comb"):
                comb = st.session_state[f"selected_{detail_type}_comb"]
                key = _daily_detail_key(comb)
                if key and key in daily_details:
                    st.markdown("---")
                    st.subheader(
                        f"每日明细：{key[4]} (触发词: {key[2]} / {key[3]})"
                    )
                    daily_df = pd.DataFrame(daily_details[key])
                    display_daily = daily_df.copy()
                    for col in ['点击率', '转化率', 'ACOS']:
                        if col in display_daily.columns:
                            display_daily[col] = display_daily[col].apply(lambda x: f"{x:.1%}" if pd.notna(x) else '-')
                    if 'CPC' in display_daily.columns:
                        display_daily['CPC'] = display_daily['CPC'].apply(lambda x: f"{x:.2f}" if pd.notna(x) else '-')
                    st.dataframe(display_daily, use_container_width=True)
                    if st.button("关闭明细", key=f"close_{detail_type}_detail"):
                        st.session_state[f"show_{detail_type}_detail"] = False
                        st.session_state[f"selected_{detail_type}_comb"] = None
                        st.rerun()
                else:
                    st.info("无每日明细数据")
        with tab_neg:
            render_search_table(negation_df, "否定词候选（高点击高花费零订单）", "neg")
        with tab_pot:
            render_search_table(potential_df, "高潜力拓词候选（有订单未投放）", "pot")






