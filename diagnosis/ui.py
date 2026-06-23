from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from diagnosis.config import DiagnosisConfig, load_diagnosis_config, save_diagnosis_config
from diagnosis.listing_assessment import (
    LISTING_FIELDS,
    LISTING_LEVELS,
    load_listing_by_asin,
    save_listing_for_asin,
)
from diagnosis.placement_diagnosis import PLACEMENT_CONCLUSION_LABELS
from diagnosis.keyword_diagnosis import KEYWORD_CONCLUSION_LABELS
from diagnosis.search_diagnosis import SEARCH_CONCLUSION_LABELS


from auth.user_context import get_current_user_id

CONCLUSION_FILTER_OPTIONS = {
    "✅ 建议加预算": "INCREASE_BUDGET",
    "📦 暂不加预算（库存不足）": "HOLD_RESTOCK",
    "📉 暂不加预算（ACOS超标）": "HOLD_OPTIMIZE",
    "⚠️ 暂无法诊断": "UNABLE_TO_DIAGNOSE",
}

_CONCLUSION_SORT_ORDER = {
    "INCREASE_BUDGET": 0,
    "HOLD_RESTOCK": 1,
    "HOLD_OPTIMIZE": 2,
    "UNABLE_TO_DIAGNOSE": 3,
}

PLACEMENT_CONCLUSION_FILTER_OPTIONS = {label: code for code, label in PLACEMENT_CONCLUSION_LABELS.items()}

_PLACEMENT_CONCLUSION_SORT_ORDER = {
    "INCREASE_SEARCH_PREMIUM": 0,
    "TRY_INCREASE_PREMIUM": 1,
    "INCREASE_SEARCH_PREMIUM_CAUTIOUS": 2,
    "REDUCE_SEARCH_BID_OR_PREMIUM": 3,
    "SEARCH_COMPETITION_WEAK": 4,
    "PENDING_LISTING": 5,
    "OPTIMIZE_LISTING": 6,
    "HOLD_RESTOCK": 7,
    "NO_ACTION_NEEDED": 8,
    "UNABLE_TO_DIAGNOSE": 9,
}


def render_diagnosis_config_sidebar() -> DiagnosisConfig:
    """Sidebar 诊断参数控件，返回当前 config。"""
    if "diagnosis_config" not in st.session_state:
        st.session_state.diagnosis_config = load_diagnosis_config(get_current_user_id())

    base: DiagnosisConfig = st.session_state.diagnosis_config

    with st.sidebar.expander("⚙️ 诊断参数", expanded=False):
        st.caption("手动分析与 AI 助手共用以下阈值。")
        threshold_pct = st.slider(
            "预算使用率阈值 (%)",
            min_value=50,
            max_value=100,
            value=int(round(base.budget_usage_threshold * 100)),
            step=5,
            key="diag_budget_usage_pct",
        )
        consecutive_days = st.number_input(
            "连续超标天数",
            min_value=1,
            max_value=14,
            value=int(base.consecutive_days),
            step=1,
            key="diag_consecutive_days",
        )
        min_cover = st.number_input(
            "最低库存可售天数",
            min_value=1,
            max_value=180,
            value=int(base.min_days_of_cover),
            step=1,
            key="diag_min_days_of_cover",
        )
        max_acos_pct = st.slider(
            "活动 ACOS 上限 (%)",
            min_value=5,
            max_value=80,
            value=int(round(base.max_campaign_acos * 100)),
            step=1,
            key="diag_max_acos_pct",
        )
        include_inbound = st.checkbox(
            "库存含在途",
            value=bool(base.include_inbound_inventory),
            key="diag_include_inbound",
        )

        st.markdown("**广告位诊断**")
        min_search_share_pct = st.slider(
            "搜索位最低点击占比 (%)",
            min_value=5,
            max_value=50,
            value=int(round(base.min_search_click_share * 100)),
            step=1,
            key="diag_min_search_click_share_pct",
        )
        min_search_clicks = st.number_input(
            "搜索位最少点击",
            min_value=1,
            max_value=500,
            value=int(base.min_search_clicks),
            step=1,
            key="diag_min_search_clicks",
        )
        max_search_placement_acos_pct = st.slider(
            "搜索位 ACOS 上限 (%)",
            min_value=5,
            max_value=80,
            value=int(round(base.max_search_placement_acos * 100)),
            step=1,
            key="diag_max_search_placement_acos_pct",
        )
        min_search_orders = st.number_input(
            "搜索位最少订单",
            min_value=0,
            max_value=100,
            value=int(base.min_search_orders),
            step=1,
            key="diag_min_search_orders",
        )
        min_search_cvr_pct = st.slider(
            "搜索位转化率下限 (%)",
            min_value=1,
            max_value=30,
            value=int(round(base.min_search_cvr * 100)),
            step=1,
            key="diag_min_search_cvr_pct",
        )
        max_pp_acos_pct = st.slider(
            "商品页 ACOS 上限 (%)",
            min_value=5,
            max_value=80,
            value=int(round(base.max_pp_acos * 100)),
            step=1,
            key="diag_max_pp_acos_pct",
        )

        st.markdown("**投放词分诊**")
        min_kw_clicks = st.number_input(
            "最少点击（样本）",
            min_value=1,
            max_value=500,
            value=int(base.min_keyword_clicks),
            step=1,
            key="diag_min_keyword_clicks",
        )
        min_kw_spend = st.number_input(
            "最少花费",
            min_value=0.0,
            max_value=500.0,
            value=float(base.min_keyword_spend),
            step=1.0,
            key="diag_min_keyword_spend",
        )
        max_kw_acos_pct = st.slider(
            "高 ACOS 阈值 (%)",
            min_value=5,
            max_value=100,
            value=int(round(base.max_keyword_acos * 100)),
            step=1,
            key="diag_max_keyword_acos_pct",
        )
        min_kw_orders_pot = st.number_input(
            "潜力词最少订单",
            min_value=1,
            max_value=50,
            value=int(base.min_keyword_orders_potential),
            step=1,
            key="diag_min_keyword_orders_potential",
        )
        max_kw_acos_pot_pct = st.slider(
            "潜力词 ACOS 上限 (%)",
            min_value=5,
            max_value=80,
            value=int(round(base.max_keyword_acos_potential * 100)),
            step=1,
            key="diag_max_keyword_acos_potential_pct",
        )
        min_kw_cvr_pot_pct = st.slider(
            "潜力词转化率下限 (%)",
            min_value=1,
            max_value=30,
            value=int(round(base.min_keyword_cvr_potential * 100)),
            step=1,
            key="diag_min_keyword_cvr_potential_pct",
        )
        min_dup_campaigns = st.number_input(
            "重复投放：最少活动数",
            min_value=2,
            max_value=20,
            value=int(base.min_duplicate_campaigns),
            step=1,
            key="diag_min_duplicate_campaigns",
        )

        st.markdown("**搜索词诊断**")
        min_neg_clicks = st.number_input(
            "否定候选：最少点击",
            min_value=1,
            max_value=500,
            value=int(base.min_negative_clicks),
            step=1,
            key="diag_min_negative_clicks",
        )
        min_neg_spend = st.number_input(
            "否定候选：最少花费",
            min_value=0.0,
            max_value=500.0,
            value=float(base.min_negative_spend),
            step=1.0,
            key="diag_min_negative_spend",
        )
        min_search_high_acos_orders = st.number_input(
            "高ACOS：最少订单",
            min_value=1,
            max_value=50,
            value=int(base.min_high_acos_orders),
            step=1,
            key="diag_min_high_acos_orders",
        )
        max_search_term_acos_pct = st.slider(
            "高ACOS阈值 (%)",
            min_value=5,
            max_value=100,
            value=int(round(base.max_search_acos * 100)),
            step=1,
            key="diag_max_search_term_acos_pct",
        )
        min_expansion_orders = st.number_input(
            "拓词候选：最少订单",
            min_value=1,
            max_value=50,
            value=int(base.min_expansion_orders),
            step=1,
            key="diag_min_expansion_orders",
        )
        max_expansion_acos_pct = st.slider(
            "拓词候选 ACOS 上限 (%)",
            min_value=5,
            max_value=80,
            value=int(round(base.max_expansion_acos * 100)),
            step=1,
            key="diag_max_expansion_acos_pct",
        )
        traffic_conc_pct = st.slider(
            "流量集中占比阈值 (%)",
            min_value=30,
            max_value=95,
            value=int(round(base.traffic_concentration_ratio * 100)),
            step=5,
            key="diag_traffic_concentration_ratio_pct",
        )
        min_traffic_bucket = st.number_input(
            "流量集中：投放词最少总花费",
            min_value=0.0,
            max_value=500.0,
            value=float(base.min_traffic_bucket_spend),
            step=1.0,
            key="diag_min_traffic_bucket_spend",
        )
        min_dup_trigger = st.number_input(
            "重复触发：最少投放词数",
            min_value=2,
            max_value=20,
            value=int(base.min_duplicate_trigger_count),
            step=1,
            key="diag_min_duplicate_trigger_count",
        )

        if st.button("💾 保存为默认", key="diag_save_defaults", use_container_width=True):
            save_diagnosis_config(
                DiagnosisConfig(
                    budget_usage_threshold=threshold_pct / 100.0,
                    consecutive_days=int(consecutive_days),
                    min_days_of_cover=float(min_cover),
                    max_campaign_acos=max_acos_pct / 100.0,
                    include_inbound_inventory=include_inbound,
                    min_search_click_share=min_search_share_pct / 100.0,
                    min_search_clicks=int(min_search_clicks),
                    max_search_placement_acos=max_search_placement_acos_pct / 100.0,
                    min_search_orders=int(min_search_orders),
                    min_search_cvr=min_search_cvr_pct / 100.0,
                    max_pp_acos=max_pp_acos_pct / 100.0,
                    min_pp_clicks=base.min_pp_clicks,
                    min_pp_orders=base.min_pp_orders,
                    min_pp_cvr=base.min_pp_cvr,
                    pp_good_min_conditions=base.pp_good_min_conditions,
                    min_keyword_clicks=int(min_kw_clicks),
                    min_keyword_spend=float(min_kw_spend),
                    max_keyword_acos=max_kw_acos_pct / 100.0,
                    min_keyword_orders_potential=int(min_kw_orders_pot),
                    max_keyword_acos_potential=max_kw_acos_pot_pct / 100.0,
                    min_keyword_cvr_potential=min_kw_cvr_pot_pct / 100.0,
                    min_duplicate_campaigns=int(min_dup_campaigns),
                    min_negative_clicks=int(min_neg_clicks),
                    min_negative_spend=float(min_neg_spend),
                    min_high_acos_orders=int(min_search_high_acos_orders),
                    max_search_acos=max_search_term_acos_pct / 100.0,
                    min_expansion_orders=int(min_expansion_orders),
                    max_expansion_acos=max_expansion_acos_pct / 100.0,
                    traffic_concentration_ratio=traffic_conc_pct / 100.0,
                    min_traffic_bucket_spend=float(min_traffic_bucket),
                    min_duplicate_trigger_count=int(min_dup_trigger),
                ),
                get_current_user_id(),
            )
            st.toast("诊断参数已保存为默认")

    return DiagnosisConfig(
        budget_usage_threshold=threshold_pct / 100.0,
        consecutive_days=int(consecutive_days),
        min_days_of_cover=float(min_cover),
        max_campaign_acos=max_acos_pct / 100.0,
        include_inbound_inventory=include_inbound,
        min_search_click_share=min_search_share_pct / 100.0,
        min_search_clicks=int(min_search_clicks),
        max_search_placement_acos=max_search_placement_acos_pct / 100.0,
        min_search_orders=int(min_search_orders),
        min_search_cvr=min_search_cvr_pct / 100.0,
        max_pp_acos=max_pp_acos_pct / 100.0,
        min_pp_clicks=base.min_pp_clicks,
        min_pp_orders=base.min_pp_orders,
        min_pp_cvr=base.min_pp_cvr,
        pp_good_min_conditions=base.pp_good_min_conditions,
        min_keyword_clicks=int(min_kw_clicks),
        min_keyword_spend=float(min_kw_spend),
        max_keyword_acos=max_kw_acos_pct / 100.0,
        min_keyword_orders_potential=int(min_kw_orders_pot),
        max_keyword_acos_potential=max_kw_acos_pot_pct / 100.0,
        min_keyword_cvr_potential=min_kw_cvr_pot_pct / 100.0,
        min_duplicate_campaigns=int(min_dup_campaigns),
        min_negative_clicks=int(min_neg_clicks),
        min_negative_spend=float(min_neg_spend),
        min_high_acos_orders=int(min_search_high_acos_orders),
        max_search_acos=max_search_term_acos_pct / 100.0,
        min_expansion_orders=int(min_expansion_orders),
        max_expansion_acos=max_expansion_acos_pct / 100.0,
        traffic_concentration_ratio=traffic_conc_pct / 100.0,
        min_traffic_bucket_spend=float(min_traffic_bucket),
        min_duplicate_trigger_count=int(min_dup_trigger),
    )


def _gate_status(store) -> list[tuple[str, bool]]:
    return [
        ("预算报表", store.get("budget") is not None),
        ("推广的商品", store.get("product_sponsored") is not None),
        ("库存报表", store.get("inventory") is not None),
        ("业务报表", store.get("business") is not None),
    ]


def _sort_rows_for_preview(rows: list[dict]) -> list[dict]:
    """建议加码优先，其次连续超标天数降序。"""
    return sorted(
        rows,
        key=lambda r: (
            _CONCLUSION_SORT_ORDER.get(r.get("诊断结论码", "UNABLE_TO_DIAGNOSE"), 99),
            -(int(r.get("连续超标天数") or 0)),
        ),
    )


def _apply_row_filters(
    rows: list[dict],
    selected_conclusion_labels: list[str],
    selected_campaigns: list[str],
) -> list[dict]:
    filtered = rows
    if selected_conclusion_labels:
        codes = {CONCLUSION_FILTER_OPTIONS[label] for label in selected_conclusion_labels if label in CONCLUSION_FILTER_OPTIONS}
        filtered = [r for r in filtered if r.get("诊断结论码") in codes]
    if selected_campaigns:
        campaign_set = set(selected_campaigns)
        filtered = [r for r in filtered if r.get("广告活动名称") in campaign_set]
    return filtered


def _row_to_display_dict(row: dict) -> dict:
    acos = row.get("活动ACOS")
    max_usage = row.get("最高使用率")
    daily = row.get("日均订单")
    cover = row.get("库存可售天数")
    return {
        "广告活动名称": row.get("广告活动名称"),
        "连续超标天数": row.get("连续超标天数"),
        "最高使用率": f"{max_usage:.1%}" if max_usage is not None else "—",
        "统计天数": row.get("统计天数"),
        "关联ASIN数": row.get("关联ASIN数"),
        "最差ASIN": row.get("最差ASIN") or "—",
        "可售数量": row.get("可售数量") if row.get("可售数量") is not None else "—",
        "日均订单": daily if daily is not None else "—",
        "库存可售天数": cover if cover is not None else "—",
        "活动ACOS": f"{acos:.1%}" if acos is not None else "—",
        "诊断结论": row.get("诊断结论"),
        "原因说明": row.get("原因说明"),
    }


def _rows_to_dataframe(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([_row_to_display_dict(r) for r in rows])


def _count_by_conclusion(rows: list[dict]) -> dict[str, int]:
    counts = {
        "INCREASE_BUDGET": 0,
        "HOLD_RESTOCK": 0,
        "HOLD_OPTIMIZE": 0,
        "UNABLE_TO_DIAGNOSE": 0,
    }
    for row in rows:
        code = row.get("诊断结论码", "UNABLE_TO_DIAGNOSE")
        counts[code] = counts.get(code, 0) + 1
    return counts


def get_budget_diagnosis_status_caption(store) -> str | None:
    """expander 外一行状态，便于不展开时感知诊断已运行。"""
    if store.get("budget") is None:
        return None
    budget_result = store.get("budget_analysis_result")
    if not budget_result or not budget_result.get("problem_activities"):
        return "预算诊断：当前无问题活动"
    result_dict = store.get("budget_diagnosis_result") or {}
    rows = result_dict.get("rows") or []
    n_problem = len(budget_result.get("problem_activities") or [])
    if not rows:
        return f"预算诊断：{n_problem} 个问题活动（请展开查看，或确认已上传联动报表）"
    counts = _count_by_conclusion(rows)
    return (
        f"预算诊断：{len(rows)} 个问题活动，"
        f"{counts.get('INCREASE_BUDGET', 0)} 个建议加码 · 展开查看"
    )


def render_budget_diagnosis_panel(store) -> None:
    """手动 Tab 预算诊断区块。"""
    result_dict = store.get("budget_diagnosis_result") or st.session_state.get("budget_diagnosis_result")
    budget_result = store.get("budget_analysis_result")

    gates = _gate_status(store)
    gate_text = " · ".join([f"{'✓' if ok else '✗'} {name}" for name, ok in gates])
    st.caption(f"数据就绪：{gate_text}")

    if store.get("budget") is None:
        st.info("请先上传预算报表。")
        return

    if not budget_result or not budget_result.get("problem_activities"):
        cfg = DiagnosisConfig.from_dict(store.get("diagnosis_config"))
        st.success(
            f"✅ 无活动满足「连续 ≥ {cfg.consecutive_days} 天使用率 > {cfg.budget_usage_threshold:.0%}」，无需预算诊断。"
        )
        return

    if result_dict is None:
        st.warning("诊断结果尚未生成，请调整参数或重新上传相关报表。")
        return

    warnings = result_dict.get("warnings") or []
    for w in warnings:
        st.warning(w)

    rows = result_dict.get("rows") or []
    if not rows:
        st.info("有问题活动，但暂无诊断明细。")
        return

    counts = _count_by_conclusion(rows)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("问题活动", len(rows))
    c2.metric("建议加码", counts.get("INCREASE_BUDGET", 0))
    c3.metric("先补货", counts.get("HOLD_RESTOCK", 0))
    c4.metric("先优化", counts.get("HOLD_OPTIMIZE", 0))
    c5.metric("无法诊断", counts.get("UNABLE_TO_DIAGNOSE", 0))

    all_campaign_names = sorted({r.get("广告活动名称") for r in rows if r.get("广告活动名称")})
    selected_conclusions = st.multiselect(
        "筛选结论类型",
        options=list(CONCLUSION_FILTER_OPTIONS.keys()),
        default=[],
        key="budget_diag_conclusion_filter",
    )
    selected_campaigns = st.multiselect(
        "筛选广告活动",
        options=all_campaign_names,
        default=[],
        key="budget_diag_campaign_filter",
    )

    has_filter = bool(selected_conclusions) or bool(selected_campaigns)
    filtered_rows = _apply_row_filters(rows, selected_conclusions, selected_campaigns)

    if has_filter:
        visible_rows = filtered_rows
        if not visible_rows:
            st.info("没有符合筛选条件的诊断结果。")
            return
        st.caption(f"共 {len(rows)} 个问题活动，筛选后 {len(visible_rows)} 条。")
    else:
        visible_rows = _sort_rows_for_preview(rows)[:1]
        st.caption(f"共 {len(rows)} 个问题活动，默认展示 1 条；使用上方筛选查看更多。")

    main_df = _rows_to_dataframe(visible_rows)
    st.dataframe(main_df, use_container_width=True, hide_index=True)

    st.download_button(
        label="📥 导出当前可见结果 CSV",
        data=main_df.to_csv(index=False).encode("utf-8-sig"),
        file_name="预算诊断结果.csv",
        mime="text/csv",
        key="budget_diagnosis_export",
    )

    with st.expander(f"📥 导出全部 {len(rows)} 条", expanded=False):
        all_df = _rows_to_dataframe(_sort_rows_for_preview(rows))
        st.download_button(
            label=f"下载全部 {len(rows)} 条诊断结果",
            data=all_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="预算诊断结果_全部.csv",
            mime="text/csv",
            key="budget_diagnosis_export_all",
        )

    visible_campaign_names = [r.get("广告活动名称") for r in visible_rows if r.get("广告活动名称")]
    asin_default_index = 0
    if len(selected_campaigns) == 1 and selected_campaigns[0] in visible_campaign_names:
        asin_default_index = visible_campaign_names.index(selected_campaigns[0])

    with st.expander("📂 查看活动 ASIN 明细（按需展开）", expanded=False):
        if not visible_campaign_names:
            st.info("当前可见结果中无活动。")
            return
        selected = st.selectbox(
            "选择活动",
            options=visible_campaign_names,
            index=asin_default_index,
            key="budget_diagnosis_asin_campaign",
        )
        if selected:
            target = next((r for r in visible_rows if r.get("广告活动名称") == selected), None)
            if target is None:
                target = next((r for r in rows if r.get("广告活动名称") == selected), None)
            if target and target.get("asin明细"):
                detail_df = pd.DataFrame(target["asin明细"])
                if "是否最差ASIN" not in detail_df.columns and "广告ASIN" in detail_df.columns:
                    worst = target.get("最差ASIN")
                    detail_df["是否最差ASIN"] = detail_df["广告ASIN"].apply(
                        lambda x: "✓" if x == worst else ""
                    )
                show_cols = [
                    c
                    for c in [
                        "广告ASIN",
                        "广告SKU",
                        "可售数量",
                        "在途库存数量",
                        "已订购商品数量",
                        "日均订单",
                        "库存可售天数",
                        "是否最差ASIN",
                    ]
                    if c in detail_df.columns
                ]
                st.dataframe(detail_df[show_cols], use_container_width=True, hide_index=True)
            else:
                st.info("该活动无 ASIN 明细。")


def _placement_gate_status(store) -> list[tuple[str, bool]]:
    return [
        ("广告位报表", store.get("placement") is not None),
        ("预算报表", store.get("budget") is not None),
        ("推广的商品", store.get("product_sponsored") is not None),
        ("库存报表", store.get("inventory") is not None),
        ("业务报表", store.get("business") is not None),
    ]


def _sort_placement_rows_for_preview(rows: list[dict]) -> list[dict]:
    return sorted(
        rows,
        key=lambda r: (
            _PLACEMENT_CONCLUSION_SORT_ORDER.get(r.get("诊断结论码", "UNABLE_TO_DIAGNOSE"), 99),
            float(r.get("搜索位点击占比") or 0),
        ),
    )


def _apply_placement_row_filters(
    rows: list[dict],
    selected_conclusion_labels: list[str],
    selected_campaigns: list[str],
) -> list[dict]:
    filtered = rows
    if selected_conclusion_labels:
        codes = {
            PLACEMENT_CONCLUSION_FILTER_OPTIONS[label]
            for label in selected_conclusion_labels
            if label in PLACEMENT_CONCLUSION_FILTER_OPTIONS
        }
        filtered = [r for r in filtered if r.get("诊断结论码") in codes]
    if selected_campaigns:
        campaign_set = set(selected_campaigns)
        filtered = [r for r in filtered if r.get("广告活动名称") in campaign_set]
    return filtered


def _placement_row_to_display_dict(row: dict) -> dict:
    def fmt_pct(v):
        return f"{v:.1%}" if v is not None else "—"

    cover = row.get("库存可售天数")
    return {
        "广告活动名称": row.get("广告活动名称"),
        "搜索位点击占比": fmt_pct(row.get("搜索位点击占比")),
        "搜索位花费占比": fmt_pct(row.get("搜索位花费占比")),
        "搜索位点击": int(row.get("搜索位点击") or 0),
        "搜索位ACOS": fmt_pct(row.get("搜索位ACOS")),
        "搜索位转化率": fmt_pct(row.get("搜索位转化率")),
        "搜索位订单": int(row.get("搜索位订单") or 0),
        "商品页ACOS": fmt_pct(row.get("商品页ACOS")),
        "最差ASIN": row.get("最差ASIN") or "—",
        "库存可售天数": cover if cover is not None else "—",
        "诊断结论": row.get("诊断结论"),
        "原因说明": row.get("原因说明"),
    }


def _placement_metric_groups(counts: dict[str, int]) -> dict[str, Any]:
    """将结论计数分为：需动作 / 无需动作（加总=诊断活动数）。"""
    action_detail = {
        "建议加溢价": counts.get("INCREASE_SEARCH_PREMIUM", 0),
        "谨慎加溢价": counts.get("INCREASE_SEARCH_PREMIUM_CAUTIOUS", 0),
        "可试加溢价": counts.get("TRY_INCREASE_PREMIUM", 0),
        "建议降竞价": counts.get("REDUCE_SEARCH_BID_OR_PREMIUM", 0),
        "搜索侧偏弱": counts.get("SEARCH_COMPETITION_WEAK", 0),
    }
    legacy_optimize = counts.get("OPTIMIZE_LISTING", 0)
    legacy_pending = counts.get("PENDING_LISTING", 0)
    if legacy_optimize:
        action_detail["（历史）先优化Listing"] = legacy_optimize
    if legacy_pending:
        action_detail["（历史）待填Listing"] = legacy_pending
    no_action_detail = {
        "结构正常": counts.get("NO_ACTION_NEEDED", 0),
        "库存不足": counts.get("HOLD_RESTOCK", 0),
        "无法诊断": counts.get("UNABLE_TO_DIAGNOSE", 0),
    }
    action_total = sum(action_detail.values())
    no_action_total = sum(no_action_detail.values())
    return {
        "action_total": action_total,
        "action_detail": action_detail,
        "no_action_total": no_action_total,
        "no_action_detail": no_action_detail,
    }


def _format_detail_caption(label: str, detail: dict[str, int]) -> str:
    parts = [f"{name} {n}" for name, n in detail.items() if n > 0]
    return f"{label}：" + " · ".join(parts) if parts else f"{label}：无"


def _count_placement_by_conclusion(rows: list[dict]) -> dict[str, int]:
    counts = {code: 0 for code in PLACEMENT_CONCLUSION_LABELS}
    for row in rows:
        code = row.get("诊断结论码", "UNABLE_TO_DIAGNOSE")
        counts[code] = counts.get(code, 0) + 1
    return counts


def get_placement_diagnosis_status_caption(store) -> str | None:
    if store.get("placement") is None:
        return None
    result_dict = store.get("placement_diagnosis_result") or {}
    rows = result_dict.get("rows") or []
    if not rows:
        return "广告位诊断：请展开查看（需已上传广告位与联动报表）"
    counts = _count_placement_by_conclusion(rows)
    groups = _placement_metric_groups(counts)
    total = len(rows)
    action = groups["action_total"]
    return f"广告位诊断：{total} 个活动，{action} 个需动作 · 展开查看"


def render_listing_assessment_form(store, all_rows: list[dict]) -> None:
    """可选 Listing 自评，不影响诊断结论。"""
    campaign_asin_map = store.get("campaign_asin_map") or {}
    campaign_options = sorted(
        {r.get("广告活动名称") for r in all_rows if r.get("广告活动名称")}
        | {c for c in campaign_asin_map if campaign_asin_map.get(c)}
    )
    if not campaign_options:
        return

    with st.expander("📝 Listing 自评（可选参考，不影响诊断结论）", expanded=False):
        st.caption("填写后仅追加风险提示至原因说明，不阻塞任何诊断流程。")
        listing_data = load_listing_by_asin(get_current_user_id())

        selected_campaign = st.selectbox(
            "选择活动",
            options=campaign_options,
            key="listing_assessment_campaign",
        )
        asins = campaign_asin_map.get(selected_campaign, [])
        if not asins:
            st.warning("该活动未在推广的商品报表中匹配到 ASIN。")
            return

        diag_row = next(
            (r for r in all_rows if r.get("广告活动名称") == selected_campaign),
            None,
        )
        preferred_asin = (diag_row or {}).get("最差ASIN")
        asin_index = asins.index(preferred_asin) if preferred_asin in asins else 0

        selected_asin = st.selectbox(
            "选择 ASIN（默认最差 ASIN）",
            options=asins,
            index=asin_index,
            key="listing_assessment_asin",
        )
        if preferred_asin and selected_asin == preferred_asin:
            st.caption(f"该活动诊断关联的最差 ASIN：{preferred_asin}")

        current = listing_data.get(selected_asin, {})
        assessment: dict[str, str] = {}
        cols = st.columns(2)
        for idx, field in enumerate(LISTING_FIELDS):
            with cols[idx % 2]:
                default_idx = LISTING_LEVELS.index(current[field]) if current.get(field) in LISTING_LEVELS else 0
                assessment[field] = st.selectbox(
                    field,
                    options=LISTING_LEVELS,
                    index=default_idx,
                    key=f"listing_{selected_asin}_{field}",
                )

        if st.button("保存 Listing 自评", key=f"listing_save_{selected_asin}", use_container_width=True):
            save_listing_for_asin(selected_asin, assessment, get_current_user_id())
            st.success(f"已保存 ASIN {selected_asin} 的 Listing 自评（覆盖旧记录）。")
            from diagnosis.recalc import recalc_placement_pipeline
            recalc_placement_pipeline(st.session_state.diagnosis_config, get_current_user_id())
            st.rerun()


def render_placement_diagnosis_panel(store) -> None:
    """手动 Tab 广告位诊断区块。"""
    result_dict = store.get("placement_diagnosis_result") or st.session_state.get("placement_diagnosis_result")

    gates = _placement_gate_status(store)
    gate_text = " · ".join([f"{'✓' if ok else '✗'} {name}" for name, ok in gates])
    st.caption(f"数据就绪：{gate_text}")

    if store.get("placement") is None:
        st.info("请先上传广告位报表。")
        return

    if result_dict is None:
        st.warning("诊断结果尚未生成，请调整参数或重新上传相关报表。")
        return

    for w in result_dict.get("warnings") or []:
        st.warning(w)

    rows = result_dict.get("rows") or []
    if not rows:
        st.info("暂无可诊断活动（可能全部被预算异常活动排除）。")
        return

    counts = _count_placement_by_conclusion(rows)
    groups = _placement_metric_groups(counts)
    total = len(rows)
    action_total = groups["action_total"]
    no_action_total = groups["no_action_total"]

    c1, c2, c3 = st.columns(3)
    c1.metric("诊断活动", total)
    c2.metric("需动作", action_total)
    c3.metric("无需动作", no_action_total)

    st.caption(f"共 {total} 个活动 = 需动作 {action_total} + 无需动作 {no_action_total}")
    st.caption(_format_detail_caption("需动作明细", groups["action_detail"]))
    st.caption(_format_detail_caption("无需动作明细", groups["no_action_detail"]))
    st.caption("Listing 自评为可选参考，填写后仅追加风险提示，不影响上述结论。")

    all_campaign_names = sorted({r.get("广告活动名称") for r in rows if r.get("广告活动名称")})
    conclusion_labels = list(PLACEMENT_CONCLUSION_FILTER_OPTIONS.keys())
    selected_conclusions = st.multiselect(
        "筛选结论类型",
        options=conclusion_labels,
        default=[],
        key="placement_diag_conclusion_filter",
    )
    selected_campaigns = st.multiselect(
        "筛选广告活动",
        options=all_campaign_names,
        default=[],
        key="placement_diag_campaign_filter",
    )

    has_filter = bool(selected_conclusions) or bool(selected_campaigns)
    filtered_rows = _apply_placement_row_filters(rows, selected_conclusions, selected_campaigns)

    if has_filter:
        visible_rows = filtered_rows
        if not visible_rows:
            st.info("没有符合筛选条件的诊断结果。")
            render_listing_assessment_form(store, rows)
            return
        st.caption(f"共 {total} 个活动，筛选后 {len(visible_rows)} 条。")
    else:
        visible_rows = _sort_placement_rows_for_preview(rows)[:1]
        st.caption(f"共 {total} 个活动，默认展示 1 条；使用上方筛选查看更多。")

    main_df = pd.DataFrame([_placement_row_to_display_dict(r) for r in visible_rows])
    st.dataframe(main_df, use_container_width=True, hide_index=True)

    st.download_button(
        label="📥 导出当前可见结果 CSV",
        data=main_df.to_csv(index=False).encode("utf-8-sig"),
        file_name="广告位诊断结果.csv",
        mime="text/csv",
        key="placement_diagnosis_export",
    )

    with st.expander(f"📥 导出全部 {len(rows)} 条", expanded=False):
        all_df = pd.DataFrame([_placement_row_to_display_dict(r) for r in _sort_placement_rows_for_preview(rows)])
        st.download_button(
            label=f"下载全部 {len(rows)} 条诊断结果",
            data=all_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="广告位诊断结果_全部.csv",
            mime="text/csv",
            key="placement_diagnosis_export_all",
        )

    render_listing_assessment_form(store, rows)


KEYWORD_CONCLUSION_FILTER_OPTIONS = {
    label: code for code, label in KEYWORD_CONCLUSION_LABELS.items()
}

_KEYWORD_CONCLUSION_SORT_ORDER = {
    "REVIEW_SEARCH_ZERO_CONV": 0,
    "REVIEW_SEARCH_HIGH_ACOS": 1,
    "REVIEW_SEARCH_POTENTIAL": 2,
    "UNABLE_TO_DIAGNOSE": 3,
}


def _keyword_row_to_display_dict(row: dict) -> dict:
    acos = row.get("总ACOS")
    cvr = row.get("总转化率")
    return {
        "广告活动名称": row.get("广告活动名称"),
        "广告组名称": row.get("广告组名称"),
        "投放": row.get("投放"),
        "匹配类型": row.get("匹配类型"),
        "总花费": round(float(row.get("总花费") or 0), 2),
        "总点击": int(row.get("总点击") or 0),
        "总订单": int(row.get("总订单") or 0),
        "总ACOS": f"{acos:.1%}" if acos is not None else "—",
        "总转化率": f"{cvr:.1%}" if cvr is not None else "—",
        "重复活动数": int(row.get("重复活动数") or 0),
        "诊断结论": row.get("诊断结论"),
        "原因说明": row.get("原因说明"),
    }


def _count_keyword_by_conclusion(rows: list[dict]) -> dict[str, int]:
    counts = {code: 0 for code in KEYWORD_CONCLUSION_LABELS}
    for row in rows:
        code = row.get("诊断结论码", "UNABLE_TO_DIAGNOSE")
        counts[code] = counts.get(code, 0) + 1
    return counts


def _count_keyword_duplicate(rows: list[dict]) -> int:
    return sum(1 for row in rows if row.get("重复投放"))


def _sort_keyword_rows_for_preview(rows: list[dict]) -> list[dict]:
    return sorted(
        rows,
        key=lambda r: (
            _KEYWORD_CONCLUSION_SORT_ORDER.get(r.get("诊断结论码", "UNABLE_TO_DIAGNOSE"), 99),
            -float(r.get("总花费") or 0),
        ),
    )


def _apply_keyword_row_filters(
    rows: list[dict],
    selected_conclusion_labels: list[str],
    selected_campaigns: list[str],
    selected_keywords: list[str],
    selected_match_types: list[str],
) -> list[dict]:
    filtered = rows
    if selected_conclusion_labels:
        codes = {
            KEYWORD_CONCLUSION_FILTER_OPTIONS[label]
            for label in selected_conclusion_labels
            if label in KEYWORD_CONCLUSION_FILTER_OPTIONS
        }
        if "DUPLICATE_KEYWORD_LAYERING" in codes:
            codes.discard("DUPLICATE_KEYWORD_LAYERING")
            filtered = [
                r for r in filtered
                if r.get("重复投放") or r.get("诊断结论码") in codes
            ]
        else:
            filtered = [r for r in filtered if r.get("诊断结论码") in codes]
    if selected_campaigns:
        campaign_set = set(selected_campaigns)
        filtered = [r for r in filtered if r.get("广告活动名称") in campaign_set]
    if selected_keywords:
        kw_set = set(selected_keywords)
        filtered = [r for r in filtered if r.get("投放") in kw_set]
    if selected_match_types:
        mt_set = set(selected_match_types)
        filtered = [r for r in filtered if r.get("匹配类型") in mt_set]
    return filtered


def get_keyword_diagnosis_status_caption(store) -> str | None:
    if store.get("keyword") is None:
        return None
    result_dict = store.get("keyword_diagnosis_result") or {}
    rows = result_dict.get("rows") or []
    if not rows:
        return "投放词分诊：当前无异常信号 · 展开查看"
    counts = _count_keyword_by_conclusion(rows)
    review = (
        counts.get("REVIEW_SEARCH_ZERO_CONV", 0)
        + counts.get("REVIEW_SEARCH_HIGH_ACOS", 0)
        + counts.get("REVIEW_SEARCH_POTENTIAL", 0)
    )
    dup = _count_keyword_duplicate(rows)
    return f"投放词分诊：{len(rows)} 条异常（需查搜索词 {review}，重复投放 {dup}）· 展开查看"


def render_keyword_diagnosis_panel(store) -> None:
    """手动 Tab 投放词分诊区块。"""
    result_dict = store.get("keyword_diagnosis_result") or st.session_state.get("keyword_diagnosis_result")

    if store.get("keyword") is None:
        st.info("请先上传投放词报表。")
        return

    if result_dict is None:
        st.warning("分诊结果尚未生成，请调整参数或重新上传投放词报表。")
        return

    for w in result_dict.get("warnings") or []:
        st.warning(w)

    rows = result_dict.get("rows") or []
    if not rows:
        st.success("✅ 未发现需关注的投放词异常（或样本未达阈值）。")
        return

    counts = _count_keyword_by_conclusion(rows)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("异常条数", len(rows))
    c2.metric("无转化", counts.get("REVIEW_SEARCH_ZERO_CONV", 0))
    c3.metric("高ACOS", counts.get("REVIEW_SEARCH_HIGH_ACOS", 0))
    c4.metric("潜力", counts.get("REVIEW_SEARCH_POTENTIAL", 0))
    c5.metric("重复投放", _count_keyword_duplicate(rows))

    st.caption("本层仅分诊，不给否定/降价最终结论；下一步请查搜索词报表。")

    all_campaigns = sorted({r.get("广告活动名称") for r in rows if r.get("广告活动名称")})
    all_keywords = sorted({r.get("投放") for r in rows if r.get("投放")})
    all_match_types = sorted({r.get("匹配类型") for r in rows if r.get("匹配类型")})
    selected_conclusions = st.multiselect(
        "筛选结论类型",
        options=list(KEYWORD_CONCLUSION_FILTER_OPTIONS.keys()),
        default=[],
        key="keyword_diag_conclusion_filter",
    )
    selected_campaigns = st.multiselect(
        "筛选广告活动",
        options=all_campaigns,
        default=[],
        key="keyword_diag_campaign_filter",
    )
    selected_keywords = st.multiselect(
        "筛选投放词",
        options=all_keywords,
        default=[],
        key="keyword_diag_keyword_filter",
    )
    selected_match_types = st.multiselect(
        "筛选匹配类型",
        options=all_match_types,
        default=[],
        key="keyword_diag_match_type_filter",
    )

    has_filter = (
        bool(selected_conclusions)
        or bool(selected_campaigns)
        or bool(selected_keywords)
        or bool(selected_match_types)
    )
    filtered_rows = _apply_keyword_row_filters(
        rows, selected_conclusions, selected_campaigns, selected_keywords, selected_match_types
    )

    if has_filter:
        visible_rows = filtered_rows
        if not visible_rows:
            st.info("没有符合筛选条件的分诊结果。")
            return
        st.caption(f"共 {len(rows)} 条异常，筛选后 {len(visible_rows)} 条。")
    else:
        visible_rows = _sort_keyword_rows_for_preview(rows)[:1]
        st.caption(f"共 {len(rows)} 条异常，默认展示 1 条；使用上方筛选查看更多。")

    main_df = pd.DataFrame([_keyword_row_to_display_dict(r) for r in visible_rows])
    st.dataframe(main_df, use_container_width=True, hide_index=True)

    st.download_button(
        label="📥 导出当前可见结果 CSV",
        data=main_df.to_csv(index=False).encode("utf-8-sig"),
        file_name="投放词分诊结果.csv",
        mime="text/csv",
        key="keyword_diagnosis_export",
    )

    with st.expander(f"📥 导出全部 {len(rows)} 条", expanded=False):
        all_df = pd.DataFrame([_keyword_row_to_display_dict(r) for r in _sort_keyword_rows_for_preview(rows)])
        st.download_button(
            label=f"下载全部 {len(rows)} 条分诊结果",
            data=all_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="投放词分诊结果_全部.csv",
            mime="text/csv",
            key="keyword_diagnosis_export_all",
        )


SEARCH_CONCLUSION_FILTER_OPTIONS = {
    label: code for code, label in SEARCH_CONCLUSION_LABELS.items()
    if code != "UNABLE_TO_DIAGNOSE"
}

_SEARCH_CONCLUSION_SORT_ORDER = {
    "NEGATIVE_CANDIDATE": 0,
    "HIGH_ACOS_TERM": 1,
    "EXPANSION_CANDIDATE": 2,
    "UNABLE_TO_DIAGNOSE": 3,
}


def _search_row_to_display_dict(row: dict) -> dict:
    acos = row.get("总ACOS")
    cvr = row.get("总转化率")
    share = row.get("花费占比")
    return {
        "广告活动名称": row.get("广告活动名称"),
        "广告组名称": row.get("广告组名称"),
        "投放": row.get("投放"),
        "匹配类型": row.get("匹配类型"),
        "客户搜索词": row.get("客户搜索词"),
        "总花费": round(float(row.get("总花费") or 0), 2),
        "总点击": int(row.get("总点击") or 0),
        "总订单": int(row.get("总订单") or 0),
        "总ACOS": f"{acos:.1%}" if acos is not None else "—",
        "总转化率": f"{cvr:.1%}" if cvr is not None else "—",
        "花费占比": f"{share:.1%}" if share is not None else "—",
        "流量集中": "是" if row.get("流量集中") else "否",
        "重复触发": "是" if row.get("重复触发") else "否",
        "重复触发投放词数": int(row.get("重复触发投放词数") or 0),
        "诊断结论": row.get("诊断结论"),
        "原因说明": row.get("原因说明"),
    }


def _count_search_by_conclusion(rows: list[dict]) -> dict[str, int]:
    counts = {code: 0 for code in SEARCH_CONCLUSION_LABELS}
    for row in rows:
        code = row.get("诊断结论码", "UNABLE_TO_DIAGNOSE")
        counts[code] = counts.get(code, 0) + 1
    return counts


def _count_search_traffic_concentration(rows: list[dict]) -> int:
    return sum(1 for row in rows if row.get("流量集中"))


def _count_search_duplicate_trigger(rows: list[dict]) -> int:
    return sum(1 for row in rows if row.get("重复触发"))


def _sort_search_rows_for_preview(rows: list[dict]) -> list[dict]:
    return sorted(
        rows,
        key=lambda r: (
            _SEARCH_CONCLUSION_SORT_ORDER.get(r.get("诊断结论码", "UNABLE_TO_DIAGNOSE"), 99),
            -float(r.get("总花费") or 0),
        ),
    )


def _apply_search_row_filters(
    rows: list[dict],
    selected_conclusion_labels: list[str],
    selected_campaigns: list[str],
    selected_terms: list[str],
    selected_match_types: list[str],
) -> list[dict]:
    filtered = rows
    if selected_conclusion_labels:
        codes = {
            SEARCH_CONCLUSION_FILTER_OPTIONS[label]
            for label in selected_conclusion_labels
            if label in SEARCH_CONCLUSION_FILTER_OPTIONS
        }
        risk_traffic = "⚠️ 流量集中风险" in selected_conclusion_labels
        risk_dup = "⚠️ 重复触发风险" in selected_conclusion_labels
        if risk_traffic or risk_dup:
            def _match(row: dict) -> bool:
                if codes and row.get("诊断结论码") in codes:
                    return True
                if risk_traffic and row.get("流量集中"):
                    return True
                if risk_dup and row.get("重复触发"):
                    return True
                return False
            filtered = [r for r in filtered if _match(r)]
        else:
            filtered = [r for r in filtered if r.get("诊断结论码") in codes]
    if selected_campaigns:
        campaign_set = set(selected_campaigns)
        filtered = [r for r in filtered if r.get("广告活动名称") in campaign_set]
    if selected_terms:
        term_set = set(selected_terms)
        filtered = [r for r in filtered if r.get("客户搜索词") in term_set]
    if selected_match_types:
        mt_set = set(selected_match_types)
        filtered = [r for r in filtered if r.get("匹配类型") in mt_set]
    return filtered


def get_search_diagnosis_status_caption(store) -> str | None:
    if store.get("search") is None:
        return None
    result_dict = store.get("search_diagnosis_result") or {}
    rows = result_dict.get("rows") or []
    if not rows:
        return "搜索词诊断：当前无候选 · 展开查看"
    counts = _count_search_by_conclusion(rows)
    traffic = _count_search_traffic_concentration(rows)
    dup = _count_search_duplicate_trigger(rows)
    return (
        f"搜索词诊断：{len(rows)} 条候选"
        f"（否定 {counts.get('NEGATIVE_CANDIDATE', 0)}，"
        f"高ACOS {counts.get('HIGH_ACOS_TERM', 0)}，"
        f"拓词 {counts.get('EXPANSION_CANDIDATE', 0)}；"
        f"流量集中 {traffic}，重复触发 {dup}）· 展开查看"
    )


def render_search_diagnosis_panel(store) -> None:
    """手动 Tab 搜索词诊断区块。"""
    result_dict = store.get("search_diagnosis_result") or st.session_state.get("search_diagnosis_result")

    if store.get("search") is None:
        st.info("请先上传搜索词报表。")
        return

    if result_dict is None:
        st.warning("诊断结果尚未生成，请调整参数或重新上传搜索词报表。")
        return

    for w in result_dict.get("warnings") or []:
        st.warning(w)

    rows = result_dict.get("rows") or []
    if not rows:
        st.success("✅ 未发现需关注的搜索词候选（或样本未达阈值）。")
        return

    counts = _count_search_by_conclusion(rows)
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("候选条数", len(rows))
    c2.metric("否定候选", counts.get("NEGATIVE_CANDIDATE", 0))
    c3.metric("高ACOS", counts.get("HIGH_ACOS_TERM", 0))
    c4.metric("拓词候选", counts.get("EXPANSION_CANDIDATE", 0))
    c5.metric("流量集中", _count_search_traffic_concentration(rows))
    c6.metric("重复触发", _count_search_duplicate_trigger(rows))

    st.caption("本层输出候选与原因，不做自动否定/降价/拓词；请人工确认后执行。")

    filter_options = list(SEARCH_CONCLUSION_FILTER_OPTIONS.keys()) + [
        "⚠️ 流量集中风险",
        "⚠️ 重复触发风险",
    ]
    all_campaigns = sorted({r.get("广告活动名称") for r in rows if r.get("广告活动名称")})
    all_terms = sorted({r.get("客户搜索词") for r in rows if r.get("客户搜索词")})
    all_match_types = sorted({r.get("匹配类型") for r in rows if r.get("匹配类型")})
    selected_conclusions = st.multiselect(
        "筛选结论类型",
        options=filter_options,
        default=[],
        key="search_diag_conclusion_filter",
    )
    selected_campaigns = st.multiselect(
        "筛选广告活动",
        options=all_campaigns,
        default=[],
        key="search_diag_campaign_filter",
    )
    selected_terms = st.multiselect(
        "筛选客户搜索词",
        options=all_terms,
        default=[],
        key="search_diag_term_filter",
    )
    selected_match_types = st.multiselect(
        "筛选匹配类型",
        options=all_match_types,
        default=[],
        key="search_diag_match_type_filter",
    )

    has_filter = (
        bool(selected_conclusions)
        or bool(selected_campaigns)
        or bool(selected_terms)
        or bool(selected_match_types)
    )
    filtered_rows = _apply_search_row_filters(
        rows, selected_conclusions, selected_campaigns, selected_terms, selected_match_types
    )

    if has_filter:
        visible_rows = filtered_rows
        if not visible_rows:
            st.info("没有符合筛选条件的诊断结果。")
            return
        st.caption(f"共 {len(rows)} 条候选，筛选后 {len(visible_rows)} 条。")
    else:
        visible_rows = _sort_search_rows_for_preview(rows)[:1]
        st.caption(f"共 {len(rows)} 条候选，默认展示 1 条；使用上方筛选查看更多。")

    main_df = pd.DataFrame([_search_row_to_display_dict(r) for r in visible_rows])
    st.dataframe(main_df, use_container_width=True, hide_index=True)

    st.download_button(
        label="📥 导出当前可见结果 CSV",
        data=main_df.to_csv(index=False).encode("utf-8-sig"),
        file_name="搜索词诊断结果.csv",
        mime="text/csv",
        key="search_diagnosis_export",
    )

    with st.expander(f"📥 导出全部 {len(rows)} 条", expanded=False):
        all_df = pd.DataFrame([_search_row_to_display_dict(r) for r in _sort_search_rows_for_preview(rows)])
        st.download_button(
            label=f"下载全部 {len(rows)} 条诊断结果",
            data=all_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="搜索词诊断结果_全部.csv",
            mime="text/csv",
            key="search_diagnosis_export_all",
        )
