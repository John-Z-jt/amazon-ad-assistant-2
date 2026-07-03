"""按用户保存百炼 API Key 与对话模型（user_dict/{user_id}/user_settings.json）。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from auth.user_context import get_current_user_id, get_user_data_dir
from utils.config_handler import rag_conf

_SETTINGS_FILENAME = "user_settings.json"

CHAT_MODEL_PRESETS: list[tuple[str, str]] = [
    ("deepseek-v4-flash", "DeepSeek V4 Flash（默认，快、省）"),
    ("deepseek-v3", "DeepSeek V3"),
    ("deepseek-r1", "DeepSeek R1（推理）"),
    ("qwen-max", "Qwen Max"),
    ("qwen-plus", "Qwen Plus"),
    ("qwen-turbo", "Qwen Turbo（更快更省）"),
]

CUSTOM_MODEL_OPTION = "__custom__"


def _settings_path(user_id: str | None = None) -> Path:
    return get_user_data_dir(user_id) / _SETTINGS_FILENAME


def load_user_settings(user_id: str | None = None) -> dict[str, Any]:
    path = _settings_path(user_id)
    if not path.is_file():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_user_settings(settings: dict[str, Any], user_id: str | None = None) -> None:
    path = _settings_path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def _clean_str(val: Any) -> str:
    return str(val or "").strip()


def mask_secret(value: str | None, *, visible_tail: int = 4) -> str:
    s = _clean_str(value)
    if not s:
        return ""
    if len(s) <= visible_tail + 3:
        return "***"
    return f"***{s[-visible_tail:]}"


def get_user_dashscope_api_key(user_id: str | None = None) -> str | None:
    key = _clean_str(load_user_settings(user_id).get("dashscope_api_key"))
    return key or None


def get_user_chat_model_name(user_id: str | None = None) -> str | None:
    name = _clean_str(load_user_settings(user_id).get("chat_model_name"))
    return name or None


def resolve_dashscope_api_key(user_id: str | None = None) -> str | None:
    """用户自配 Key > Secrets / 环境变量全局 Key。"""
    user_key = get_user_dashscope_api_key(user_id)
    if user_key:
        return user_key
    import os

    env_key = _clean_str(os.environ.get("DASHSCOPE_API_KEY"))
    return env_key or None


def resolve_chat_model_name(user_id: str | None = None) -> str:
    """用户自配模型名 > config/rag.yml 默认。"""
    user_model = get_user_chat_model_name(user_id)
    if user_model:
        return user_model
    return str(rag_conf.get("chat_model_name") or "deepseek-v4-flash")


def user_has_dashscope_key(user_id: str | None = None) -> bool:
    return bool(resolve_dashscope_api_key(user_id))


def dashscope_key_source(user_id: str | None = None) -> str:
    if get_user_dashscope_api_key(user_id):
        return "user"
    import os

    if _clean_str(os.environ.get("DASHSCOPE_API_KEY")):
        return "global"
    return "none"


def preset_model_ids() -> list[str]:
    return [model_id for model_id, _ in CHAT_MODEL_PRESETS]


def chat_model_label(model_id: str) -> str:
    for mid, label in CHAT_MODEL_PRESETS:
        if mid == model_id:
            return label
    return model_id


def invalidate_runtime_after_settings_change() -> None:
    from model.factory import reset_model_caches

    reset_model_caches()
    try:
        import streamlit as st

        st.session_state.pop("agent", None)
    except Exception:
        pass
    try:
        from Agent.agent_tool import clear_rag_service_cache

        clear_rag_service_cache()
    except Exception:
        pass
