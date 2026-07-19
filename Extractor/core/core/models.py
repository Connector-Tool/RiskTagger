from dataclasses import dataclass, field
from typing import List, Dict, Union, Optional
from pydantic import BaseModel


@dataclass
class ProjectInfo:
    """项目元数据类：记录黑客事件的基本信息"""
    event_name: Union[str, None] = "n/a"  # 事件名称 (例如: XX交易所被盗事件)
    date: Union[str, None] = "n/a"  # 事件发生时间
    source_report_url: Union[List[str], None] = field(default_factory=list)  # 来源报告的 URL 列表

    def is_empty(self):
        """判断是否没有提取到任何项目信息"""
        return (self.event_name == "n/a" and self.date == "n/a") or (not self.event_name and not self.date)


@dataclass
class Finding:
    """发现项类：记录具体的攻击细节、被盗金额和洗钱路径"""
    id: Union[str, int] = 0  # 编号
    attack_vector: List[str] = field(default_factory=list)  # 攻击向量/手段 (如: 私钥泄露, 闪电贷攻击)
    affected_platform: str = ""  # 受影响平台
    chain: List[str] = field(default_factory=list)  # 涉及的区块链名称
    contract_address: List[str] = field(default_factory=list)  # 被攻击的合约地址
    attacker_addresses: List[str] = field(default_factory=list)  # 黑客控制的地址
    victim_addresses: List[str] = field(default_factory=list)  # 受害者地址
    stolen_amount_usd: Union[int, float, str] = 0  # 被盗的美元总价值
    stolen_amount_token: Dict[str, Union[int, float, str]] = field(default_factory=dict)  # 被盗代币详情及数量
    laundering_methods: List[str] = field(default_factory=list)  # 洗钱方法 (如: 混币器, 跨链桥)
    laundering_path: List[str] = field(default_factory=list)  # 洗钱资金转移路径
    evidence_snippets: List[str] = field(default_factory=list)  # 从报告中提取的支撑性证据(原句截图)


@dataclass
class MapReduceResult:
    """Map-Reduce 操作返回的复合结果结构"""
    project_info: ProjectInfo = field(default_factory=ProjectInfo)
    findings: List[Finding] = field(default_factory=list)


@dataclass
class Context:
    """Map-Reduce 在不同阶段传递的上下文结构"""
    index: int = 0  # 文本片段的索引
    document: str = ""  # 切割后的文本片段内容
    response: str = ""  # LLM 处理该片段返回的提取结果
    length: int = 0  # 该片段计算得出的 Token 长度


class Report(BaseModel):
    """最终输出给用户的综合报告模型"""
    path: str = ""  # 原文件路径
    project_info: ProjectInfo = field(default_factory=ProjectInfo)
    findings: List[Finding] = field(default_factory=list)

    def append_finding(self, finding: Finding):
        self.findings.append(finding)