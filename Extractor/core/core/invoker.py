import os
import sys
import ell
import yaml
import dotenv
from pathlib import Path
from loguru import logger
from openai import OpenAI

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from project_config import EXTRACTOR_CONFIG_FILE, EXTRACTOR_CONFIG_ROOT, EXTRACTOR_OUTPUT_ROOT


def resolve_config_path(value) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (EXTRACTOR_CONFIG_ROOT / path).resolve()


with EXTRACTOR_CONFIG_FILE.open("r", encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)

VERBOSE = CONFIG["global"]["verbose"]
INTERVAL = CONFIG["global"]["interval"]
TIMEOUT = CONFIG["global"]["timeout"]
LOG_LEVEL = CONFIG["global"]["log_level"]

logger.remove()
logger.add(sink=sys.stdout, colorize=True, level=LOG_LEVEL)

LOG_DIR = str(resolve_config_path(CONFIG["global"]["log_dir"]))
MAX_RETRIES = CONFIG["global"]["max_retries"]
dotenv.load_dotenv(resolve_config_path(CONFIG["global"]["env_path"]))
API_KEY = os.getenv("API_KEY")

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

os.environ["TIKTOKEN_CACHE_DIR"] = os.getenv("TIKTOKEN_CACHE_DIR") or str(EXTRACTOR_OUTPUT_ROOT / ".cache" / "tiktoken")
ell.init(verbose=VERBOSE, store=LOG_DIR, autocommit=False)
ell.config.register_model(MODEL, CLIENT, supports_streaming=CONFIG["llm"]["parameters"]["streaming"])


@ell.simple(model=MODEL, client=CLIENT, temperature=TEMPERATURE)
def invoke_map(document: str):
    return [
        ell.system(
            "You are Axiom, an AI expert in blockchain incident analysis, cryptocurrency forensics, and anti-money-laundering (AML)."),
        ell.user(
            'You are given a document describing a Web3 hacking or laundering incident. Your task is to extract relevant information if mentioned about the attack and the origin address of the money laundering account.Specifically,find any event_name, date, source_report_url(answer "n/a" if not provided), attack_vector(answer "n/a" if not provided), affected_platform(answer "n/a" if not provided), chain(answer "n/a" if not provided), contract_address(answer "n/a" if not provided), attacker_addresses(answer "n/a" if not provided), victim_addresses(answer "n/a" if not provided), stolen_amount_usd(answer "n/a" if not provided), stolen_amount_token(answer "n/a" if not provided), laundering_methods(answer "n/a" if not provided), laundering_path(answer "n/a" if not provided), and evidence_snippets(answer "n/a" if not provided). \nPlease format the output clearly. Start your response with "Answer: " followed by the extracted details in JSON format.'
        ),
        ell.assistant(
            "Yes, I understand. I will extract all relevant incident & laundering information from the document fragment you provided."),
        ell.user(f"Document fragment:\n{document}\n\n---\n Please start extracting the information.")
    ]


@ell.simple(model=MODEL, client=CLIENT, temperature=TEMPERATURE)
def invoke_reduce(map_results: str):
    # 此处已去除会导致底层系统崩溃渲染的特殊语法，直接用普通 JSON 字符串
    output_example = '{ "project_info": { "event_name": "Bybit Hot Wallet Compromise 2023", "date": "2023-07-20","source_report_url": ["[https://securityfirm.example/report-bybit](https://securityfirm.example/report-bybit)"] }, "findings":[{ "id": 0, "attack_vector": ["private key compromise"], "affected_platform": "Bybit", "chain": ["Ethereum", "Tron"], "contract_address": ["0x1234..."], "attacker_addresses": ["0xdead...","TTz9..."], "victim_addresses": ["0xbybithot1..."], "stolen_amount_usd": 28000000, "stolen_amount_token": {"USDT": 12000000, "ETH": 4000}, "laundering_methods": ["cross-chain bridge","mixer"], "laundering_path": ["0xattacker -> TornadoCash -> Bridge -> Tron -> CEX"], "evidence_snippets": ["Snippet 1"]}] }'

    return [
        ell.system("You are Axiom, an AI expert in blockchain incident consolidation and transaction forensics."),
        ell.user(
            'You are given a set of extracted fragment-level outputs (map step results). These fragments contain information about an attack (potential duplicates or invalid entries may be present). Your task is to:\n1. Clean and deduplicate addresses, tokens, and URLs.\n2. Organize the relevant address details.\n3. Generate a well-structured JSON output matching the format provided below. Use a null value "n/a" for missing fields or entries that could not be determined.'
        ),
        ell.assistant(
            "Yes, I understand. I will clean, deduplicate, and organize the extracted attack incident and address details to generate a structured JSON output."),
        ell.user(
            f"Extracted data:\n{map_results}\n\n\n Please combine the fragments and output one well-structured JSON format exactly like this:\n{output_example}")
    ]
