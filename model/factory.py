from abc import ABC, abstractmethod
from typing import Optional
from langchain_core.embeddings import Embeddings
from langchain_community.chat_models.tongyi import BaseChatModel
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.chat_models.tongyi import ChatTongyi
from utils.config_handler import rag_conf


class BaseModelFactory(ABC):
    @abstractmethod
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        """生成 LangChain 模型实例。

        Returns:
            Optional[Embeddings | BaseChatModel]: 聊天模型或嵌入模型实例。

        Raises:
            NotImplementedError: 子类未实现此方法。
        """
        pass


class ChatModelFactory(BaseModelFactory):
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        """创建通义千问聊天模型实例。

        Returns:
            Optional[Embeddings | BaseChatModel]: ChatTongyi 聊天模型实例。

        Raises:
            None
        """
        return ChatTongyi(model=rag_conf["chat_model_name"])


class EmbeddingsFactory(BaseModelFactory):
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        """创建 DashScope 嵌入模型实例。

        Returns:
            Optional[Embeddings | BaseChatModel]: DashScopeEmbeddings 嵌入模型实例。

        Raises:
            None
        """
        return DashScopeEmbeddings(model=rag_conf["embedding_model_name"])


chat_model = ChatModelFactory().generator()
embed_model = EmbeddingsFactory().generator()
