from __future__ import annotations

import streamlit as st

from data_df_store.data_store import store
from ad_analyzers.budget_analyzer import get_budget_analysis
from diagnosis.budget_diagnosis import run_budget_diagnosis
from diagnosis.config import DiagnosisConfig
from diagnosis.placement_diagnosis import run_placement_diagnosis
from diagnosis.keyword_diagnosis import run_keyword_diagnosis
from diagnosis.search_diagnosis import run_search_diagnosis


def recalc_budget_pipeline(config: DiagnosisConfig) -> None:
    """按当前 config 重算预算分析与预算诊断。"""
    budget_df = store.get("budget")
    if budget_df is not None:
        budget_result = get_budget_analysis(
            budget_df,
            threshold=config.budget_usage_threshold,
            consecutive_days=config.consecutive_days,
        )
        store.set("budget_analysis_result", budget_result)
        st.session_state.budget_analysis_result = budget_result
    else:
        store.set("budget_analysis_result", None)
        st.session_state.budget_analysis_result = None

    diagnosis_result = run_budget_diagnosis(config)
    store.set("budget_diagnosis_result", diagnosis_result.to_dict())
    st.session_state.budget_diagnosis_result = diagnosis_result.to_dict()


from auth.user_context import get_current_user_id


def recalc_placement_pipeline(config: DiagnosisConfig, user_id: str | None = None) -> None:
    """按当前 config 重算广告位诊断。"""
    if user_id is None:
        user_id = get_current_user_id()
    placement_result = run_placement_diagnosis(config, user_id=user_id)
    store.set("placement_diagnosis_result", placement_result.to_dict())
    st.session_state.placement_diagnosis_result = placement_result.to_dict()


def recalc_keyword_pipeline(config: DiagnosisConfig) -> None:
    """按当前 config 重算投放词分诊。"""
    keyword_result = run_keyword_diagnosis(config)
    store.set("keyword_diagnosis_result", keyword_result.to_dict())
    st.session_state.keyword_diagnosis_result = keyword_result.to_dict()


def recalc_search_pipeline(config: DiagnosisConfig) -> None:
    """按当前 config 重算搜索词诊断。"""
    search_result = run_search_diagnosis(config)
    store.set("search_diagnosis_result", search_result.to_dict())
    st.session_state.search_diagnosis_result = search_result.to_dict()


def recalc_diagnosis_pipelines(config: DiagnosisConfig, user_id: str | None = None) -> None:
    """统一重算预算 + 广告位 + 投放词分诊 + 搜索词诊断，并同步 config。"""
    if user_id is None:
        user_id = get_current_user_id()
    store.set("diagnosis_config", config.to_dict())
    recalc_budget_pipeline(config)
    recalc_placement_pipeline(config, user_id=user_id)
    recalc_keyword_pipeline(config)
    recalc_search_pipeline(config)


def maybe_recalc_on_config_change(config: DiagnosisConfig, user_id: str | None = None) -> None:
    """config 指纹变化时触发重算。"""
    if user_id is None:
        user_id = get_current_user_id()
    fp = config.fingerprint()
    if st.session_state.get("_diagnosis_config_fp") == fp:
        return
    st.session_state["_diagnosis_config_fp"] = fp
    st.session_state.diagnosis_config = config
    recalc_diagnosis_pipelines(config, user_id=user_id)
