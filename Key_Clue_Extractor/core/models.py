from dataclasses import dataclass
from dataclasses import field
from typing import List, Dict, Union, Optional, Literal
from pydantic import BaseModel, RootModel, Field


@dataclass
class ProjectInfo:
    # 项目信息类，存储区块链安全事件的基本元数据
    event_name: Union[str, None] = "n/a"                                        # 事件名称，描述安全事件的标题或标识符
    date: Union[str, None] = "n/a"                                              # 事件发生日期，格式通常为YYYY-MM-DD
    source_report_url: Union[List[str], None] = field(default_factory=list)     # 来源报告URL列表，指向描述此事件的外部报告或文章
    
    def is_empty(self):
        # 检查项目信息是否为空（只有默认值或无值）
        if (self.event_name == "n/a" and self.date == "n/a") or (
            not self.event_name and not self.date
        ):
            return True
        return False

@dataclass
class Finding:
    # 发现类，存储单个安全事件的详细技术信息和取证数据
    
    id: Union[str, int] = 0                                         # 发现项的唯一标识符，用于区分同一事件中的多个发现
    attack_vector: List[str] = field(default_factory=list)          # 攻击向量列表，描述攻击者利用的攻击方法或漏洞类型
    affected_platform: str = ""                                     # 受影响的平台或项目名称，标识被攻击的目标
    chain: List[str] = field(default_factory=list)                  # 受影响的区块链网络列表，如Ethereum、Bitcoin、Tron等
    contract_address: List[str] = field(default_factory=list)       # 相关合约地址列表，包括被攻击合约或恶意合约地址
    attacker_addresses: List[str] = field(default_factory=list)     # 攻击者地址列表，标识攻击者使用的区块链地址
    victim_addresses: List[str] = field(default_factory=list)       # 受害者地址列表，标识被盗资金的原地址
    stolen_amount_usd: Union[int, float] = 0                        # 被盗资金总额（以美元计），量化攻击造成的财务损失
    stolen_amount_token: Dict[str, Union[int, float]] = field(default_factory=dict)  # 被盗代币明细字典，键为代币符号，值为对应代币的数量
    laundering_methods: List[str] = field(default_factory=list)     # 洗钱方法列表，描述攻击者转移和隐藏资金的技术
    laundering_path: List[str] = field(default_factory=list)        # 洗钱路径列表，描述资金在地址和网络间的流动轨迹
    evidence_snippets: List[str] = field(default_factory=list)      # 证据片段列表，包含支持发现的文本证据或交易链接

@dataclass
class MapReduceResult:
    project_info: ProjectInfo = field(default_factory=ProjectInfo)
    findings: List[Finding] = field(default_factory=list)


@dataclass
class Context:
    """
    The context message that is passed between the different stages of the pipeline.
    """
    # document_pdf and llm_response
    index: int = 0
    document: str = ""
    response: str = ""
    length: int = 0


# class CWE:
#     def __init__(
#         self, ID: int, Name: str, Description: str, Abstraction: str, Mapping: str
#     ):
#         self.ID = ID
#         self.Name = Name
#         self.Description = Description
#         self.Abstraction: Literal["Pillar", "Class", "Base", "Variant"] = Abstraction
#         self.Mapping: Literal[
#             "Allowed", "Allowed-with-Review", "Discouraged", "Prohibited"
#         ] = Mapping
#         self.Peer: List["CWE"] = []
#         self.Parent: List["CWE"] = []
#         self.Child: List["CWE"] = []

#     def add_child(self, child_cwe: "CWE"):
#         self.Child.append(child_cwe)
#         child_cwe.Parent.append(self)


class CWE(BaseModel):
    ID: int
    Name: str
    Description: str = ""
    Abstraction: Literal["Pillar", "Class", "Base", "Variant", "Compound"]
    Mapping: Literal["Allowed", "Allowed-with-Review", "Discouraged", "Prohibited"]
    Peer: List = Field(default_factory=list)
    Parent: List = Field(default_factory=list)
    Child: List[int] = Field(default_factory=list)

    def __str__(self) -> str:
        return f"CWE-{self.ID}: {self.Name}"

    def __hash__(self):
        return hash(str(self))

    def add_child(self, child_cwe: "CWE"):
        self.Child.append(child_cwe)
        child_cwe.Parent.append(self)


class CWEDatabase(RootModel):
    root: Dict[str, CWE]

    def get_by_id(self, id: int | str):
        name = f"CWE-{id}"
        return self.root[name]

    def get_by_name(self, name: str):
        return self.root[name]


@dataclass
# use for get code( url/address for fetch)
class Address:
    address: str
    network: str = ""
    account_type: str = ""


@dataclass
class GithubUrl:
    href: str
    git_url: str = ""
    proj: str = ""
    owner: str = ""
    repo: str = ""
    branch: str = ""
    dir_name: str = ""
    file_name: str = ""
    fragment: str = ""


@dataclass
class FetchObject:
    fetcher_name: str
    target: str


class Report(BaseModel):
    # finally complete object of the audit report
    path: str = ""
    project_info: ProjectInfo = field(default_factory=ProjectInfo)
    findings: List[Finding] = field(default_factory=list)

    def append_finding(self, finding: Finding):
        self.findings.append(finding)


class History(BaseModel):
    finished: List = []
    failed: List = []
