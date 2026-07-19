import os
import sys
from pathlib import Path
import dotenv


# verbose=True 会在找不到文件时发出警告
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from project_config import (
    BLOCKCHAIN_SPIDER_ROOT,
    TRACER_CONFIG_ROOT,
    TRACER_DATA_ROOT,
    TRACER_OUTPUT_ROOT,
    TRACER_REFERENCE_ROOT,
    TRACER_ROOT,
)

dotenv.load_dotenv(TRACER_CONFIG_ROOT / ".env", verbose=True)
# EVENT_NAME = "VulcanForged"
# EVENT_NAME = "Ronin"
# EVENT_NAME = "Li_Fi"
#EVENT_NAME = "Bybit"
EVENT_NAME = os.getenv("RISKTAGGER_EVENT_NAME", "HTX_&_Heco_Bridge")
#BASE_EVENT_NAME = EVENT_NAME.replace("_without_COT", "").replace("_without_memory", "").replace("_without_filter", "").replace("_without_reflection", "").replace("_without_COT2", "")
# 逻辑：只要遇到 _without，就切一刀，拿走左边的部分,with也是同理，但是要先拆分without再拆分with，避免事件名称中同时包含两者时处理出问题
BASE_EVENT_NAME = EVENT_NAME.split('_without')[0].split('_with')[0]
BASE_DIR = TRACER_ROOT
class Config:
    # ================= 项目基础路径配置 =================
    # 建议将此路径改为相对路径或通过环境变量获取
    BASE_DIR = TRACER_ROOT# tracer父目录
    # 数据存储结构
    # Directory layout: configured by project_config.py
    EVENT_NAME = EVENT_NAME
    BASE_EVENT_NAME = BASE_EVENT_NAME
    # 针对 raw_tx_data 的特殊处理：如果包含 without_COT/without_memory，则将其剔除
    DATA_DIR = TRACER_DATA_ROOT / EVENT_NAME / "data"
    DATA_LLM_DIR = TRACER_DATA_ROOT / EVENT_NAME
    SPIDER_DIR = BLOCKCHAIN_SPIDER_ROOT
    CONTRACT_CACHE_FILE = TRACER_OUTPUT_ROOT / "contract_check_cache.json"
    # 各类数据子目录
    PATHS = {
        "source_addr": DATA_DIR / "src_addr_token",      # 每一层的源地址 CSV
        "base_source_addr": TRACER_DATA_ROOT / BASE_EVENT_NAME / "data" / "src_addr_token", # 每一层的源地址 CSV 的基准版本（不包含 without_COT/without_memory 等后缀），从里面读取种子地址
        "raw_tx_data": TRACER_DATA_ROOT / BASE_EVENT_NAME / "data" / "blockscan_data",    # 爬虫抓取的原始交易数据
        "normal_addr_info": DATA_DIR / "all_data_normal",  # 判定为正常账户的存放路径
        "risktagger_hack": DATA_DIR / "RiskTagger_hack",   # 判定为洗钱账户的结果
        "reference": TRACER_REFERENCE_ROOT,# 参考账户，包括交易所等，所有事件共用
        "experiment": DATA_LLM_DIR / "Experiment", # 实验过程文件
        "llm_result": DATA_LLM_DIR / "LLM_result/llmResult", # LLM 推理结果文本
        "llm_input": DATA_LLM_DIR / "LLM_result/llmInput",   # LLM 输入的 JSON Context
        "mappings": DATA_DIR /  "mappings",                  # 地址标签映射文件等
        "memory_db": DATA_LLM_DIR / "llm_memory_db",        # 本地向量数据库存放路径
        "crosschain_data": DATA_DIR / "crosschain_data",   # 跨链桥数据存放路径
        "logs": DATA_LLM_DIR / "logs",  # 日志文件路径
        "source_report_path": DATA_LLM_DIR / "report",   # 最开始存放源地址等信息的报告路径
        "result": DATA_DIR / "result",                    # 最终结果存放路径
    }

    # ================= 爬虫配置 (BlockchainSpider) =================
    class Spider:
        # 从环境变量读取字符串，然后按逗号分割成列表
        _keys_str = os.getenv("SPIDER_API_KEYS", "")
        # 使用列表推导式去除空格并过滤空字符串
        API_KEYS = [k.strip() for k in _keys_str.split(",") if k.strip()]
        ENDPOINT = "https://api.etherscan.io/v2/api?chainid=1"
        STRATEGY = "BlockchainSpider.strategies.txs.Poison"
        _middlewares = [
            "BlockchainSpider.middlewares.txs.blockscan.ExternalTransferMiddleware",
            "BlockchainSpider.middlewares.txs.blockscan.InternalTransferMiddleware",
            "BlockchainSpider.middlewares.txs.blockscan.Token20TransferMiddleware"
        ]
        # 拼接成字符串
        TYPE = ",".join(_middlewares)
        MAX_WORKERS = 10  # 爬虫并发线程数
        TIMEOUT = 120      # 单个爬虫任务超时时间(秒)

    # ================= LLM 配置 =================
    #放入环境变量
    class LLM:
        API_KEY = os.getenv("OPENAI_API_KEY")
        MODEL_NAME = os.getenv("MODEL_NAME")
        BASE_URL = os.getenv("OPENAI_BASE_URL")
        # embedding模型的配置
        API_KEY_EMB = os.getenv("OPENAI_API_KEY_EMB")
        MODEL_NAME_EMB = os.getenv("MODEL_NAME_EMB")
        BASE_URL_EMB = os.getenv("OPENAI_BASE_URL_EMB")

        TEMPERATURE = 0.3
        MAX_TOKENS = 2000

    # ================= 过滤与分析阈值 =================
    class Filter:
        # Read event name again inside nested scope to avoid static-analysis issues
        # with referencing the outer Config class during class body evaluation.
        # 洗钱追踪时的金额阈值
        MIN_AMOUNT = 0.00
        # 每一跳地址下一层保留的最大地址数
        MAX_ADDRESSES_PER_HOP = 100#(bybit 12层开始限制,原本是100)
        # 下游账户超过多少的就直接舍弃（有不在标签库中的服务商的嫌疑）
        MAX_HOP = 70
        # 保留前 N% 的大额交易
        TOP_AMOUNT_RATIO = 1
        # 追踪资金比例
        COVERAGE_THRESHOLD = 1

        Trace_others = 0  # 是否追踪其他账户（如交易所热钱包等），1代表追踪，0代表不追踪
        CONTRACT_TRACE = 1 # 是否追踪合约账户，1代表追踪，0代表不追踪
        # 时间窗口，单位：秒 (默认 50 天)
        MAX_TIME_WINDOW = 50 * 24 * 3600
        # 起始时间戳
        _START_TIMESTAMP_BY_EVENT = {
            "Bybit": 1740067200,  # 2025-02-21
            "Bybit_without_COT": 1740067200,  # 2025-02-21
            # 在此处添加更多事件，例如：
            "Li_Fi": 1721059200,  #2024-07-16
            "Li_FI_without_COT": 1721059200,  # 2024-07-16
            "Li_FI_without_memory": 1721059200,  # 2024-07-16
            "Li_FI_without_filter": 1721059200,  # 2024-07-16
            "VulcanForged": 1639324800,  #2021-12-13
            "Harmony_Horizon": 1655913600,  #2022-6-23
            "Alphahomara": 1613145600,#2021-2-13
            "Nomad": 1659283200, #2022-8-1
            "Wazirx": 1721232000,   #2024-7-18
            "Ronin": 1647964800,   #2022-3-23
            "Ronin_without_COT": 1647964800,  # 2022-3-23
            "Ronin_without_memory": 1647964800,  # 2022-3-23
            "Ronin_without_filter": 1647964800,  # 2022-3-23
            "HTX_&_Heco_Bridge": 1700582400,   #2023-11-22
        }
        _DEFAULT_START_TIMESTAMP = 1721059200
        START_TIMESTAMP = (_START_TIMESTAMP_BY_EVENT.get(BASE_EVENT_NAME, _DEFAULT_START_TIMESTAMP))

        # 常见合约白名单 (USDT, mETH, stETH, cmETH, ETH等)
        CONTRACT_WHITELIST = {
            "0xdac17f958d2ee523a2206206994597c13d831ec7",  # USDT
            "0xd5f7838f5c461feff7fe49ea5ebaf7728bb0adfa",  # mETH
            "0xae7ab96520de3a18e5e111b5eaab095312d7fe84",  # stETH
            "0xe6829d9a7ee3040e1276fa75293bde931859e8fa",  # cmETH
            #"0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WEth很少在用户之间流动
            "0x0000000000000000000000000000000000000000",   # 0x0 ETH
            "0x6B175474E89094C44Da98b954EedeAC495271d0F",   #DAI
            "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",   #USDC
            "0x9534ad65fb398E27Ac8F4251dAe1780B989D136e",   #PYR
            # HTX_&_Heco_Bridge中增加的代币
            "0x0000000000085d4780B73119b644AE5ecd22b376", #TUSD
            "0x514910771AF9Ca656af840dff83E8264EcF986CA", #LINK
            "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984", #UNI
            "0x95aD61b0a150d79219dCF64E1E6Cc01f0B64C4cE", #SHIB
            "0x0316EB71485b0Ab14103307bf65a021042c6d380", #HBTC
        }

    # ================= 并行处理配置 =================
    class Concurrency:
        # 默认使用的 CPU 核心数，None 表示自动计算
        PROCESS_WORKERS = 16

    @staticmethod
    def ensure_dirs():
        """初始化时创建所有必要的目录"""
        for path in Config.PATHS.values():
            path.mkdir(parents=True, exist_ok=True)
