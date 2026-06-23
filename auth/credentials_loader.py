from __future__ import annotations

import copy
import os
from typing import Any

import streamlit as st
import yaml

from utils.path_tool import get_abs_path


def _to_plain_dict(value: Any) -> Any:
    """将 Streamlit SecretDict / 嵌套结构转为普通 dict。"""
    if isinstance(value, dict):
        return {str(k): _to_plain_dict(v) for k, v in value.items()}
    if hasattr(value, "keys"):
        return {str(k): _to_plain_dict(value[k]) for k in value.keys()}
    return value


def _hash_password(pwd: str) -> str:
    if pwd.startswith("$2b$"):
        return pwd

    import streamlit_authenticator as stauth

    hasher = stauth.Hasher
    if hasattr(hasher, "hash"):
        try:
            return str(hasher.hash(pwd))
        except TypeError:
            pass

    try:
        return str(hasher([pwd]).generate()[0])
    except Exception:
        import bcrypt

        return bcrypt.hashpw(pwd.encode("utf-8"), bcrypt.genalt()).decode("utf-8")


def _hash_plain_passwords(credentials: dict) -> dict:
    creds = copy.deepcopy(credentials)
    usernames = creds.get("usernames") or {}
    for user in usernames.values():
        if not isinstance(user, dict):
            continue
        pwd = str(user.get("password", ""))
        if pwd:
            user["password"] = _hash_password(pwd)
    return creds


def _normalize_credentials(raw: dict) -> dict:
    creds = _to_plain_dict(raw)
    if "usernames" in creds:
        return creds
    # 兼容误把 usernames 内容平铺在 credentials 下的情况
    if creds and all(isinstance(v, dict) for v in creds.values()):
        return {"usernames": creds}
    raise ValueError("credentials 结构无效，需要 [credentials.usernames.xxx] 配置块")


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
    return _hash_plain_passwords(_normalize_credentials(credentials)), dict(cookie)


def _load_from_streamlit_secrets() -> tuple[dict, dict] | None:
    """读取 Streamlit Cloud Secrets 中的 credentials / cookie。"""
    try:
        if "credentials" not in st.secrets:
            return None
    except Exception:
        return None

    raw_credentials = _to_plain_dict(st.secrets["credentials"])
    cookie = _to_plain_dict(st.secrets.get("cookie", {}))
    credentials = _normalize_credentials(raw_credentials)
    if not credentials.get("usernames"):
        raise ValueError("Secrets 中 credentials.usernames 为空")

    return _hash_plain_passwords(credentials), cookie


def load_authenticator_config() -> tuple[dict, dict]:
    """
    读取登录配置。优先 config/credentials.yaml（本地），其次 st.secrets（上云）。
    返回 (credentials, cookie_config)。
    """
    loaded = _load_from_yaml()
    if loaded is not None:
        return loaded

    try:
        if "credentials" in st.secrets:
            loaded = _load_from_streamlit_secrets()
            if loaded is not None:
                return loaded
    except Exception as e:
        raise RuntimeError(f"读取 Streamlit Secrets 登录配置失败: {e}") from e

    raise FileNotFoundError(
        "未找到登录配置。请复制 config/credentials.yaml.example 为 config/credentials.yaml，"
        "或在 Streamlit Cloud Settings → Secrets 中配置 [credentials.usernames.*]。"
    )
