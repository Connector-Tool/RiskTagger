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
            'You are given a document (such as exchange announcements, forensic reports, security firm notes, or news articles) describing a Web3 hacking or laundering incident. Your task is to extract relevant information if mentioned about the attack and the origin address of the money laundering account.Specifically,find any event_name, date, source_report_url(answer "n/a" if not provided), attack_vector(answer "n/a" if not provided), affected_platform(answer "n/a" if not provided), chain(answer "n/a" if not provided), contract_address(answer "n/a" if not provided), attacker_addresses(answer "n/a" if not provided), victim_addresses(answer "n/a" if not provided), stolen_amount_usd(answer "n/a" if not provided), stolen_amount_token(answer "n/a" if not provided), laundering_methods(answer "n/a" if not provided), laundering_path(answer "n/a" if not provided), and evidence_snippets(answer "n/a" if not provided). \nPlease format the output clearly. Start your response with "Answer: " followed by the extracted details. If no relevant information is found, reply with "Answer: None".'
        ),
        ell.user(
            "Assistant: Yes, I understand. I am Axiom and will extract all relevant incident & laundering information from the document fragment you provided."
        ),
        ell.user(
            f"Document fragment:\n{document}\n\n---\n Please start extracting the information."
        ),
    ]

@ell.simple(model=MODEL, client=CLIENT, temperature=TEMPERATURE)
def invoke_reduce(map_results: str):

    # Reduce step: 将多段 map 输出合并、去重、规范化并生成最终事件级 JSON 记录
    # 输入: map_results (str) - 多个 map 结果（可能包含重复或冲突信息）
    # 输出: 规范化、去重并聚合后的事件级 JSON（以 "Answer: " 开头）

    output_example = """```json\n{"project_info": { "event_name": "Bybit Hot Wallet Compromise 2023", "date": "2023-07-20","source_report_url": ["https://securityfirm.example/report-bybit"] },  "findings":[{ "id": 0, "attack_vector": ["private key compromise"], "affected_platform": "Bybit", "chain": ["Ethereum", "Tron"], "contract_address": ["0x1234..."], "attacker_addresses": ["0xdead...","TTz9..."], "victim_addresses": ["0xbybithot1..."], "stolen_amount_usd": 28000000, "stolen_amount_token": {"USDT": 12000000, "ETH": 4000}, "laundering_methods": ["cross-chain bridge","mixer"], "laundering_path": ["0xattacker -> TornadoCash -> Bridge -> Tron -> CEX"], "evidence_snippets": [         "\"The attackers deployed malicious contracts in advance, tampered with the core system logic, and deceived Bybit signers into approving malicious transactions through a forged signature interface (front?end UI deception).\"","\"The hackers may have also employed social engineering tactics (such as infiltrating devices or exploiting internal network trust) to transfer funds in bulk to their control address through specific functions in the malicious contract.\"","\"Account 1 was flagged as Bybit Exploit, the source of Bybit money laundering\"", "\"Bybit hackers tend to engage in frequent fund transfers\"", "\"The address of the source account is flagged as Bybit Exploit on the blockchain explorer, identified as Account 1\""]}]\n```"""
    return [
        ell.system("You are Axiom, an AI expert in blockchain incident consolidation and transaction forensics."),
        ell.user(
            'You are given a set of extracted fragment-level outputs (map step results). These fragments  contain information about the attack (potential duplicates or invalid entries may be present),as well as details related to the attack address, money laundering source address (e.g. on-chain address and chain name).Your task is to:\n1.Clean and deduplicate addresses, tokens, and URLs.\nOrganize the relevant address details(e.g.,on-chain address,and chain name)3. 3. Generate a well-structured JSON output in the following format: \n{ "project_info": { "event_name": "<Event name>", "date": "<Date>", "source_report_url": ["<Source report URL, if exists>"], "findings": [{ "id": 0, "attack_vector": ["<Attack vector>"], "affected_platform": "<Affected platform>", "chain": ["<Chain name>"], "contract_address": ["<Contract address>"], "attacker_addresses": ["<Attacker address>"], "victim_addresses": ["<Victim address>"], "stolen_amount_usd": <Stolen amount in USD>, "stolen_amount_token": {"<Token symbol>": <Amount>}, "laundering_methods": ["<Laundering method>"], "laundering_path": ["<Laundering path>"], "evidence_snippets": ["<Evidence snippet>"]}]}\n\n Use a null value "n/a" for missing fields or entries that could not be determined.'
        ),
        ell.user(
            "Assistant: Yes, I understand. I am Axiom, and I will clean, deduplicate, and organize the extracted attack incident and address details to generate a structured JSON output."
        ),
        ell.user(
            f"Extracted data:\n{map_results}\n\n\n Please Remember combine the fragments and output one well-structured JSON format like: {output_example}"
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
