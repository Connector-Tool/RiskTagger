import pandas as pd
import json
import threading  # [新增] 用于线程安全
from datetime import datetime
from typing import List, Dict, Set, Union, TypedDict, Optional
from collections import defaultdict, OrderedDict
from decimal import Decimal
import statistics
from pathlib import Path
import pickle
# 引入配置和工具
from config.settings import Config
from utils.logger import logger
from utils.file_utils import load_csv_as_dict, save_json
from utils.crypto_utils import wei_to_ether, format_token_amount, is_contract_whitelisted

# [新增] 全局地址映射器类
class GlobalAddressMapper:
    """
    持久化地址映射器：
    1. 自动加载本地 JSON 映射表。
    2. 保证同一事件下，地址 ID (Addr-X) 永久不变。
    3. 线程安全，支持并发写入。
    """

    def __init__(self, event_name: str):
        self.event_name = event_name
        self.lock = threading.Lock()  # 线程锁
        self.file_path = Config.PATHS["mappings"] / f"{event_name}_mapping.json"

        # 内存中的映射表
        self.addr_to_id: Dict[str, str] = {}
        self.next_id_num = 1

        # 初始化加载
        self._load()

    def _load(self):
        """从磁盘加载现有的映射表"""
        if self.file_path.exists():
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.addr_to_id = data.get("mapping", {})
                    self.next_id_num = data.get("next_id", 1)
                logger.info(f"已加载地址映射表: {len(self.addr_to_id)} 个地址, 下一个ID: {self.next_id_num}")
            except Exception as e:
                logger.error(f"加载映射表失败: {e}, 将创建新表")
        else:
            logger.info("未发现现有映射表，将创建新表。")

    def _save(self):
        """保存到磁盘 (必须在锁内调用)"""
        try:
            data = {
                "next_id": self.next_id_num,
                "mapping": self.addr_to_id
            }
            # 临时保存逻辑，避免写入损坏
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"保存映射表失败: {e}")

    def get_short_id(self, address: str) -> str:
        """
        获取短 ID。如果不存在，则生成新 ID 并立即保存。
        """
        if not address: return "Unknown"
        addr_lower = address.lower().strip()

        # 特殊地址处理
        if addr_lower.startswith("0x00000000"):
            return "Null_Addr"

        # 1. 快速检查 (读操作不需要锁，或者为了严谨可以加锁，但 Python 字典读取是原子的)
        if addr_lower in self.addr_to_id:
            return self.addr_to_id[addr_lower]

        # 2. 生成新 ID (写操作必须加锁)
        with self.lock:
            # 双重检查 (防止在等待锁的过程中被其他线程创建了)
            if addr_lower in self.addr_to_id:
                return self.addr_to_id[addr_lower]

            # 分配新 ID
            short_id = f"Addr-{self.next_id_num}"
            self.addr_to_id[addr_lower] = short_id
            self.next_id_num += 1

            # 立即保存 (保证持久化)
            self._save()

            return short_id


# 定义 LLM 输入的标准化数据结构 (TypedDict 或 class 均可)
class TransactionContext(TypedDict):
    target_address: str
    transaction_flow_summary: Dict
    top_transactions: List[Dict]
    related_addresses: Set[str]
    total_token_types: int
    data_generation_time: str
    
class DataTranslator:
    """
    负责读取原始交易 CSV，清洗数据，计算特征，并生成 LLM Prompt 所需的 JSON Context。
    对应 RiskTagger 架构中的 Translator 模块。
    """
    
    def __init__(self, event_name: str):
        # 从配置中获取白名单，并统一转为小写集合以便快速查找
        self.whitelist = {addr.lower() for addr in Config.Filter.CONTRACT_WHITELIST}
        self.raw_data_base_path = Config.PATHS["raw_tx_data"]
        #初始化映射器
        self.mapper = GlobalAddressMapper(event_name)
        # --- [新增] 1. 结果路径和缓存 ---
        self.result_base_path = Config.PATHS["llm_result"]
        self.label_cache: Dict[str, str] = {}  # 混合缓存：包含 CSV 标签和已查询过的 JSON 结果

        # --- [新增] 2. 预加载 CSV 标签库 (Ground Truth) ---
        self._load_ground_truth_labels()

    def _load_ground_truth_labels(self):
        """
        一次性将 CSV 中的标签加载到内存缓存中，引入 Pickle 二进制缓存加速海量数据读取。
        """

        def load_csv_to_dict_with_cache(file_path: Path, default_label: str, is_ai_result: bool = False) -> dict:
            if not file_path.exists():
                return {}

            # 定义缓存文件路径
            cache_path = file_path.parent / f"{file_path.stem}_dict.pkl"

            # 1. 检查缓存是否有效 (缓存存在，且修改时间晚于原始 CSV)
            if cache_path.exists() and cache_path.stat().st_mtime > file_path.stat().st_mtime:
                try:
                    with open(cache_path, "rb") as f:
                        cached_dict = pickle.load(f)
                    logger.info(f"从缓存加载标签: {file_path.name} ({len(cached_dict)} 条)")
                    return cached_dict
                except Exception as e:
                    logger.error(f"读取缓存失败，将重新解析 CSV: {e}")

            # 2. 缓存失效或不存在，解析 CSV
            logger.info(f"正在解析原始标签文件 (首次或已更新): {file_path.name}...")
            result_dict = {}
            try:
                # 预读前两行，判断是否存在 'name_tag' 列，防止读取时报错
                sample_df = pd.read_csv(file_path, nrows=2)
                has_name_tag = "name_tag" in sample_df.columns

                usecols = ["address"]
                if has_name_tag:
                    usecols.append("name_tag")

                # 使用 C 引擎加速，统一读取为字符串防止精度丢失
                df = pd.read_csv(
                    file_path,
                    usecols=usecols,
                    dtype=str,
                    engine="c",
                    low_memory=False
                )

                for _, row in df.iterrows():
                    addr = str(row["address"]).strip().lower()
                    if addr == "nan" or not addr:
                        continue

                    # 确定最终的标签名
                    if has_name_tag and pd.notna(row.get("name_tag")):
                        raw_tag = str(row["name_tag"]).strip()
                        if is_ai_result:
                            # 提取类似 "High_Layer0" 中的 "High"
                            final_label = f"AI-{raw_tag.split('_')[0]}"
                        else:
                            # 拼接类似 "Exchange-Binance"
                            final_label = f"{default_label}-{raw_tag}"
                    else:
                        final_label = default_label

                    result_dict[addr] = final_label

            except Exception as e:
                logger.error(f"解析标签名单失败 {file_path.name}: {e}")
                return {}

            # 3. 写入缓存
            try:
                with open(cache_path, "wb") as f:
                    pickle.dump(result_dict, f)
                logger.info(f"已创建标签缓存: {cache_path.name}")
            except Exception as e:
                logger.error(f"写入标签缓存失败 {cache_path.name}: {e}")

            return result_dict

        # ==========================================
        # 执行加载，使用 update 快速合并字典
        # ==========================================

        # 1. 加载动态推断名单 (LLM跑出来的黑客与正常账户)
        hacker_csv = Config.PATHS["risktagger_hack"] / "accounts-hacker.csv"
        normal_csv = Config.PATHS["normal_addr_info"] / "normal_addr_info.csv"

        self.label_cache.update(load_csv_to_dict_with_cache(hacker_csv, "AI-Hacker", is_ai_result=True))
        self.label_cache.update(load_csv_to_dict_with_cache(normal_csv, "AI-Normal", is_ai_result=True))

        # 2. 加载已知基础设施实体名单
        ref_dir = Config.PATHS["reference"]
        self.label_cache.update(load_csv_to_dict_with_cache(ref_dir / "exchange-list.csv", "Exchange"))
        self.label_cache.update(load_csv_to_dict_with_cache(ref_dir / "wallet-list.csv", "Wallet"))
        self.label_cache.update(load_csv_to_dict_with_cache(ref_dir / "others-list.csv", "other"))

        logger.info(f"已预加载总计 {len(self.label_cache)} 个已知地址标签到内存缓存。")

    def _get_existing_label(self, address: str) -> Optional[str]:
        """
        查询顺序：内存缓存(CSV+已查过的JSON) -> 硬盘JSON
        """
        address_lower = address.lower()

        # 1. 查内存 (命中 CSV 数据或之前的查询结果) - 极快
        if address_lower in self.label_cache:
            return self.label_cache[address_lower]

        # 2. 查 LLM 历史结果 (作为补充) - 较慢
        candidates = [
            self.result_base_path / f"{address}.json",
            self.result_base_path / f"{address_lower}.json"
        ]

        risk_label = None
        for json_path in candidates:
            if json_path.exists():
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if "risk_level" in data:
                            # 格式化一下，比如 "LLM-High" 以区分来源
                            risk_label = f"AI-{data['risk_level']}"
                            break
                except Exception:
                    continue

        # 3. 写入缓存 (避免下次重复查硬盘)
        # 注意：如果是 None 也存进去，防止重复对不存在的文件进行 IO 操作
        self.label_cache[address_lower] = risk_label

        return risk_label

    def _get_transaction_data(self, address: str) -> List[Dict]:
        """
        根据地址读取其原始交易 CSV 文件。
        路径格式: {raw_data_base_path}/{address}/AccountTransferItem.csv
        """
        csv_path = self.raw_data_base_path / address / "AccountTransferItem.csv"
        
        if not csv_path.exists():
            logger.warning(f"地址 {address} 缺少原始交易数据文件: {csv_path}")
            return []

        # 使用 file_utils 加载，自动处理编码问题
        return load_csv_as_dict(csv_path)

    def _clean_and_filter_data(self, raw_data: List[Dict]) -> List[Dict]:
        """
        清洗和过滤原始数据 (保留白名单合约交易)。
        """
        cleaned_data = []
        for row in raw_data:
            # 1. 跳过非白名单合约的交易
            is_token_transfer = row.get("contract_address") not in ["", "0x0000000000000000000000000000000000000000"]
            
            if is_token_transfer:
                token_addr = row["contract_address"].lower()
                if not is_contract_whitelisted(token_addr, self.whitelist):
                    continue
            
            # 2. 转换为 Decimal 以保证金额计算精度
            try:
                row["value_decimal"] = wei_to_ether(row["value"], decimals=int(row.get("decimals", 18)))
                row["timestamp_dt"] = datetime.fromtimestamp(int(row["timestamp"]))
                cleaned_data.append(row)
            except Exception as e:
                logger.debug(f"清洗时数据格式错误: {e}, Row: {row}")
                continue
                
        return cleaned_data

    def _analyze_features(self, transactions: List[Dict], target_address: str) -> Dict:
        """
        计算交易特征，包括统计数据、交易流向等 (对应原 analyze_transaction_flow 核心逻辑)。
        """
        summary = {
            "total_transactions": len(transactions),
            "total_value_in": Decimal(0),
            "total_value_out": Decimal(0),
            "avg_value": Decimal(0),
            "std_dev_value": Decimal(0),
            "in_degree": 0,
            "out_degree": 0,
            "first_tx_time": "",
            "last_tx_time": "",
            "active_period_days": 0,
            "sender_count": defaultdict(int),
            "receiver_count": defaultdict(int),
            "token_type_count": defaultdict(int),
        }
        
        values = []
        timestamps = []
        related_addresses = set()
        
        target_address_lower = target_address.lower()

        for tx in transactions:
            value = tx["value_decimal"]
            values.append(value)
            timestamps.append(tx["timestamp_dt"])
            
            sender = tx["address_from"].lower()
            receiver = tx["address_to"].lower()
            token = tx.get("symbol", "ETH")
            
            # 1. 计算流入/流出总额、度数
            if receiver == target_address_lower:
                summary["total_value_in"] += value
                summary["in_degree"] += 1
                related_addresses.add(sender)
                summary["sender_count"][sender] += 1
            elif sender == target_address_lower:
                summary["total_value_out"] += value
                summary["out_degree"] += 1
                related_addresses.add(receiver)
                summary["receiver_count"][receiver] += 1

            # 2. 统计代币类型
            summary["token_type_count"][token] += 1
        
        # 3. 统计特征
        if values:
            summary["avg_value"] = Decimal(statistics.mean(values))
            if len(values) > 1:
                try:
                    summary["std_dev_value"] = Decimal(statistics.stdev(values))
                except statistics.StatisticsError: # 只有两个值时 stdev 会报错
                    summary["std_dev_value"] = Decimal(0)
        
        # 4. 时间特征
        if timestamps:
            timestamps.sort()
            summary["first_tx_time"] = timestamps[0].strftime("%Y-%m-%d %H:%M:%S")
            summary["last_tx_time"] = timestamps[-1].strftime("%Y-%m-%d %H:%M:%S")
            time_diff = timestamps[-1] - timestamps[0]
            summary["active_period_days"] = round(time_diff.total_seconds() / (24 * 3600), 2)
           
        summary["related_addresses"] = related_addresses
        
        return summary

    def _prepare_top_transactions(self, transactions: List[Dict]) -> List[Dict]:
        """
        提取 Top N 的交易作为 LLM Context 的输入。
        在输出时，将地址替换为 Mapper 中的短 ID
        """

        # 按照交易金额排序
        transactions.sort(key=lambda x: x["value_decimal"], reverse=True)
        
        # 提取前 N 笔交易 (例如：最多50笔)
        top_txs = transactions[:50]
        
        # 格式化输出 (只保留关键字段)
        formatted_txs = []
        for tx in top_txs:
            # 格式化金额，使用 tx 原始的 decimals 信息（如果存在）
            token_decimals = int(tx.get("decimals", 18))

            # [关键] 调用 mapper 获取短 ID
            from_id = self.mapper.get_short_id(tx["address_from"])
            to_id = self.mapper.get_short_id(tx["address_to"])

            # 获取标签 (现在的 _get_existing_label 已经是混合增强版了)
            from_risk_label = self._get_existing_label(tx["address_from"])
            to_risk_label = self._get_existing_label(tx["address_to"])

            # 格式化显示
            from_display = f"{from_id} [{from_risk_label}]" if from_risk_label else from_id
            to_display = f"{to_id} [{to_risk_label}]" if to_risk_label else to_id
            formatted_txs.append({
                #"hash": tx["hash"], # 可选保留交易哈希
                "from": from_display,
                "to": to_display,
                # "value_wei": tx["value"],
                "value_formatted": format_token_amount(tx["value"], token_decimals),
                "token_symbol": tx.get("symbol", "ETH"),
                "timestamp": tx["timestamp_dt"].strftime("%Y-%m-%d %H:%M:%S")
            })
            
        return formatted_txs

    def generate_llm_context(self, address: str) -> Optional[TransactionContext]:
        """
        主函数：处理单个地址，生成 LLM 推理所需的结构化 Context。
        """
        
        # 1. 获取和清洗数据
        raw_transactions = self._get_transaction_data(address)
        if not raw_transactions:
            return None
            
        transactions = self._clean_and_filter_data(raw_transactions)
        
        if not transactions:
            logger.info(f"地址 {address} 的交易在过滤白名单后为空.")
            return None

        # 2. 计算特征和总结
        summary = self._analyze_features(transactions, address)
        top_txs = self._prepare_top_transactions(transactions)

        # 获取目标地址的 ID
        target_id = self.mapper.get_short_id(address)

        # 3. 构建 Context
        context: TransactionContext = {
            "target_address":address,
            "target_address_id": target_id,
            "transaction_flow_summary": {
                # [修正] 增加排除 "related_addresses"
                k: str(v) if isinstance(v, Decimal) else v
                for k, v in summary.items() 
                if k not in ["sender_count", "receiver_count", "related_addresses", "token_type_count"]
            },
            "top_transactions": top_txs,
            # "related_addresses": list(summary["related_addresses"]),
            "total_token_types": len(summary["token_type_count"]),
            # "data_generation_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            "note": f"Addresses are mapped: [TARGET] is {target_id}."
        }
        
        # 4. 保存 JSON 文件 (对应原 LLM_detection.py 的 save_path 逻辑)
        llm_input_path = Config.PATHS["llm_input"] / f"{address}.json"
        save_json(context, llm_input_path)

        logger.info(f"地址 {address} 的 LLM Context 已生成并保存: {llm_input_path.name}")
        
        return context

if __name__ == "__main__":
    # 示例测试
    # 假设 '0x123...' 路径下有一个 AccountTransferItem.csv
    # Config.ensure_dirs()
    # translator = DataTranslator()
    # context = translator.generate_llm_context(
    #     "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045", 
    #     risk_level_source="Seed"
    # )
    # print(json.dumps(context, indent=2))
    pass