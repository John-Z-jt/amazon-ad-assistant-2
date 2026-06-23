"""
总结服务类：用户提问，搜索参考资料，将提问和参考资料提交给模型，让模型总结回复
"""
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from Rag.Vector_store import VectorStoreService
from utils.prompt_loader import load_rag_prompts
from langchain_core.prompts import PromptTemplate
from model.factory import chat_model


def print_prompt(prompt):
    """打印 Prompt 模板内容并原样返回。

    Args:
        prompt: LangChain Prompt 对象。

    Returns:
        prompt: 传入的 Prompt 对象。

    Raises:
        None
    """
    print("="*20)
    print(prompt.to_string())
    return prompt



class RagSummarizeService(object):
    def __init__(self):
        """初始化 RAG 总结服务，加载向量库与提示词链。

        Returns:
            None

        Raises:
            None
        """
        self.vector_store = VectorStoreService()
        self.retriever = self.vector_store.get_retriever()
        self.prompt_text = load_rag_prompts()
        self.prompt_template = PromptTemplate.from_template(self.prompt_text)
        self.model = chat_model
        self.chain = self._init_chain()

    def _init_chain(self):
        """构建提示词、模型与输出解析器的处理链。

        Returns:
            Runnable: 可执行的 LangChain 处理链。

        Raises:
            None
        """
        chain = self.prompt_template |self.model | StrOutputParser()
        return chain

    def retriever_docs(self, query: str) -> list[Document]:
        """根据查询检索相关参考文档。

        Args:
            query (str): 用户查询文本。

        Returns:
            list[Document]: 检索到的文档列表。

        Raises:
            None
        """
        return self.retriever(query)

    def rag_summarize(self, query: str) -> str:

        """检索参考资料并生成总结回复。

        Args:
            query (str): 用户提问。

        Returns:
            str: 模型生成的总结文本。

        Raises:
            Exception: 检索或模型调用失败。
        """
        context_docs = self.retriever_docs(query)

        context = ""
        counter = 0
        for doc in context_docs:
            counter += 1
            context += f"【参考资料{counter}】: 参考资料：{doc.page_content} | 参考元数据：{doc.metadata}\n\n"

        return self.chain.invoke(
            {
                "input": query,
                "context": context,
            }
        )



if __name__ == '__main__':
    rag = RagSummarizeService()
    print(rag.rag_summarize("搜索词份额"))



