#原本forge代码格式以及提示词
@dataclass
class ProjectInfo:
    url: Union[str, int, List, None] = "n/a"
    commit_id: Union[str, int, List, None] = "n/a"
    address: Union[str, int, List, None] = "n/a"
    chain: Union[str, int, List, None] = "n/a"
    compiler_version: Union[str, List, None] = "n/a"
    project_path: Union[str, List, Dict, None] = "n/a"

    def is_empty(self):
        if (self.url == "n/a" and self.address == "n/a") or (
            not self.url and not self.address
        ):
            return True
        return False


@dataclass
class Finding:
    id: Union[str, int] = 0
    category: Dict = field(default_factory=dict)
    title: str = ""
    description: str = ""
    severity: str = ""
    location: Union[str, int, List] = ""
    # contract: Union[str, int, List] = ""
    # function: Union[str, int, List] = ""
    # lineNumber: Union[str, int, List] = ""


@dataclass
class MapReduceResult:
    project_info: ProjectInfo = field(default_factory=ProjectInfo)
    findings: List[Finding] = field(default_factory=list)

########################################################################

@dataclass
class ProjectInfo:
    event_name: Union[str, None] = "n/a"
    date: Union[str, None] = "n/a"
    source_report_url: Union[List[str], None] = field(default_factory=list)
    
    def is_empty(self):
        if (self.event_name == "n/a" and self.date == "n/a") or (
            not self.event_name and not self.date
        ):
            return True
        return False

@dataclass
class Finding:
    id: Union[str, int] = 0
    attack_vector: List[str] = field(default_factory=list)
    affected_platform: str = ""
    chain: List[str] = field(default_factory=list)
    contract_address: List[str] = field(default_factory=list)
    attacker_addresses: List[str] = field(default_factory=list)
    victim_addresses: List[str] = field(default_factory=list)
    stolen_amount_usd: Union[int, float] = 0
    stolen_amount_token: Dict[str, Union[int, float]] = field(default_factory=dict)
    laundering_methods: List[str] = field(default_factory=list)
    laundering_path: List[str] = field(default_factory=list)
    evidence_snippets: List[str] = field(default_factory=list)

@dataclass
class MapReduceResult:
    project_info: ProjectInfo = field(default_factory=ProjectInfo)
    findings: List[Finding] = field(default_factory=list)