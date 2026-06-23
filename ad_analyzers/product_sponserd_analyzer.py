# ad_analyzers/product_sponserd_analyzer.py
import pandas as pd
import numpy as np
import streamlit as st
from typing import Dict, Any
from data_df_store.data_store import store

# ---------- 清洗函数 ----------
def to_float(series):
    """将 Series 清洗并转换为浮点数。"""
    s = series.astype(str).str.strip()
    s = s.str.replace(r'[¥$€]', '', regex=True)
    s = s.str.replace(',', '', regex=False)
    s = s.str.replace(r'\s+', '', regex=True)
    s = s.replace('', pd.NA)
    return pd.to_numeric(s, errors='coerce')


def to_percent_float(series):
    """将百分比字符串 Series 转换为 0-1 范围的浮点数。"""
    s = series.astype(str).str.replace('%', '', regex=False).str.strip()
    s = s.replace('', pd.NA)
    return pd.to_numeric(s, errors='coerce') / 100


def clean_product_sponsored_report(df: pd.DataFrame) -> pd.DataFrame:
    """清洗推广的商品报表，返回标准中文列名 DataFrame。"""
    df_clean = df.copy()

    if '日期' in df_clean.columns:
        df_clean['日期'] = pd.to_datetime(df_clean['日期'], errors='coerce')

    df_clean['展示量'] = pd.to_numeric(df_clean['展示量'], errors='coerce')
    df_clean['点击量'] = pd.to_numeric(df_clean['点击量'], errors='coerce')

    orders_col = '7天总订单数(#)' if '7天总订单数(#)' in df_clean.columns else '7天总订单数'
    units_col = '7天总销售量(#)' if '7天总销售量(#)' in df_clean.columns else '7天总销售量'
    cvr_col = '7天的转化率' if '7天的转化率' in df_clean.columns else '7天转化率'
    cpc_col = '单次点击成本 (CPC)' if '单次点击成本 (CPC)' in df_clean.columns else '单次点击成本(CPC)'
    acos_col = '广告投入产出比 (ACOS) 总计' if '广告投入产出比 (ACOS) 总计' in df_clean.columns else 'ACOS'
    roas_col = '总广告投资回报率 (ROAS)' if '总广告投资回报率 (ROAS)' in df_clean.columns else 'ROAS'

    df_clean['7天总订单数'] = pd.to_numeric(df_clean[orders_col], errors='coerce') if orders_col in df_clean.columns else np.nan
    df_clean['7天总销售量'] = pd.to_numeric(df_clean[units_col], errors='coerce') if units_col in df_clean.columns else np.nan
    df_clean['花费'] = to_float(df_clean['花费']) if '花费' in df_clean.columns else np.nan
    df_clean['7天总销售额'] = to_float(df_clean['7天总销售额']) if '7天总销售额' in df_clean.columns else np.nan
    df_clean['单次点击成本 (CPC)'] = to_float(df_clean[cpc_col]).fillna(0) if cpc_col in df_clean.columns else 0.0

    if acos_col in df_clean.columns:
        df_clean['ACOS'] = to_percent_float(df_clean[acos_col])
    else:
        df_clean['ACOS'] = np.nan

    if roas_col in df_clean.columns:
        df_clean['ROAS'] = to_float(df_clean[roas_col])
    else:
        df_clean['ROAS'] = np.nan

    if cvr_col in df_clean.columns:
        df_clean['7天转化率'] = to_percent_float(df_clean[cvr_col])
    else:
        df_clean['7天转化率'] = df_clean['7天总订单数'] / df_clean['点击量']

    df_clean['点击率'] = df_clean['点击量'] / df_clean['展示量']

    keep_cols = [
        '日期', '广告活动名称', '广告组名称', '广告SKU', '广告ASIN',
        '展示量', '点击量', '点击率', '单次点击成本 (CPC)', '花费',
        '7天总销售额', '7天总订单数', '7天总销售量', '7天转化率', 'ACOS', 'ROAS',
    ]
    keep_cols = [c for c in keep_cols if c in df_clean.columns]
    df_clean = df_clean[keep_cols]
    df_clean = df_clean.dropna(subset=['花费', '7天总销售额'], how='all')
    return df_clean


# ---------- 核心分析函数 ----------
@st.cache_data(ttl=3600)
def get_product_sponsored_analysis(df_clean: pd.DataFrame) -> Dict[str, Any]:
    """按广告ASIN、广告SKU、广告活动、广告组 分组聚合，返回汇总和每日明细。"""
    if df_clean is None or df_clean.empty:
        return {"summary": [], "daily_details": {}}

    required = [
        '广告活动名称', '广告组名称', '广告SKU', '广告ASIN',
        '展示量', '点击量', '花费', '7天总销售额', '7天总订单数', '7天总销售量',
    ]
    missing = [c for c in required if c not in df_clean.columns]
    if missing:
        return {"summary": [], "daily_details": {}, "error": f"缺少列: {missing}"}

    group_cols = ['广告活动名称', '广告组名称', '广告ASIN', '广告SKU']
    summary_df = df_clean.groupby(group_cols).agg(
        总展示量=('展示量', 'sum'),
        总点击量=('点击量', 'sum'),
        总花费=('花费', 'sum'),
        总销售额=('7天总销售额', 'sum'),
        总订单数=('7天总订单数', 'sum'),
        总销售量=('7天总销售量', 'sum'),
    ).reset_index()

    summary_df['平均CPC'] = summary_df['总花费'] / summary_df['总点击量']
    summary_df['总点击率'] = summary_df['总点击量'] / summary_df['总展示量']
    summary_df['7天转化率'] = summary_df['总订单数'] / summary_df['总点击量']
    summary_df['总ACOS'] = summary_df['总花费'] / summary_df['总销售额']
    summary_df['总ROAS'] = summary_df['总销售额'] / summary_df['总花费']
    summary_df.replace([np.inf, -np.inf], np.nan, inplace=True)

    daily_details = {}
    if '日期' in df_clean.columns:
        df_clean = df_clean.dropna(subset=['日期'])
        for key, group in df_clean.groupby(group_cols):
            daily = group[[
                '日期', '花费', '7天总销售额', '点击量', '展示量',
                '7天总订单数', '7天总销售量', '单次点击成本 (CPC)', 'ACOS', 'ROAS', '7天转化率',
            ]].copy()
            daily = daily.sort_values('日期')
            daily.rename(columns={
                '7天总销售额': '销售额',
                '7天总订单数': '订单数',
                '7天总销售量': '销售量',
                '单次点击成本 (CPC)': 'CPC',
            }, inplace=True)
            daily['点击率'] = daily['点击量'] / daily['展示量']
            if daily['7天转化率'].isna().all():
                daily['7天转化率'] = daily['订单数'] / daily['点击量']
            daily_details[key] = daily.to_dict(orient='records')

    return {
        "summary": summary_df.to_dict(orient='records'),
        "daily_details": daily_details,
    }


# ---------- UI 展示 ----------
def render_product_sponsored_analysis_result(result: dict, *, key_prefix: str = "ps") -> None:
    """展示推广的商品分析结果（四级联动：ASIN → SKU → 活动 → 组）。"""
    if result.get("error"):
        st.warning(result["error"])
        return
    if not result["summary"]:
        st.info("没有有效的推广商品数据")
        return

    summary_df = pd.DataFrame(result["summary"])

    all_asins = sorted(summary_df['广告ASIN'].unique())
    selected_asins = st.multiselect(
        "选择广告ASIN查看每日明细",
        all_asins,
        default=[],
        key=f"{key_prefix}_asin",
    )

    if selected_asins:
        filtered_by_asin = summary_df[summary_df['广告ASIN'].isin(selected_asins)]
        all_skus = sorted(filtered_by_asin['广告SKU'].unique())
    else:
        all_skus = []
    selected_skus = st.multiselect(
        "选择广告SKU查看每日明细",
        all_skus,
        default=[],
        key=f"{key_prefix}_sku",
    )

    if selected_skus:
        filtered_by_sku = summary_df[
            summary_df['广告ASIN'].isin(selected_asins)
            & summary_df['广告SKU'].isin(selected_skus)
        ]
        all_activities = sorted(filtered_by_sku['广告活动名称'].unique())
    else:
        all_activities = []
    selected_activities = st.multiselect(
        "选择广告活动查看每日明细",
        all_activities,
        default=[],
        key=f"{key_prefix}_act",
    )

    if selected_activities:
        filtered_by_act = summary_df[
            summary_df['广告ASIN'].isin(selected_asins)
            & summary_df['广告SKU'].isin(selected_skus)
            & summary_df['广告活动名称'].isin(selected_activities)
        ]
        all_adgroups = sorted(filtered_by_act['广告组名称'].unique())
    else:
        all_adgroups = []
    selected_adgroups = st.multiselect(
        "选择广告组查看每日明细",
        all_adgroups,
        default=[],
        key=f"{key_prefix}_adg",
    )

    mask = pd.Series(True, index=summary_df.index)
    if selected_asins:
        mask &= summary_df['广告ASIN'].isin(selected_asins)
    if selected_skus:
        mask &= summary_df['广告SKU'].isin(selected_skus)
    if selected_activities:
        mask &= summary_df['广告活动名称'].isin(selected_activities)
    if selected_adgroups:
        mask &= summary_df['广告组名称'].isin(selected_adgroups)

    filtered_df = summary_df[mask]
    if filtered_df.empty:
        st.info("没有符合筛选条件的数据")
        return

    display_df = filtered_df.copy()
    display_cols = [
        '广告ASIN', '广告SKU', '广告活动名称', '广告组名称',
        '总展示量', '总点击量', '总点击率', '平均CPC', '总花费',
        '总销售额', '总ACOS', '总订单数', '总销售量', '7天转化率', '总ROAS',
    ]
    display_df = display_df[[c for c in display_cols if c in display_df.columns]]
    for col in ['总点击率', '7天转化率', '总ACOS']:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(lambda x: f"{x:.1%}" if pd.notna(x) else '-')
    if '平均CPC' in display_df.columns:
        display_df['平均CPC'] = display_df['平均CPC'].apply(lambda x: f"{x:.2f}" if pd.notna(x) else '-')
    if '总ROAS' in display_df.columns:
        display_df['总ROAS'] = display_df['总ROAS'].apply(lambda x: f"{x:.2f}" if pd.notna(x) else '-')
    st.dataframe(display_df, use_container_width=True)

    if (
        result["daily_details"]
        and selected_asins
        and selected_skus
        and selected_activities
        and selected_adgroups
    ):
        st.markdown("---")
        with st.expander("📅 每日明细（点击展开）"):
            for asin in selected_asins:
                for sku in selected_skus:
                    for act in selected_activities:
                        for adg in selected_adgroups:
                            detail_key = (act, adg, asin, sku)
                            if detail_key not in result["daily_details"]:
                                continue
                            daily_records = result["daily_details"][detail_key]
                            daily_df = pd.DataFrame(daily_records)
                            total_spend = daily_df['花费'].sum()
                            total_sales = daily_df['销售额'].sum()
                            total_orders = daily_df['订单数'].sum()
                            avg_acos = total_spend / total_sales if total_sales > 0 else 0
                            with st.expander(
                                f"📁 {asin} / {sku} / {act} / {adg} | 花费: {total_spend:.2f} | "
                                f"销售额: {total_sales:.2f} | 订单: {int(total_orders)} | ACOS: {avg_acos:.1%}"
                            ):
                                display_daily = daily_df.copy()
                                for col in ['点击率', '7天转化率', 'ACOS']:
                                    if col in display_daily.columns:
                                        display_daily[col] = display_daily[col].apply(
                                            lambda x: f"{x:.1%}" if pd.notna(x) else '-'
                                        )
                                if 'CPC' in display_daily.columns:
                                    display_daily['CPC'] = display_daily['CPC'].apply(
                                        lambda x: f"{x:.2f}" if pd.notna(x) else '-'
                                    )
                                if 'ROAS' in display_daily.columns:
                                    display_daily['ROAS'] = display_daily['ROAS'].apply(
                                        lambda x: f"{x:.2f}" if pd.notna(x) else '-'
                                    )
                                st.dataframe(display_daily, use_container_width=True)
            st.markdown("**建议**：关注高花费低转化的 ASIN/SKU，适当降低出价或暂停。")


def analyze_product_sponsored(df_clean: pd.DataFrame) -> None:
    """四级联动：广告ASIN → 广告SKU → 活动 → 广告组"""
    result = store.get("product_sponsored_analysis_result")
    if result is None:
        result = get_product_sponsored_analysis(df_clean)
        store.set("product_sponsored_analysis_result", result)
    st.subheader("📦 推广的商品分析 (广告ASIN/广告SKU/活动/广告组)")
    render_product_sponsored_analysis_result(result, key_prefix="ps")
