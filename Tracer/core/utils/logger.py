import logging
import sys
from pathlib import Path
from config.settings import Config, EVENT_NAME


def setup_logger(name: str, log_file: Path = None, level=logging.INFO):
    """
    配置 Logger，支持同时输出到控制台和文件
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # 防止重复添加 handler
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - [%(levelname)s] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 控制台 Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件 Handler (如果指定)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger

# 预定义一个全局 logger，并指定日志文件路径（比如放在项目根目录的 logs 文件夹下）
log_path = Config.PATHS["logs"] / f"{EVENT_NAME}.log"
logger = setup_logger("RiskTagger", log_file=log_path)