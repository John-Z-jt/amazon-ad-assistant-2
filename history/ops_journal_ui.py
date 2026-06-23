from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from history.ops_journal_storage import (
    create_journal_entry,
    delete_journal_entries,
    query_journal_entries,
)


def _entries_to_display_rows(entries: list[dict]) -> list[dict]:
    rows = []
    for item in entries:
        rows.append(
            {
                "日期": item.get("event_date") or "",
                "ASIN": item.get("asin") or "",
                "广告活动": item.get("campaign_name") or "",
                "广告组": item.get("ad_group_name") or "",
                "备注": item.get("content") or "",
            }
        )
    return rows


def _entry_option_label(item: dict) -> str:
    parts = [
        item.get("event_date") or "",
        item.get("asin") or "-",
        item.get("campaign_name") or "-",
        (item.get("content") or "")[:40],
    ]
    return " | ".join(parts)


def render_ops_journal_readonly(
    start_date: date,
    end_date: date,
    *,
    title: str = "运营日志",
) -> None:
    """历史查询联动：只读展示该时间段内的运营日志。"""
    st.markdown("---")
    st.markdown(f"#### {title}")
    st.caption(f"{start_date.isoformat()} ~ {end_date.isoformat()}")

    entries = query_journal_entries(start_date, end_date)
    if not entries:
        st.caption("该时间段暂无运营日志。")
        return

    st.dataframe(
        _entries_to_display_rows(entries),
        use_container_width=True,
        hide_index=True,
    )


def render_ops_journal_tab() -> None:
    st.subheader("运营日志")
    st.caption("记录广告动作、Listing 变动、市场情况等，供后续复盘参考。只记录，不分析。")

    st.markdown("#### 新增日志")
    today = date.today()
    col1, col2 = st.columns(2)
    with col1:
        event_date = st.date_input("日期", value=today, key="ops_journal_new_date")
    with col2:
        asin = st.text_input("ASIN（可空）", key="ops_journal_new_asin")
    col3, col4 = st.columns(2)
    with col3:
        campaign_name = st.text_input("广告活动（可空）", key="ops_journal_new_campaign")
    with col4:
        ad_group_name = st.text_input("广告组（可空）", key="ops_journal_new_ad_group")
    content = st.text_area("备注内容", key="ops_journal_new_content", height=120)

    if st.button("保存", key="ops_journal_save", type="primary"):
        try:
            create_journal_entry(
                event_date,
                content,
                asin=asin,
                campaign_name=campaign_name,
                ad_group_name=ad_group_name,
            )
            st.success("已保存运营日志。")
            st.rerun()
        except ValueError as e:
            st.error(str(e))

    st.markdown("#### 查询日志")
    default_start = today - timedelta(days=30)
    q_col1, q_col2 = st.columns(2)
    with q_col1:
        query_start = st.date_input("开始日期", value=default_start, key="ops_journal_query_start")
    with q_col2:
        query_end = st.date_input("结束日期", value=today, key="ops_journal_query_end")

    f_col1, f_col2 = st.columns(2)
    with f_col1:
        filter_asin = st.text_input("ASIN 筛选（可选）", key="ops_journal_filter_asin")
    with f_col2:
        filter_campaign = st.text_input("广告活动筛选（可选）", key="ops_journal_filter_campaign")

    if query_start > query_end:
        st.error("开始日期不能晚于结束日期。")
        return

    entries = query_journal_entries(
        query_start,
        query_end,
        asin=filter_asin or None,
        campaign_name=filter_campaign or None,
    )

    if not entries:
        st.caption("暂无符合条件的日志。")
        return

    st.dataframe(
        _entries_to_display_rows(entries),
        use_container_width=True,
        hide_index=True,
    )

    id_by_label = {_entry_option_label(item): int(item["id"]) for item in entries}
    selected_labels = st.multiselect(
        "选择要删除的日志",
        options=list(id_by_label.keys()),
        default=[],
        key="ops_journal_delete_choices",
    )
    if st.button("删除所选", key="ops_journal_delete_submit", disabled=not selected_labels):
        to_delete = [id_by_label[label] for label in selected_labels]
        deleted = delete_journal_entries(to_delete)
        st.success(f"已删除 {deleted} 条日志。")
        st.rerun()
