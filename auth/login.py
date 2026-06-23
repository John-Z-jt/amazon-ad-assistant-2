from __future__ import annotations

import streamlit as st
import streamlit_authenticator as stauth

from auth.credentials_loader import load_authenticator_config


def render_login() -> stauth.Authenticate | None:
    """
    渲染登录页。成功登录后写入 st.session_state.user_id。
    返回 authenticator 供侧边栏 logout 使用；配置缺失时返回 None。
    """
    try:
        credentials, cookie = load_authenticator_config()
    except (FileNotFoundError, RuntimeError) as e:
        st.error(str(e))
        return None

    authenticator = stauth.Authenticate(
        credentials,
        cookie.get("name", "amazon_ad_auth"),
        cookie.get("key", "change-this-cookie-sign-key-in-production"),
        cookie.get("expiry_days", 30),
    )

    authenticator.login(location="main")

    auth_status = st.session_state.get("authentication_status")
    if auth_status is True:
        username = st.session_state.get("username")
        if username:
            from auth.user_context import set_current_user_id

            set_current_user_id(str(username).strip())
        return authenticator

    if auth_status is False:
        st.error("用户名或密码不正确")
    else:
        st.info("请登录后使用广告诊断助手")
    return None


def require_login() -> tuple[stauth.Authenticate, str]:
    """未登录则 st.stop()；已登录返回 (authenticator, user_id)。"""
    authenticator = render_login()
    if authenticator is None or not st.session_state.get("authentication_status"):
        st.stop()
    user_id = st.session_state.user_id
    return authenticator, user_id
