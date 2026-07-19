import subprocess
import os
import json
import csv
from pathlib import Path
from typing import List, Dict, Union, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import time
# 引入我们刚才定义的配置和工具
from config.settings import Config
from utils.logger import logger
from utils.file_utils import ensure_dir

import sys
import subprocess
import os
import json
import random
from pathlib import Path
from typing import List, Dict, Union
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import time

from config.settings import Config
from utils.logger import logger
from utils.file_utils import ensure_dir


class TransactionFetcher:
    """
    负责调用 BlockchainSpider 抓取链上交易数据
    """

    def __init__(self):
        self.spider_cwd = Config.SPIDER_DIR
        self.output_base = Config.PATHS["raw_tx_data"]

    def _check_existing_data(self, address: str) -> bool:
        target_file = self.output_base / address / "AccountTransferItem.csv"
        if target_file.exists():
            try:
                with open(target_file, 'r', encoding='utf-8') as f:
                    lines = [line.strip() for line in f if line.strip()]
                    if len(lines) > 1:
                        return True
            except Exception:
                pass
        return False

    def run_spider_single(self, address: str, check_existing: bool = True) -> bool:
        if not address.lower().startswith("0x"):
            logger.error(f"无效地址格式: {address}")
            return False

        if check_existing and self._check_existing_data(address):
            return True

        output_dir = str(self.output_base.absolute())
        ensure_dir(self.output_base)

        api_keys_str = ",".join(Config.Spider.API_KEYS)

        cmd = [
            sys.executable, "-m", "scrapy", "crawl", "txs.blockscan",
            "-a", f"source={address}",
            "-a", f"apikeys={api_keys_str}",
            "-a", f"endpoint={Config.Spider.ENDPOINT}",
            "-a", f"strategy={Config.Spider.STRATEGY}",
            "-a", f"enable={Config.Spider.TYPE}",
            "-a", f"out={output_dir}/{address}",
            "-a", f"max_pages=1",
            "-a", f"max_page_size=1000",
            "-a", f"depth=0"
        ]

        try:
            # 优化点 1：引入随机延迟 (Jitter)，防止多个 Scrapy 进程在同一毫秒发起请求
            time.sleep(random.uniform(0.5, 3.0))

            result = subprocess.run(
                cmd,
                cwd=self.spider_cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=Config.Spider.TIMEOUT
            )

            if result.returncode == 0:
                if self._check_existing_data(address):
                    return True
                else:
                    logger.warning(f"爬虫返回成功但文件未生成/为空: {address}")
                    # 打印出输出以便排查是被 block 了还是没数据
                    logger.debug(f"爬虫输出摘要: {result.stdout[:500]}")
                    return False
            else:
                logger.error(f"爬虫执行失败 {address}: {result.stderr[:200]}...")
                return False

        except subprocess.TimeoutExpired as e:
            logger.warning(f"爬虫超时 ({Config.Spider.TIMEOUT}s): {address}")
            return False  # 优化点 2：超时应该视为失败，让外层重试，而不是返回 True
        except Exception as e:
            logger.error(f"调用爬虫进程异常 {address}: {str(e)}")
            return False

    def fetch_batch(self, addresses: List[str], max_workers: int = None, max_retries: int = 20) -> Dict[str, str]:
        if not addresses:
            return {}

        # 优化点 3：强制降低外部多进程并发数，建议不要超过你 API Key 的数量
        workers =max_workers or Config.Spider.MAX_WORKERS

        final_results = {addr: "pending" for addr in addresses}
        pending_addresses = list(addresses)

        logger.info(f"开始并行爬取 {len(addresses)} 个地址 (最大重试: {max_retries}, 并发进程数: {workers})...")

        for attempt in range(1, max_retries + 1):
            if not pending_addresses:
                break

            if attempt > 1:
                logger.warning(f"⚠️ 第 {attempt} 次尝试: 重试 {len(pending_addresses)} 个失败地址...")
                # 优化点 4：退避算法（Exponential Backoff），被拒绝后等待时间加长
                time.sleep(5 * attempt)

            current_failed = []

            with ThreadPoolExecutor(max_workers=workers) as executor:
                future_to_addr = {
                    executor.submit(self.run_spider_single, addr): addr
                    for addr in pending_addresses
                }

                desc = "Fetch Txs" if attempt == 1 else f"Retry Txs (Att {attempt})"

                with tqdm(total=len(pending_addresses), desc=desc, unit="addr") as pbar:
                    for future in as_completed(future_to_addr):
                        addr = future_to_addr[future]
                        try:
                            success = future.result()
                            if success:
                                final_results[addr] = "success"
                            else:
                                final_results[addr] = "failed"
                                current_failed.append(addr)
                        except Exception as e:
                            logger.error(f"线程异常 {addr}: {e}")
                            final_results[addr] = "error"
                            current_failed.append(addr)

                        pbar.update(1)

            pending_addresses = current_failed

        success_count = list(final_results.values()).count("success")
        if success_count == len(addresses):
            logger.info(f"✅ 完美！本层 {len(addresses)} 个地址已全部成功爬取。")
        else:
            logger.error(f"❌ 警告：已达到最大重试次数，仍有 {len(pending_addresses)} 个地址彻底失败。")

        return final_results

    @staticmethod
    def extract_seed_addresses(report_path: Union[str, Path]) -> List[str]:
        """
        从分析报告 JSON 中提取初始攻击者地址 (对应原 json_to_csv)
        """
        report_path = Path(report_path)
        if not report_path.exists():
            logger.error(f"报告文件不存在: {report_path}")
            return []
            
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            attacker_addresses = []
            # 兼容 findings 列表结构
            for finding in data.get("findings", []):
                attacker_addresses.extend(finding.get("attacker_addresses", []))
            
            # 去重并统一格式
            unique_addrs = list(set([addr.strip().lower() for addr in attacker_addresses if addr]))
            logger.info(f"从报告提取到 {len(unique_addrs)} 个种子地址")
            return unique_addrs
            
        except Exception as e:
            logger.error(f"解析报告失败: {e}")
            return []
'''
if __name__ == "__main__":
    # 简单的单元测试
    fetcher = TransactionFetcher()
    # 测试单个地址 (Vitalik's address for test)
    fetcher.run_spider_single("0x8107a003db76130810a7a08a1cc094cb2d1de6ed")
    pass
'''