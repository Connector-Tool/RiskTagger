from dataclasses import dataclass
from dataclasses import field
from typing import List, Dict, Union, Optional, Literal
from pydantic import BaseModel, RootModel, Field


@dataclass
class ProjectInfo(BaseModel):
    # �����¼�������Ϣ
    event_name: Union[str, None] = "n/a"        # �����¼����ƣ��硰Bybit �ڿ͹����¼�����
    date: Union[str, None] = "n/a"              # ����ʱ��
    source_report_url: Union[str, List[str], None] = "n/a"
    #source_report_url: Union[str, None] = "n/a" # ԭʼ�������������

    def is_empty(self):
        if (self.event_name == "n/a" and self.date == "n/a") or (
            not self.event_name and not self.date
        ):
            return True
        return False


@dataclass
class Finding(BaseModel):
    # ���������Ϣ
    attack_vector: Union[str, None] = "n/a"     # �����ַ�/©�����ͣ���˽Կй¶�����㡢������©����
    affected_platform: Union[str, None] = "n/a" # ������ƽ̨��������/Э������
    chain: Union[str, List, None] = "n/a"       # �漰���������� Ethereum, Tron, BSC��
    contract_address: Union[str, List, None] = "n/a" # ��غ�Լ��Э���ַ
    #attacker_addresses: Union[List[str], None] = None # ������Ǯ����ַ
    #victim_addresses: Union[List[str], None] = None   # �ܺ���Ǯ����ַ���罻������Ǯ����
    attacker_addresses: Union[str, List[str], None] = None
    victim_addresses: Union[str, List[str], None] = None

    # �ʽ������ģ
    stolen_amount_usd: Union[float, None] = None # ��������Ԫ�ƣ�
    stolen_amount_token: Union[Dict, None] = None # ����������ϸ {token: amount}
    laundering_methods: Union[List[str], None] = None # ϴǮ��ʽ��������������š�CEX���֣�
    laundering_path: Union[List[str], None] = None   # �ʽ���·������A �� Mixer �� CEX��

    # ��в����
    severity: Union[str, None] = "n/a"          # ���س̶ȣ���/��/�ͣ�
    impact_scope: Union[str, None] = "n/a"      # Ӱ�췶Χ����һ��������������̬��
    attribution: Union[str, None] = "n/a"       # ���������� Lazarus Group, δ֪�ڿͣ�

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
