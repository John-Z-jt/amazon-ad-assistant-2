from __future__ import annotations

import os
from typing import Any

from auth.credentials_loader import _to_plain_dict
from auth.user_context import get_current_user_id


def _secrets_turso() -> dict | None:
    try:
        import streamlit as st

        turso = st.secrets.get("turso")
        if turso:
            return _to_plain_dict(turso)
    except Exception:
        pass
    return None


def turso_configured() -> bool:
    """是否已通过 Secrets / 环境变量启用 Turso（云端部署）。"""
    turso = _secrets_turso()
    if turso and turso.get("databases"):
        return True
    return bool(os.environ.get("TURSO_DATABASE_URL") and os.environ.get("TURSO_AUTH_TOKEN"))


def turso_http_base_url(url: str) -> str:
    """libsql://... → https://..."""
    url = str(url).strip().rstrip("/")
    if url.startswith("libsql://"):
        return "https://" + url[len("libsql://") :]
    if url.startswith("http://"):
        return "https://" + url[len("http://") :]
    if url.startswith("https://"):
        return url
    return "https://" + url


def turso_url_candidates(url: str) -> list[str]:
    """libsql-client 可尝试的 URL 形式。"""
    url = str(url).strip().rstrip("/")
    candidates = [url]
    if url.startswith("libsql://"):
        https_url = "https://" + url[len("libsql://") :]
        if https_url not in candidates:
            candidates.append(https_url)
    elif url.startswith("https://"):
        libsql_url = "libsql://" + url[len("https://") :]
        if libsql_url not in candidates:
            candidates.append(libsql_url)
    return candidates


def get_turso_credentials(user_id: str | None = None) -> tuple[str, str] | None:
    """返回当前用户的 (database_url, auth_token)。未配置时返回 None。"""
    if user_id is None:
        user_id = get_current_user_id()
    user_id = str(user_id).strip()

    turso = _secrets_turso()
    if turso:
        databases = _to_plain_dict(turso.get("databases", {}))
        tokens = _to_plain_dict(turso.get("tokens", {}))
        url = databases.get(user_id)
        token = tokens.get(user_id) or turso.get("auth_token")
        if url and token:
            return str(url).strip(), str(token).strip()

    url = os.environ.get("TURSO_DATABASE_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN")
    if url and token:
        return url.strip(), token.strip()

    return None
