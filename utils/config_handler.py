"""
yaml
k: v
"""
import yaml
from utils.path_tool import get_abs_path

def load_rag_config(config_path: str = get_abs_path("config/rag.yml"), encoding: str = "utf-8"):
    """加载 RAG 相关 YAML 配置。

    Args:
        config_path (str): 配置文件路径，默认为 config/rag.yml。
        encoding (str): 文件编码，默认为 utf-8。

    Returns:
        dict: 解析后的配置字典。

    Raises:
        FileNotFoundError: 配置文件不存在。
        yaml.YAMLError: YAML 解析失败。
    """
    with open(config_path,"r",encoding = encoding) as f:
        return yaml.load(f,Loader = yaml.FullLoader)

def load_chroma_config(config_path: str = get_abs_path("config/chroma.yml"), encoding: str = "utf-8"):
    """加载向量库相关 YAML 配置。

    Args:
        config_path (str): 配置文件路径，默认为 config/chroma.yml。
        encoding (str): 文件编码，默认为 utf-8。

    Returns:
        dict: 解析后的配置字典。

    Raises:
        FileNotFoundError: 配置文件不存在。
        yaml.YAMLError: YAML 解析失败。
    """
    with open(config_path,"r",encoding = encoding) as f:
        return yaml.load(f,Loader = yaml.FullLoader)

def load_prompts_config(config_path: str = get_abs_path("config/prompts.yml"), encoding: str = "utf-8"):
    """加载提示词路径相关 YAML 配置。

    Args:
        config_path (str): 配置文件路径，默认为 config/prompts.yml。
        encoding (str): 文件编码，默认为 utf-8。

    Returns:
        dict: 解析后的配置字典。

    Raises:
        FileNotFoundError: 配置文件不存在。
        yaml.YAMLError: YAML 解析失败。
    """
    with open(config_path,"r",encoding = encoding) as f:
        return yaml.load(f,Loader =yaml.FullLoader)

def load_agent_config(config_path: str = get_abs_path("config/agent.yml"), encoding: str = "utf-8"):
    """加载 Agent 相关 YAML 配置。

    Args:
        config_path (str): 配置文件路径，默认为 config/agent.yml。
        encoding (str): 文件编码，默认为 utf-8。

    Returns:
        dict: 解析后的配置字典。

    Raises:
        FileNotFoundError: 配置文件不存在。
        yaml.YAMLError: YAML 解析失败。
    """
    with open(config_path,"r",encoding = encoding) as f:
        return yaml.load(f,Loader =yaml.FullLoader)

rag_conf = load_rag_config()
chroma_conf = load_chroma_config()
prompts_conf = load_prompts_config()
agent_conf = load_agent_config()

if __name__ == '__main__':
    print(prompts_conf["main_prompt_path"])



