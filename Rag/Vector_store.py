import os
import pickle
import faiss
import numpy as np
from typing import List
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from utils.config_handler import chroma_conf
from model.factory import embed_model
from utils.path_tool import get_abs_path
from utils.file_handler import pdf_loader, txt_loader, listdir_with_allowed_type, get_file_md5_hex
from utils.logger_handler import logger
from utils.config_handler import prompts_conf
# 辅助函数：将 Document 列表转为向量
def _embed_documents(docs: List[Document]) -> np.ndarray:
    """将 Document 列表批量转换为嵌入向量数组。

    Args:
        docs (List[Document]): 待嵌入的文档列表。

    Returns:
        np.ndarray: float32 类型的向量数组。

    Raises:
        Exception: 嵌入模型调用失败。
    """
    texts = [doc.page_content for doc in docs]
    # embed_model 是 LangChain 的嵌入模型，它返回的是向量的列表
    vectors = embed_model.embed_documents(texts)
    return np.array(vectors).astype('float32')


class VectorStoreService:
    def __init__(self):
        """初始化 FAISS 向量库服务，尝试从磁盘加载已有索引。

        Returns:
            None

        Raises:
            None
        """
        self.index = None
        self.doc_store = {}  # id -> Document
        self.next_id = 0
        self.index_path = get_abs_path(chroma_conf["vector_path"])
        self.doc_store_path = get_abs_path(chroma_conf["doc_path"])

        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chroma_conf["chunk_size"],
            chunk_overlap=chroma_conf["chunk_overlap"],
            separators=chroma_conf["separators"],
            length_function=len,
        )

        # 尝试加载已有索引和文档存储
        if os.path.exists(self.index_path) and os.path.exists(self.doc_store_path):
            self.index = faiss.read_index(self.index_path)
            with open(self.doc_store_path, "rb") as f:
                self.doc_store = pickle.load(f)
            # 恢复 next_id
            if self.doc_store:
                self.next_id = max(self.doc_store.keys()) + 1
            logger.info("从磁盘加载 FAISS 索引和文档存储")

    def _add_documents(self, docs: List[Document]):
        """内部添加文档到索引和存储"""
        if not docs:
            return
        vectors = _embed_documents(docs)
        ids = np.arange(self.next_id, self.next_id + len(docs))
        if self.index is None:
            # 创建新的 FAISS 索引 (使用 L2 距离)
            dim = vectors.shape[1]
            base_index = faiss.IndexFlatL2(dim)
            self.index = faiss.IndexIDMap(base_index)
        self.index.add_with_ids(vectors, ids)
        for doc, idx in zip(docs, ids):
            self.doc_store[idx] = doc
        self.next_id += len(docs)



    def load_documents(self):

        """从 data 文件夹加载文档并构建向量库"""
        if self.index is not None:
            logger.info("向量库已存在，跳过加载")
            return

        """
        要计算文件的MD5做去重
        从数据文件夹内读取数据文件，转为向量存入向量库
        :return: None
        """

        def check_md5_hex(md5_for_check: str):
            """检查 MD5 值是否已存在于去重记录中。

            Args:
                md5_for_check (str): 待检查的 MD5 十六进制字符串。

            Returns:
                bool: 已存在返回 True，否则返回 False。

            Raises:
                None
            """
            md5_file = get_abs_path(chroma_conf["md5_hex_store"])
            if not os.path.exists(md5_file):
                open(md5_file, "w", encoding="utf-8").close()
                return False
            with open(md5_file, "r", encoding="utf-8") as f:
                for line in f.readlines():
                    if line.strip() == md5_for_check:
                        return True
            return False

        def save_md5_hex(md5_for_check: str):
            """将 MD5 值追加写入去重记录文件。

            Args:
                md5_for_check (str): 待保存的 MD5 十六进制字符串。

            Returns:
                None

            Raises:
                IOError: 文件写入失败。
            """
            with open(get_abs_path(chroma_conf["md5_hex_store"]), "a", encoding="utf-8") as f:
                f.write(md5_for_check + "\n")

        def get_file_documents(read_path: str):
            """根据文件后缀选择加载器并读取文档。

            Args:
                read_path (str): 文件路径。

            Returns:
                list[Document]: 解析后的文档列表；不支持的格式返回空列表。

            Raises:
                Exception: 文件读取或解析失败。
            """
            if read_path.endswith("txt"):
                return txt_loader(read_path)
            if read_path.endswith("pdf"):
                return pdf_loader(read_path)
            return []

        allowed_files_path = listdir_with_allowed_type(
            get_abs_path(chroma_conf["data_path"]),
            tuple(chroma_conf["allow_knowledge_file_type"])
        )

        for path in allowed_files_path:
            md5_hex = get_file_md5_hex(path)
            if check_md5_hex(md5_hex):
                logger.info(f"[加载知识库]{path} 内容已经存在知识库内，跳过")
                continue

            try:
                documents = get_file_documents(path)
                if not documents:
                    logger.warning(f"[加载知识库]{path} 内没有有效文本内容，跳过")
                    continue

                split_document = self.splitter.split_documents(documents)
                if not split_document:
                    logger.warning(f"[加载知识库]{path} 分片后没有有效文本内容，跳过")
                    continue

                self._add_documents(split_document)


                save_md5_hex(md5_hex)
                logger.info(f"[加载知识库]{path} 内容加载成功")
            except Exception as e:
                logger.error(f"[加载知识库]{path} 加载失败：{str(e)}", exc_info=True)
                continue

        # 在所有文件处理完成后，保存索引和文档存储
        if self.index is not None:
            faiss.write_index(self.index, self.index_path)
            with open(self.doc_store_path, "wb") as f:
                pickle.dump(self.doc_store, f)
            logger.info("FAISS 索引和文档存储已保存到磁盘")

    def get_retriever(self, k: int = None):
        """返回一个可调用的检索器"""
        if self.index is None:
            logger.info("向量库不存在，尝试从 data/ 自动构建索引…")
            self.load_documents()
        if self.index is None:
            raise ValueError("向量库为空，请先调用 load_documents() 加载文档")
        if k is None:
            k = chroma_conf.get("k", 4)

        def retriever_func(query: str):
            """根据查询向量检索最相似的文档。

            Args:
                query (str): 查询文本。

            Returns:
                list[Document]: 检索到的文档列表。

            Raises:
                None
            """
            # 将查询转为向量
            query_vec = embed_model.embed_query(query)
            query_np = np.array([query_vec]).astype('float32')
            distances, ids = self.index.search(query_np, k)
            results = []
            for idx, dist in zip(ids[0], distances[0]):
                if idx >= 0:
                    doc = self.doc_store.get(idx)
                    if doc:
                        results.append(doc)
            return results

        return retriever_func


if __name__ == '__main__':
    vs = VectorStoreService()

    vs.load_documents()

    retriever = vs.get_retriever()
    res = retriever("搜索词份额")
    for r in res:
        print(r.page_content)
        print("-" * 20)










