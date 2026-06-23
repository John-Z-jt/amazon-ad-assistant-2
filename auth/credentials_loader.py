from __future__ import annotations

import copy
import os

import streamlit as st
import yaml

from utils.path_tool import get_abs_path


def _hash_plain_passwords(credentials: dict) -> dict:
    import streamlit_authenticator as stauth
    creds = copy.deepcopy(credentials)
    for user in creds.get("usernames", {}).values():
        pwd = str(user.get("password", ""))
        if pwd and not pwd.startswith("$2b$"):
            user["password"] = stauth.Hasher.hash(pwd)
    return creds


def _load_from_yaml() -> tuple[dict, dict] | None:
    path = get_abs_path("config/credentials.yaml")
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    credentials = cfg.get("credentials")
    if not credentials:
        return None
    cookie = cfg.get("cookie", {})
    return _hash_plain_passwords(credentials), cookie


def _load_from_streamlit_secrets() -> tuple[dict, dict] | None:
    """读取 .streamlit/secrets.toml；无文件或缺少 credentials 时返回 None。"""
    try:
        if "credentials" not in st.secrets:
            return None
        credentials = dict(st.secrets["credentials"])
        cookie = dict(st.secrets.get("cookie", {}))
        return _hash_plain_passwords(credentials), cookie
    except Exception:
        return None


def load_authenticator_config() -> tuple[dict, dict]:
    """
    读取登录配置。优先 config/credentials.yaml（本地），其次 st.secrets（上云）。
    返回 (credentials, cookie_config)。
    """
    loaded = _load_from_yaml()
    if loaded is not None:
        return loaded

    loaded = _load_from_streamlit_secrets()
    if loaded is not None:
        return loaded

    raise FileNotFoundError(
        "未找到登录配置。请复制 config/credentials.yaml.example 为 config/credentials.yaml，"
        "或在 .streamlit/secrets.toml 中配置 credentials。"
    )
