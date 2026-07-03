"""登录用户切换时的 Streamlit 会话重置。

ensure_user_session 在 app 入口调用：user_id 变化时清空上传数据、分析结果、
AI Agent 缓存等，避免不同运营账号串数据。
"""
from __future__ import annotations

import streamlit as st

from data_df_store.data_store import store
from diagnosis.config import load_diagnosis_config
from history.database import invalidate_all_cached_turso_connections
from history.ui import (
    clear_all_upload_data_fingerprints,
    clear_ingest_fingerprints,
    invalidate_uploads_list_cache,
)


def reset_app_state_for_user(user_id: str) -> None:
    """切换登录用户时清空上传与分析会话状态（保留登录信息）。"""
    for key in (
        "df_budget",
        "df_placement",
        "df_keyword",
        "df_search",
        "df_search_share",
        "df_product_sponsored",
        "df_inventory",
        "df_business",
        "placement_analysis_result",
        "keyword_analysis_result",
        "search_analysis_result",
        "search_term_trend_result",
        "product_sponsored_analysis_result",
        "session_upload_ids",
        "history_report_query",
        "history_budget_query",
        "show_end_session_dialog",
        "user_history_store",
        "_history_store_user",
        "agent",
        "messages",
    ):
        st.session_state.pop(key, None)

    store.clear_all()
    clear_ingest_fingerprints()
    clear_all_upload_data_fingerprints()
    invalidate_uploads_list_cache()
    invalidate_all_cached_turso_connections()

    try:
        from model.factory import reset_model_caches

        reset_model_caches()
    except Exception:
        pass
    try:
        from Agent.agent_tool import clear_rag_service_cache

        clear_rag_service_cache()
    except Exception:
        pass

    st.session_state.diagnosis_config = load_diagnosis_config(user_id)
    st.session_state._diagnosis_config_fp = st.session_state.diagnosis_config.fingerprint()
    st.session_state.session_upload_ids = []
    st.session_state.show_end_session_dialog = False


def ensure_user_session(user_id: str) -> None:
    """首次进入或换用户时重置业务 session。"""
    if st.session_state.get("_active_user_id") != user_id:
        reset_app_state_for_user(user_id)
        st.session_state._active_user_id = user_id
