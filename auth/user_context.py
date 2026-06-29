"""多用户隔离：ContextVar + session_state 提供当前 user_id 与数据目录。"""
from __future__ import annotations

from contextvars import ContextVar
from pathlib import Path

import streamlit as st

from utils.config_handler import agent_conf
from utils.path_tool import get_abs_path

_user_id_ctx: ContextVar[str | None] = ContextVar("user_id", default=None)


def bind_user_id(user_id: str) -> None:
    """在当前线程绑定 user_id（Agent 工具线程内使用）。"""
    _user_id_ctx.set(str(user_id).strip())


def set_current_user_id(user_id: str) -> None:
    """登录成功后写入 session，并绑定主线程 user_id。"""
    user_id = str(user_id).strip()
    st.session_state.user_id = user_id
    bind_user_id(user_id)


def get_current_user_id() -> str:
    """当前登录运营的用户 id。优先读线程 context，其次 session_state。"""
    ctx_user = _user_id_ctx.get()
    if ctx_user:
        return ctx_user

    user_id = st.session_state.get("user_id") or st.session_state.get("username")
    if user_id:
        return str(user_id).strip()

    raise RuntimeError("未登录，无法获取 user_id")


def get_user_data_dir(user_id: str | None = None) -> Path:
    """user_dict/{user_id}/，自动创建目录。"""
    if user_id is None:
        user_id = get_current_user_id()
    root = Path(get_abs_path(agent_conf["session_id_dir_path"]))
    path = root / user_id
    path.mkdir(parents=True, exist_ok=True)
    return path
