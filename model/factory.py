"""百炼（DashScope）对话模型与 Embedding 工厂。

Key / 模型名解析优先级（见 auth.user_settings）：
    用户自配 > Streamlit Secrets / 环境变量 > config/rag.yml 默认。

实例通过 lru_cache 缓存；用户修改 AI 配置或切换登录用户时需调用 reset_model_caches()。
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Optional

from langchain_core.embeddings import Embeddings
from langchain_community.chat_models.tongyi import BaseChatModel, ChatTongyi
from langchain_community.embeddings import DashScopeEmbeddings

from utils.config_handler import rag_conf


def _dashscope_api_key() -> str | None:
    """读取当前生效的百炼 API Key（用户自配或全局）。"""
    try:
        from auth.user_settings import resolve_dashscope_api_key

        key = resolve_dashscope_api_key()
        if key:
            return key
    except Exception:
        pass
    env_key = os.environ.get("DASHSCOPE_API_KEY")
    return str(env_key).strip() if env_key else None


def _chat_model_name() -> str:
    """读取当前生效的对话模型名。"""
    try:
        from auth.user_settings import resolve_chat_model_name

        return resolve_chat_model_name()
    except Exception:
        return str(rag_conf.get("chat_model_name") or "deepseek-v4-flash")


class BaseModelFactory(ABC):
    """LangChain 模型实例工厂基类。"""

    @abstractmethod
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        pass


class ChatModelFactory(BaseModelFactory):
    """创建 ChatTongyi 对话模型。"""

    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        kwargs = {"model": _chat_model_name()}
        api_key = _dashscope_api_key()
        if api_key:
            kwargs["dashscope_api_key"] = api_key
        return ChatTongyi(**kwargs)


class EmbeddingsFactory(BaseModelFactory):
    """创建 DashScopeEmbeddings（模型名来自 rag.yml，Key 来源同对话模型）。"""

    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        kwargs = {"model": rag_conf["embedding_model_name"]}
        api_key = _dashscope_api_key()
        if api_key:
            kwargs["dashscope_api_key"] = api_key
        return DashScopeEmbeddings(**kwargs)


@lru_cache(maxsize=1)
def get_chat_model() -> BaseChatModel:
    """获取缓存的单例对话模型。"""
    return ChatModelFactory().generator()


@lru_cache(maxsize=1)
def get_embed_model() -> Embeddings:
    """获取缓存的单例 Embedding 模型。"""
    return EmbeddingsFactory().generator()


def reset_model_caches() -> None:
    """清空模型缓存（用户改 Key/模型或切换账号后调用）。"""
    get_chat_model.cache_clear()
    get_embed_model.cache_clear()


def __getattr__(name: str):
    """兼容旧代码：from model.factory import chat_model / embed_model。"""
    if name == "chat_model":
        return get_chat_model()
    if name == "embed_model":
        return get_embed_model()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
