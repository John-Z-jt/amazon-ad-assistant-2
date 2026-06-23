from __future__ import annotations

import os


def bootstrap_env_from_secrets() -> None:
    """将 Streamlit Secrets 中的 API Key 注入 os.environ（Cloud 部署用）。"""
    try:
        import streamlit as st

        dashscope_key = st.secrets.get("DASHSCOPE_API_KEY")
        if dashscope_key:
            os.environ.setdefault("DASHSCOPE_API_KEY", str(dashscope_key))
    except Exception:
        pass

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        pass
