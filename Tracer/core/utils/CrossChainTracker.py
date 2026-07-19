import asyncio
import aiohttp
import time
import os
import csv
import random
from config.settings import Config
from pathlib import Path
from utils.file_utils import ensure_dir

# 跨平台文件锁支持
msvcrt = None
fcntl = None
try:
    import msvcrt  # Windows 文件锁
    USING_WINDOWS = True
except ImportError:
    import fcntl  # Linux 文件锁
    USING_WINDOWS = False


class AsyncBridgePoller:
    def __init__(self):
        # 🚨 [扩充] 增加了 4 个原有桥 + 3 个新桥/混币器检测
        self.bridge_configs = {
            # 原有的跨链桥
            "LayerZero/Stargate": "https://scan-api.layerzero-scan.com/v1/messages/tx/{tx_hash}",
            "Across": "https://app.across.to/api/deposit/status?originChainId=1&depositTxnRef={tx_hash}",
            "Wormhole": "https://api.wormholescan.io/api/v1/operations/{tx_hash}",
            "Celer": "https://cbridge-prod2.celer.network/v2/getTransferStatus?transfer_id={tx_hash}",
            "THORChain": "https://thornode.ninerealms.com/thorchain/tx/{tx_hash_upper_no_0x}",
            "Axelar/Squid": "https://api.axelarscan.io/cross-chain/transfers?txHash={tx_hash}",
            "Hop_Protocol": "https://explorer-api.hop.exchange/v1/transfers?transactionHash={tx_hash}",
            "deBridge": "https://descan.debridge.finance/v1/tx/{tx_hash}",
            "Synapse": "https://explorer.omnirpc.io/api/v1/transactions/{tx_hash}",

            # 🔥 [新增] Orbiter Finance (L2 主流跨链桥)
            "Orbiter_Finance": "https://api.orbiter.finance/explore/v3/tx/info?hash={tx_hash}",

            # 🔥 [新增] Circle CCTP (原生 USDC 跨链协议，此处示例查询 Ethereum Domain=0 的消息)
            "Circle_CCTP": "https://iris-api.circle.com/v1/messages/0/{tx_hash}",

            # 🌪️ [新增] Tornado.Cash 混币池检测 (需填入你的 Etherscan API Key)
            "Tornado_Cash(Mixer)": f"https://api.etherscan.io/api?module=proxy&action=eth_getTransactionByHash&txhash={{tx_hash}}&apikey={os.getenv('ETHERSCAN_API_KEY', '')}"
        }
        self.timeout = aiohttp.ClientTimeout(total=2)  # 节点增多，略微放宽超时避免漏报

        # 处理路径
        self.output_csv = Path(Config.PATHS['crosschain_data']) / "aml_crosschain_report.csv"
        ensure_dir(self.output_csv.parent)
        self.csv_lock_file = str(self.output_csv) + '.lock'  # 创建锁文件路径

    def is_valid_response(self, bridge_name, data):
        """假阳性误判拦截，确保 API 返回的是有效的交易数据"""
        if not data: return False

        # 原有的桥校验...
        if bridge_name == "THORChain":
            return isinstance(data, dict) and "error" not in data and "observed_tx" in data
        elif bridge_name == "Celer":
            return isinstance(data, dict) and "err" not in data
        elif bridge_name == "LayerZero/Stargate":
            return isinstance(data, dict) and bool(data.get("messages"))
        elif bridge_name == "Across":
            return isinstance(data, dict) and "error" not in data and ("status" in data or "depositId" in data)
        elif bridge_name == "Wormhole":
            return (isinstance(data, list) and len(data) > 0) or (
                    isinstance(data, dict) and "error" not in data and "message" not in data)
        elif bridge_name == "Axelar/Squid":
            return isinstance(data, dict) and "data" in data and len(data["data"]) > 0
        elif bridge_name == "Hop_Protocol":
            return isinstance(data, dict) and "data" in data and len(data["data"]) > 0
        elif bridge_name == "deBridge":
            return isinstance(data, dict) and "error" not in data and "txHash" in data
        elif bridge_name == "Synapse":
            return isinstance(data, dict) and "data" in data and bool(data["data"])

        # 🔥 新增桥校验
        elif bridge_name == "Orbiter_Finance":
            return isinstance(data, dict) and data.get("code") == 0 and bool(data.get("data"))

        elif bridge_name == "Circle_CCTP":
            return isinstance(data, dict) and "messages" in data and len(data["messages"]) > 0

        elif bridge_name == "Tornado_Cash(Mixer)":
            # 提取交易详情中的 "To" 地址，判断是否属于已知的 Tornado Cash 存款合约
            result = data.get("result")
            if not isinstance(result, dict): return False
            to_address = result.get("to", "")
            if not to_address: return False

            # 主流 Tornado Cash 存款合约 (示例: 0.1 ETH, 1 ETH, 10 ETH, 100 ETH 池)
            tornado_contracts = [
                "0x12d66f87a04a9e220743712ce6d9bb1b5616b8fc",
                "0x47ce0c6ed5b0ce3d3a51fdb1c52dc66a7c3c2936",
                "0x910cbd523d972eb0a6f4cae44a8d1ce4dae501d0",
                "0xa160cdab225685da0d56aa342d9aa5e547846a84",
                "0xd90e2f925DA726b50C4Ed8D0Fb90Ad053324F31b"
            ]
            return to_address.lower() in tornado_contracts

        return False

    def lock_file(self, file_obj):
        """跨平台文件锁定"""
        if USING_WINDOWS:
            # Windows 锁定
            try:
                # IMPORTANT:
                # - Lock a fixed region starting at offset 0 so every process contends on the same bytes.
                # - Lock more than 1 byte to avoid edge cases with different file pointers.
                file_obj.seek(0)
                msvcrt.locking(file_obj.fileno(), msvcrt.LK_LOCK, 4096)
                return True
            except:
                return False
        else:
            # Linux/Unix 锁定
            try:
                fcntl.flock(file_obj.fileno(), fcntl.LOCK_EX)
                return True
            except:
                return False

    def unlock_file(self, file_obj):
        """跨平台文件解锁"""
        if USING_WINDOWS:
            try:
                file_obj.seek(0)
                msvcrt.locking(file_obj.fileno(), msvcrt.LK_UNLCK, 4096)
                return True
            except:
                return False
        else:
            try:
                fcntl.flock(file_obj.fileno(), fcntl.LOCK_UN)
                return True
            except:
                return False

    async def fetch_bridge_api(self, session, bridge_name, url):
        try:
            async with session.get(url, timeout=self.timeout) as response:
                if response.status == 200:
                    data = await response.json()
                    if self.is_valid_response(bridge_name, data):
                        return {"bridge": bridge_name, "found": True, "raw_data": data}
        except Exception:
            pass
        return {"bridge": bridge_name, "found": False, "raw_data": None}

    def parse_bridge_data(self, bridge_name, raw_data):
        """解析数据，提取目标链和黑客接收地址"""
        parsed_result = {
            "Destination_Chain": "Unknown",
            "Destination_Address": "Unknown",
            "Status": "Unknown"
        }

        try:
            # 原有的桥解析逻辑...
            if bridge_name == "THORChain":
                obs_tx = raw_data.get("observed_tx", {})
                tx_info = obs_tx.get("tx", {})
                memo = tx_info.get("memo", "")
                parsed_result["Status"] = obs_tx.get("status", "Unknown")
                if memo.startswith("SWAP") or memo.startswith("="):
                    parts = memo.split(":")
                    if len(parts) >= 3:
                        parsed_result["Destination_Chain"] = parts[1].split(".")[0]
                        parsed_result["Destination_Address"] = parts[2]
                else:
                    parsed_result["Destination_Chain"] = tx_info.get("chain", "Unknown")
                    parsed_result["Destination_Address"] = tx_info.get("to_address", "Unknown")

            elif bridge_name == "LayerZero/Stargate":
                msg = raw_data.get("messages", [{}])[0]
                parsed_result["Destination_Chain"] = msg.get("dstChainKey", str(msg.get("dstChainId", "Unknown")))
                parsed_result["Destination_Address"] = msg.get("dstUaAddress", msg.get("dstAddress", "Unknown"))
                parsed_result["Status"] = msg.get("status", "Unknown")

            elif bridge_name == "Across":
                parsed_result["Destination_Chain"] = f"ChainID: {raw_data.get('destinationChainId', 'Unknown')}"
                parsed_result["Destination_Address"] = raw_data.get("recipient", "Unknown")
                parsed_result["Status"] = raw_data.get("status", "Unknown")

            elif bridge_name == "Axelar/Squid":
                tx_data = raw_data.get("data", [{}])[0]
                parsed_result["Destination_Chain"] = tx_data.get("source", {}).get("destinationChain", "Unknown")
                parsed_result["Destination_Address"] = tx_data.get("source", {}).get("recipientAddress", "Unknown")
                parsed_result["Status"] = tx_data.get("status", "Unknown")

            elif bridge_name == "Hop_Protocol":
                tx_data = raw_data.get("data", [{}])[0]
                parsed_result["Destination_Chain"] = tx_data.get("destinationChain", "Unknown")
                parsed_result["Destination_Address"] = tx_data.get("recipient", "Unknown")
                parsed_result["Status"] = "Completed" if tx_data.get("destinationTxHash") else "Pending"

            elif bridge_name == "deBridge":
                parsed_result["Destination_Chain"] = f"ChainID: {raw_data.get('dstChainId', 'Unknown')}"
                parsed_result["Destination_Address"] = raw_data.get("receiver", raw_data.get("dstAddress", "Unknown"))
                parsed_result["Status"] = "Success" if raw_data.get("isExecuted") else "Pending"

            elif bridge_name == "Synapse":
                tx_data = raw_data.get("data", {})
                parsed_result["Destination_Chain"] = tx_data.get("toChain", "Unknown")
                parsed_result["Destination_Address"] = tx_data.get("toAddress", "Unknown")
                parsed_result["Status"] = "Success"

            # 🔥 新增的桥解析逻辑
            elif bridge_name == "Orbiter_Finance":
                tx_data = raw_data.get("data", [{}])[0]
                parsed_result["Destination_Chain"] = str(tx_data.get("toChain", "Unknown"))
                parsed_result["Destination_Address"] = tx_data.get("toAddress", "Unknown")
                parsed_result["Status"] = "Success" if tx_data.get("state") == 1 else "Pending"

            elif bridge_name == "Circle_CCTP":
                msg = raw_data.get("messages", [{}])[0]
                parsed_result["Destination_Chain"] = f"DomainID: {msg.get('destinationDomainId', 'Unknown')}"
                parsed_result["Destination_Address"] = msg.get("recipient", "Unknown")
                parsed_result["Status"] = "Attested"

            elif bridge_name == "Tornado_Cash(Mixer)":
                # AML 核心追踪点：资金在这里断了线，需要上报给调查人员
                parsed_result["Destination_Chain"] = "Ethereum (Mixed)"
                parsed_result["Destination_Address"] = "⚠️ Hidden by Tornado.Cash Pool"
                parsed_result["Status"] = "Money Laundered / Deposited"

        except Exception as e:
            print(f"解析 {bridge_name} 时发生错误: {e}")

        return parsed_result

    def save_to_csv(self, tx_hash, bridge_name, parsed_data):
        """将提取的情报追加保存到本地 CSV 表格中（多进程强一致版本）

        Guarantees (when all writers use this function):
        - At most one process writes to the CSV at a time.
        - CSV header is written exactly once.
        - No interleaved/partial CSV rows.

        Design:
        - Use a dedicated lock file opened in append mode (no truncation) and lock it.
        - While holding the lock, append one CSV row using the stdlib csv module.
        """
        new_row = {
            "Source_Tx_Hash": tx_hash,
            "Used_Bridge": bridge_name,
            "Destination_Chain": parsed_data["Destination_Chain"],
            "Destination_Address": parsed_data["Destination_Address"],
            "CrossChain_Status": parsed_data["Status"],
            "Scan_Time": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        # 固定列顺序，避免不同进程/不同 pandas 版本导致列顺序不一致
        fieldnames = [
            "Source_Tx_Hash",
            "Used_Bridge",
            "Destination_Chain",
            "Destination_Address",
            "CrossChain_Status",
            "Scan_Time",
        ]

        # 使用文件锁确保多进程安全写入
        lock_acquired = False
        # 等待锁时间：建议生产环境可设小(如 3s)以避免单条交易阻塞过久；
        # 压测/高并发写入时建议更大(如 30s)以减少丢写概率。
        # 可通过环境变量 RT_CSV_LOCK_WAIT 覆盖(单位：秒)。
        try:
            max_wait_time = float(os.getenv('RT_CSV_LOCK_WAIT', '30'))
        except Exception:
            max_wait_time = 30.0
        wait_time = 0

        # 退避参数(单位：秒)
        # - RT_CSV_LOCK_BACKOFF_START: 初始等待
        # - RT_CSV_LOCK_BACKOFF_MAX: 最大等待上限
        try:
            backoff = float(os.getenv('RT_CSV_LOCK_BACKOFF_START', '0.02'))
        except Exception:
            backoff = 0.02
        try:
            backoff_max = float(os.getenv('RT_CSV_LOCK_BACKOFF_MAX', '0.5'))
        except Exception:
            backoff_max = 0.5

        lock_file = None

        try:
            # 尝试获取锁，最多等待 max_wait_time 秒
            while wait_time < max_wait_time:
                try:
                    # Use append mode to avoid truncating the lock file (truncation can cause subtle races).
                    # newline='' is important for csv module on Windows.
                    lock_file = open(self.csv_lock_file, 'a+', encoding='utf-8', newline='')
                    lock_acquired = self.lock_file(lock_file)
                    if lock_acquired:
                        # 成功获取锁：在持锁期间完成“header判定 + 追加写入”，避免重复 header / 行交错
                        ensure_dir(self.output_csv.parent)

                        file_exists = os.path.exists(self.output_csv)
                        file_is_empty = (not file_exists) or (os.path.getsize(self.output_csv) == 0)

                        # Use stdlib csv for deterministic writing and less overhead than pandas
                        with open(self.output_csv, 'a', encoding='utf-8-sig', newline='') as out_f:
                            writer = csv.DictWriter(out_f, fieldnames=fieldnames)
                            if file_is_empty:
                                writer.writeheader()
                            writer.writerow(new_row)
                            out_f.flush()
                            try:
                                os.fsync(out_f.fileno())
                            except Exception:
                                # Some filesystems/OS combinations may not support fsync; best effort.
                                pass
                        break  # 写入成功，退出循环
                except IOError:
                    pass

                # 如果锁文件已创建但获取锁失败，关闭它
                if lock_file:
                    try:
                        lock_file.close()
                    except:
                        pass
                    lock_file = None

                # 等待一段时间后重试：指数退避 + 抖动，减少高并发自旋开销
                sleep_s = min(backoff, max(0.0, max_wait_time - wait_time))
                # jitter in [0, 20%]
                sleep_s += random.random() * (sleep_s * 0.2)
                time.sleep(sleep_s)
                wait_time += sleep_s
                backoff = min(backoff_max, backoff * 2)

            if not lock_acquired:
                print(f"警告：无法获取文件锁，数据写入失败: {tx_hash}")

        finally:
            # 确保锁被释放（如果已获取）
            if lock_acquired and lock_file:
                try:
                    self.unlock_file(lock_file)
                    lock_file.close()
                except:
                    pass

    async def poll_transaction(self, tx_hash, session=None):
        tx_hash_upper_no_0x = (tx_hash[2:] if tx_hash.startswith("0x") else tx_hash).upper()

        async def fetch_all(sess):
            tasks = []
            for bridge_name, url_template in self.bridge_configs.items():
                url = url_template.format(tx_hash=tx_hash, tx_hash_upper_no_0x=tx_hash_upper_no_0x)
                tasks.append(asyncio.create_task(self.fetch_bridge_api(sess, bridge_name, url)))
            return await asyncio.gather(*tasks)

        if session is None:
            async with aiohttp.ClientSession() as new_sess:
                results = await fetch_all(new_sess)
        else:
            results = await fetch_all(session)

        found_bridges = [res for res in results if res["found"]]

        if found_bridges:
            match = found_bridges[0]
            bridge_name = match['bridge']
            raw_data = match['raw_data']

            parsed_data = self.parse_bridge_data(bridge_name, raw_data)
            self.save_to_csv(tx_hash, bridge_name, parsed_data)

            return match
        else:
            return None
