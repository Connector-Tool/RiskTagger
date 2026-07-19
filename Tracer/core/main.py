import json
import pandas as pd
import time
import sys
from typing import List, Dict, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from pathlib import Path
import shutil

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRACER_ROOT = Path(__file__).resolve().parents[1]
TRACER_CORE_ROOT = Path(__file__).resolve().parent
for path in (PROJECT_ROOT, TRACER_ROOT, TRACER_CORE_ROOT):
    path_text = str(path)
    if path_text in sys.path:
        sys.path.remove(path_text)
    sys.path.insert(0, path_text)

# 引入核心模块
from config.settings import Config
from utils.logger import logger
from utils.file_utils import load_csv_as_dict, save_csv, ensure_dir

from core.fetcher import TransactionFetcher
from core.translator import DataTranslator
from core.reasoner_langchain import LaunderingReasoner  # 实现了记忆功能的版本
#from core.reasoner_without_COT import LaunderingReasoner  # 不使用 COT 的版本，速度更快但可能准确率略有下降,消融实验1
#from core.reasoner_langchain_without_memory import LaunderingReasoner  # 不使用 Memory 的版本,消融实验2
#from core.reasoner_langchain_without_reflection import LaunderingReasoner  # 不使用 reflection 的版本,消融实验4
from core.filter import GraphExpander
#from core.filter_without_filter import GraphExpander #消融Filter模块，直接扩展所有转出边，不进行任何智能过滤,消融实验3

class RiskTaggerRunner:
    """
    RiskTagger 主控程序
    流程: Seed -> Fetch -> Translate -> Reason -> Filter -> Next Hop -> Loop
    """

    def __init__(self, event_name: str):
        self.event_name = event_name

        # 初始化各个核心组件
        self.fetcher = TransactionFetcher()
        self.translator = DataTranslator(event_name)
        self.reasoner = LaunderingReasoner()
        self.expander = GraphExpander()

        # 运行时状态
        self.current_hacker_addrs: List[Dict] = []  # 当前层确定的黑客/洗钱地址
        self.current_normal_addrs: List[str] = []  # 当前层确定的正常地址
        self.current_high_risk_addrs: List[Dict] = []  # 当前层高风险地址集合(需要继续扩展的）

        # 确保目录存在
        Config.ensure_dirs()

    def initialize_seeds(self, report_path: str = None) -> None:
        """
        初始化种子地址 (Depth 0)
        """
        # 1.直接读取
        depth_0_path = Config.PATHS["source_addr"] / f"{self.event_name}_source_addr0.csv"

        if depth_0_path.exists():
            logger.info(f"发现已存在的种子文件: {depth_0_path}")
            return
        # 2.尝试从 BASE_EVENT_NAME 目录或模板文件复制
        # 注意：这里假设你有 self.base_event_name 属性，或者你可以直接替换为具体的字符串
        base_event_name = Config.BASE_EVENT_NAME
        base_addr0_path = Config.PATHS["base_source_addr"] / f"{base_event_name}_source_addr0.csv"

        if base_addr0_path.exists():
            logger.info(f"检测到基础种子文件，正在从 {base_event_name} 复制...")
            try:
                shutil.copy(base_addr0_path, depth_0_path)
                logger.info(f"成功创建新事件种子文件: {depth_0_path}")
                return  # 复制成功后直接返回，无需再从报告提取
            except Exception as e:
                logger.error(f"复制种子文件失败: {e}")

        #3.从报告中提取
        if not report_path:
            # 尝试默认路径
            report_path =Config.PATHS["source_report_path"] / f"{self.event_name}_report.pdf.json"

        logger.info(f"正在从报告提取种子地址: {report_path}")
        seeds = self.fetcher.extract_seed_addresses(report_path)

        if seeds:
            # 初始化 parent_tx_time，如果没有配置 START_TIMESTAMP，默认为 0
            start_time = getattr(Config.Filter, 'START_TIMESTAMP', 0)
            data = [{"address": addr, "parent_tx_time": start_time} for addr in seeds]
            save_csv(data, depth_0_path)
            logger.info(f"种子地址已保存: {len(seeds)} 个")
        else:
            logger.error("未找到种子地址，请检查报告路径或手动创建 source_addr0.csv")

    def _analyze_single_address(self, address: str) -> Dict:
        """
        单地址分析流水线: Translate -> Reason
        """
        # 增加本地结果缓存机制，避免重复调用 LLM 分析同一地址
        output_dir = Config.PATHS["llm_result"]
        result_file = output_dir / f"{address}.json"
        if result_file.exists():
            try:
                with open(result_file, 'r', encoding='utf-8') as f:
                    saved_data = json.load(f)
                    # 简单的校验
                    if "risk_level" in saved_data:
                        logger.info(f"读取已有 LLM 分析结果: {address} -> {saved_data['risk_level']}")
                        return saved_data
            except Exception:
                pass
        try:
            # 1. 转换数据
            context = self.translator.generate_llm_context(address)
            if not context:
                # 无法生成 Context (无数据或被白名单过滤) -> 视为无效/正常
                return {"address": address, "risk_level": "Skip", "reason": "No Data/Whitelisted"}

            # 2. LLM 推理
            result = self.reasoner.analyze_address(context)
            #print(result)
            return result
        except Exception as e:
            logger.error(f"分析地址出错 {address}: {e}")
            return {"address": address, "risk_level": "Error", "reason": str(e)}

    def run_layer(self, depth: int):
        """
        执行特定层级的完整处理流程
        """
        logger.info(f"\n{'=' * 20} Processing Depth {depth} {'=' * 20}")

        # 1. 加载当前层待处理地址
        source_path = Config.PATHS["source_addr"] / f"{self.event_name}_source_addr{depth}.csv"
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
                    addr_time_map[addr.lower()] = int(float(item.get("parent_tx_time", Config.Filter.START_TIMESTAMP )))
                except:
                    addr_time_map[addr.lower()] = Config.Filter.START_TIMESTAMP

        # 去重并提取地址列表
        address_list = list(set(address_list))

        if not address_list:
            logger.warning("当前层没有地址需要处理。")
            return False

        logger.info(f"当前层 ({depth}) 共有 {len(address_list)} 个地址待处理")
        if len(address_list) >200:
            print("address too long")
            return False                # 可以设置阈值，避免错误结果导致成本过高（正确运行时应注释掉）

        # ---------------- Stage 1: Fetching ----------------
        logger.info(">>> Stage 1: Fetching Transactions...")
        self.fetcher.fetch_batch(address_list)

        # ---------------- Stage 2: Analysis (LLM) ----------------
        logger.info(">>> Stage 2: Analyzing Risk (LLM)...")

        # 清空状态
        self.current_hacker_addrs = []
        self.current_normal_addrs = []
        self.current_high_risk_addrs = []  # 确保清空高风险列表

        with ThreadPoolExecutor(max_workers=Config.Concurrency.PROCESS_WORKERS or 4) as executor:
            future_to_addr = {
                executor.submit(self._analyze_single_address, addr): addr
                for addr in address_list
            }

            with tqdm(total=len(address_list), desc="Analyzing") as pbar:
                for future in as_completed(future_to_addr):
                    res = future.result()
                    addr = res["address"]
                    #addr = original_target_addr
                    risk = res.get("risk_level", "None")

                    if risk in ["High", "Medium", "high-ML", "mid-ML", "Low", "low-ML"]:
                        self.current_hacker_addrs.append({
                            "address": addr,
                            "name_tag": f"{risk}_Layer{depth}",
                            "label": "1"
                        })
                        if risk in ["High", "Medium", "high-ML", "mid-ML"]:
                            self.current_high_risk_addrs.append({
                                "address": addr,
                                "name_tag": f"{risk}_Layer{depth}",
                                "label": "1"
                            })
                    elif risk in ["None", "Skip"]:
                        self.current_normal_addrs.append({
                            "address": addr,
                            "name_tag": f"{risk}_Layer{depth}",
                            "label": "0"
                        })

                    pbar.update(1)

        # 保存本层结果
        self._save_layer_results()

        # ==========================================================
        # 【跨层动态知识库同步 (内存级别)】
        # 将本层 LLM 跑出的新结果直接注入到内存，下一层秒级生效，无需重读硬盘
        # ==========================================================
        new_normals = [i['address'] for i in self.current_normal_addrs]
        new_hackers = [i['address'] for i in self.current_hacker_addrs]

        # 1. 同步给 Filter (防止重复扩展这些节点)
        self.expander.update_known_lists(new_normal_addrs=new_normals, new_hackers=new_hackers)

        # 2. 同步给 Translator (提升下一层 LLM 的情境感知能力)
        if hasattr(self.translator, 'label_cache'):
            for item in self.current_normal_addrs:
                self.translator.label_cache[item['address'].lower()] = "AI-Normal"
            for item in self.current_hacker_addrs:
                # item['name_tag'] 可能是 "High_Layer1"，切割出 "High"
                risk_level = item['name_tag'].split('_')[0]
                self.translator.label_cache[item['address'].lower()] = f"AI-{risk_level}"

        logger.info(f"动态知识库已同步: 新增 {len(new_normals)} 个正常节点, {len(new_hackers)} 个风险节点。")
        # ==========================================================


        # ---------------- Stage 3: Expansion (Next Hop) ----------------
        logger.info(">>> Stage 3: Expanding Graph (Next Hop)...")

        targets_to_expand = [item["address"] for item in self.current_high_risk_addrs]

        if not targets_to_expand:
            logger.info("本层无高风险节点，停止扩展。")
            return False

        logger.info(f"本层发现 {len(targets_to_expand)} 个高风险节点，准备扩展...")

        # 动态更新 Filter
        self.expander.update_known_lists(new_normal_addrs=[i['address'] for i in self.current_normal_addrs])

        # 【修正 1】使用字典来存储下一层候选者，key是地址，value是包含时间戳的字典
        next_layer_candidates_dict = {}

        with ThreadPoolExecutor(max_workers=Config.Concurrency.PROCESS_WORKERS or 4) as executor:
            future_to_addr = {
                executor.submit(
                    self.expander.get_next_hop_candidates,
                    addr,
                    addr_time_map.get(addr.lower(),Config.Filter.START_TIMESTAMP),  # 传入上一跳时间
                    depth  # 传入当前层级
                ): addr
                for addr in targets_to_expand
            }

            for future in tqdm(as_completed(future_to_addr), total=len(targets_to_expand), desc="Expanding"):
                try:
                    candidates = future.result()  # filter.py 返回 List[Dict]

                    for cand in candidates:
                        # 处理 filter.py 返回的每一个候选者
                        # 确保 cand 是字典且包含 address
                        if isinstance(cand, dict) and "address" in cand:
                            addr_str = cand["address"]
                            # 1. 获取新候选路径的时间
                            # 建议转为 int 或 float 进行数值比较
                            new_cand_time = int(float(cand.get('parent_tx_time', Config.Filter.START_TIMESTAMP)))

                            # 2. 检查逻辑：地址不存在 OR (地址存在 AND 新时间更早)
                            if addr_str not in next_layer_candidates_dict:
                                # 情况A: 第一次遇到该地址，直接添加
                                next_layer_candidates_dict[addr_str] = cand
                            else:
                                # 情况B: 地址已存在，检查是否需要更新为更早的时间
                                existing_cand = next_layer_candidates_dict[addr_str]
                                existing_time = int(float(existing_cand.get('parent_tx_time', Config.Filter.START_TIMESTAMP)))

                                # 如果新发现的路径时间比记录中的更早，则覆盖旧记录（更新为最优路径）
                                if new_cand_time < existing_time:
                                    # 保留最早时间，但合并父地址
                                    cand["parent_address"] = existing_cand["parent_address"] + ";" + cand[
                                        "parent_address"]
                                    next_layer_candidates_dict[addr_str] = cand
                                elif new_cand_time >= existing_time:
                                    # 时间不更新，但也把当前父地址追加进去
                                    existing_cand["parent_address"] = existing_cand["parent_address"] + ";" + cand[
                                        "parent_address"]
                        elif isinstance(cand, str):
                            # 兼容旧代码返回字符串的情况 (虽然现在 filter 改了，但为了健壮性保留)
                            if cand not in next_layer_candidates_dict:
                                next_layer_candidates_dict[cand] = {"address": cand, "parent_tx_time": Config.Filter.START_TIMESTAMP}

                except Exception as e:
                    logger.error(f"扩展地址时发生错误: {e}")

        # 保存下一层地址
        # 【修正 2】将字典的值转为列表进行保存，确保 parent_tx_time 被写入 CSV
        if next_layer_candidates_dict:
            next_layer_list = list(next_layer_candidates_dict.values())
            next_path = Config.PATHS["source_addr"] / f"{self.event_name}_source_addr{depth + 1}.csv"
            save_csv(next_layer_list, next_path)
            logger.info(f"已生成下一层 ({depth + 1}) 地址文件，共 {len(next_layer_list)} 个地址")
            return True
        else:
            logger.info("未发现更多可疑下游地址，追踪结束。")
            return False

    def _save_layer_results(self):
        """将本层的分析结果追加写入到总表中"""
        if self.current_hacker_addrs:
            hacker_path = Config.PATHS["risktagger_hack"] / "accounts-hacker.csv"
            old_hackers = load_csv_as_dict(hacker_path)
            existing_addrs = {row["address"] for row in old_hackers}
            new_rows = [row for row in self.current_hacker_addrs if row["address"] not in existing_addrs]

            if new_rows:
                final_data = old_hackers + new_rows
                save_csv(final_data, hacker_path)
                logger.info(f"已追加 {len(new_rows)} 个黑客/洗钱账户")

        if self.current_normal_addrs:
            normal_path = Config.PATHS["normal_addr_info"] / "normal_addr_info.csv"
            old_normal = load_csv_as_dict(normal_path)
            existing_addrs = {row["address"] for row in old_normal}
            new_rows = [row for row in self.current_normal_addrs if row["address"] not in existing_addrs]

            if new_rows:
                final_data = old_normal + new_rows
                save_csv(final_data, normal_path)
                logger.info(f"已追加 {len(new_rows)} 个正常账户")

    def run(self, start_depth=0, max_depth=10):
        """主循环"""
        logger.info(f"启动 RiskTagger 追踪任务: {self.event_name}")

        # 如果从 0 开始，尝试初始化种子
        if start_depth == 0:
            self.initialize_seeds()

        for d in range(start_depth, max_depth):
            has_next = self.run_layer(d)
            if not has_next:
                logger.info("追踪链路中断或完成。")
                break

            time.sleep(2)


if __name__ == "__main__":
    EVENT_NAME = Config.EVENT_NAME
    START_DEPTH =0
    MAX_DEPTH = 10

    runner = RiskTaggerRunner(EVENT_NAME)
    runner.run(start_depth=START_DEPTH, max_depth=MAX_DEPTH)
