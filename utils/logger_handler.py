import logging
from utils.path_tool import get_abs_path
import os
from datetime import datetime

# 日志保存的根目录
LOG_ROOT = get_abs_path("logs")

# 确保日志的目录存在
os.makedirs(LOG_ROOT, exist_ok = True)

# 日志的格式配置
DEFAULT_LOG_FORMAT = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')

def get_logger(
    name: str = "agent",
    console_level: int = logging.INFO,
    file_level: int = logging.DEBUG,
    log_file = None
):
    """创建并配置带有控制台与文件输出的 Logger。

    Args:
        name (str): Logger 名称，默认为 agent。
        console_level (int): 控制台日志级别，默认为 INFO。
        file_level (int): 文件日志级别，默认为 DEBUG。
        log_file: 日志文件路径；为 None 时按日期自动生成。

    Returns:
        logging.Logger: 配置完成的 Logger 实例。

    Raises:
        None
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # 避免重复添加Handler
    if logger.handlers:
        return logger

    # 控制台Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(DEFAULT_LOG_FORMAT)

    logger.addHandler(console_handler)

    # 文件Handler
    if not log_file:
        log_file = os.path.join(LOG_ROOT, f"{name}_{datetime.now().strftime('%Y%m%d')}.log")

    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(file_level)
    file_handler.setFormatter(DEFAULT_LOG_FORMAT)

    logger.addHandler(file_handler)

    return logger

logger = get_logger()   # 使用默认参数创建全局 logger

