from __future__ import annotations

import hashlib
from datetime import date, timedelta

import streamlit as st

from ad_analyzers.budget_analyzer import get_budget_analysis, render_budget_analysis_result
from ad_analyzers.keyword_analyzer import get_keyword_analysis, render_keyword_analysis_result
from ad_analyzers.placement_analyzer import get_placement_analysis, render_placement_analysis_result
from ad_analyzers.search_analyzer import get_search_analysis, render_search_analysis_result
from ad_analyzers.search_term_trend import get_search_term_trend, render_search_term_trend_result
from ad_analyzers.product_sponserd_analyzer import (
    get_product_sponsored_analysis,
    render_product_sponsored_analysis_result,
)
from data_df_store.data_store import store
from history.budget_storage import list_all_uploads, query_budget_dataframe
from history.keyword_storage import query_keyword_dataframe
from history.placement_storage import query_placement_dataframe
from history.product_sponsored_storage import query_product_sponsored_dataframe
from history.search_storage import query_search_dataframe
from history.search_share_storage import query_search_share_dataframe
from history.ops_journal_ui import render_ops_journal_readonly

REPORT_TYPE_LABELS = {
    "budget": "预算",
    "placement": "广告位",
    "keyword": "投放词",
    "search": "搜索词",
    "search_share": "搜索词份额",
    "product_sponsored": "推广的商品",
}

SUPPORTED_HISTORY_REPORTS = {
    "预算": "budget",
    "广告位": "placement",
    "投放词": "keyword",
    "搜索词": "search",
    "搜索词份额": "search_share",
    "推广的商品": "product_sponsored",
}


def _init_session_upload_state() -> None:
    if "session_upload_ids" not in st.session_state:
        st.session_state.session_upload_ids = []
    if "show_end_session_dialog" not in st.session_state:
        st.session_state.show_end_session_dialog = False


def register_session_upload(upload_id: int) -> None:
    _init_session_upload_state()
    if upload_id not in st.session_state.session_upload_ids:
        st.session_state.session_upload_ids.append(upload_id)


BUDGET_INGEST_FP_KEY = "budget_ingest_fingerprint"
PLACEMENT_INGEST_FP_KEY = "placement_ingest_fingerprint"
KEYWORD_INGEST_FP_KEY = "keyword_ingest_fingerprint"
SEARCH_INGEST_FP_KEY = "search_ingest_fingerprint"
SEARCH_SHARE_INGEST_FP_KEY = "search_share_ingest_fingerprint"
PRODUCT_SPONSORED_INGEST_FP_KEY = "product_sponsored_ingest_fingerprint"


def _upload_data_fingerprint(df, source_filename: str) -> str:
    payload = f"{source_filename}\n{df.to_csv(index=False)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def clear_budget_ingest_fingerprint() -> None:
    st.session_state.pop(BUDGET_INGEST_FP_KEY, None)


def clear_placement_ingest_fingerprint() -> None:
    st.session_state.pop(PLACEMENT_INGEST_FP_KEY, None)


def clear_keyword_ingest_fingerprint() -> None:
    st.session_state.pop(KEYWORD_INGEST_FP_KEY, None)


def clear_search_ingest_fingerprint() -> None:
    st.session_state.pop(SEARCH_INGEST_FP_KEY, None)


def clear_search_share_ingest_fingerprint() -> None:
    st.session_state.pop(SEARCH_SHARE_INGEST_FP_KEY, None)


def clear_product_sponsored_ingest_fingerprint() -> None:
    st.session_state.pop(PRODUCT_SPONSORED_INGEST_FP_KEY, None)


def clear_ingest_fingerprints() -> None:
    clear_budget_ingest_fingerprint()
    clear_placement_ingest_fingerprint()
    clear_keyword_ingest_fingerprint()
    clear_search_ingest_fingerprint()
    clear_search_share_ingest_fingerprint()
    clear_product_sponsored_ingest_fingerprint()


def _upload_option_label(item: dict) -> str:
    report_type = item.get("report_type", "")
    return (
        f"{REPORT_TYPE_LABELS.get(report_type, report_type)} | "
        f"{item.get('uploaded_at', '')} | "
        f"{item.get('period_start')} ~ {item.get('period_end')} | "
        f"{item.get('source_filename', '')}"
    )


def _build_upload_select_options(uploads: list[dict]) -> tuple[list[str], dict[str, int]]:
    options: list[str] = []
    id_by_label: dict[str, int] = {}
    for item in uploads:
        label = _upload_option_label(item)
        options.append(label)
        id_by_label[label] = int(item["upload_id"])
    return options, id_by_label


def _clear_ingest_fingerprint_for_report(report_type: str) -> None:
    clearers = {
        "budget": clear_budget_ingest_fingerprint,
        "placement": clear_placement_ingest_fingerprint,
        "keyword": clear_keyword_ingest_fingerprint,
        "search": clear_search_ingest_fingerprint,
        "search_share": clear_search_share_ingest_fingerprint,
        "product_sponsored": clear_product_sponsored_ingest_fingerprint,
    }
    clearer = clearers.get(report_type)
    if clearer:
        clearer()


def _apply_upload_deletions(upload_ids: list[int], uploads: list[dict]) -> int:
    """删除历史库 upload，并同步 session 状态。返回实际删除条数。"""
    if not upload_ids:
        return 0

    from history.budget_storage import delete_uploads

    id_set = set(upload_ids)
    to_delete = [uid for uid in upload_ids if uid in id_set]
    delete_uploads(to_delete)

    _init_session_upload_state()
    st.session_state.session_upload_ids = [
        uid for uid in st.session_state.session_upload_ids if uid not in id_set
    ]

    deleted_types = {u["report_type"] for u in uploads if int(u["upload_id"]) in id_set}
    for report_type in deleted_types:
        _clear_ingest_fingerprint_for_report(report_type)

    st.session_state.pop("history_report_query", None)
    st.session_state.pop("history_budget_query", None)
    return len(to_delete)


def maybe_ingest_budget_upload(df, source_filename: str) -> int | None:
    """同一文件在 uploader 中停留时，仅首次写入历史库（避免 Streamlit rerun 重复入库）。"""
    from history.budget_storage import ingest_budget_upload

    _init_session_upload_state()
    fp = _upload_data_fingerprint(df, source_filename)
    if st.session_state.get(BUDGET_INGEST_FP_KEY) == fp:
        return None

    upload_id = ingest_budget_upload(df, source_filename=source_filename)
    st.session_state[BUDGET_INGEST_FP_KEY] = fp
    register_session_upload(upload_id)
    return upload_id


def maybe_ingest_placement_upload(df, source_filename: str) -> int | None:
    from history.placement_storage import ingest_placement_upload

    _init_session_upload_state()
    fp = _upload_data_fingerprint(df, source_filename)
    if st.session_state.get(PLACEMENT_INGEST_FP_KEY) == fp:
        return None

    upload_id = ingest_placement_upload(df, source_filename=source_filename)
    st.session_state[PLACEMENT_INGEST_FP_KEY] = fp
    register_session_upload(upload_id)
    return upload_id


def maybe_ingest_keyword_upload(df, source_filename: str) -> int | None:
    from history.keyword_storage import ingest_keyword_upload

    _init_session_upload_state()
    fp = _upload_data_fingerprint(df, source_filename)
    if st.session_state.get(KEYWORD_INGEST_FP_KEY) == fp:
        return None

    upload_id = ingest_keyword_upload(df, source_filename=source_filename)
    st.session_state[KEYWORD_INGEST_FP_KEY] = fp
    register_session_upload(upload_id)
    return upload_id


def maybe_ingest_search_upload(df, source_filename: str) -> int | None:
    from history.search_storage import ingest_search_upload

    _init_session_upload_state()
    fp = _upload_data_fingerprint(df, source_filename)
    if st.session_state.get(SEARCH_INGEST_FP_KEY) == fp:
        return None

    upload_id = ingest_search_upload(df, source_filename=source_filename)
    st.session_state[SEARCH_INGEST_FP_KEY] = fp
    register_session_upload(upload_id)
    return upload_id


def maybe_ingest_search_share_upload(df, source_filename: str) -> int | None:
    from history.search_share_storage import ingest_search_share_upload

    _init_session_upload_state()
    fp = _upload_data_fingerprint(df, source_filename)
    if st.session_state.get(SEARCH_SHARE_INGEST_FP_KEY) == fp:
        return None

    upload_id = ingest_search_share_upload(df, source_filename=source_filename)
    st.session_state[SEARCH_SHARE_INGEST_FP_KEY] = fp
    register_session_upload(upload_id)
    return upload_id


def maybe_ingest_product_sponsored_upload(df, source_filename: str) -> int | None:
    from history.product_sponsored_storage import ingest_product_sponsored_upload

    _init_session_upload_state()
    fp = _upload_data_fingerprint(df, source_filename)
    if st.session_state.get(PRODUCT_SPONSORED_INGEST_FP_KEY) == fp:
        return None

    upload_id = ingest_product_sponsored_upload(df, source_filename=source_filename)
    st.session_state[PRODUCT_SPONSORED_INGEST_FP_KEY] = fp
    register_session_upload(upload_id)
    return upload_id


def render_upload_summary_table(
    uploads: list[dict],
    *,
    key_prefix: str = "summary",
    allow_delete: bool = False,
) -> None:
    if not uploads:
        st.caption("暂无已入库记录。")
        return

    display_rows = []
    for item in uploads:
        report_type = item.get("report_type", "")
        display_rows.append(
            {
                "报表类型": REPORT_TYPE_LABELS.get(report_type, report_type),
                "上传时间": item.get("uploaded_at", ""),
                "日期段": f"{item.get('period_start')} ~ {item.get('period_end')}",
                "文件名": item.get("source_filename", ""),
            }
        )
    st.dataframe(display_rows, use_container_width=True, hide_index=True)

    if not allow_delete:
        return

    st.caption("删除 upload **仅影响历史库**，不影响当前会话「手动分析」中的数据。")
    options, id_by_label = _build_upload_select_options(uploads)
    selected_labels = st.multiselect(
        "选择要删除的 upload",
        options=options,
        default=[],
        key=f"{key_prefix}_delete_choices",
    )

    if selected_labels:
        preview = "\n".join(f"- {label}" for label in selected_labels)
        st.warning(f"即将删除以下 {len(selected_labels)} 条记录：\n{preview}")

    confirmed = st.checkbox(
        "我确认删除所选记录，此操作不可恢复",
        value=False,
        key=f"{key_prefix}_delete_confirm",
    )

    delete_disabled = not selected_labels or not confirmed
    if st.button(
        "删除所选",
        key=f"{key_prefix}_delete_submit",
        disabled=delete_disabled,
        type="primary",
    ):
        to_delete = [id_by_label[label] for label in selected_labels]
        deleted = _apply_upload_deletions(to_delete, uploads)
        if deleted:
            st.success(f"已删除 {deleted} 条 upload，请重新生成历史分析。")
            st.rerun()
        else:
            st.warning("未删除任何记录。")


def _budget_analysis_config() -> tuple[float, int]:
    cfg = store.get("diagnosis_config") or {}
    return float(cfg.get("budget_usage_threshold", 0.9)), int(cfg.get("consecutive_days", 3))


def _build_period_state(report: str, start_date: date, end_date: date) -> dict:
    if report == "budget":
        df, missing_days = query_budget_dataframe(start_date, end_date)
        cell_hint = "活动+日期"
    elif report == "placement":
        df, missing_days = query_placement_dataframe(start_date, end_date)
        cell_hint = "活动+放置+日期"
    elif report == "keyword":
        df, missing_days = query_keyword_dataframe(start_date, end_date)
        cell_hint = "活动+广告组+投放+匹配类型+日期"
    elif report == "search":
        df, missing_days = query_search_dataframe(start_date, end_date)
        cell_hint = "活动+广告组+投放+匹配类型+客户搜索词+日期"
    elif report == "product_sponsored":
        df, missing_days = query_product_sponsored_dataframe(start_date, end_date)
        cell_hint = "活动+广告组+广告ASIN+广告SKU+日期"
    else:
        df, missing_days = query_search_share_dataframe(start_date, end_date)
        cell_hint = "搜索词+日期+活动+广告组+投放+匹配类型"
    return {
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "empty": df.empty,
        "missing_days": [d.isoformat() for d in missing_days],
        "cell_hint": cell_hint,
    }


def _normalize_history_query(query_state: dict | None) -> dict | None:
    """统一为 {mode, report, periods}；兼容旧版 history_budget_query。"""
    if not query_state:
        return None
    if query_state.get("report") not in SUPPORTED_HISTORY_REPORTS.values():
        if query_state.get("report") == "budget" or "start" in query_state:
            query_state = {**query_state, "report": "budget"}
        else:
            return None
    if "periods" in query_state:
        return query_state
    if "start" in query_state and "end" in query_state:
        return {
            "mode": "single",
            "report": query_state.get("report", "budget"),
            "periods": [
                {
                    "start": query_state["start"],
                    "end": query_state["end"],
                    "empty": query_state.get("empty", False),
                    "missing_days": query_state.get("missing_days") or [],
                    "cell_hint": "活动+日期",
                }
            ],
        }
    return None


def _render_history_budget_period(period: dict, *, key_prefix: str, title: str) -> None:
    start_date = date.fromisoformat(period["start"])
    end_date = date.fromisoformat(period["end"])
    missing_days = [date.fromisoformat(d) for d in period.get("missing_days") or []]

    st.markdown(f"#### {title}")
    st.caption(f"{start_date.isoformat()} ~ {end_date.isoformat()}")

    if period.get("empty"):
        st.warning("该段无数据。")
        if missing_days:
            st.caption(f"所选范围内均无入库数据（共 {len(missing_days)} 天）。")
        return

    df, missing_days = query_budget_dataframe(start_date, end_date)
    if df.empty:
        st.warning("该段无数据。")
        return

    st.caption(f"按各{period.get('cell_hint', '活动+日期')}最新一批拼数。")
    if missing_days:
        sample = "、".join(d.strftime("%Y-%m-%d") for d in missing_days[:10])
        suffix = f" 等共 {len(missing_days)} 天" if len(missing_days) > 10 else ""
        st.info(f"该段内有部分日期无数据：{sample}{suffix}")

    threshold, consecutive_days = _budget_analysis_config()
    result = get_budget_analysis(df, threshold=threshold, consecutive_days=consecutive_days)
    render_budget_analysis_result(
        result,
        threshold=threshold,
        consecutive_days=consecutive_days,
        key_prefix=key_prefix,
    )


def _render_history_placement_period(period: dict, *, key_prefix: str, title: str) -> None:
    start_date = date.fromisoformat(period["start"])
    end_date = date.fromisoformat(period["end"])
    missing_days = [date.fromisoformat(d) for d in period.get("missing_days") or []]

    st.markdown(f"#### {title}")
    st.caption(f"{start_date.isoformat()} ~ {end_date.isoformat()}")

    if period.get("empty"):
        st.warning("该段无数据。")
        if missing_days:
            st.caption(f"所选范围内均无入库数据（共 {len(missing_days)} 天）。")
        return

    df, missing_days = query_placement_dataframe(start_date, end_date)
    if df.empty:
        st.warning("该段无数据。")
        return

    st.caption(f"按各{period.get('cell_hint', '活动+放置+日期')}最新一批拼数。")
    if missing_days:
        sample = "、".join(d.strftime("%Y-%m-%d") for d in missing_days[:10])
        suffix = f" 等共 {len(missing_days)} 天" if len(missing_days) > 10 else ""
        st.info(f"该段内有部分日期无数据：{sample}{suffix}")

    result = get_placement_analysis(df)
    render_placement_analysis_result(result, key_prefix=key_prefix)


def _render_history_keyword_period(period: dict, *, key_prefix: str, title: str) -> None:
    start_date = date.fromisoformat(period["start"])
    end_date = date.fromisoformat(period["end"])
    missing_days = [date.fromisoformat(d) for d in period.get("missing_days") or []]

    st.markdown(f"#### {title}")
    st.caption(f"{start_date.isoformat()} ~ {end_date.isoformat()}")

    if period.get("empty"):
        st.warning("该段无数据。")
        if missing_days:
            st.caption(f"所选范围内均无入库数据（共 {len(missing_days)} 天）。")
        return

    df, missing_days = query_keyword_dataframe(start_date, end_date)
    if df.empty:
        st.warning("该段无数据。")
        return

    st.caption(f"按各{period.get('cell_hint', '活动+广告组+投放+匹配类型+日期')}最新一批拼数。")
    if missing_days:
        sample = "、".join(d.strftime("%Y-%m-%d") for d in missing_days[:10])
        suffix = f" 等共 {len(missing_days)} 天" if len(missing_days) > 10 else ""
        st.info(f"该段内有部分日期无数据：{sample}{suffix}")

    result = get_keyword_analysis(df)
    render_keyword_analysis_result(result, key_prefix=key_prefix)


def _render_history_search_period(period: dict, *, key_prefix: str, title: str) -> None:
    start_date = date.fromisoformat(period["start"])
    end_date = date.fromisoformat(period["end"])
    missing_days = [date.fromisoformat(d) for d in period.get("missing_days") or []]

    st.markdown(f"#### {title}")
    st.caption(f"{start_date.isoformat()} ~ {end_date.isoformat()}")

    if period.get("empty"):
        st.warning("该段无数据。")
        if missing_days:
            st.caption(f"所选范围内均无入库数据（共 {len(missing_days)} 天）。")
        return

    df, missing_days = query_search_dataframe(start_date, end_date)
    if df.empty:
        st.warning("该段无数据。")
        return

    st.caption(
        f"按各{period.get('cell_hint', '活动+广告组+投放+匹配类型+客户搜索词+日期')}最新一批拼数。"
    )
    if missing_days:
        sample = "、".join(d.strftime("%Y-%m-%d") for d in missing_days[:10])
        suffix = f" 等共 {len(missing_days)} 天" if len(missing_days) > 10 else ""
        st.info(f"该段内有部分日期无数据：{sample}{suffix}")

    result = get_search_analysis(df)
    render_search_analysis_result(result, key_prefix=key_prefix)


def _render_history_search_share_period(period: dict, *, key_prefix: str, title: str) -> None:
    start_date = date.fromisoformat(period["start"])
    end_date = date.fromisoformat(period["end"])
    missing_days = [date.fromisoformat(d) for d in period.get("missing_days") or []]

    st.markdown(f"#### {title}")
    st.caption(f"{start_date.isoformat()} ~ {end_date.isoformat()}")

    if period.get("empty"):
        st.warning("该段无数据。")
        if missing_days:
            st.caption(f"所选范围内均无入库数据（共 {len(missing_days)} 天）。")
        return

    df, missing_days = query_search_share_dataframe(start_date, end_date)
    if df.empty:
        st.warning("该段无数据。")
        return

    st.caption(f"按各{period.get('cell_hint', '搜索词+日期+活动+广告组+投放+匹配类型')}最新一批拼数。")
    if missing_days:
        sample = "、".join(d.strftime("%Y-%m-%d") for d in missing_days[:10])
        suffix = f" 等共 {len(missing_days)} 天" if len(missing_days) > 10 else ""
        st.info(f"该段内有部分日期无数据：{sample}{suffix}")

    result = get_search_term_trend(df)
    render_search_term_trend_result(result, key_prefix=key_prefix)


def _render_history_product_sponsored_period(period: dict, *, key_prefix: str, title: str) -> None:
    start_date = date.fromisoformat(period["start"])
    end_date = date.fromisoformat(period["end"])
    missing_days = [date.fromisoformat(d) for d in period.get("missing_days") or []]

    st.markdown(f"#### {title}")
    st.caption(f"{start_date.isoformat()} ~ {end_date.isoformat()}")

    if period.get("empty"):
        st.warning("该段无数据。")
        if missing_days:
            st.caption(f"所选范围内均无入库数据（共 {len(missing_days)} 天）。")
        return

    df, missing_days = query_product_sponsored_dataframe(start_date, end_date)
    if df.empty:
        st.warning("该段无数据。")
        return

    st.caption(f"按各{period.get('cell_hint', '活动+广告组+广告ASIN+广告SKU+日期')}最新一批拼数。")
    if missing_days:
        sample = "、".join(d.strftime("%Y-%m-%d") for d in missing_days[:10])
        suffix = f" 等共 {len(missing_days)} 天" if len(missing_days) > 10 else ""
        st.info(f"该段内有部分日期无数据：{sample}{suffix}")

    result = get_product_sponsored_analysis(df)
    render_product_sponsored_analysis_result(result, key_prefix=key_prefix)


def _render_history_period(
    report: str,
    period: dict,
    *,
    key_prefix: str,
    title: str,
) -> None:
    if report == "budget":
        _render_history_budget_period(period, key_prefix=key_prefix, title=title)
    elif report == "placement":
        _render_history_placement_period(period, key_prefix=key_prefix, title=title)
    elif report == "keyword":
        _render_history_keyword_period(period, key_prefix=key_prefix, title=title)
    elif report == "search":
        _render_history_search_period(period, key_prefix=key_prefix, title=title)
    elif report == "product_sponsored":
        _render_history_product_sponsored_period(period, key_prefix=key_prefix, title=title)
    else:
        _render_history_search_share_period(period, key_prefix=key_prefix, title=title)

    start_date = date.fromisoformat(period["start"])
    end_date = date.fromisoformat(period["end"])
    render_ops_journal_readonly(start_date, end_date)


def _dual_filter_widget_keys(report: str, side: str) -> list[str]:
    """双时间段模式下各报表 multiselect 的 session_state key。"""
    prefix = f"history_{report}_{side}"
    if report == "budget":
        return [f"{prefix}_activity_filter"]
    if report == "placement":
        return [f"{prefix}_activity_filter", f"{prefix}_filter"]
    if report == "keyword":
        return [f"{prefix}_act", f"{prefix}_adg", f"{prefix}_kw", f"{prefix}_match_type"]
    if report == "search":
        return [
            f"{prefix}_act",
            f"{prefix}_adg",
            f"{prefix}_target",
            f"{prefix}_match_type",
            f"{prefix}_term",
        ]
    if report == "search_share":
        return [f"{prefix}_trend_term"]
    if report == "product_sponsored":
        return [f"{prefix}_asin", f"{prefix}_sku", f"{prefix}_act", f"{prefix}_adg"]
    return []


def _dual_filter_snapshot(report: str, side: str) -> dict:
    snapshot = {}
    for key in _dual_filter_widget_keys(report, side):
        val = st.session_state.get(key)
        if isinstance(val, list):
            snapshot[key] = list(val)
        else:
            snapshot[key] = val
    return snapshot


def _clear_dual_filter_sync_track(report: str | None = None) -> None:
    if report:
        st.session_state.pop(f"history_dual_last_a_{report}", None)
        return
    for key in list(st.session_state.keys()):
        if key.startswith("history_dual_last_a_"):
            st.session_state.pop(key, None)


def _maybe_sync_dual_filters_from_a(report: str) -> None:
    """
    A 列筛选变更时，将相同选项写入 B 列 widget state（默认跟随 A）。
    若仅改 B、A 未变，则保留 B 的自定义选择。
    """
    a_keys = _dual_filter_widget_keys(report, "a")
    b_keys = _dual_filter_widget_keys(report, "b")
    current_a = _dual_filter_snapshot(report, "a")
    track_key = f"history_dual_last_a_{report}"
    last_a = st.session_state.get(track_key)
    if last_a == current_a:
        return
    st.session_state[track_key] = current_a
    for a_key, b_key in zip(a_keys, b_keys):
        if a_key not in st.session_state:
            continue
        val = st.session_state[a_key]
        st.session_state[b_key] = list(val) if isinstance(val, list) else val


def _render_history_results(query_state: dict) -> None:
    normalized = _normalize_history_query(query_state)
    if not normalized:
        return

    report = normalized["report"]
    periods = normalized["periods"]
    label = REPORT_TYPE_LABELS.get(report, report)

    if normalized.get("mode") == "dual" and len(periods) >= 2:
        st.caption("双时间段：B 列筛选默认跟随 A；修改 A 后会重新同步，仍可在 B 列单独调整。")
        col_a, col_b = st.columns(2)
        with col_a:
            _render_history_period(
                report,
                periods[0],
                key_prefix=f"history_{report}_a",
                title=f"{label}分析 A",
            )
        _maybe_sync_dual_filters_from_a(report)
        with col_b:
            _render_history_period(
                report,
                periods[1],
                key_prefix=f"history_{report}_b",
                title=f"{label}分析 B",
            )
        return

    _render_history_period(
        report,
        periods[0],
        key_prefix=f"history_{report}",
        title=f"{label}分析结果",
    )


def _render_history_date_inputs(
    *,
    report_key: str,
    mode: str,
    today: date,
    default_start: date,
    default_b_start: date,
    default_b_end: date,
) -> tuple[bool, list[tuple[date, date]]]:
    prefix = f"history_{report_key}"
    if mode == "单时间段":
        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            start = st.date_input("开始日期", value=default_start, key=f"{prefix}_start_date")
        with col2:
            end = st.date_input("结束日期", value=today, key=f"{prefix}_end_date")
        with col3:
            st.write("")
            st.write("")
            run = st.button("生成分析", key=f"{prefix}_run_query", use_container_width=True)
        return run, [(start, end)]

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**时间段 A**")
        start_a = st.date_input("开始", value=default_start, key=f"{prefix}_dual_start_a")
        end_a = st.date_input("结束", value=today, key=f"{prefix}_dual_end_a")
    with col_b:
        st.markdown("**时间段 B**")
        start_b = st.date_input("开始", value=default_b_start, key=f"{prefix}_dual_start_b")
        end_b = st.date_input("结束", value=default_b_end, key=f"{prefix}_dual_end_b")
    _, btn_col, _ = st.columns([2, 1, 2])
    with btn_col:
        run = st.button("生成分析", key=f"{prefix}_run_query_dual", use_container_width=True)
    return run, [(start_a, end_a), (start_b, end_b)]


def _save_history_query(report: str, mode: str, ranges: list[tuple[date, date]]) -> bool:
    for i, (start, end) in enumerate(ranges):
        if start > end:
            label = f"时间段 {chr(65 + i)}" if mode == "dual" else "所选"
            st.error(f"{label}：开始日期不能晚于结束日期。")
            st.session_state.history_report_query = None
            return False

    periods = [_build_period_state(report, start, end) for start, end in ranges]
    st.session_state.history_report_query = {
        "mode": mode,
        "report": report,
        "periods": periods,
    }
    _clear_dual_filter_sync_track(report)
    return True


def render_history_query_tab() -> None:
    _init_session_upload_state()
    st.subheader("历史查询")
    st.caption(
        "从 SQLite 历史库按日期范围查询；拼数规则：各单元格取最新一批。"
        "手动分析 Tab 仍看当前会话上传。"
    )

    st.markdown("#### 已入库 upload 摘要")
    render_upload_summary_table(list_all_uploads(), key_prefix="history_summary", allow_delete=True)

    st.markdown("#### 查询条件")
    report_options = ["预算", "广告位", "投放词", "搜索词", "搜索词份额", "推广的商品"]
    selected_report = st.selectbox("报表类型", options=report_options, index=0, key="history_report_type")
    report_key = SUPPORTED_HISTORY_REPORTS.get(selected_report)
    if not report_key:
        st.info("该报表类型历史查询尚未支持。")
        return

    today = date.today()
    default_start = today - timedelta(days=7)
    default_b_start = today - timedelta(days=14)
    default_b_end = today - timedelta(days=8)

    query_mode = st.radio(
        "查询模式",
        options=["单时间段", "双时间段"],
        horizontal=True,
        key=f"history_query_mode_{report_key}",
    )
    mode_key = "dual" if query_mode == "双时间段" else "single"

    run_query, date_ranges = _render_history_date_inputs(
        report_key=report_key,
        mode=query_mode,
        today=today,
        default_start=default_start,
        default_b_start=default_b_start,
        default_b_end=default_b_end,
    )
    if run_query:
        _save_history_query(report_key, mode_key, date_ranges)

    query_state = st.session_state.get("history_report_query")
    if query_state is None:
        query_state = st.session_state.get("history_budget_query")
    normalized = _normalize_history_query(query_state)
    if normalized and normalized.get("report") == report_key:
        st.markdown("---")
        _render_history_results(normalized)


def render_end_session_dialog() -> None:
    from history.budget_storage import get_uploads_by_ids

    _init_session_upload_state()
    session_ids = list(st.session_state.session_upload_ids)

    st.markdown("---")
    with st.container(border=True):
        st.subheader("结束本次分析")
        st.caption("删除 upload **仅影响历史库**，不影响当前会话「手动分析」中的数据。")

        if not session_ids:
            st.info("本会话暂无写入历史库的 upload。")
            if st.button("关闭", key="end_session_close_empty"):
                st.session_state.show_end_session_dialog = False
                st.rerun()
            return

        uploads = get_uploads_by_ids(session_ids)
        options, id_by_label = _build_upload_select_options(uploads)

        selected_labels = st.multiselect(
            "勾选要删除的 upload（默认不删）",
            options=options,
            default=[],
            key="end_session_delete_choices",
        )

        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("删除所选并结束", key="end_session_delete_and_close"):
                to_delete = [id_by_label[label] for label in selected_labels]
                if to_delete:
                    _apply_upload_deletions(to_delete, uploads)
                    clear_ingest_fingerprints()
                st.session_state.show_end_session_dialog = False
                st.success("已删除所选 upload。" if to_delete else "已结束本次分析。")
                st.rerun()
        with c2:
            if st.button("不删除，结束", key="end_session_keep_and_close"):
                st.session_state.show_end_session_dialog = False
                st.rerun()
        with c3:
            if st.button("取消，继续分析", key="end_session_cancel"):
                st.session_state.show_end_session_dialog = False
                st.rerun()


def render_top_bar_end_session_button() -> None:
    _init_session_upload_state()
    _, col_btn = st.columns([6, 1])
    with col_btn:
        if st.button("结束本次分析", key="topbar_end_session", use_container_width=True):
            st.session_state.show_end_session_dialog = True
