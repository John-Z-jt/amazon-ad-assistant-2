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
    key = os.environ.get("DASHSCOPE_API_KEY")
    return str(key).strip() if key else None


class BaseModelFactory(ABC):
    @abstractmethod
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        pass


class ChatModelFactory(BaseModelFactory):
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        kwargs = {"model": rag_conf["chat_model_name"]}
        api_key = _dashscope_api_key()
        if api_key:
            kwargs["dashscope_api_key"] = api_key
        return ChatTongyi(**kwargs)


class EmbeddingsFactory(BaseModelFactory):
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        kwargs = {"model": rag_conf["embedding_model_name"]}
        api_key = _dashscope_api_key()
        if api_key:
            kwargs["dashscope_api_key"] = api_key
        return DashScopeEmbeddings(**kwargs)


@lru_cache(maxsize=1)
def get_chat_model() -> BaseChatModel:
    return ChatModelFactory().generator()


@lru_cache(maxsize=1)
def get_embed_model() -> Embeddings:
    return EmbeddingsFactory().generator()


def __getattr__(name: str):
    if name == "chat_model":
        return get_chat_model()
    if name == "embed_model":
        return get_embed_model()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
