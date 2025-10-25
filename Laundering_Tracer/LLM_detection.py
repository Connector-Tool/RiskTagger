

# 2.0在文件中增加地址映射功能,并优化读取已爬取文件时的代码
# 该文件增加一些统计性特征，方便大模型理解
import csv
import json
from datetime import datetime
from typing import List, Dict, Set
from collections import defaultdict,OrderedDict
# 1. 安装依赖：pip install openai （若使用其他模型，替换为对应 SDK，如 qianfan-sdk）
from openai import OpenAI
import os
from os.path import join
import statistics
import sys


# --------------------------
# 配置项（根据实际情况修改）
# --------------------------
# 保存爬虫数据的 CSV 文件路径（本地文件，确保路径正确）
CSV_FILE_PATH = "G:/RiskTagger/all_data_token" 
# 大模型 API 配置（以 qwen 为例，其他模型需调整）
OPENAI_API_KEY = "XX"  # 替换为你的 API Key
MODEL_NAME = "qwen3-max"
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


TARGET_ADDRESS = None  # 可以手动提前指定

def check_contract_address(row: Dict) -> bool:
    """检查合约地址是否在白名单中，若在则返回 true，反之返回 false（跳过该交易）"""
    # 白名单集合（包含常见合约地址）
    #转化为小写
    whitelist = {"0xdac17f958d2ee523a2206206994597c13d831ec7",  # USDT
                    "0xd5f7838f5c461feff7fe49ea5ebaf7728bb0adfa",  # mETH
                    "0xae7ab96520de3a18e5e111b5eaab095312d7fe84",  # stETH
                    "0xe6829d9a7ee3040e1276fa75293bde931859e8fa",  # cmETH  
                    "0x0000000000000000000000000000000000000000"   # 0x0 ETH
                }
    contract_address = row["contract_address"].strip().lower()
    
    if contract_address and contract_address in whitelist:
        return True  # 在白名单中，保留该交易
    else:
        # print(f"过滤交易，合约地址不在白名单中: {contract_address}")
        return False  # 不在白名单中，过滤该交易


# --------------------------
# 1. 读取 CSV 交易数据
# --------------------------
def read_blockchain_csv(file_path: str) -> List[Dict]:
    """读取 CSV 文件，返回结构化的交易数据列表"""
    transactions = []
    # 打开 CSV 文件（encoding 适配中文/特殊字符，errors 忽略不可读字符）
    with open(file_path, mode="r", encoding="utf-8", errors="ignore") as f:
        # 用 csv.DictReader 自动将表头作为字典键
        csv_reader = csv.DictReader(f)
        # 遍历每一行交易数据，转换数据类型并添加到列表
        for row in csv_reader:
            if row["value"] == '0':
                continue  # 跳过零值交易
            # 检查合约地址是否在白名单中
            if check_contract_address(row) is False:
                continue 
            # 转换数值类型（原始 CSV 读取的是字符串，需转为int/float）
            processed_row = {
                "address_from": row["address_from"].strip(),  # 转出地址
                "address_to": row["address_to"].strip(),  # 转入地址
                "block_number": int(row["block_number"]),  # 区块号
                "contract_address": row["contract_address"].strip(),  # 合约地址
                "decimals": int(row["decimals"]),  # 代币小数位
                "hash": row["hash"].strip(),  # 交易哈希
                "symbol": row["symbol"].strip(),  # 代币符号
                "timestamp": int(row["timestamp"]),  # 时间戳
                "token_id": row["token_id"].strip() if row["token_id"] else "",  # NFT 代币ID（可为空）
                "value": int(row["value"])  # 原始金额（未格式化）
            }
            transactions.append(processed_row)
    print(f"成功读取 CSV 文件，共 {len(transactions)} 条交易数据")
    return transactions


# --------------------------
# 2. 数据清洗与标准化（提升大模型理解效率）
# --------------------------
def format_token_amount(original_value: int, decimals: int) -> str:
    """将原始代币金额（如 20000000000000000000000000）转为可读格式（如 20000.0 HACKER）"""
    if decimals == 0:
        return f"{original_value}"
    # 按小数位转换（避免科学计数法，保留6位小数方便阅读）
    readable_amount = original_value / (10 ** decimals)
    return f"{readable_amount:,.6f}"


def format_time(timestamp: int) -> str:
    """将时间戳（如 1740158423）转为可读日期（如 2024-01-22 12:00:23）"""
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


#下面的两个函数用于保存和加载地址映射表，保证一个事件的地址映射表唯一，并保存在本地便于事后复盘

# 映射表缓存（可选：避免重复读磁盘）
_MAPPING_CACHE = {}
def _load_address_mapping(eventname: str) -> OrderedDict:
    #"""加载指定事件的地址映射表，若不存在则创建空表"""
    global _MAPPING_CACHE

    if eventname in _MAPPING_CACHE:
        return _MAPPING_CACHE[eventname]

    filename = f"address_mapping_{eventname}.json"
    mapping = OrderedDict()
    readpath = os.path.join("D:/FORGE2/BlockchainSpider-master/blockscan_data", filename)
    if os.path.exists(readpath):
            try:
                with open(readpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                    # 确保 data 是字典
                    if not isinstance(data, dict):
                        print(f"Warning: {filename} is not a JSON object, got {type(data)}. Creating new mapping.")
                        return mapping  # 返回空 OrderedDict

                    # 安全地提取并排序 items
                    valid_items = []

                    for addr, info in data.items():
                        try:
                            mapped_id = info["mapped_id"]  # 如 "[Addr-1]"
                            if len(mapped_id.split('-')) < 2:
                                print(f"Skipping invalid key format (no dash): {addr_lower}")
                                continue
                            # 去掉括号和前缀
                            if mapped_id.startswith("[Addr-") and mapped_id.endswith("]"):
                                id_num = int(mapped_id.split('-')[1].strip(']'))  # 提取 1, 2, 3...
                                valid_items.append((addr, info, id_num))
                            else:
                                print(f"Skipping invalid mapped_id format: {mapped_id}")
                        except (ValueError, IndexError, KeyError) as e:
                            print(f"Error parsing mapped_id for {addr}: {e}")
                            continue

                    # 按 ID 排序并重建 mapping
                    valid_items.sort(key=lambda x: x[2])  # 按 id_num 排序
                    for addr_lower, info, _ in valid_items:
                        mapping[addr_lower] = info

            except json.JSONDecodeError as e:
                print(f"Warning: JSON decode error in {filename}, creating new mapping. Error: {e}")
            except Exception as e:
                print(f"Warning: Unexpected error loading {filename}: {e}")
    _MAPPING_CACHE[eventname] = mapping
    return mapping


def _save_address_mapping(eventname: str, mapping: OrderedDict):
    """保存映射表到本地文件"""
    global _MAPPING_CACHE

    filename = f"address_mapping_{eventname}.json"
    writepath = os.path.join("D:/FORGE2/BlockchainSpider-master/blockscan_data", filename)
    try:
        with open(writepath, 'w', encoding='utf-8') as f:
            json.dump(mapping, f, ensure_ascii=False, indent=2)
        _MAPPING_CACHE[eventname] = mapping.copy()  # 缓存副本
    except Exception as e:
        print(f"Error saving mapping file {filename}: {e}")


def analyze_transaction_flow(transactions: List[Dict], target_addr: str, eventname: str, topk: int) -> Dict:
    """
    分析核心地址的交易流向：统计转入/转出记录、关联地址、金额等
    扩展支持：
      - 节点拓扑结构（出入度、邻居分布）
      - 交易行为统计（频次、金额分布、大额占比、时间模式）
      - 标签信息预留字段
      - 地址映射以压缩 prompt 长度
    """
    # 地址映射系统（保持一致性）
    address_mapping = _load_address_mapping(eventname)
    addr_counter = len(address_mapping) + 1

    def get_mapped_address(addr: str) -> str:
        nonlocal addr_counter
        addr_lower = addr.lower()
        if addr_lower not in address_mapping:
            mapped = f"[Addr-{addr_counter}]"
            address_mapping[addr_lower] = {
                "mapped_id": mapped,
                "original": addr
            }
            addr_counter += 1
        return address_mapping[addr_lower]["mapped_id"]

    # 初始化结果结构
    analysis_result = {
        "target_address": get_mapped_address(target_addr),
        "original_target_address": target_addr,  # 保留原始地址用于溯源
        "total_transactions": len(transactions),
        "total_incoming": 0,
        "total_outgoing": 0,
        "incoming_transactions": [],
        "outgoing_transactions": [],
        "related_addresses": set(),
        "total_token_types": set(),

        # 拓扑结构特征
        "in_degree": 0,                    # 转入交易来源地址数量（独立地址数）
        "out_degree": 0,                   # 转出交易去向地址数量
        "in_out_ratio": 0.0,               # 出入度比值
        "unique_counterparties": 0,        # 总交互地址数（in + out 去重）

        # 交易行为统计
        "total_in_value": defaultdict(float),   # 按代币统计总转入额
        "total_out_value": defaultdict(float),  # 按代币统计总转出额
        "all_in_amounts": [],              # 所有转入金额（数值）
        "all_out_amounts": [],             # 所有转出金额（数值）
        "transaction_times": [],           # 所有交易时间戳
        "token_decimals": {},              # 记录各代币精度，用于计算

        # 衍生统计量（后续计算）
        "avg_in_amount": 0.0,
        "avg_out_amount": 0.0,
        "std_in_amount": 0.0,
        "std_out_amount": 0.0,
        "median_in_amount": 0.0,
        "median_out_amount": 0.0,
        "in_transaction_frequency": 0.0,   # 每天平均转入次数
        "out_transaction_frequency": 0.0,  # 每天平均转出次数
        "large_transfer_threshold": "1000", # 大额标准
        "large_incoming_ratio": 0.0,       # 大额转入占比（笔数）
        "large_outgoing_ratio": 0.0,       # 大额转出占比（笔数）

        # 标签信息（预留，可集成外部标签服务）
        "labels": []
    }

    # 用于统计的变量
    incoming_from_addrs: Set[str] = set()  # 转入来源地址集合（映射后）
    outgoing_to_addrs: Set[str] = set()    # 转出去向地址集合（映射后）
    target_addr_lower = target_addr.lower()

    # 临时存储原始交易数据用于排序
    raw_incoming = []
    raw_outgoing = []

    for tx in transactions:

        from_addr_orig = tx["address_from"]
        to_addr_orig = tx["address_to"]
        from_addr = from_addr_orig.lower()
        to_addr = to_addr_orig.lower()
        symbol = tx["symbol"]
        decimals = int(tx.get("decimals", 18))
        raw_value = float(tx["value"])
        cleaned = format_token_amount(tx["value"], decimals).replace(',', '')
        readable_amount = float(cleaned)
        timestamp = tx["timestamp"]

        # 记录代币精度
        analysis_result["token_decimals"][symbol] = decimals

        # 获取映射地址
        from_mapped = get_mapped_address(from_addr_orig)
        to_mapped = get_mapped_address(to_addr_orig)

        # 判断交易方向
        is_incoming = (to_addr == target_addr_lower)
        is_outgoing = (from_addr == target_addr_lower)

        if is_incoming:
            analysis_result["total_incoming"] += 1
            analysis_result["total_in_value"][symbol] += readable_amount
            analysis_result["all_in_amounts"].append(readable_amount)
            analysis_result["transaction_times"].append(timestamp)
            raw_incoming.append({
                "from_address": from_mapped,
                "token_symbol": symbol,
                "readable_amount": readable_amount,
                "transaction_time": format_time(timestamp),
                "original_amount_str": f"{readable_amount:.6f}".rstrip('0').rstrip('.')
            })
            #analysis_result["incoming_transactions"].append(incoming_tx)
            analysis_result["related_addresses"].add(from_mapped)
            incoming_from_addrs.add(from_mapped)

        if is_outgoing:
            analysis_result["total_outgoing"] += 1
            analysis_result["total_out_value"][symbol] += readable_amount
            analysis_result["all_out_amounts"].append(readable_amount)
            analysis_result["transaction_times"].append(timestamp)
            raw_outgoing.append({
                "to_address": to_mapped,
                "token_symbol": symbol,
                "readable_amount": readable_amount,
                "transaction_time": format_time(timestamp),
                "original_amount_str": f"{readable_amount:.6f}".rstrip('0').rstrip('.')
            })
            #analysis_result["outgoing_transactions"].append(outgoing_tx)
            analysis_result["related_addresses"].add(to_mapped)
            outgoing_to_addrs.add(to_mapped)

        # 统计涉及的代币类型
        analysis_result["total_token_types"].add(symbol)
    #只保留

    # === 排序并保留 topk 大额交易 ===
    # 按金额降序排列，保留最多 topk 条
    raw_incoming.sort(key=lambda x: x["readable_amount"], reverse=True)
    raw_outgoing.sort(key=lambda x: x["readable_amount"], reverse=True)

    # 填充最终的交易列表（只保留 topk 条，并格式化金额）
    analysis_result["incoming_transactions"] = [
        {
            "from_address": item["from_address"],
            "token_symbol": item["token_symbol"],
            "readable_amount": item["original_amount_str"],
            "transaction_time": item["transaction_time"]
        }
        for item in raw_incoming[:topk]
    ]

    analysis_result["outgoing_transactions"] = [
        {
            "to_address": item["to_address"],
            "token_symbol": item["token_symbol"],
            "readable_amount": item["original_amount_str"],
            "transaction_time": item["transaction_time"]
        }
        for item in raw_outgoing[:topk]
    ]

    # === 第二阶段：计算衍生特征 ===

    # 拓扑结构
    analysis_result["in_degree"] = len(incoming_from_addrs)
    analysis_result["out_degree"] = len(outgoing_to_addrs)
    analysis_result["unique_counterparties"] = len(analysis_result["related_addresses"])
    analysis_result["in_out_ratio"] = (
        round(analysis_result["out_degree"] / analysis_result["in_degree"], 3)
        if analysis_result["in_degree"] > 0 else float('inf')
    )

    # 时间范围（用于频率计算）
    if analysis_result["transaction_times"]:
        min_time = min(analysis_result["transaction_times"])
        max_time = max(analysis_result["transaction_times"])
        duration_days = max((max_time - min_time) / (24 * 3600), 1)  # 至少1天
        analysis_result["in_transaction_frequency"] = round(analysis_result["total_incoming"] / duration_days, 3)
        analysis_result["out_transaction_frequency"] = round(analysis_result["total_outgoing"] / duration_days, 3)
    else:
        duration_days = 1

    # 金额统计（转入）
    if analysis_result["all_in_amounts"]:
        amounts = analysis_result["all_in_amounts"]
        analysis_result["avg_in_amount"] = round(statistics.mean(amounts), 6)
        analysis_result["median_in_amount"] = round(statistics.median(amounts), 6)
        if len(amounts) > 1:
            analysis_result["std_in_amount"] = round(statistics.stdev(amounts), 6)
        # 大额交易占比（>1000 单位）
        large_in_count = sum(1 for amt in amounts if amt >= 1000)
        analysis_result["large_incoming_ratio"] = round(large_in_count / len(amounts), 3)

    # 金额统计（转出）
    if analysis_result["all_out_amounts"]:
        amounts = analysis_result["all_out_amounts"]
        analysis_result["avg_out_amount"] = round(statistics.mean(amounts), 6)
        analysis_result["median_out_amount"] = round(statistics.median(amounts), 6)
        if len(amounts) > 1:
            analysis_result["std_out_amount"] = round(statistics.stdev(amounts), 6)
        large_out_count = sum(1 for amt in amounts if amt >= 1000)
        analysis_result["large_outgoing_ratio"] = round(large_out_count / len(amounts), 3)

    # 转换为列表以便序列化
    analysis_result["related_addresses"] = list(analysis_result["related_addresses"])
    analysis_result["total_token_types"] = list(analysis_result["total_token_types"])

    # 保存更新的地址映射
    _save_address_mapping(eventname, address_mapping)
    analysis_result2 = analysis_result
    del analysis_result2["related_addresses"]
    del analysis_result2["all_in_amounts"]
    del analysis_result2["all_out_amounts"]
    del analysis_result2["transaction_times"]
    del analysis_result2["token_decimals"]

    return analysis_result2


# --------------------------
# 3. 构建大模型 Prompt（核心：清晰传递判断依据）
# --------------------------
def build_money_laundering_prompt(analysis_result: Dict) -> str:
    """构建判断洗钱地址的 Prompt，包含交易分析结果和判断要求"""
    # 将分析结果转为格式化字符串（大模型更易读取）
    formatted_analysis = json.dumps(analysis_result, ensure_ascii=False, indent=2)
    
    #print("################################################formatted_analysis",len(formatted_analysis))
    #print("################################################formatted_analysis",formatted_analysis)
    save_path = "G:/RiskTagger/LLM_result/" + analysis_result['original_target_address'] + "_input_analysis.json"
    with open(save_path, "w", encoding="utf-8") as f:
        f.write(formatted_analysis)

    prompt = f"""
1、You are a blockchain security analyst tasked with determining if the core address {analysis_result['target_address']} is suspected of money laundering using transaction data. Follow this structured process:  

### 1. Data Preparation  
First, parse {formatted_analysis} to extract:  
- **Key Metrics**: Transaction frequency, amounts, fund flows (inbound/outbound paths), associated addresses, token types, and timestamps.  
- **Token Details**: Market cap, liquidity, and compliance status (e.g., privacy coins like Monero, low-liquidity tokens).  


### 2. Risk Dimensions to Check  
Assess the address against these money-laundering-linked patterns, citing specific transaction records:  

#### a) Transaction Patterns  
- **Anomalies**: High-frequency/large-value transfers in short periods, amounts just below regulatory thresholds (e.g., < $50k if the reporting limit is $50k), round-number transfers (e.g., 1,000/10,000 units) without business logic, or self-transfers/reversals.  

#### b) Fund Flows  
- **Aggregation & Dispersion**: Funds pooling from many scattered addresses then quickly sent to others; layered transfers via intermediates (if detectable).  

#### c) Associated Addresses  
- **Risk Links**: Connections to known high-risk entities (darknets, sanctions), anonymized addresses (mixers/stealth addresses), or addresses with short/zero transaction history.  

#### d) Temporal & Behavioral Signs  
- **Odd Timing**: Large transactions during non-business hours (e.g., 2-4 AM).  
- **Sudden Shifts**: Spikes in volume/frequency (e.g., from 3 to 50 daily transactions) or activity conflicting with stated purposes (e.g., e-commerce address getting random small transfers).  


### 3. Conclusion & Documentation  
- **Suspicion Level**: Classify as High/Medium/Low/No Suspicion based on the above.  (e.g., "Suspicion Level: High")
- **Justification**: Link your conclusion to transaction evidence (e.g., "Justification: On 2024-05-10, received 12 scattered USDT transfers, then sent funds to darknet-linked addresses within 10 mins").  
- **Risk Details**: Highlight key suspicious transactions/addresses; if no suspicion, explain (e.g., "Risk Details: 50% of counterparties are licensed institutions, transactions align with business hours").  
- **Gaps**: Note unverified info (e.g., "Gaps: Intermediate address identities not confirmed").  

### 4. Internal Reflection

1、You are a blockchain security auditor tasked with reviewing and improving the money laundering suspicion analysis of the core address {analysis_result['target_address']}. Follow this structured reflection process. Only provide the final result.

#### 1. Analysis Logic Validation
- Verify if the initial analysis covered all risk dimensions in the original framework (transaction patterns, fund flows, associated addresses, temporal signs). If any dimension was omitted, explain the potential impact .
- Check if the justification directly links to specific transaction records. Identify vague statements (e.g., "high-frequency transfers" without timestamp/amount details) and suggest how to make them concrete.
- Assess if the suspicion level classification aligns with the weight of evidence.

#### 2. Evidence Quality Review
- Identify conflicting evidence that was not addressed.

#### 3. Bias and Blind Spot Detection
- Reflect on potential confirmation bias: Did the analysis overemphasize evidence supporting the initial suspicion while downplaying mitigating factors (e.g., regulatory compliance documents for the address)?
- Identify assumptions that lack validation.

### 5. Output Example  
Provide your findings in this JSON format:
{{
    "suspicion_level": "Classification of suspicion (High/Medium/Low/No Suspicion)",
    "a_transaction_patterns": {{
        "result": "",
        "evidence": ""
    }},
    "b_fund_flows": {{
        "result": "",
        "evidence": ""
    }},
    "c_associated_addresses": {{
        "result": "",
        "evidence": ""
    }},
    "d_temporal_behavioral_signs": {{
        "result": "",
        "evidence": ""
    }}
}}
"""
    return prompt.strip()


# --------------------------
# 4. 调用大模型获取判断结果
# --------------------------
def call_openai_model(prompt: str, api_key: str, model_name: str, base_url: str) -> str:
    """调用 OpenAI 大模型，获取洗钱判断结果"""
    # 初始化客户端
    client = OpenAI(api_key=api_key, base_url=BASE_URL)
    try:
        # 发送请求（temperature=0.3 降低随机性，确保判断更严谨）
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a professional blockchain money laundering detection analyst. Your judgment should be based on data and be logically rigorous, without making subjective assumptions."},
                {"role": "assistant", "content": "Yes, I understand. I am a professional blockchain money laundering detection analyst and will analyze the provided data to detect money laundering activities based on data-driven and logically rigorous judgment, without making subjective assumptions."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=2000  # 足够容纳详细分析结果
        )
        # 提取大模型回复
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"大模型调用失败：{str(e)}"


# --------------------------
# 5. 主函数（串联全流程）
# --------------------------
def llm_based_detect(target_address:str = TARGET_ADDRESS,eventname: str = "bybit") -> tuple[bool,str]:
    # 步骤1：读取 CSV 数据
    label = "unknown"
    csv_path = "G:/RiskTagger/blockscan_data/"+target_address+"/AccountTransferItem.csv"
    transactions = read_blockchain_csv(csv_path) # 对交易进行过滤及处理（过滤零交易和非白名单交易）
    if not transactions:
        print("未读取到交易数据，程序终止")
        return [False,label]

    # 步骤2：分析核心地址的交易流向
    tx_analysis = analyze_transaction_flow(transactions, target_address, eventname=eventname, topk=50)

    print("\n核心地址交易分析完成，概要信息：")
    print(f"- 核心地址：{tx_analysis['target_address']}")
    print(f"- 总交易数：{tx_analysis['total_transactions']}")
    print(f"- 转入交易数：{len(tx_analysis['incoming_transactions'])}")
    print(f"- 转出交易数：{len(tx_analysis['outgoing_transactions'])}")
    '''
    print(f"- 关联地址数：{len(tx_analysis['related_addresses'])}")
    print(f"- 涉及代币类型：{tx_analysis['total_token_types']}")
    '''
    # 步骤3：构建大模型 Prompt，加入反思机制
    prompt = build_money_laundering_prompt(tx_analysis)
    # 步骤4：调用大模型并输出结果
    print("\n开始调用大模型进行洗钱判断...")
    response_text = call_openai_model(prompt, OPENAI_API_KEY, MODEL_NAME, BASE_URL)
    print("\n" + "=" * 50)
    print("大模型判断结果：")
    print("=" * 50)
    #print(response_text)
    save_path = "G:/RiskTagger/LLM_result/" + target_address + ".txt"
    with open(save_path, "w", encoding="utf-8") as f:
        f.write(response_text)

    # 只提取“suspicion_level”之后的内容
    start = response_text.find("suspicion_level")
    if start == -1:
        label = "unknown"
    else:
        # 截取结论后的一小段（比如100字符），避免扫描全文
        conclusion_part = response_text[start:start + 35]
        if "High" in conclusion_part or "high" in conclusion_part:
            label = "high-ML"
        elif "Medium" in conclusion_part or "medium" in conclusion_part:
            label = "mid-ML"
        elif "Low" in conclusion_part or "low" in conclusion_part:
            label = "low-ML"
        elif "No Suspicion" in conclusion_part or "no suspicion" in conclusion_part or "No suspicion" in conclusion_part:
            label = "No Suspicion"
        else:
            label = "unknown"
    if label != "unknown" and label != "No Suspicion":
        return [True,label]
    else:
        return [False,label]

    return [False,label]
