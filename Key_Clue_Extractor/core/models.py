from dataclasses import dataclass
from dataclasses import field
from typing import List, Dict, Union, Optional, Literal
from pydantic import BaseModel, RootModel, Field


@dataclass
class ProjectInfo:
    # ��Ŀ��Ϣ�࣬�洢��������ȫ�¼��Ļ���Ԫ����
    event_name: Union[str, None] = "n/a"                                        # �¼����ƣ�������ȫ�¼��ı�����ʶ��
    date: Union[str, None] = "n/a"                                              # �¼��������ڣ���ʽͨ��ΪYYYY-MM-DD
    source_report_url: Union[List[str], None] = field(default_factory=list)     # ��Դ����URL�б�ָ���������¼����ⲿ���������
    
    def is_empty(self):
        # �����Ŀ��Ϣ�Ƿ�Ϊ�գ�ֻ��Ĭ��ֵ����ֵ��
        if (self.event_name == "n/a" and self.date == "n/a") or (
            not self.event_name and not self.date
        ):
            return True
        return False

@dataclass
class Finding:
    # �����࣬�洢������ȫ�¼�����ϸ������Ϣ��ȡ֤����
    
    id: Union[str, int] = 0                                         # �������Ψһ��ʶ������������ͬһ�¼��еĶ������
    attack_vector: List[str] = field(default_factory=list)          # ���������б��������������õĹ���������©������
    affected_platform: str = ""                                     # ��Ӱ���ƽ̨����Ŀ���ƣ���ʶ��������Ŀ��
    chain: List[str] = field(default_factory=list)                  # ��Ӱ��������������б���Ethereum��Bitcoin��Tron��
    contract_address: List[str] = field(default_factory=list)       # ��غ�Լ��ַ�б�������������Լ������Լ��ַ
    attacker_addresses: List[str] = field(default_factory=list)     # �����ߵ�ַ�б���ʶ������ʹ�õ���������ַ
    victim_addresses: List[str] = field(default_factory=list)       # �ܺ��ߵ�ַ�б���ʶ�����ʽ��ԭ��ַ
    stolen_amount_usd: Union[int, float] = 0                        # �����ʽ��ܶ����Ԫ�ƣ�������������ɵĲ�����ʧ
    stolen_amount_token: Dict[str, Union[int, float]] = field(default_factory=dict)  # ����������ϸ�ֵ䣬��Ϊ���ҷ��ţ�ֵΪ��Ӧ���ҵ�����
    laundering_methods: List[str] = field(default_factory=list)     # ϴǮ�����б�����������ת�ƺ������ʽ�ļ���
    laundering_path: List[str] = field(default_factory=list)        # ϴǮ·���б������ʽ��ڵ�ַ�������������켣
    evidence_snippets: List[str] = field(default_factory=list)      # ֤��Ƭ���б�����֧�ַ��ֵ��ı�֤�ݻ�������

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
