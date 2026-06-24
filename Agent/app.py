# 临时将当前文件所在目录加入 sys.path，以便能导入 utils（因为此时还没添加根目录）
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.path_tool import get_project_root

project_root = get_project_root()
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import streamlit as st

st.set_page_config(layout="wide")

from utils.env_bootstrap import bootstrap_env_from_secrets

bootstrap_env_from_secrets()

import tempfile
import time
import io

import pandas as pd

from user_history_store import FileHistoryStore
from data_df_store.data_store import store
from react_agent import ReactAgent
from ad_analyzers.budget_analyzer import analyze_budget
from ad_analyzers.placement_analyzer import analyze_placement, clean_placement_data, get_placement_analysis
from ad_analyzers.keyword_analyzer import clean_keyword_report, analyze_keyword,analyze_keyword_cross_activities,get_keyword_analysis
from ad_analyzers.search_analyzer import clean_search_report, analyze_search,get_search_analysis
from ad_analyzers.search_term_trend import clean_search_share_report, analyze_search_term_trend,get_search_term_trend
from ad_analyzers.product_sponserd_analyzer import (
    clean_product_sponsored_report,
    analyze_product_sponsored,
    get_product_sponsored_analysis,
)
from report_processors._csv_loader import read_report_file
from report_processors.inventory_processor import load_inventory_data
from report_processors.business_processor import load_business_data
from diagnosis.linkage import refresh_linkage_indexes
from diagnosis.recalc import maybe_recalc_on_config_change, recalc_diagnosis_pipelines
from diagnosis.ui import (
    render_budget_diagnosis_panel,
    render_placement_diagnosis_panel,
    render_keyword_diagnosis_panel,
    render_search_diagnosis_panel,
    render_diagnosis_config_sidebar,
    get_budget_diagnosis_status_caption,
    get_placement_diagnosis_status_caption,
    get_keyword_diagnosis_status_caption,
    get_search_diagnosis_status_caption,
)
from history.ui import (
    clear_budget_ingest_fingerprint,
    clear_placement_ingest_fingerprint,
    clear_keyword_ingest_fingerprint,
    clear_search_ingest_fingerprint,
    clear_search_share_ingest_fingerprint,
    clear_product_sponsored_ingest_fingerprint,
    maybe_ingest_budget_upload,
    maybe_ingest_placement_upload,
    maybe_ingest_keyword_upload,
    maybe_ingest_search_upload,
    maybe_ingest_search_share_upload,
    maybe_ingest_product_sponsored_upload,
    render_end_session_dialog,
    render_history_query_tab,
    render_top_bar_end_session_button,
)
from history.ops_journal_ui import render_ops_journal_tab
from auth.login import require_login
from auth.session_reset import ensure_user_session


authenticator, user_id = require_login()
ensure_user_session(user_id)

if "user_history_store" not in st.session_state:
    st.session_state.user_history_store = FileHistoryStore(user_id)

st.title("亚马逊广告诊断助手")
render_top_bar_end_session_button()
if st.session_state.get("show_end_session_dialog"):
    render_end_session_dialog()

# 初始化session_state
if "agent" not in st.session_state:
    st.session_state.agent = ReactAgent()  # 实例化你的Agent
if "messages" not in st.session_state:
    st.session_state.messages = []
if "df_budget" not in st.session_state:
    st.session_state.df_budget = None
if "df_placement" not in st.session_state:
    st.session_state.df_placement = None
if "df_keyword" not in st.session_state:
    st.session_state.df_keyword = None
if "df_search" not in st.session_state:
    st.session_state.df_search = None
if "df_search_share" not in st.session_state:
    st.session_state.df_search_share = None
if "df_product_sponsored" not in st.session_state:
    st.session_state.df_product_sponsored = None
if "df_inventory" not in st.session_state:
    st.session_state.df_inventory = None
if "df_business" not in st.session_state:
    st.session_state.df_business = None
if "_diagnosis_config_fp" not in st.session_state:
    st.session_state._diagnosis_config_fp = st.session_state.diagnosis_config.fingerprint()
if "session_upload_ids" not in st.session_state:
    st.session_state.session_upload_ids = []
if "show_end_session_dialog" not in st.session_state:
    st.session_state.show_end_session_dialog = False


st.info("💡 提示：刷新页面后需要重新上传文件。请先上传所有需要的报表。")

REPORT_FILE_TYPES = ["csv", "xlsx"]

with st.sidebar:
    authenticator.logout("退出登录", "sidebar")
    st.caption(f"当前用户：**{user_id}**")
    st.header("上传广告报表")
    budget_file = st.file_uploader("预算报表 (CSV / Excel)", type=REPORT_FILE_TYPES)
    placement_file = st.file_uploader("广告活动广告位 (CSV / Excel)", type=REPORT_FILE_TYPES)
    keyword_file = st.file_uploader("投放词报表 (CSV / Excel)", type=REPORT_FILE_TYPES)
    search_file = st.file_uploader("搜索词报表 (CSV / Excel)", type=REPORT_FILE_TYPES)
    search_share_file = st.file_uploader("搜索词份额报告 (CSV / Excel)", type=REPORT_FILE_TYPES)
    product_report_file = st.file_uploader("推广的商品报告 (CSV / Excel)", type=REPORT_FILE_TYPES)

    st.header("上传业务/库存报表")
    business_file = st.file_uploader("业务报表 (CSV / Excel)", type=REPORT_FILE_TYPES)
    inventory_file = st.file_uploader("FBA 库存报表 (CSV / Excel)", type=REPORT_FILE_TYPES)

    current_config = render_diagnosis_config_sidebar()
    maybe_recalc_on_config_change(current_config, user_id)


def render_full_dataframe_preview(df: pd.DataFrame, label: str) -> None:
    """预览 DataFrame，保留并展示全部列。"""
    st.caption(f"{label}：{len(df)} 行 × {len(df.columns)} 列（全部展示，可横向滚动）")
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_order=df.columns.tolist(),
    )


@st.cache_data
def load_report_file(uploaded_file):
    """读取上传的 CSV 或 xlsx 报表。"""
    if uploaded_file is None:
        return None
    filename = getattr(uploaded_file, "name", None)
    try:
        return read_report_file(uploaded_file, "报表", filename=filename)
    except ValueError as e:
        st.error(str(e))
        return None
    except Exception:
        st.error("无法读取文件，请确认格式为 CSV 或 xlsx。")
        return None


if budget_file is None:
    clear_budget_ingest_fingerprint()
else:
    df = load_report_file(budget_file)
    if df is not None:
        store.set("budget", df)
        st.session_state.df_budget = df
        try:
            upload_id = maybe_ingest_budget_upload(
                df,
                source_filename=budget_file.name or "budget.csv",
                file_content=budget_file.getvalue(),
            )
            if upload_id is not None:
                st.sidebar.success("预算已写入历史库。")
        except ValueError as e:
            st.sidebar.warning(f"预算历史入库跳过：{e}")
        except Exception as e:
            st.sidebar.error(f"预算历史入库失败：{e}")
        recalc_diagnosis_pipelines(st.session_state.diagnosis_config, user_id)

if placement_file is None:
    clear_placement_ingest_fingerprint()
else:
    df = load_report_file(placement_file)
    if df is not None:
        df_clean = clean_placement_data(df)
        store.set("placement", df_clean)
        st.session_state.df_placement = df_clean
        result = get_placement_analysis(df_clean)
        st.session_state.placement_analysis_result = result
        store.set("placement_analysis_result", result)
        try:
            upload_id = maybe_ingest_placement_upload(
                df,
                source_filename=placement_file.name or "placement.csv",
                file_content=placement_file.getvalue(),
            )
            if upload_id is not None:
                st.sidebar.success("广告位已写入历史库。")
        except ValueError as e:
            st.sidebar.warning(f"广告位历史入库跳过：{e}")
        except Exception as e:
            st.sidebar.error(f"广告位历史入库失败：{e}")
        recalc_diagnosis_pipelines(st.session_state.diagnosis_config, user_id)

if keyword_file is None:
    clear_keyword_ingest_fingerprint()
else:
    df = load_report_file(keyword_file)
    if df is not None:
        df_keyword_clean = clean_keyword_report(df)
        st.session_state.df_keyword = df_keyword_clean
        store.set("keyword", df_keyword_clean)
        # 预计算投放词分析结果
        result = get_keyword_analysis(df_keyword_clean)
        st.session_state.keyword_analysis_result = result
        store.set("keyword_analysis_result", result)
        try:
            upload_id = maybe_ingest_keyword_upload(
                df,
                source_filename=keyword_file.name or "keyword.csv",
                file_content=keyword_file.getvalue(),
            )
            if upload_id is not None:
                st.sidebar.success("投放词已写入历史库。")
        except ValueError as e:
            st.sidebar.warning(f"投放词历史入库跳过：{e}")
        except Exception as e:
            st.sidebar.error(f"投放词历史入库失败：{e}")
        recalc_diagnosis_pipelines(st.session_state.diagnosis_config, user_id)

if search_file is None:
    clear_search_ingest_fingerprint()
else:
    df = load_report_file(search_file)
    if df is not None:
        df_search_clean = clean_search_report(df)
        st.session_state.df_search = df_search_clean
        store.set("search", df_search_clean)   # 如果后续 Agent 需要，可以存入 store
        # 预计算搜索词分析结果
        result = get_search_analysis(df_search_clean)
        st.session_state.search_analysis_result = result
        store.set("search_analysis_result", result)
        try:
            upload_id = maybe_ingest_search_upload(
                df,
                source_filename=search_file.name or "search.csv",
                file_content=search_file.getvalue(),
            )
            if upload_id is not None:
                st.sidebar.success("搜索词已写入历史库。")
        except ValueError as e:
            st.sidebar.warning(f"搜索词历史入库跳过：{e}")
        except Exception as e:
            st.sidebar.error(f"搜索词历史入库失败：{e}")
        recalc_diagnosis_pipelines(st.session_state.diagnosis_config, user_id)

if search_share_file is None:
    clear_search_share_ingest_fingerprint()
else:
    df = load_report_file(search_share_file)
    if df is not None:
        df_clean = clean_search_share_report(df)
        st.session_state.df_search_share = df_clean
        store.set("search_share", df_clean)
        # 预计算搜索词趋势分析结果
        if not df_clean.empty:
            result = get_search_term_trend(df_clean)
            st.session_state.search_term_trend_result = result
            store.set("search_term_trend_result", result)
        try:
            upload_id = maybe_ingest_search_share_upload(
                df,
                source_filename=search_share_file.name or "search_share.csv",
                file_content=search_share_file.getvalue(),
            )
            if upload_id is not None:
                st.sidebar.success("搜索词份额已写入历史库。")
        except ValueError as e:
            st.sidebar.warning(f"搜索词份额历史入库跳过：{e}")
        except Exception as e:
            st.sidebar.error(f"搜索词份额历史入库失败：{e}")

if product_report_file is None:
    clear_product_sponsored_ingest_fingerprint()
else:
    df = load_report_file(product_report_file)
    if df is not None:
        df_product_clean = clean_product_sponsored_report(df)
        st.session_state.df_product_sponsored = df_product_clean
        store.set("product_sponsored", df_product_clean)
        result = get_product_sponsored_analysis(df_product_clean)
        st.session_state.product_sponsored_analysis_result = result
        store.set("product_sponsored_analysis_result", result)
        refresh_linkage_indexes(product_df=df_product_clean)
        if store.get("budget") is not None or store.get("placement") is not None:
            recalc_diagnosis_pipelines(st.session_state.diagnosis_config, user_id)
        try:
            upload_id = maybe_ingest_product_sponsored_upload(
                df,
                source_filename=product_report_file.name or "product_sponsored.csv",
                file_content=product_report_file.getvalue(),
            )
            if upload_id is not None:
                st.sidebar.success("推广的商品已写入历史库。")
        except ValueError as e:
            st.sidebar.warning(f"推广的商品历史入库跳过：{e}")
        except Exception as e:
            st.sidebar.error(f"推广的商品历史入库失败：{e}")

if inventory_file is not None:
    try:
        inventory_df = load_inventory_data(inventory_file, filename=inventory_file.name)
        st.session_state.df_inventory = inventory_df
        store.set("inventory", inventory_df)
        refresh_linkage_indexes(inventory_df=inventory_df)
        if store.get("budget") is not None or store.get("placement") is not None:
            recalc_diagnosis_pipelines(st.session_state.diagnosis_config, user_id)
    except ValueError as e:
        st.error(str(e))
    except Exception as e:
        st.error(f"库存报表加载失败：{e}")

if business_file is not None:
    try:
        business_df = load_business_data(business_file, filename=business_file.name)
        st.session_state.df_business = business_df
        store.set("business", business_df)
        refresh_linkage_indexes(business_df=business_df)
        if store.get("budget") is not None or store.get("placement") is not None:
            recalc_diagnosis_pipelines(st.session_state.diagnosis_config, user_id)
    except ValueError as e:
        st.error(str(e))
    except Exception as e:
        st.error(f"业务报表加载失败：{e}")

# 标签页
tab1, tab_history, tab_ops, tab2 = st.tabs(
    ["📊 手动分析", "📅 历史查询", "📝 运营日志", "🤖 AI助手"]
)

with tab_history:
    render_history_query_tab()

with tab_ops:
    render_ops_journal_tab()

with tab1:
    if st.session_state.df_budget is not None:
        status_line = get_budget_diagnosis_status_caption(store)
        if status_line:
            st.caption(status_line)
        with st.expander("📊 预算分析", expanded=False):
            analyze_budget(st.session_state.df_budget)
        with st.expander("🩺 预算诊断", expanded=False):
            render_budget_diagnosis_panel(store)
    else:
        st.info("请先在左侧上传预算报表")

    if st.session_state.df_placement is not None:
        placement_status = get_placement_diagnosis_status_caption(store)
        if placement_status:
            st.caption(placement_status)
        with st.expander("📈 广告位分析", expanded=False):
            analyze_placement(st.session_state.df_placement)
        with st.expander("🩺 广告位诊断", expanded=False):
            render_placement_diagnosis_panel(store)
    else:
        st.info("请先在左侧上传广告活动_广告位报表")

    if st.session_state.get('df_keyword') is not None:
        kw_status = get_keyword_diagnosis_status_caption(store)
        if kw_status:
            st.caption(kw_status)
        with st.expander("🔑 投放词分析", expanded=False):
            analyze_keyword(st.session_state.df_keyword)
            st.markdown("---")
            analyze_keyword_cross_activities(st.session_state.df_keyword)
        with st.expander("🩺 投放词分诊", expanded=False):
            render_keyword_diagnosis_panel(store)
    else:
        st.info("请先在左侧上传投放词报表")

    # 搜索词分析（添加外层折叠）
    if st.session_state.get('df_search') is not None:
        search_status = get_search_diagnosis_status_caption(store)
        if search_status:
            st.caption(search_status)
        with st.expander("🔍 搜索词分析", expanded=False):
            analyze_search(st.session_state.df_search)
        with st.expander("🩺 搜索词诊断", expanded=False):
            render_search_diagnosis_panel(store)
    else:
        st.info("请先在左侧上传搜索词报表")

    # 搜索词趋势分析（基于搜索词份额报告）
    if st.session_state.get('df_search_share') is not None:
        with st.expander("📈 搜索词趋势分析（每日排名与份额）", expanded=False):
            analyze_search_term_trend(st.session_state.df_search_share)
    else:
        st.info("请先在左侧上传搜索词份额报告")

    if st.session_state.get("df_product_sponsored") is not None:
        with st.expander("📦 推广的商品分析", expanded=False):
            analyze_product_sponsored(st.session_state.df_product_sponsored)
    else:
        st.info("请先在左侧上传推广的商品报告")

    if st.session_state.get("df_inventory") is not None:
        with st.expander("📋 库存数据预览", expanded=False):
            render_full_dataframe_preview(
                st.session_state.df_inventory,
                "库存报表（已清洗）",
            )
    else:
        st.info("请先在左侧上传 FBA 库存报表（可选，用于后续预算与库存联动）")

    if st.session_state.get("df_business") is not None:
        with st.expander("📈 业务报表数据预览", expanded=False):
            render_full_dataframe_preview(
                st.session_state.df_business,
                "业务报表（已清洗）",
            )
    else:
        st.info("请先在左侧上传业务报表（可选，用于后续广告与 ASIN 联动）")


with tab2:
    chat_store = st.session_state.user_history_store
    for message in chat_store.get_history():
        st.chat_message(message["role"]).write(message["content"])

    prompt = st.chat_input()

    if prompt:
        st.chat_message("user").write(prompt)
        history = chat_store.get_history()

        message_with_historys = history + [{"role": "user", "content": prompt}]
        response_message = []
        with st.spinner("智能客服思考中..."):
            res_stream = st.session_state["agent"].execute_stream(
                message_with_historys, user_id=user_id
            )

            def capture(generate, cache_list):
                for chunk in generate:
                    cache_list.append(chunk)
                    for char in chunk:
                        time.sleep(0.01)
                        yield char

            st.chat_message("assistant").write_stream(capture(res_stream, response_message))
            chat_store.add_message(role="user", content=prompt)
            chat_store.add_message(role="assistant", content=response_message[-1])
        st.rerun()

        

