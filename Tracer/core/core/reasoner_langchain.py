import json
import re
import os
import pandas as pd
from typing import Dict, Optional, TypedDict
import threading
from pathlib import Path

# --- 新增 LangChain 相关库 ---
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain.memory import VectorStoreRetrieverMemory
from langchain.chains import ConversationChain, LLMChain
from langchain.prompts import PromptTemplate


# 引入配置和工具
from config.settings import Config
from utils.logger import logger
from utils.file_utils import save_json


class RiskResult(TypedDict):
    address: str
    risk_level: str  # High, Medium, Low, None
    raw_response: str
    parsed_details: Dict

class RiskResultMemory(TypedDict): #用于存储到记忆库中用于检索（只保留每个维度的结果字符串）
    address: str
    risk_level: str  # High, Medium, Low, None
    a_transaction_patterns: str
    b_fund_flows: str
    c_associated_addresses: str
    d_temporal_behavioral_signs: str


class LaunderingReasoner:
    """
    负责调用 LLM 进行洗钱风险推理 (CoT + Reflection)。
    [升级] 集成 LangChain + Chroma 实现长期记忆与自动存储。
    对应 RiskTagger 架构中的 Reasoner 模块。
    """

    # 原始任务指令模板 (作为 Chain 的 input)
    # 注意：去掉了开头的 System Role 定义，交给 Chain 的 Template 统一管理
    PROMPT_TEMPLATE = """
The core address to analyze is {target_address}. Follow this structured process:

# Context
Target Address: `{target_address}`
Data Source: `{formatted_analysis}`

# Core Analysis Rules
1. **Risk Catalyst vs. Volume**: A massive inflow from a flagged source is a red flag; a negligible amount (e.g., dusting) in a high-volume account suggests a "tainting attack."
2. **Account Maturity Stabilizer**: High transaction counts and a long lifespan (years) suggest a legitimate user. "Professional relays" typically exhibit short lifespans or "burst" activity.
3. **Flow Substance**: Focus on the **Layering Rate**.Laundering addresses show "Pass-through" patterns (Inbound ≈ Outbound within a short window). Legitimate accounts show complex, non-linear flows and significant fund retention.
4. If the account maturity score is High, the risk level shall be directly determined as Low..

# Structured Analysis Process
1. **Maturity & Exposure**: Calculate Account Age, Total Tx Count, and the **Exposure Ratio** (Suspicious Inflow / Total Historical Volume).
2. **Transaction Patterns**: Identify "Full-in, Full-out" behavior. Contrast this with the account's historical average transaction size.
3. **Fund Flows**:  Determine if the address is a "blind relay" (e.g., >95% flow-through) or an organic aggregator.
4. [**Temporal Signs**: Distinguish between automated "washing" cycles (rapid bursts) and organic human activity.

# Classification Criteria
- **High Suspicion**: A short-lived account with a high Velocity Rate (e.g., more than 90% outflow) and a high Exposure Ratio involving funds from flagged sources.
- **Medium Suspicion**: Mature account with a sudden, significant high-risk inflow that deviates from its historical baseline.
- **Low Suspicion**: Mature account where flagged inflow is a tiny fraction of total volume or funds are not immediately "relayed".

# Internal Reflection (Anti-False-Positive)
- **The Taint Test**: Does this account have a large number of transactions (e.g., 1,000 or more)? If yes, don't over-weight a single small suspicious inflow..
- **The Relay Test**: Did the funds actually "pass through," or did they mix into a large, pre-existing balance?
- **The Outlier Test**: Is the suspicious transaction a clear deviation from the account's recent activity, such as its activity over the past six months?
If the account maturity score is High, the risk level shall be directly determined as Low.(Accounts confirmed to be money laundering addresses are excluded.)

# Output Format (JSON)
{{
    "suspicion_level": "High/Medium/Low/No Suspicion",
    "account_maturity_score": "High/Medium/Low (Age/Volume)",
    "a_transaction_patterns": {{
        "result": "Pattern vs. Historical baseline",
        "evidence": "Ratio, retention, and exposure %"
    }},
    "b_fund_flows": {{
        "result": "Relay vs. Organic movement",
        "evidence": "Layering rate and path description"
    }},
    "c_associated_addresses": {{
        "result": "Risk association vs. Diversity",
        "evidence": "Flagged addresses impact on total balance"
    }},
    "d_temporal_behavioral_signs": {{
        "result": "Automated vs. Human",
        "evidence": "Activity window analysis"
    }}
}}
"""

    def __init__(self):
        # 1. 设置环境变量 (LangChain 组件通常需要读取 env)
        os.environ['OPENAI_API_KEY'] = Config.LLM.API_KEY
        if Config.LLM.BASE_URL:
            os.environ['OPENAI_BASE_URL'] = Config.LLM.BASE_URL

        self.output_dir = Config.PATHS["llm_result"]
        self.memory_lock = threading.Lock()  # 新增锁，确保多线程环境下对 memory 的访问安全
        # 2. 初始化 LangChain 的 LLM
        self.llm = ChatOpenAI(
            model=Config.LLM.MODEL_NAME,
            request_timeout=180,
            temperature=Config.LLM.TEMPERATURE,
            max_retries=0,
            max_tokens=Config.LLM.MAX_TOKENS,
            api_key=Config.LLM.API_KEY,
            base_url=Config.LLM.BASE_URL
        )

        # 3. 初始化 Embedding 模型 (用于向量化记忆)
        self.embedding_model = OpenAIEmbeddings(
            model=Config.LLM.MODEL_NAME_EMB,  # 阿里云的通用嵌入模型
            api_key=Config.LLM.API_KEY_EMB,
            base_url=Config.LLM.BASE_URL_EMB,
            check_embedding_ctx_length=False,
            request_timeout=60
        )

        # 4. 初始化/加载本地向量数据库 (Chroma)
        # 记忆库存储路径: data/llm_result/memory_db
        self.persist_dir = str(Config.PATHS["memory_db"])

        logger.info(f"正在加载向量记忆库: {self.persist_dir}")
        self.vectorstore = Chroma(
            embedding_function=self.embedding_model,
            persist_directory=self.persist_dir
        )

        # 5. 配置记忆组件 (Retriever)
        # k=1 表示每次分析新地址时，只提取 1 条最相关的历史经验，避免干扰
        retriever = self.vectorstore.as_retriever(search_kwargs=dict(k=1))
        self.memory = VectorStoreRetrieverMemory(retriever=retriever)

        # 6. 创建带有记忆槽位的全局 Prompt Template
        chain_template = """You are a professional blockchain money laundering detection analyst.
Your judgment must be based on data and be logically rigorous, without subjective assumptions.

Here is relevant historical analysis or context from our knowledge base that might help:
{history}

Current Analysis Task:
{input}"""

        self.chain_prompt = PromptTemplate(
            input_variables=["history", "input"],
            template=chain_template
        )
        # 7. 初始化对话链 (手动管理记忆存取)
        self.chain = LLMChain(
            llm=self.llm,
            prompt=self.chain_prompt,
            # 默认是false，开启会打印每次调用细节，调试时可用
            #verbose=True
        )

        # 简单的映射表
        self.risk_level_map = {
            "high": "High",
            "medium": "Medium",
            "mid": "Medium",
            "low": "Low",
            "no suspicion": "No Suspicion",
            "none": "None"
        }
        # 插入背景知识 (如果记忆库为空)
        self._seed_background_knowledge()

    def _seed_background_knowledge(self):
        """
        向向量数据库中注入一条初始的背景知识
        """
        # 检查当前向量库中的文档数量
        count = self.vectorstore._collection.count()

        if count == 0:
            logger.info("检测到记忆库为空，正在注入初始背景知识...")
            base_event_name = Config.BASE_EVENT_NAME
            base_addr0_path = Config.PATHS["base_source_addr"] / f"{base_event_name}_source_addr0.csv"

            if not base_addr0_path.exists():
                logger.warning(f"未找到基础种子文件，跳过事实注入: {base_addr0_path}")
                return
            try:
                # 1. 读取 CSV 文件
                df = pd.read_csv(base_addr0_path)
                seed_addresses = df['address'].unique().tolist()

                for addr in seed_addresses:
                    # 这里定义你想要 LLM 永远记住的“背景知识”
                    background_input = f"Facts about address: {addr}"
                    background_output = (
                        f"GROUND TRUTH: The address {addr} is a money laundering seed for the {base_event_name} event."
                    )

                    # 使用 memory 的接口保存，这样格式能与后续自动生成的记忆保持一致
                    self.memory.save_context(
                        {"input": background_input},
                        {"output": background_output}
                    )
                    logger.info("初始背景知识注入成功。")
            except Exception as e:
                logger.error(f"读取种子文件或注入记忆时发生错误: {e}")

    def _build_prompt(self, context: Dict) -> str:
        """填充 Prompt 模板"""
        # 将 Context 转换为 JSON 字符串嵌入 Prompt
        # 为了节省 Token，可以选择性地只放入摘要和 Top 交易
        analysis_subset = {
            "summary": context.get("transaction_flow_summary"),
            "top_transactions": context.get("top_transactions"),
            "related_addresses_count": len(context.get("related_addresses", [])),
            "token_types": context.get("total_token_types")
        }

        formatted_analysis = json.dumps(analysis_subset, ensure_ascii=False, indent=2)

        return self.PROMPT_TEMPLATE.format(
            target_address=context["target_address"],
            formatted_analysis=formatted_analysis
        )

    def _call_llm(self, current_prompt_content: str, address_info: str) -> str:
        """
        参数说明：
        current_prompt_content: 这是完整的包含指令的 Prompt (用于给 LLM 看)
        address_info: 这是你只想存下来的精简信息 (比如 "地址0x123，涉嫌洗钱，高风险")
        """

        # 1. 【手动检索历史】
        # 这里的 inputs 随便填一个跟当前任务相关的关键词，或者就用 address_info，会根据它去 Chroma 检索
        # load_memory_variables 会去 Chroma 找最相似的过往案例
        # core/reasoner_langchain.py 中的 _call_llm 方法
        try:
            # 1. 检索阶段日志
            logger.info(f"开始检索向量记忆...")
            history_data = self.memory.load_memory_variables({"input": address_info})
            history_text = history_data.get("history", "")
            logger.info(f"记忆检索完成，准备调用 LLM...")  # 如果不打印这一行，说明卡在 Embedding 了

            # 2. 调用 LLM
            res = self.chain.invoke({
                "history": history_text,
                "input": current_prompt_content
            })
            logger.info(f"LLM 响应成功。")
            return res['text'].strip()
        except Exception as e:
            logger.error(f"LLM 调用链异常: {e}")
            return ""

    def _parse_json_response(self, text: str) -> Dict:
        """清洗和提取 JSON (保持不变)"""
        try:
            # 1. 尝试直接解析
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 2. 提取 Markdown 代码块中的 JSON
        pattern = r"```json\s*(\{.*?\})\s*```"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # 3. 提取最外层大括号
        pattern_loose = r"\{.*\}"
        match_loose = re.search(pattern_loose, text, re.DOTALL)
        if match_loose:
            try:
                return json.loads(match_loose.group(0))
            except json.JSONDecodeError:
                pass

        return {}

    def _save_structured_memory(self, context: Dict, parsed_result: Dict, raw_response: str):
        """
        将结构化的分析结果存入向量记忆库
        """
        target_addr = context["target_address"]

        # 1. 提取结构化字段 (对应 RiskResultMemory 的定义)
        # 注意：这里需要防御性编程，因为 parsed_result 可能解析失败或字段缺失
        memory_data: RiskResultMemory = {
            "address": target_addr,
            "risk_level": parsed_result.get("suspicion_level", "Unknown"),
            "a_transaction_patterns": parsed_result.get("a_transaction_patterns", {}).get("result", "N/A"),
            "b_fund_flows": parsed_result.get("b_fund_flows", {}).get("result", "N/A"),
            "c_associated_addresses": parsed_result.get("c_associated_addresses", {}).get("result", "N/A"),
            "d_temporal_behavioral_signs": parsed_result.get("d_temporal_behavioral_signs", {}).get("result", "N/A")
        }

        # 2. 构造【Input】(搜索索引)
        # 这是未来检索的“钩子”。当未来分析新地址时，我们希望通过类似的“风险特征”搜到这个案例。
        # 建议包含：地址 + 简单的交易流摘要 (来自 context)
        search_key = f"Address: {target_addr}. Risk Profile: {context.get('transaction_flow_summary', '')}"

        # 3. 构造【Output】(历史经验内容)
        # 这是 LLM 读到的“历史”。最好直接存成 JSON 字符串，因为 LLM 读 JSON 最快最准。
        # 我们把上面提取的 clean memory 序列化
        memory_content = json.dumps(memory_data, ensure_ascii=False)

        # 4. 执行保存
        with self.memory_lock:  # 加锁确保写入安全
            logger.info(f"正在保存结构化记忆: {target_addr}")
            self.memory.save_context(
                {"input": search_key},
                {"output": memory_content}
            )

    def _determine_risk_level(self, parsed_json: Dict, raw_text: str) -> str:
        """
        根据 JSON 或原始文本确定风险等级
        """
        # 优先从 JSON 获取
        level_str = parsed_json.get("suspicion_level", "").lower()

        # 如果 JSON 解析失败或字段为空，回退到文本搜索
        if not level_str:
            lower_text = raw_text.lower()
            # 简单的关键词匹配优先级
            if "suspicion level: high" in lower_text or '"suspicion_level": "High"' in lower_text:
                level_str = "high"
            elif "suspicion level: medium" in lower_text or '"suspicion_level": "Medium"' in lower_text:
                level_str = "medium"
            elif "suspicion level: low" in lower_text or '"suspicion_level": "Low"' in lower_text:
                level_str = "low"
            elif "No Suspicion" in lower_text:
                level_str = "none"

        # 映射到标准输出
        for key, val in self.risk_level_map.items():
            if key in level_str:
                return val
        return "Unknown"

    def analyze_address(self, context: Dict) -> RiskResult:
        """主入口：分析单个地址"""
        target_addr = context["target_address"]

        # 1. 检查是否存在已有的 JSON 结果 (文件缓存)
        result_file = self.output_dir / f"{target_addr}.json"
        if result_file.exists():
            try:
                with open(result_file, 'r', encoding='utf-8') as f:
                    saved_data = json.load(f)
                    # 简单的校验
                    if "risk_level" in saved_data:
                        logger.info(f"读取已有 LLM 分析结果: {target_addr} -> {saved_data['risk_level']}")
                        return saved_data
            except Exception:
                pass

        # 2. 构建任务 Prompt
        prompt = self._build_prompt(context)
        # 构建一个精简描述用于存记忆 (可以利用你定义的 RiskResultMemory 结构)
        # 传输给 LLM 的是完整 Prompt，这个simple_info 用于检索记忆时，只需包含关键信息（避免检索太多内容）
        simple_info = f"Address: {target_addr}, Risk Indicators: {context.get('transaction_flow_summary')}"

        # 3. 调用 LLM (通过 LangChain + Memory)
        logger.info(f"正在调用 LLM 分析地址: {target_addr} (含记忆检索) ...")
        raw_response = self._call_llm(prompt, simple_info)

        if not raw_response:
            logger.error(f"LLM 未返回有效内容: {target_addr}")
            return {"address": target_addr, "risk_level": "Error", "raw_response": "", "parsed_details": {}}

        # 4. 解析结果
        parsed_json = self._parse_json_response(raw_response)
        risk_level = self._determine_risk_level(parsed_json, raw_response)

        # 5. 保存结构化记忆
        # 只有当解析成功（哪怕部分成功）时才保存，避免把 Error 存进去
        if parsed_json:
            self._save_structured_memory(context, parsed_json, raw_response)

        # 6. 保存结果到文件
        result: RiskResult = {
            "address": target_addr,
            "risk_level": risk_level,
            "raw_response": raw_response,
            "parsed_details": parsed_json
        }
        save_json(result, result_file)
        txt_path = self.output_dir / f"{target_addr}.txt"
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(raw_response)

        logger.info(f"LLM 分析完成: {target_addr} -> {risk_level}")

        return result


if __name__ == "__main__":
    # 单元测试
    # reasoner = LaunderingReasoner()
    # mock_context = {"target_address": "0x123", "transaction_flow_summary": {}, "top_transactions": []}
    # res = reasoner.analyze_address(mock_context)
    # print(res)
    pass