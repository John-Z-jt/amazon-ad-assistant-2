"""侧边栏：百炼 API Key 与对话模型配置。"""
from __future__ import annotations

import streamlit as st

from auth.user_settings import (
    CHAT_MODEL_PRESETS,
    CUSTOM_MODEL_OPTION,
    dashscope_key_source,
    get_user_chat_model_name,
    get_user_dashscope_api_key,
    invalidate_runtime_after_settings_change,
    load_user_settings,
    mask_secret,
    preset_model_ids,
    save_user_settings,
)


def render_user_settings_panel() -> None:
    """侧边栏「AI 配置（百炼）」：保存/清除 Key 与对话模型。"""
    with st.sidebar.expander("⚙️ AI 配置（百炼）", expanded=False):
        st.caption(
            "仅 **AI 助手** 需要配置。手动分析、历史查询、诊断不依赖 API Key。"
            "Embedding 仍使用系统默认，无需填写。"
        )

        settings = load_user_settings()
        saved_key = get_user_dashscope_api_key()
        saved_model = get_user_chat_model_name()

        st.markdown("**API Key**")
        if saved_key:
            st.caption(f"已保存：{mask_secret(saved_key)}")
        elif dashscope_key_source() == "global":
            st.caption("当前使用管理员配置的全局 Key。")
        else:
            st.caption("未配置 Key，无法使用 AI 助手。")

        dashscope_input = st.text_input(
            "DashScope API Key",
            value="",
            type="password",
            placeholder="sk-...（留空表示不修改已保存的 Key）",
            key="user_settings_dashscope_input",
        )

        st.markdown("**对话模型**")
        preset_ids = preset_model_ids()
        if saved_model and saved_model not in preset_ids:
            default_select = CUSTOM_MODEL_OPTION
        else:
            default_select = saved_model or preset_ids[0]

        select_options = [label for _, label in CHAT_MODEL_PRESETS] + ["自定义（手动填写）"]
        id_by_label = {label: mid for mid, label in CHAT_MODEL_PRESETS}
        id_by_label["自定义（手动填写）"] = CUSTOM_MODEL_OPTION

        label_by_id = {mid: label for mid, label in CHAT_MODEL_PRESETS}
        default_label = (
            "自定义（手动填写）"
            if default_select == CUSTOM_MODEL_OPTION
            else label_by_id.get(default_select, select_options[0])
        )
        default_index = select_options.index(default_label) if default_label in select_options else 0

        chosen_label = st.selectbox(
            "选择模型",
            options=select_options,
            index=default_index,
            key="user_settings_model_select",
        )
        chosen_id = id_by_label[chosen_label]

        custom_model = ""
        if chosen_id == CUSTOM_MODEL_OPTION:
            custom_model = st.text_input(
                "自定义模型 ID",
                value=saved_model if saved_model and saved_model not in preset_ids else "",
                placeholder="如 deepseek-v4-flash",
                key="user_settings_custom_model",
            )

        if st.button("保存 AI 配置", key="user_settings_save", use_container_width=True, type="primary"):
            new_settings = dict(settings)
            key_to_save = dashscope_input.strip() or saved_key
            if not key_to_save and dashscope_key_source() != "global":
                st.warning("请填写 API Key，或请管理员在 Secrets 中配置全局 Key。")
            else:
                if key_to_save:
                    new_settings["dashscope_api_key"] = key_to_save
                if chosen_id == CUSTOM_MODEL_OPTION:
                    model_name = custom_model.strip()
                    if not model_name:
                        st.warning("请选择预设模型，或填写自定义模型 ID。")
                        return
                    new_settings["chat_model_name"] = model_name
                else:
                    new_settings["chat_model_name"] = chosen_id
                save_user_settings(new_settings)
                invalidate_runtime_after_settings_change()
                st.success("已保存 AI 配置。")
                st.rerun()

        c1, c2 = st.columns(2)
        with c1:
            if st.button("清除 Key", key="user_settings_clear_key", use_container_width=True):
                new_settings = dict(settings)
                new_settings.pop("dashscope_api_key", None)
                save_user_settings(new_settings)
                invalidate_runtime_after_settings_change()
                st.info("已清除本人 API Key。")
                st.rerun()
        with c2:
            if st.button("恢复默认模型", key="user_settings_clear_model", use_container_width=True):
                new_settings = dict(settings)
                new_settings.pop("chat_model_name", None)
                save_user_settings(new_settings)
                invalidate_runtime_after_settings_change()
                st.info("已恢复默认对话模型。")
                st.rerun()

        st.caption(
            "[获取百炼 API Key](https://help.aliyun.com/zh/model-studio/get-api-key) · "
            "模型 ID 以百炼控制台为准。"
        )
