import os
import hashlib
from utils.logger_handler import logger
from langchain_core.documents import Document
from langchain_community.document_loaders import PyPDFLoader, TextLoader


def get_file_md5_hex(file_path: str):
    """计算指定文件的 MD5 十六进制摘要值。

    Args:
        file_path (str): 待计算 MD5 的文件路径。

    Returns:
        str | None: 文件的 MD5 十六进制字符串；路径无效或计算失败时返回 None。

    Raises:
        None
    """
    if not os.path.exists(file_path):
        logger.error(f"[md5计算]文件{file_path}不存在")
        # 需要检查文件路径配置
        return None

    if not os.path.isfile(file_path):
        logger.error(f"[md5计算]路径{file_path}不是一个文件")
        return None

    md5_obj = hashlib.md5()

    chunk_size = 4096  # 4KB分片，避免文件过大爆内存
    try:
        with open(file_path,"rb") as f:
            chunk = f.read(chunk_size)
            while chunk:
                md5_obj.update(chunk)
                chunk = f.read(chunk_size)
            md5_hex = md5_obj.hexdigest()
            return md5_hex
    except Exception as e:
        logger.error(f"计算文件{file_path}md5失败，{str(e)}")
        return None

def listdir_with_allowed_type(file_path:str, allowed_types:tuple[str]):     # 返回文件夹内的文件列表（允许的文件后缀）
    """列出目录中符合指定后缀类型的文件。

    Args:
        file_path (str): 目标目录路径。
        allowed_types (tuple[str]): 允许的文件后缀名元组。

    Returns:
        list[str]: 符合条件的文件绝对路径列表；目录无效时返回空列表。

    Raises:
        None
    """
    if not os.path.isdir(file_path):
        logger.error(f"[listdir_with_allowed_type]{file_path}不是一个文件夹")
        return []

    files = []
    for f in os.listdir(file_path):
        if f.endswith(allowed_types):
            files.append(os.path.join(file_path,f))

    return files

def pdf_loader(file_path: str, passwd=None):
    """加载 PDF 文件并解析为 Document 列表。

    Args:
        file_path (str): PDF 文件路径。
        passwd: PDF 密码，默认为 None。

    Returns:
        list[Document]: 解析后的文档列表。

    Raises:
        Exception: PDF 读取或解析失败时由底层加载器抛出。
    """
    return PyPDFLoader(file_path,passwd).load()

def txt_loader(file_path: str):
    """加载 UTF-8 编码的文本文件并解析为 Document 列表。

    Args:
        file_path (str): 文本文件路径。

    Returns:
        list[Document]: 解析后的文档列表。

    Raises:
        Exception: 文件读取或解析失败时由底层加载器抛出。
    """
    return TextLoader(file_path, encoding = "utf-8").load()

















