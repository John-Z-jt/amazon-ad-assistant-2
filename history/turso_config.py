from __future__ import annotations

import os

from auth.user_context import get_current_user_id


def _secrets_turso() -> dict | None:
    try:
        import streamlit as st

        turso = st.secrets.get("turso")
        if turso:
            return dict(turso)
    except Exception:
        pass
    return None


def turso_configured() -> bool:
    """是否已通过 Secrets / 环境变量启用 Turso（云端部署）。"""
    turso = _secrets_turso()
    if turso and turso.get("databases"):
        return True
    return bool(os.environ.get("TURSO_DATABASE_URL") and os.environ.get("TURSO_AUTH_TOKEN"))


def get_turso_credentials(user_id: str | None = None) -> tuple[str, str] | None:
    """返回当前用户的 (database_url, auth_token)。未配置时返回 None。"""
    if user_id is None:
        user_id = get_current_user_id()
    user_id = str(user_id).strip()

    turso = _secrets_turso()
    if turso:
        databases = dict(turso.get("databases", {}))
        tokens = dict(turso.get("tokens", {}))
        url = databases.get(user_id)
        token = tokens.get(user_id) or turso.get("auth_token")
        if url and token:
            return str(url).strip(), str(token).strip()

    url = os.environ.get("TURSO_DATABASE_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN")
    if url and token:
        return url.strip(), token.strip()

    return None
