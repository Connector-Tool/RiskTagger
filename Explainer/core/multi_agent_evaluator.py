import os
import json
import re
import concurrent.futures
import sys
from pathlib import Path
from openai import OpenAI
from pydantic import BaseModel
from typing import List, Dict

from dotenv import load_dotenv

load_dotenv()


# ==========================================
# 1. 强约束的评估输出结构 (Pydantic Schema)
# ==========================================
class OverallAssessment(BaseModel):
    overall_score: float
    summary: str


class EvaluationResult(BaseModel):
    accuracy_score: float
    accuracy_reasoning: List[str]
    logic_score: float
    logic_reasoning: List[str]
    professionalism_score: float
    professionalism_reasoning: List[str]
    actionability_score: float
    actionability_reasoning: List[str]
    overall_assessment: OverallAssessment


# ==========================================
# 2. 多智能体评估器类 (支持多线程并行)
# ==========================================
class MultiAgentEvaluator:
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def _extract_json(self, text: str) -> dict:
        try:
            text = text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            return json.loads(text.strip())
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            raise ValueError("无法从模型输出中提取有效的 JSON")

    def build_evaluation_prompt(self, gt_json_data: dict, gt_txt_stats: str, gt_txt_reasoner: str,
                                generated_report: str) -> str:
        system_prompt = """你是一位拥有 10 年经验的资深 Web3 安全审计专家和加密货币反洗钱（AML）调查员。
你的任务是根据提供的【人工核查过的准确事实基准 (Ground Truth)】，对自动化系统生成的【Markdown 取证报告】进行盲测打分。

【特别说明】：本次输入的事实基准由三个独立维度的文件组成，以提供全局一致的上下文。
1. 文件1 (JSON)：案发初始线索与结构化信息（事件背景）。
2. 文件2 (TXT)：追踪器跑出的各层级宏观统计分布数据。
3. 文件3 (TXT)：追踪器提取的核心风险节点微观推理日志。

请综合这三份数据的上下文来进行评判。如果在报告中出现了这三份基准中完全没有的统计数额或凭空捏造的具体地址，则视为幻觉。

评分采用 5 分制（1-5分），必须涵盖以下四个核心维度：
1. 准确性 (accuracy_score)：报告内容是否与原始证据及基准结论严格一致，是否存在“幻觉”。
2. 逻辑严密性 (logic_score)：洗钱路径推导是否符合 AML 红旗指标，上下文因果是否合理。
3. 专业性 (professionalism_score)：术语使用是否符合 Web3 安全规范，结构排版是否专业客观。
4. 取证价值 (actionability_score)：提炼的洞察和建议能否有效辅助执法人员进行资产追踪与冻结。

【强制要求】：你的输出必须是一个纯 JSON 对象，格式严格如下，不要输出任何 JSON 之外的问候语或解释文字！
{
  "accuracy_score": 5,
  "accuracy_reasoning": ["理由1...", "理由2..."],
  "logic_score": 4,
  "logic_reasoning": ["理由1...", "理由2..."],
  "professionalism_score": 5,
  "professionalism_reasoning": ["理由1...", "理由2..."],
  "actionability_score": 4,
  "actionability_reasoning": ["理由1...", "理由2..."],
  "overall_assessment": {
    "overall_score": 4,
    "summary": "综合评价总结..."
  }
}
"""
        user_prompt = f"""
========================================
【事实基准文件 1：初始线索 (JSON)】
{json.dumps(gt_json_data, ensure_ascii=False, indent=2)}

========================================
【事实基准文件 2：宏观层级统计 (TXT)】
{gt_txt_stats}

========================================
【事实基准文件 3：核心节点推理日志 (TXT)】
{gt_txt_reasoner}

========================================
【待评估的自动生成报告 (Generated Report)】
{generated_report}
========================================
请根据上述基准对照，给出你的交叉打分（仅输出 JSON）：
"""
        return system_prompt, user_prompt

    def evaluate_with_openai_compatible(self, model_name: str, api_key: str, base_url: str, sys_prompt: str,
                                        user_prompt: str) -> dict:
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=240.0)
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        return self._extract_json(response.choices[0].message.content)

    # 【新增】将单个 Agent 的执行逻辑剥离出来，以便交给线程池执行
    def _process_single_agent(self, agent: dict, sys_prompt: str, user_prompt: str):
        model = agent['model_name']
        raw_save_path = os.path.join(self.output_dir, f"evaluation_raw_{model.replace('/', '_')}.json")

        # 检查是否已有缓存
        if os.path.exists(raw_save_path):
            print(f"⏩ 发现已有 [{model}] 的评估结果，跳过 API 调用，直接读取 -> {raw_save_path}")
            with open(raw_save_path, 'r', encoding='utf-8') as f:
                result = json.load(f)
            EvaluationResult(**result)  # 验证格式
            return model, result, True  # True 表示是从本地读取的

        # 如果没有缓存，则发起 API 请求
        print(f"🚀 正在呼叫 Agent: [{model}] (并行处理中)...")
        if agent['provider'] == 'openai':
            result = self.evaluate_with_openai_compatible(
                model, agent['api_key'], agent.get('base_url'), sys_prompt, user_prompt
            )
        else:
            raise ValueError(f"未知的 provider: {agent['provider']}")

        EvaluationResult(**result)  # 验证返回格式

        # 保存结果
        with open(raw_save_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"✅ [{model}] 评分完成，原始日志已保存 -> {raw_save_path}")

        return model, result, False  # False 表示是新生成的

    def run_multi_agent_evaluation(self, agents_config: List[dict], gt_json_data: dict, gt_txt_stats: str,
                                   gt_txt_reasoner: str, report_path: str):
        with open(report_path, 'r', encoding='utf-8') as f:
            generated_report = f.read()

        sys_prompt, user_prompt = self.build_evaluation_prompt(gt_json_data, gt_txt_stats, gt_txt_reasoner,
                                                               generated_report)

        all_results = {}
        summary_scores = {
            "accuracy": [], "logic": [], "professionalism": [], "actionability": [], "overall": []
        }
        # 【新增】定义一个字典，用于存放各模型的具体得分详情
        model_scores_breakdown = {}

        # 【核心修改】：使用 ThreadPoolExecutor 开启多线程并行调度
        print(f"⚡ 启动多线程并发评估，最大并发数: {len(agents_config)}")
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(agents_config)) as executor:
            # 提交所有任务到线程池
            future_to_agent = {
                executor.submit(self._process_single_agent, agent, sys_prompt, user_prompt): agent
                for agent in agents_config
            }

            try:
                for future in concurrent.futures.as_completed(future_to_agent, timeout=300.0):
                    agent = future_to_agent[future]
                    model = agent['model_name']
                    try:
                        returned_model, result, is_cached = future.result()

                        # 1. 统计全局分数列表（用于计算平均分）
                        summary_scores["accuracy"].append(result["accuracy_score"])
                        summary_scores["logic"].append(result["logic_score"])
                        summary_scores["professionalism"].append(result["professionalism_score"])
                        summary_scores["actionability"].append(result["actionability_score"])
                        summary_scores["overall"].append(result["overall_assessment"]["overall_score"])

                        # 2. 【核心更新】记录每个模型的细粒度得分
                        model_scores_breakdown[returned_model] = {
                            "accuracy_score": result["accuracy_score"],
                            "logic_score": result["logic_score"],
                            "professionalism_score": result["professionalism_score"],
                            "actionability_score": result["actionability_score"],
                            "overall_score": result["overall_assessment"]["overall_score"]
                        }

                    except concurrent.futures.TimeoutError:
                        print(f"⏰ [{model}] 评估超时！未能在此次运行中获取到结果。")
                    except Exception as exc:
                        print(f"❌ [{model}] 评估过程发生异常: {exc}")

            except concurrent.futures.TimeoutError:
                print("🚨 总体并行任务执行超时！部分 Agent 的结果可能丢失。")

        print("\n========================================")
        print("📊 多智能体交叉评分汇总 (Multi-Agent Scoring Summary)")
        print("========================================")

        # 3. 【核心更新】重构最终的统计报告结构
        final_summary = {
            "event_name": os.path.basename(os.path.dirname(report_path)),
            "global_averages": {},
            "detailed_model_scores": model_scores_breakdown
        }

        for dim, scores in summary_scores.items():
            if scores:
                avg_score = sum(scores) / len(scores)
                final_summary["global_averages"][f"{dim}_avg"] = round(avg_score, 2)
                print(f"- {dim.capitalize().ljust(15)} : 平均 {avg_score:.2f} 分")

        # 保存新的结构化汇总报告
        summary_path = os.path.join(self.output_dir, "evaluation_summary_cross_agent.json")
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(final_summary, f, ensure_ascii=False, indent=2)
        print("========================================")
        print(f"📁 包含各模型详细得分的成绩单已保存至 -> {summary_path}\n")


# ==========================================
# 3. 执行入口
# ==========================================
if __name__ == "__main__":
    AGENTS_CONFIG = [
        {"model_name": "deepseek-v4-flash", "provider": "openai", "api_key": os.getenv("DS_API_KEY"),
         "base_url": os.getenv("DS_BASE_URL")},
        {"model_name": "deepseek-v4-pro", "provider": "openai", "api_key": os.getenv("DS_API_KEY"),
         "base_url": os.getenv("DS_BASE_URL")},
        {"model_name": "qwen3-max", "provider": "openai", "api_key": os.getenv("QWEN_API_KEY"),
         "base_url": os.getenv("QWEN_BASE_URL")},
        {"model_name": "claude-opus-4-7", "provider": "openai", "api_key": os.getenv("N1N_API_KEY"),
         "base_url": os.getenv("N1N_BASE_URL")},
        {"model_name": "gpt-5.4", "provider": "openai", "api_key": os.getenv("N1N_API_KEY"),
         "base_url": os.getenv("N1N_BASE_URL")},
        {"model_name": "gemini-3.5-flash", "provider": "openai", "api_key": os.getenv("N1N_API_KEY"),
         "base_url": os.getenv("N1N_BASE_URL")},
        {"model_name": "Pro/zai-org/GLM-5.1", "provider": "openai", "api_key": os.getenv("SF_API_KEY"),
         "base_url": os.getenv("SF_BASE_URL")},
    ]

    #EVENT_NAME = "HTX_&_Heco_Bridge"
    #EVENT_NAME = "Li_Fi"
    #EVENT_NAME = "VulcanForged"
    #EVENT_NAME = "Ronin"
    EVENT_NAME = "Bybit"


    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from project_config import EXTRACTOR_OUTPUT_ROOT, TRACER_DATA_ROOT

    GT_JSON_FILE = EXTRACTOR_OUTPUT_ROOT / EVENT_NAME / f"{EVENT_NAME}_report.json"
    GT_TXT_FILE = TRACER_DATA_ROOT / EVENT_NAME / "data" / "result" / "hack_statistics_summary.txt"
    GT_REASONER_FILE = TRACER_DATA_ROOT / EVENT_NAME / "Experiment" / "merge" / "sample_reasoner.txt"

    with open(GT_JSON_FILE, 'r', encoding='utf-8') as f_json:
        gt_json_data = json.load(f_json)

    with open(GT_TXT_FILE, 'r', encoding='utf-8') as f_txt:
        gt_txt_content = f_txt.read().strip()

    try:
        with open(GT_REASONER_FILE, 'r', encoding='utf-8') as f_reasoner:
            gt_reasoner_content = f_reasoner.read().strip()
    except FileNotFoundError:
        print(f"⚠️ 未找到第三个文件 {GT_REASONER_FILE}，将使用空文本。")
        gt_reasoner_content = "暂无具体推理日志文件。"

    GENERATED_REPORT_FILE = EXTRACTOR_OUTPUT_ROOT / EVENT_NAME / f"{EVENT_NAME}_comprehensive_evidence_report.md"
    OUTPUT_DIR = EXTRACTOR_OUTPUT_ROOT / EVENT_NAME / "evaluation"

    evaluator = MultiAgentEvaluator(output_dir=OUTPUT_DIR)
    evaluator.run_multi_agent_evaluation(
        agents_config=AGENTS_CONFIG,
        gt_json_data=gt_json_data,
        gt_txt_stats=gt_txt_content,
        gt_txt_reasoner=gt_reasoner_content,
        report_path=GENERATED_REPORT_FILE
    )
