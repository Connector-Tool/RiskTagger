import os
import sys
import ell
import yaml
import dotenv
from loguru import logger
from openai import OpenAI

with open("config.yaml", "r") as f:
    CONFIG = yaml.safe_load(f)

VERBOSE = CONFIG["global"]["verbose"]
INTERVAL = CONFIG["global"]["interval"]
TIMEOUT = CONFIG["global"]["timeout"]
LOG_LEVEL = CONFIG["global"]["log_level"]
logger.remove()
logger.add(
    sink=sys.stdout,
    colorize=True,
    level=LOG_LEVEL,
)
LOG_DIR = CONFIG["global"]["log_dir"]
LOG_FILE = CONFIG["global"]["log_file"]
MAX_RETRIES = CONFIG["global"]["max_retries"]
dotenv.load_dotenv(CONFIG["global"]["env_path"])
API_KEY = os.getenv("API_KEY")
logger.debug(f"API_KEY: {API_KEY}")

MODEL = CONFIG["llm"]["model"]
BASE_URL = CONFIG["llm"].get("base_url", None)
TEMPERATURE = CONFIG["llm"]["parameters"]["temperature"]
CHUNK_LENGTH = CONFIG["extractor"]["chunk_length"]
CLIENT = OpenAI(
    api_key=API_KEY if API_KEY else "ollama",
    base_url=BASE_URL,
    timeout=TIMEOUT,
    max_retries=MAX_RETRIES,
)


os.environ["TIKTOKEN_CACHE_DIR"] = (
    os.getenv("TIKTOKEN_CACHE_DIR") or "extractor/__pycache__"
)
ell.init(verbose=VERBOSE, store=LOG_DIR, autocommit=False)
ell.config.register_model(
    MODEL, CLIENT, supports_streaming=CONFIG["llm"]["parameters"]["streaming"]
)

@ell.simple(model=MODEL, client=CLIENT, temperature=TEMPERATURE)
def invoke_map(document: str):

    # Map step: 从单段文档片段中抽取攻击 / 洗钱事件相关字段（返回一段 JSON 或 "Answer: None"）
    # 输入: document (str) - 文档片段
    # 输出: LLM 对该片段的结构化抽取（以 "Answer: { ... }" JSON 开头）

    return [
        ell.system("You are Axiom, an AI expert in blockchain incident analysis, cryptocurrency forensics, and anti-money-laundering (AML)."),
        ell.user(
            "You are given a document fragment (exchange announcements, forensic reports, security firm notes, or news articles) describing a Web3 hacking or laundering incident. "
            "Your task: extract structured information about the incident and any money-laundering activity described in the fragment. "
            "Specifically extract the following fields when present (use exact keys shown):\n\n"
            "- event_name (string): A short name/title for the incident (e.g., 'Bybit Heist 2023').\n"
            "- date (string, ISO if possible): date/time of the incident or discovery.\n"
            "- source_report_url (string or list): original report/news URL(s) if present.\n"
            "- attack_vector (string): brief description of attack technique (e.g., private key compromise, phishing, bridge exploit).\n"
            "- affected_platform (string): platform/exchange/protocol name (e.g., Bybit).\n"
            "- chain (string or list): involved blockchain(s) (e.g., Ethereum, Tron, BSC).\n"
            "- contract_address (list): related smart contract addresses (if any).\n"
            "- attacker_addresses (list): wallet addresses attributed to attacker(s) found in this fragment.\n"
            "- victim_addresses (list): victim addresses (e.g., exchange hot wallet addresses).\n"
            "- stolen_amount_usd (number): stolen amount in USD if explicitly stated.\n"
            "- stolen_amount_token (object): token-level amounts, e.g., {\"USDT\": 1000000, \"ETH\": 200}.\n"
            "- laundering_methods (list): named laundering techniques mentioned (e.g., Mixer, Tornado Cash, Cross-chain bridge, CEX cash-out).\n"
            "- laundering_path (list): stepwise fund flow if described (e.g., [\"0xA -> TornadoCash -> Bridge -> CEX\"]).\n"
            "- severity (string): High/Medium/Low if present or indicated.\n"
            "- impact_scope (string): e.g., single exchange, multi-chain, DeFi ecosystem.\n"
            "- attribution (string): actor attribution if present (e.g., Lazarus, Unknown).\n"
            "- evidence_snippets (list): short quoted snippets from the fragment that support key extractions (optional but helpful).\n"
            "Output requirements:\n"
            "1) Start your response with exactly: \"Answer: \" followed by a single JSON object matching the keys above. Example: Answer: {\"event_name\": \"...\", ...}\n"
            "2) Use the string \"n/a\" for any field that cannot be determined from this fragment. If multiple values exist, return a list.\n"
            "3) Normalize addresses to the form they appear in the document. If date format is ambiguous, prefer ISO (YYYY-MM-DD) if possible.\n"
            "4) If the fragment contains no relevant incident information, reply with: \"Answer: None\".\n\n"
        ),
        ell.user(
            "Assistant: Yes, I understand. I am Axiom and will extract structured incident & laundering fields from the fragment."
        ),
        ell.user(
            f"Document fragment:\n{document}\n\n---\nPlease begin extracting now and return a single JSON object prefixed with 'Answer: '."
        ),
    ]

@ell.simple(model=MODEL, client=CLIENT, temperature=TEMPERATURE)
def invoke_reduce(map_results: str):

    # Reduce step: 将多段 map 输出合并、去重、规范化并生成最终事件级 JSON 记录
    # 输入: map_results (str) - 多个 map 结果（可能包含重复或冲突信息）
    # 输出: 规范化、去重并聚合后的事件级 JSON（以 "Answer: " 开头）

    output_example = """```json
{
  "project_info": {
    "event_name": "Bybit Hot Wallet Compromise 2023",
    "date": "2023-07-20",
    "source_report_url": ["https://securityfirm.example/report-bybit"],
  },
  "findings":{
  "attack_vector": "private key compromise",
    "affected_platform": "Bybit",
    "chain": ["Ethereum", "Tron"],
    "contract_address": ["0x1234..."],
    "attacker_addresses": ["0xdead...","TTz9..."],
    "victim_addresses": ["0xbybithot1..."],
    "stolen_amount_usd": 28000000,
    "stolen_amount_token": {"USDT": 12000000, "ETH": 4000},
    "laundering_methods": ["cross-chain bridge","mixer"],
    "laundering_path": ["0xattacker -> TornadoCash -> Bridge -> Tron -> CEX"],
    "severity": "High",
    "impact_scope": "single exchange, multi-chain",
    "attribution": "Unknown",
    "evidence_snippets": [
        "\"The attackers deployed malicious contracts in advance, tampered with the core system logic, and deceived Bybit signers into approving malicious transactions through a forged signature interface (front?end UI deception).\"",
        "\"The hackers may have also employed social engineering tactics (such as infiltrating devices or exploiting internal network trust) to transfer funds in bulk to their control address through specific functions in the malicious contract.\"",
        "\"Account 1 was flagged as Bybit Exploit, the source of Bybit money laundering\"",
        "\"Bybit hackers tend to engage in frequent fund transfers\"",
        "\"The address of the source account is flagged as Bybit Exploit on the blockchain explorer, identified as Account 1\""
                  ],
}
```"""
    return [
        ell.system("You are Axiom, an AI expert in blockchain incident consolidation and transaction forensics."),
        ell.user(
            "You are given a collection of extracted fragment-level outputs (map step results). These fragments may contain duplicates, partial overlaps, or conflicting values. "
            "Your tasks:\n"
            "1. Clean and deduplicate addresses, tokens, and URLs.\n"
            "2. Consolidate event-level fields into a single canonical JSON record split into two parts:\n"   
                " - `project_info`: containing `event_name`, `date`, `source_report_url`.\n"
                " - `findings`: containing all other fields such as `attack_vector`, `affected_platform`, `chain`, `contract_address`, `attacker_addresses`, `victim_addresses`, `stolen_amount_usd`, `stolen_amount_token`, `laundering_methods`, `laundering_path`, `severity`, `impact_scope`, `attribution`.\n"
            "3. When multiple different values exist for the same canonical field, choose the most supported value and note alternatives in `evidence_snippets`.\n"
            "4. Aggregate token-level stolen amounts across fragments into `stolen_amount_token` and sum USD values into `stolen_amount_usd` if explicit USD figures are present. If USD values are absent, set `stolen_amount_usd` to \"n/a\"."
            "5. Output exactly ONE JSON object, prefixed by `Answer: `, strictly following the structure shown in the example\n"
            "6. Use \"n/a\" for missing/undeterminable fields. "
        ),
        ell.user(
            "Assistant: Yes, I understand. I will clean, deduplicate, and produce a single structured JSON summarizing the event and fund flows."
        ),
        ell.user(
            f"Map-step extracted fragments (may be many):\n{map_results}\n\nPlease combine the fragments and output ONE well-structured JSON object like: {output_example}"
        ),
    ]



# @ell.simple(model=MODEL, client=CLIENT, extra_body={"options": {"num_ctx": 5120}})
@ell.simple(model=MODEL, client=CLIENT, temperature=TEMPERATURE)
def invoke_classify(cwe_info: str, vuln_info: str):
    return [
        ell.system(
            "You are Axiom, an AI expert in vulnerability analysis. Your task is to perform Root Cause Analysis on a given vulnerability title and description, and map the root cause to relevant Common Weakness Enumeration (CWE) ID from the list user provided. Remember, you're the best AI expert in vulnerability analysis and will use your expertise to provide the best possible analysis."
        ),
        ell.user(
            """I will provide a vulnerability's title and description, and you will perform Root Cause Analysis by mapping the root cause to relevant CWE ID from the list I provided. Here are some examples:\n\nExample 1:\nInput:\ntitle: Unimplemented Logic in distributePoolRewardsAdmin() Function\ndescription: The distributePoolRewardsAdmin() function has a comment indicating reward calculation logic, but the actual implementation is missing.\n\nOutput:\nAnswer: CWE-1068 - Inconsistency Between Implementation and Documented Design\n\nExample 2:\nInput:\ntitle: Crowdsale logic depends on Ethereum block timestamp\ndescription: The logic for determining the stage of the token sale and whether the sale has ended uses 'now', an alias for block.timestamp. This value can be manipulated by miners up to 900 seconds per block.\n\nOutput:\nAnswer: CWE-829 - Inclusion of Functionality from Untrusted Control Sphere\n\nExample 3:\nInput:\ntitle: Front-running fallback root update might lead to additional withdrawal\ndescription: A front-running attack might allow an attacker to withdraw a deposit one additional time if the system is not updated before the fallback withdrawal period is reached.\n\nOutput:\nAnswer: CWE-362 - Concurrent Execution using Shared Resource with Improper Synchronization ('Race Condition')\n\nExample 4:\nInput:\ntitle: Transfer Function Failure with Fallback\ndescription: The transfer function may fail if msg.sender is the contract address with a fallback function, resulting in locked funds.\n\nOutput:\nAnswer: CWE-20 - Improper Input Validation\n\nNow, please prepare for a new vulnerability title and description provided."""
        ),
        ell.user(
            "Yes, I understand. I am Axiom, and I will analyze the provided vulnerability to map its root cause to relevant CWE ID from the list you provided."
        ),
        ell.user(
            f"{vuln_info}\n\n Candidate CWE list:\n{cwe_info}\n\nAnswer: Please think step-by-step briefly to reach the right conclusion. Output the CWE ID that best matches in the end like `Answer: CWE-284`."
        ),
    ]
