import pickle
import random
from os import getenv

import aiohttp
import pandas as pd
from typing import List, Set, Dict, Optional
from decimal import Decimal
from pathlib import Path
import csv
import time
import sys
import json
import threading
import atexit
import asyncio

from win32print import PRINTER_ATTRIBUTE_LOCAL

# 【新增】：解决 Windows 下的 ProactorPipeTransport 垃圾回收报错
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# 引入配置和工具
from config.settings import Config
from utils.logger import logger
from utils.file_utils import load_csv_as_dict
from utils.crypto_utils import wei_to_ether, is_contract_whitelisted
from utils.crypto_utils import get_token_price_eth
from utils.check_contract import is_contract
from utils.CrossChainTracker import AsyncBridgePoller
class GraphExpander:
    """
    负责在 BFS 过程中，根据交易规则和黑白名单，筛选出下一跳待追踪的地址。
    对应 RiskTagger 架构中的 Filter 模块。
    """

    def __init__(self):
        # 初始化过滤集合
        self.exchange_addrs: Set[str] = set()
        self.wallet_addrs: Set[str] = set()
        self.normal_addrs: Set[str] = set()
        self.others_addrs: Set[str] = set()
        self.known_hackers: Set[str] = set()

        # 加载参考列表 (黑/白名单)
        self._load_reference_lists()

        # 阈值配置
        self.min_amount = Decimal(str(Config.Filter.MIN_AMOUNT))
        self.top_ratio = Config.Filter.TOP_AMOUNT_RATIO
        self.max_addrs = Config.Filter.MAX_ADDRESSES_PER_HOP
        self.coverage_threshold = Decimal(Config.Filter.COVERAGE_THRESHOLD)  # 覆盖资金流向的比例
        self.whitelist_contract = {addr.lower() for addr in Config.Filter.CONTRACT_WHITELIST}
        self.max_time_window = Config.Filter.MAX_TIME_WINDOW # 新增配置：时间窗口 (秒)，默认 30 天
        #self.bridge_poller = AsyncBridgePoller()
        # 【初始化本地已知跨链数据集】
        self.known_crosschain_data = {}
        self._load_known_crosschain_data()

        # 【初始化智能合约持久化全局缓存】
        self.contract_cache_file = Config.CONTRACT_CACHE_FILE
        self.contract_cache_lock = threading.Lock()  # 线程安全锁
        self.contract_cache = {}
        self.unsaved_cache_count = 0
        self._load_contract_cache()

        # 【初始化资金覆盖率持久化文件与线程锁】
        self.coverage_report_file = Config.PATHS["risktagger_hack"] / "coverage_report.csv"
        self.coverage_lock = threading.Lock()

    def _save_coverage_metrics(self, current_address: str, total_valid: Decimal, cross_chain: Decimal,
                               eoa_tracked: Decimal, ratio: float,depth: int,expanded_count: int):
        """线程安全地将资金覆盖率指标追加保存到 CSV 文件中"""
        try:
            # 开启线程锁，确保同一瞬间只有一个地址在写文件
            with self.coverage_lock:
                file_exists = self.coverage_report_file.exists()

                # a 模式代表追加写入
                with open(self.coverage_report_file, 'a', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)

                    # 如果文件是第一次创建，先写入表头
                    if not file_exists:
                        writer.writerow([
                            'Source_Address',
                            'Total_Valid_Outbound',
                            'CrossChain_Contract_Value',
                            'EOA_Tracked_Value',
                            'Coverage_Ratio(%)',
                            'Depth',
                            'Expanded_Account_Count',  # 【新增】：扩展的账户数目
                            'Scan_Time'
                        ])

                    scan_time = time.strftime("%Y-%m-%d %H:%M:%S")
                    writer.writerow([
                        current_address,
                        f"{total_valid:.4f}",
                        f"{cross_chain:.4f}",
                        f"{eoa_tracked:.4f}",
                        f"{ratio:.2f}",
                        depth,
                        expanded_count,  # 【新增】：对应数值
                        scan_time
                    ])
        except Exception as e:
            logger.error(f"保存资金覆盖率到本地失败: {e}")

    def _load_contract_cache(self):
        """从本地加载合约状态缓存"""
        if self.contract_cache_file.exists():
            try:
                with open(self.contract_cache_file, "r", encoding="utf-8") as f:
                    self.contract_cache = json.load(f)
                logger.info(f"成功加载本地合约状态缓存: {len(self.contract_cache)} 条记录。")
            except Exception as e:
                logger.error(f"加载合约状态缓存失败: {e}")

        # 注册退出钩子：当 Python 脚本运行结束时，自动把内存中还没来得及存的数据落盘
        atexit.register(self.flush_contract_cache)

    def _update_contract_cache(self, addr: str, status: int):
        """更新缓存并智能批量落盘"""
        # 使用锁保证多线程下的写入安全
        with self.contract_cache_lock:
            self.contract_cache[addr] = status
            self.unsaved_cache_count += 1

            # 每查询到 50 个全新的地址，才执行一次硬盘写入，极大地提高性能
            if self.unsaved_cache_count >= 50:
                self._force_flush_under_lock()

    def flush_contract_cache(self):
        """手动或程序退出时，将剩余数据强制写入磁盘"""
        with self.contract_cache_lock:
            if self.unsaved_cache_count > 0:
                self._force_flush_under_lock()

    def _force_flush_under_lock(self):
        """实际写入磁盘的逻辑"""
        try:
            with open(self.contract_cache_file, "w", encoding="utf-8") as f:
                json.dump(self.contract_cache, f)
            self.unsaved_cache_count = 0
        except Exception as e:
            logger.error(f"落盘保存合约缓存失败: {e}")

    def _load_known_crosschain_data(self):
        """
        一次性加载本地已知的跨链交易哈希表，用于直接跳过 API 请求
        """
        # 使用用户指定的绝对路径
        known_file = Config.PATHS["crosschain_data"] / "aml_crosschain_know.csv"

        if known_file.exists():
            try:
                # 使用 pandas 读取
                df = pd.read_csv(known_file, dtype=str)
                for _, row in df.iterrows():
                    tx_hash = str(row.get("Source_Tx_Hash", "")).strip().lower()
                    if tx_hash and tx_hash != "nan":
                        # 将每行数据组装成字典存入内存
                        self.known_crosschain_data[tx_hash] = {
                            "Used_Bridge": row.get("Used_Bridge", "Unknown"),
                            "Destination_Chain": row.get("Destination_Chain", "Unknown"),
                            "Destination_Address": row.get("Destination_Address", "Unknown"),
                            "Status": row.get("CrossChain_Status", "Unknown")
                        }
                logger.info(f"成功加载本地已知跨链记录: {len(self.known_crosschain_data)} 条。")
            except Exception as e:
                logger.error(f"加载本地跨链记录文件失败: {e}")
        else:
            logger.warning(f"未找到本地跨链记录文件: {known_file}")
    def _load_reference_lists(self):
        """
        加载所有用于过滤的参考地址列表 (Exchange, Wallet, LargeAddr, Hacker)
        """
        ref_dir = Config.PATHS["reference"] # reference_list 目录
        RiskTagger_Data = Config.PATHS["risktagger_hack"]
        normal_path = Config.PATHS["normal_addr_info"] / "normal_addr_info.csv"

        # 1. 交易所
        #self.exchange_addrs = self._read_addr_set(ref_dir / "exchange-list.csv")
        self.exchange_addrs = self._read_addr_set_with_cache(ref_dir / "exchange-list.csv")
        # 2. 钱包
        self.wallet_addrs = self._read_addr_set_with_cache(ref_dir / "wallet-list.csv")
        # 3. 历史黑客
        self.known_hackers = self._read_addr_set_with_cache(RiskTagger_Data / "accounts-hacker.csv")
        # 4. others
        self.others_addrs = self._read_addr_set_with_cache(ref_dir / "others-list.csv")
        # 5. 已识别的正常账户
        if normal_path.exists():
            self.normal_addrs = self._read_addr_set_with_cache(normal_path)

        logger.info(f"过滤名单加载完成: Exchange({len(self.exchange_addrs)}), "
                    f"Wallet({len(self.wallet_addrs)}), "
                    f"Normal({len(self.normal_addrs)}), "
                    f"Hacker({len(self.known_hackers)})")


    def _read_addr_set_with_cache(self,file_path: Path) -> set:
        """
        读取地址集，并使用 Pickle 进行二进制缓存加速
        """
        if not file_path.exists():
            logger.warning(f"文件不存在: {file_path}")
            return set()

        # 定义缓存文件路径 (例如 exchange-list.csv -> exchange-list.csv.pkl)
        cache_path = file_path.with_suffix(file_path.suffix + ".pkl")

        # 逻辑：检查缓存是否存在，且缓存文件的修改时间晚于原始文件（确保数据是最新的）
        if cache_path.exists() and cache_path.stat().st_mtime > file_path.stat().st_mtime:
            try:
                with open(cache_path, "rb") as f:
                    addr_set = pickle.load(f)
                logger.info(f"从缓存加载完成: {file_path.name} ({len(addr_set)} 条)")
                return addr_set
            except Exception as e:
                logger.error(f"读取缓存失败，尝试重新解析 CSV: {e}")

        # 如果没有缓存或缓存过期，则读取 CSV
        logger.info(f"正在解析原始文件 (首次或已更新): {file_path.name}...")
        try:
            # 使用 pandas 的 C 引擎只读取 'address' 列，速度极快
            df = pd.read_csv(
                file_path,
                usecols=["address"],
                dtype={"address": str},
                engine="c",
                low_memory=False
            )

            # 转换为集合并统一小写（防止匹配失效）
            addr_set = set(df["address"].str.strip().str.lower())

            # 写入缓存
            with open(cache_path, "wb") as f:
                pickle.dump(addr_set, f)

            logger.info(f"缓存已创建: {cache_path.name}")
            return addr_set

        except Exception as e:
            logger.error(f"解析 CSV 失败 {file_path}: {e}")
            return set()

    def _is_valid_neighbor(self, address: str) -> bool:
        """
        判断一个邻居地址是否值得追踪。
        如果在交易所、钱包或已知正常列表中，则返回 False。
        """
        addr_lower = address.lower()
        if addr_lower in self.exchange_addrs:
            print(f"地址 {address} 在交易所名单中，跳过追踪。")
            return False
        if addr_lower in self.wallet_addrs:
            print(f"地址 {address} 在钱包名单中，跳过追踪。")
            return False
        if addr_lower in self.others_addrs and (not Config.Filter.Trace_others):
            print(f"地址 {address} 在其他名单中，跳过追踪。")
            return False
        if addr_lower in self.normal_addrs:
            print(f"地址 {address} 在正常账户名单中，跳过追踪。")
            return False
        if addr_lower in self.known_hackers:
            print(f"地址 {address} 在已知黑客名单中，跳过追踪。")
            return False
        # 注意：不排除 known_hackers，因为可能存在洗钱回环或汇集
        # 需要排除已经确定为黑客的地址，避免死循环
        return True

        # 记得在 filter.py 顶部加上: import aiohttp

    async def _run_batch_bridge_probing(self, tx_hashes: List[str]):
        """内部异步方法：并发执行多个哈希的探测（使用共享会话）"""
        # 针对这批（如 52 个）哈希，我们只创建一个 Session
        async with aiohttp.ClientSession() as session:
            # 动态创建 poller 实例，确保它在这个新事件循环中
            bridge_poller = AsyncBridgePoller()

            # 将共享的 session 传递给 poll_transaction
            tasks = [bridge_poller.poll_transaction(h, session) for h in tx_hashes]

            # 并发执行所有探测任务
            await asyncio.gather(*tasks, return_exceptions=True)

        # 【解决 Windows 报错的终极绝招】
        # async with 块结束时，aiohttp 触发了 close，但底层 transport 彻底断开需要一点时间
        # 强制休眠 0.25 秒，让底层的 Proactor 有足够时间去清理那几百个已关闭的 Socket
        await asyncio.sleep(0.25)

    def get_next_hop_candidates(self, current_address: str,
                                parent_tx_time: int = Config.Filter.START_TIMESTAMP,
                                current_depth: int = 0) -> List[Dict]:
        """
        核心逻辑：分析当前地址的交易，筛选出下一跳候选地址。
        返回格式示例: [{"address": "0x...", "parent_tx_time": 1698765432,"parent_address": }, ...]
        """
        # 1. 读取交易数据
        raw_data_path = Config.PATHS["raw_tx_data"] / current_address / "AccountTransferItem.csv"
        if not raw_data_path.exists():
            return []

        transactions = load_csv_as_dict(raw_data_path)
        # 是否要通过交易笔数限制潜在的风险
        if not transactions:
            return []

        current_addr_lower = current_address.lower()
        outbound_txs = []

        # 用于记录每个接收地址的“最早到账时间”
        # 格式: { "0x接收地址": 最小时间戳 }
        earliest_arrival_times = {}
        contract_tx_hashes = []  # 用于收集待探测的哈希
        # 动态计算截断阈值（后续可以动态调整）
        dynamic_max_limit = self.max_addrs

        # 【资金覆盖率1】资金覆盖率统计变量
        total_valid_outbound_value = Decimal(0)
        cross_chain_value = Decimal(0)
        #print(transactions)
        # 2. 预处理交易
        from utils.CrossChainTracker import AsyncBridgePoller
        local_poller = AsyncBridgePoller()
        #print("transa",len(transactions))
        if (len(transactions) > 10000):  # 极少会有洗钱账户有这么多笔交易，先过滤掉，避免爆炸
            return []
        for tx in transactions:
            # A. 基础过滤：只看转出
            if tx.get("address_from", "").lower() != current_addr_lower:
                continue

            # B. 基础过滤：去除 Value=0
            if tx.get("value", "0") == "0":
                continue

            # 获取时间戳
            try:
                tx_time = int(tx.get("timestamp", Config.Filter.START_TIMESTAMP))
            except ValueError:
                tx_time = Config.Filter.START_TIMESTAMP

            # C. 时间窗口过滤 (防止时光倒流 或 超过窗口期)
            if parent_tx_time >= Config.Filter.START_TIMESTAMP and tx_time >= Config.Filter.START_TIMESTAMP:
                # 忽略比上一跳更早的交易 (允许少量误差，比如 1小时容错，视情况而定)
                # 这里需要设定的时间长一些，因为存在存量交易问题（设定为30天）
                if tx_time < (parent_tx_time - self.max_time_window)  :
                    continue
                # 也可以选择过滤掉超过窗口期的交易，视追踪策略而定，如果想要更严格地追踪近期资金流动，可以启用下面的过滤：
                #if tx_time > (parent_tx_time + self.max_time_window):
                    continue
            # 交易时间过早也需要过滤掉(上面只考虑了相对时间，这里加一个绝对时间的过滤，防止时光倒流问题)
            if tx_time < Config.Filter.START_TIMESTAMP:
                continue
            # D. 合约白名单 / 黑洞地址过滤
            contract_addr = tx.get("contract_address", "").strip().lower()
            to_addr = tx.get("address_to", "").lower()

            is_native_eth = contract_addr in ["", "0x", "0x0000000000000000000000000000000000000000"]# 原生 ETH 转账没有合约地址
            # 代币地址需要检查，过滤非白名单合约转账
            if not is_native_eth and contract_addr not in self.whitelist_contract:
                continue
            #print(tx)
            #金额过滤：提前在这里计算金额并拦截
            try:
                # 1. 计算代币的绝对数量
                token_amount = wei_to_ether(tx["value"], int(tx.get("decimals", 18)))
                # 2. 获取该代币相对于 1 ETH 的价值权重
                token_price_eth = get_token_price_eth(contract_addr)
                # 3. 计算真实的 ETH 等值价值
                val = token_amount * token_price_eth
                if val < self.min_amount:
                    continue  # 如果金额太小（粉尘交易），无论是普通转账还是跨链，直接丢弃！
                tx["value_decimal"] = val  # 存下来后面排序用
            except Exception:
                continue
            if not self._is_valid_neighbor(to_addr):
                continue

            # 【资金覆盖率 2】：累加总有效转出金额 (作为分母)
            total_valid_outbound_value += val

            # 【判断是否是合约地址，全局持久化缓存拦截】
            # 1. 优先查内存/本地缓存，O(1) 极速拦截
            if to_addr not in self.contract_cache:
                try:
                    # 只有遇到真·全新地址，才去请求 Infura
                    is_ct = is_contract(to_addr)
                    # 请求成功后，更新全局缓存并视情况落盘
                    self._update_contract_cache(to_addr, is_ct)
                except Exception as e:
                    logger.warning(f"检查地址合约状态失败 {to_addr}: {e}")
                    # 【巧妙处理】：异常时，我们在本次运行的内存中临时当作合约(1)进行阻断。
                    # 但故意不调用 _update_contract_cache 落盘！这样错误判断就不会被永久记录，
                    # 下次跑脚本时还能重新查一遍。
                    self.contract_cache[to_addr] = 0# 异常情况当做合约账户

                    # 2. 读取最终状态
            is_contract_flag = self.contract_cache[to_addr]
            # 如果接收方是智能合约
            if is_contract_flag == 1:
                #【资金覆盖率3】：记录命中跨链/合约拦截的资金 (作为分子的一部分)
                cross_chain_value += val
                h = tx.get("hash")
                if h:
                    h_lower = h.lower()
                    # 在加入待探测列表前，先查本地“户口本”
                    if h_lower in self.known_crosschain_data:
                        known_info = self.known_crosschain_data[h_lower]
                        logger.info(
                            f"✅ 命中本地跨链库 (Tx: {h_lower})，跳过API查询。去向 -> 链: {known_info['Destination_Chain']}, 地址: {known_info['Destination_Address']}")
                        try:
                            # 模拟 API 成功的效果，将记录写入本次追踪的 AML 报告
                            local_poller.save_to_csv(
                                h_lower,
                                known_info["Used_Bridge"],
                                known_info
                            )
                        except Exception as e:
                            logger.error(f"写入跨链报告失败: {e}")
                    else:
                        # 只有本地找不到的，才加入待探测列表
                        contract_tx_hashes.append(h)
                if  not Config.Filter.CONTRACT_TRACE:
                    continue  # 如果配置里不追踪合约流向，直接丢弃这笔交易，不加入后续的跨链探测和地址扩展逻辑

            # ==========================================================
            # E. 金额处理

            try:
                outbound_txs.append(tx)
                # --- 核心修改点：记录该接收地址的最早时间,最早不能比事件发生起点早 ---
                if tx_time >= Config.Filter.START_TIMESTAMP:
                    if to_addr not in earliest_arrival_times:
                        earliest_arrival_times[to_addr] = tx_time
                    else:
                        # 如果当前交易时间更早，更新为更早的时间
                        if tx_time < earliest_arrival_times[to_addr]:
                            earliest_arrival_times[to_addr] = tx_time

            except Exception:
                continue

        # 循环结束后，批量执行异步探测
        if contract_tx_hashes:
            contract_tx_hashes = list(set(contract_tx_hashes))
            if len(contract_tx_hashes) > 100:
                logger.warning(
                    f"地址 {to_addr} 疑似路由/热钱包 (合约交易数 {len(contract_tx_hashes)} > 100)，停止跨链下钻以防爆炸。")
            else:
                logger.info(f"发现 {len(contract_tx_hashes)} 笔转入合约交易，启动批量跨链探测...")
                try:
                    # 针对同步环境（ThreadPool）启动异步任务
                    asyncio.run(self._run_batch_bridge_probing(contract_tx_hashes))
                except Exception as e:
                    logger.error(f"批量跨链探测执行失败: {e}")
        #print("outbound_txs",len(outbound_txs))
        if not outbound_txs:
            return []

        # 3. 排序策略：按金额降序 (用于选出大额接收者)
        outbound_txs.sort(key=lambda x: x["value_decimal"], reverse=True)
        '''
        # 4. 剥离链检测 (如果只有少量转出，全部返回)
        if len(outbound_txs) <= 3:
            candidates = []
            seen_addrs = set()
            for tx in outbound_txs:
                addr = tx["address_to"].lower()
                if addr not in seen_addrs and self._is_valid_neighbor(addr):
                    seen_addrs.add(addr)
                    # 取出记录的最早时间，如果没有则默认为 parent_tx_time 或 事件开始时间
                    p_time = earliest_arrival_times.get(addr, Config.Filter.START_TIMESTAMP)
                    candidates.append({
                        "address": addr,
                        "parent_tx_time": p_time,
                        "parent_address": current_address  # 记录溯源的父地址
                    })
            return candidates
        '''
        # 5. 常规截断策略 (Top Ratio & Max Count)
        keep_count_ratio = max(1, int(len(outbound_txs) * self.top_ratio))
        filtered_by_ratio = outbound_txs[:keep_count_ratio]
        # 按接收地址汇总金额
        receiver_totals = {}
        for tx in filtered_by_ratio:
            to_addr = tx["address_to"].lower()
            if to_addr not in receiver_totals:
                receiver_totals[to_addr] = Decimal(0)
            receiver_totals[to_addr] += tx["value_decimal"]

        sorted_receivers = sorted(receiver_totals.items(), key=lambda item: item[1], reverse=True)
        selected_receivers = []
        cumulative_value = 0
        #print("sorted_receivers:", sorted_receivers)
        # top_receivers = sorted_receivers[:dynamic_max_limit] # 不根据数量截断，根据资金覆盖比例动态调整

        total_outbound_value = sum(val for addr, val in sorted_receivers)
        #print("total_outbound_value:", total_outbound_value)
        # 通过total_outbound_value还可以计算出追踪到的资金占总转出金额的比例，作为后续分析的一个重要指标
        if total_outbound_value == 0:
            return []
        cumulative_value = Decimal(0)
        selected_receivers = []

        coverage_threshold = self.coverage_threshold  # 设置覆盖资金的比例
        #min_addrs = 2  # 哪怕比例够了，也至少追踪前 2 个地址以防万一
        max_addrs = dynamic_max_limit # 哪怕比例不够，最高追踪的地址个数，防止路径爆炸

        for addr, val in sorted_receivers:
            selected_receivers.append((addr, val))
            #【资金覆盖率4】不是新增的部分，是为了计算当前已选地址覆盖了多少资金流向，来决定是否继续添加地址，同时也可以判断追踪了多少资金
            cumulative_value += val
            # 满足以下条件之一则停止：
            # 1. 累计金额已达到总额的 98%，且已选地址数达到最小保障值
            #if cumulative_value >= total_outbound_value * coverage_threshold and len(selected_receivers) >= min_addrs:
            # 1. 累计金额已达到总额的 98%,不强制要求最小保障值，避免粉尘攻击导致的路径爆炸
            if cumulative_value >= total_outbound_value * coverage_threshold:
                break
            # 2. 达到硬性上限，强制截断防止爆炸
            if len(selected_receivers) >= max_addrs:
                break
        #print("selected_receivers:", selected_receivers)

        # 6. 结果封装
        final_candidates = []
        for addr, total_val in selected_receivers:
            if self._is_valid_neighbor(addr):#是不是在最开始就要过滤
                start_time = earliest_arrival_times.get(addr, Config.Filter.START_TIMESTAMP)
                final_candidates.append({
                    "address": addr,
                    "parent_tx_time": start_time,
                    "parent_address": current_address  # 记录溯源的父地址
                })
        expanded_account_count = len(final_candidates)

        # 【资金覆盖率5】：【评估结果】：计算并打印资金覆盖率日志（增加每一个账户扩展的下游个数）
        if total_valid_outbound_value > 0:
            tracked_total = cross_chain_value + cumulative_value
            # 转为 float 方便格式化
            coverage_ratio = float((tracked_total / total_valid_outbound_value) * 100)

            # logger.info(f"📊 [资金覆盖率评估] 溯源节点: {current_address}")
            # logger.info(f"   ├─ 总有效转出金额: {total_valid_outbound_value:.4f}")
            # logger.info(f"   ├─ 跨链/合约流向:  {cross_chain_value:.4f}")
            # logger.info(f"   ├─ 下一跳EOA流向:  {cumulative_value:.4f}")
            # logger.info(f"   └─ 综合资金覆盖率: {coverage_ratio:.2f}%")

            # 调用本地保存
            self._save_coverage_metrics(
                current_address,
                total_valid_outbound_value,
                cross_chain_value,
                cumulative_value,
                coverage_ratio,
                depth=current_depth,
                expanded_count=expanded_account_count  # 传入账户数
            )
        else:
            logger.info(f"📊 [资金覆盖率评估] 溯源节点: {current_address} 无可追踪的有效流出资金。")
            # 即使没有流出，也记录一条 0% 的记录，方便事后分析哪些节点是“断头路”
            self._save_coverage_metrics(
                current_address,
                Decimal(0), Decimal(0), Decimal(0), 0.0, depth=current_depth,expanded_count=expanded_account_count  # 传入账户数
            )
        if expanded_account_count > Config.Filter.MAX_HOP:
            print("May be a potential service provider; skip.")
            return []
        return final_candidates

    def update_known_lists(self, new_normal_addrs: List[str] = None, new_hackers: List[str] = None):
        """
        (可选) 在运行时更新内存中的过滤列表，例如当 LLM 判定某地址为 Normal 后，
        将其加入 normal_addrs 以免重复追踪。
        """
        if new_normal_addrs:
            for addr in new_normal_addrs:
                self.normal_addrs.add(addr.lower())
        if new_hackers:
            for addr in new_hackers:
                self.known_hackers.add(addr.lower())

def get_time(depth: int, address: str):
    source_path = Config.PATHS["source_addr"] / f"bybit_source_addr{depth}.csv"
    if not source_path.exists():
        logger.error(f"未找到当前层地址文件: {source_path}")
        return False
    current_addresses_dict = load_csv_as_dict(source_path)
    # 修改点：建立 地址 -> 入账时间 的映射，用于传给 Filter
    addr_time_map = {}
    address_list = []
    for item in current_addresses_dict:
        if item.get("address"):
            addr = item["address"].strip()
            address_list.append(addr)
            try:
                # 读取上一跳传下来的时间
                addr_time_map[addr.lower()] = int(float(item.get("parent_tx_time", Config.Filter.START_TIMESTAMP)))
            except:
                addr_time_map[addr.lower()] = Config.Filter.START_TIMESTAMP
    return addr_time_map[address.lower()]

if __name__ == "__main__":
    # 单元测试
    address = '0x8B3Cb6Bf982798fba233Bca56749e22EEc42DcF3'
    parent_time = 1721059200 #Config.Filter.START_TIMESTAMP#get_time(13,address)
    expander = GraphExpander()
    next_hops = expander.get_next_hop_candidates(address,parent_time)
    print(next_hops)
    pass
