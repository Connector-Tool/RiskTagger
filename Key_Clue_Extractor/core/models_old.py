from dataclasses import dataclass
from dataclasses import field
from typing import List, Dict, Union, Optional, Literal
from pydantic import BaseModel, RootModel, Field


@dataclass
class ProjectInfo(BaseModel):
    # 攻击事件基本信息
    event_name: Union[str, None] = "n/a"        # 攻击事件名称（如“Bybit 黑客攻击事件”）
    date: Union[str, None] = "n/a"              # 发生时间
    source_report_url: Union[str, List[str], None] = "n/a"
    #source_report_url: Union[str, None] = "n/a" # 原始报告或新闻链接

    def is_empty(self):
        if (self.event_name == "n/a" and self.date == "n/a") or (
            not self.event_name and not self.date
        ):
            return True
        return False


@dataclass
class Finding(BaseModel):
    # 技术相关信息
    attack_vector: Union[str, None] = "n/a"     # 攻击手法/漏洞类型（如私钥泄露、钓鱼、跨链桥漏洞）
    affected_platform: Union[str, None] = "n/a" # 被攻击平台（交易所/协议名）
    chain: Union[str, List, None] = "n/a"       # 涉及区块链（如 Ethereum, Tron, BSC）
    contract_address: Union[str, List, None] = "n/a" # 相关合约或协议地址
    #attacker_addresses: Union[List[str], None] = None # 攻击者钱包地址
    #victim_addresses: Union[List[str], None] = None   # 受害者钱包地址（如交易所热钱包）
    attacker_addresses: Union[str, List[str], None] = None
    victim_addresses: Union[str, List[str], None] = None

    # 资金流与规模
    stolen_amount_usd: Union[float, None] = None # 被盗金额（美元计）
    stolen_amount_token: Union[Dict, None] = None # 被盗代币明细 {token: amount}
    laundering_methods: Union[List[str], None] = None # 洗钱方式（混币器、跨链桥、CEX提现）
    laundering_path: Union[List[str], None] = None   # 资金流路径（链A → Mixer → CEX）

    # 威胁分析
    severity: Union[str, None] = "n/a"          # 严重程度（高/中/低）
    impact_scope: Union[str, None] = "n/a"      # 影响范围（单一交易所、多链生态）
    attribution: Union[str, None] = "n/a"       # 攻击归因（如 Lazarus Group, 未知黑客）

    evidence_snippets: Union[List[str], None] = None
    notes:Union[str, None] = "n/a"

@dataclass
class MapReduceResult(BaseModel):
    project_info: ProjectInfo = field(default_factory=ProjectInfo)
    #findings: List[Finding] = field(default_factory=list)
    findings: Union[Finding, List[Finding]] = field(default_factory=list)


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
