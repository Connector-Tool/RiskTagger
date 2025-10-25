import subprocess
import os
import re
from typing import List, Optional, Tuple, Union
from  LLM_detection import llm_based_detect

# --------------------------
# 函数默认参数配置（直接修改此处值，可改变函数默认输入）
# --------------------------
# 1. 必选参数默认值（建议首次使用时先配置）
DEFAULT_SOURCE = "0x"  # 默认起始地址
DEFAULT_APIKEYS = ["X"]  # 默认API密钥（至少1个）

# 2. 可选参数默认值
#DEFAULT_ENDPOINT = "https://api.etherscan.io/api"  # 默认区块链 explorer 端点（Etherscan）
DEFAULT_ENDPOINT = "https://api.etherscan.io/v2/api?chainid=1"  # 默认以太坊主链 ID
DEFAULT_STRATEGY = "BlockchainSpider.strategies.txs.Poison"  # 默认遍历策略（BFS）
#DEFAULT_STRATEGY = "BlockchainSpider.strategies.txs.BFS"  # 默认遍历策略（BFS）

DEFAULT_ALLOWED_TOKENS = None  # 默认不限制代币（None 表示爬取所有代币）
DEFAULT_OUT = "G:/RiskTagger/blockscan_data"  # 默认数据输出目录
DEFAULT_OUT_FIELDS = [  # 默认输出字段（包含核心交易信息）
    "hash", "address_from", "address_to", "value",
    "timestamp", "block_number", "contract_address",
    "symbol", "decimals", "token_id"
]
DEFAULT_ENABLE = [  # 默认启用的中间件（ETH+ERC-20）
    "BlockchainSpider.middlewares.txs.blockscan.ExternalTransferMiddleware",
    "BlockchainSpider.middlewares.txs.blockscan.Token20TransferMiddleware"
]
DEFAULT_START_BLK = None  # 默认起始区块（None 表示从第一个区块开始）
DEFAULT_END_BLK = None  # 默认结束区块（None 表示到最新区块）
DEFAULT_MAX_PAGES = 1  # 默认每个中间件最大请求页数
DEFAULT_MAX_PAGE_SIZE = 1000  # 默认每页最大交易数（最大值10000）
DEFAULT_DEPTH = 1  # 默认爬取深度

DEFAULT_EVENTNAME = "bybit"  # 默认事件名称

def run_blockscan_spider(
        # 必选参数：使用上述默认值，可直接修改默认值或调用时覆盖
        source: str = DEFAULT_SOURCE,
        # 可选参数：使用上述默认值，无需每次调用传参
        apikeys: Union[str, List[str]] = DEFAULT_APIKEYS,
        endpoint: Optional[str] = DEFAULT_ENDPOINT,
        strategy: Optional[str] = DEFAULT_STRATEGY,
        allowed_tokens: Optional[Union[str, List[str]]] = DEFAULT_ALLOWED_TOKENS,
        out: Optional[str] = DEFAULT_OUT,
        out_fields: Optional[Union[str, List[str]]] = DEFAULT_OUT_FIELDS,
        enable: Optional[Union[str, List[str]]] = DEFAULT_ENABLE,
        start_blk: Optional[int] = DEFAULT_START_BLK,
        end_blk: Optional[int] = DEFAULT_END_BLK,
        max_pages: Optional[int] = DEFAULT_MAX_PAGES,
        max_page_size: Optional[int] = DEFAULT_MAX_PAGE_SIZE,
        depth:Optional[int] = DEFAULT_DEPTH,
        check_existing: bool = True # 是否检查已存在结果(LLM检测时不检查)
) -> bool:
    """
    调用 txs.blockscan 爬虫，收集指定地址的区块链交易数据（如 Etherscan 数据）。
    核心优势：默认参数在函数开头集中配置，修改默认值即可改变函数默认输入，无需重复传参。

    参数说明（若未特殊说明，默认使用函数开头的 DEFAULT_* 配置）：
    :param source: 起始地址（必填，默认值见 DEFAULT_SOURCE）
    :param apikeys: API 密钥（必填，默认值见 DEFAULT_APIKEYS，支持字符串/列表）
    :param endpoint: 爬虫 API 端点（可选，如 BSC 用 "https://api.bscscan.com/api"）
    :param strategy: 遍历策略（可选，支持 Poison/APPR/TTR 等）
    :param allowed_tokens: 允许的代币合约地址（可选，None 表示不限制）
    :param out: 输出目录（可选，默认自动创建）
    :param out_fields: 输出字段（可选，默认包含核心交易字段）
    :param enable: 启用的中间件（可选，默认爬取 ETH+ERC-20）
    :param start_blk: 起始区块号（可选，None 表示从首个区块开始）
    :param end_blk: 结束区块号（可选，None 表示到最新区块）
    :param max_pages: 每个中间件最大请求页数（可选）
    :param max_page_size: 每页最大交易数（可选，最大值10000）

    返回值：
    :return: 爬虫执行成功返回 True，失败返回 False
    """

    out = out + f"/{source}"  # 每个地址单独存放一个子目录
    # 目标目录不存在则创建，存在则直接读取里面的文件
    if not os.path.exists(out):
        os.makedirs(out, exist_ok=True)
        #print(f"ℹ️  提示：已自动创建输出目录 -> {os.path.abspath(out)}")
    target_addr = source  # 目标地址（与 source 保持一致，便于理解）
    # 如果存在则直接读取结果返回
    out_path = os.path.join(out, 'AccountTransferItem.csv')

    if os.path.exists(out_path):
        # 读取结果并返回
        # 判断文件中是否存在内容(除表头外)
        with open(out_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]
            if len(lines) <= 1:
                print(f"❌ 提示：文件 {os.path.abspath(out_path)} 仅包含表头或为空，可能爬虫执行失败，重新爬取")
                if not check_existing:
                    print(f"ℹ️  提示：已存在爬虫结果，但结果为空，直接读取 -> {os.path.abspath(out_path)}")
                    return True
            else:
                print(f"ℹ️  提示：已存在爬虫结果，直接读取 -> {os.path.abspath(out_path)}")
                return True
    else:
        print(f"ℹ️  提示：未发现已存在结果,开始爬取")
        #return ##测试修改
    # ------------------------
    # 1. 参数预处理与校验（确保符合爬虫格式）
    # --------------------------
    # 校验必填参数格式
    if not source.startswith("0x"):
        print(f"❌ 错误：起始地址 {source} 格式无效，需以 '0x' 开头")
        return False
    if not apikeys:
        print("❌ 错误：API 密钥不能为空，至少需配置1个（修改 DEFAULT_APIKEYS）")
        return False

    # 处理列表参数（转为爬虫支持的逗号分隔字符串）
    def format_param(param: Optional[Union[str, List[str]]]) -> Optional[str]:
        if isinstance(param, list):
            return ",".join(param)
        return param  # 字符串/None 直接返回

    # 转换所有列表型参数
    apikeys_str = format_param(apikeys)
    allowed_tokens_str = format_param(allowed_tokens)
    out_fields_str = format_param(out_fields)
    enable_str = format_param(enable)

    # --------------------------
    # 2. 构建爬虫执行命令
    # --------------------------
    # 基础命令（scrapy crawl 固定格式）
    base_cmd = ["scrapy", "crawl", "txs.blockscan"]
    # 必选参数（source/apikeys 等）
    cmd_params = [
        #"-a", f"chainid=1",  # 以太坊主链 ID
        "-a", f"source={source}",
        "-a", f"apikeys={apikeys_str}",
        "-a", f"endpoint={endpoint}",
        "-a", f"strategy={strategy}",
        "-a", f"out={out}",
        "-a", f"max_pages={max_pages}",
        "-a", f"max_page_size={max_page_size}",
        #"-a", f"depth={depth}"  # 设置为0表示只爬取当前地址
    ]
    # 可选参数（仅当值不为 None 时添加）
    if allowed_tokens_str:
        cmd_params.extend(["-a", f"allowed_tokens={allowed_tokens_str}"])
    if out_fields_str:
        cmd_params.extend(["-a", f"out_fields={out_fields_str}"])
    if enable_str:
        cmd_params.extend(["-a", f"enable={enable_str}"])
    if start_blk is not None:
        cmd_params.extend(["-a", f"start_blk={start_blk}"])
    if end_blk is not None:
        cmd_params.extend(["-a", f"end_blk={end_blk}"])
    if depth is not None:
        cmd_params.extend(["-a", f"depth={depth}"])

    # 组合完整命令（转为字符串便于打印）
    full_cmd = base_cmd + cmd_params
    print(f"\nℹ️  即将执行爬虫命令：\n{' '.join(full_cmd)}\n")

    os.chdir('D:/FORGE2/BlockchainSpider-master/')  # 改成自己BlockchainSpider的相关路径
    # --------------------------
    # 3. 执行爬虫并捕获结果 (带超时控制)
    # --------------------------
    try:
            # 设置超时时间（例如 60 秒）
        timeout_seconds = 60  # 👈 可以根据需要修改这个时间
        # 执行命令，实时捕获输出（合并 stdout/stderr，方便排查错误）
        process = subprocess.run(
            full_cmd,
            check=True,  # 命令返回非0时抛出异常
            # stdout=subprocess.PIPE,
            # stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            timeout=timeout_seconds  # ⚠️ 添加超时限制
        )
        # 打印成功日志
        # print("✅ 爬虫执行成功！输出信息：")
        # print("-" * 50)
        # print(process.stdout)
        # print("-" * 50)
        print(f"ℹ️  交易数据已保存至：{os.path.abspath(out)}")
        return True
    except subprocess.TimeoutExpired as e:
        # ⚠️ 命令执行超时，被中断
        print(f"⚠️  爬虫执行超时（>{timeout_seconds}秒），已自动中断。")
        #print("-" * 50)
        #print("已捕获部分输出：")
        #print(e.output)  # 输出超时前已产生的内容
        #print("-" * 50)
        # ✅ 继续执行后续代码（不报错）
        print(f"ℹ️  爬取部分数据，继续处理后续逻辑...")
        return True  # 或根据业务决定返回值
    except subprocess.CalledProcessError as e:
        # 命令执行失败（如 API 密钥无效、爬虫不存在）
        print("❌ 爬虫执行失败！错误信息：")
        print("-" * 50)
        print(e.stdout)
        print("-" * 50)
        print(f"❌ 失败原因参考：1. API 密钥无效/超限；2. 地址格式错误；3. 中间件路径错误")
        return False

    except Exception as e:
        # 其他异常（如 Scrapy 未安装、权限不足）
        print(f"❌ 爬虫调用异常：{str(e)}")
        print("❌ 异常原因参考：1. 未安装 Scrapy（执行 pip install scrapy）；2. 输出目录无写入权限；3. 爬虫未注册")
        return False

def LLM_Addr_Detect(source: str = DEFAULT_SOURCE,eventname: str = DEFAULT_EVENTNAME) -> Tuple[bool,str]:
    #如果存在LLM输出的txt文件，则直接读取结果返回
    label = "unknown"

    result_dir = "G:/RiskTagger/LLM_result"
    out_path = os.path.join(result_dir, source + '.txt')
    if os.path.exists(out_path):
        print(f"ℹ️  提示：已存在 LLM 结果，直接读取 -> {os.path.abspath(out_path)}")
        with open(out_path, 'r', encoding='utf-8') as f:
            response_text = f.read()
        # 只提取“明确结论：”之后的内容
            start = response_text.find("suspicion_level")
        if start == -1:
            label = "-1_unknown"
        else:
            # 截取结论后的一小段（比如100字符），避免扫描全文
            conclusion_part = response_text[start:start + 35]
            #print(f"conclusion_part: {conclusion_part}")
            if "High" in conclusion_part or "high" in conclusion_part:
                label = "high-ML"
            elif "Medium" in conclusion_part or "medium" in conclusion_part:
                label = "mid-ML"
            elif "Low" in conclusion_part or "low" in conclusion_part:
                label = "low-ML"
            elif "No Suspicion" in conclusion_part or "no suspicion" in conclusion_part or "No suspicion" in conclusion_part:
                label = "No Suspicion"
        if label != "unknown" and label != "No Suspicion":
            return [True,label]
        else:
            return [False,label]
    
  
    # 直接调用（使用函数开头 DEFAULT_* 配置的默认值）
    #print("ℹ️  开始执行 blockscan 爬虫（使用默认参数配置）...")
    #success = run_blockscan_spider(source,check_existing=True) # LLM检测时不检查已存在结果,不重新爬取
    success = True
    # 根据执行结果提示
    if success:
        print("\n🎉 爬虫任务全部完成！")
    else:
        print("\n⚠️  爬虫任务失败，请检查默认参数配置或错误日志。")
        return [False,label]

    return llm_based_detect(source,eventname=eventname)


