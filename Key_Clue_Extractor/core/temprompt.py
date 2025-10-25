
@ell.simple(model=MODEL, client=CLIENT, temperature=TEMPERATURE)
def invoke_map(document: str):
    return [
        ell.system("You are Axiom, an AI expert in smart contract security."),
        ell.user(
            'You are given a document containing excerpts from various sources such as smart contract audit reports or bug bounty disclosures. Your task is to extract relevant information if mentioned about the audited project and all security vulnerabilities involved. Specifically, find any links, addresses or references to where the project source code audited can be found(e.g., GitHub repository with certain commit id (branch id), on-chain address and chain name). Besides, identify and extract the following details:\nVulnerability Title, Vulnerability Description (answer "n/a" if not provided), Severity Level (answer "n/a" if not provided), Location of Vulnerability (contract, function, etc.). \nPlease format the output clearly. Start your response with "Answer: " followed by the extracted details. If no relevant information is found, reply with "Answer: None".'
        ),
        ell.user(
            "Assistant: Yes, I understand. I am Axiom, and I will extract all relevant vulnerabilities information from the document fragment you provided."
        ),
        ell.user(
            f"Document fragment:\n{document}\n\n---\n Please start extracting the information."
        ),
    ]


@ell.simple(model=MODEL, client=CLIENT, temperature=TEMPERATURE)
def invoke_reduce(map_results: str):
    output_example = """```json\n{"project_info": { "url": "https://github.com/xxx/xxx/", "commit_id": "ad048598b092457acf346orkhg9898987", "address": "n/a", "chain": "n/a" }, "findings": [ { "id": 0, "title": "Out of gas in includeInReward() function", "description": "The function `includeInReward()` uses a loop to...", "severity": "Low", "location": "includeInReward()" },...]}\n```"""
    return [
        ell.system("You are Axiom, an AI expert in smart contract security."),
        ell.user(
            'You are given a set of extracted vulnerability info from a smart contract audit report or bug bounty disclosure. These fragments include information about various vulnerabilities (potential duplicates or invalid entries may be present) and details related to the source code (such as GitHub repository links or on-chain addresses). Your task is to: \n1. Clean and deduplicate the extracted vulnerability data\n2. Organize the relevant source code details (e.g., GitHub URL, on-chain address, and chain name)\n3. Generate a well-structured JSON output in the following format: \n{ "project_info": { "url": "<GitHub repository URL, if exists>", "commit_id": "<branch or commit hash/name/id, if exists>", "address": "<On-chain address, if exists>", "chain": "<Blockchain name (e.g., eth, bsc, base, polygon), if exists>" }, "findings": [ {"id":0, "title": "<Vulnerability title>", "description": "<Detailed description of the vulnerability>", "severity": "<Severity level (e.g., Low, Medium, High, Critical)>", "location": "<The contract or funtion or line where the vulnerability code is located or affected component>"},{"id": 1,...},... ] }.\n\n Use a null value "n/a" for missing fields or entries that could not be determined.'
        ),
        ell.user(
            "Assistant: Yes, I understand. I am Axiom, and I will clean, deduplicate, and organize the extracted vulnerability data and source code details to generate a structured JSON output."
        ),
        ell.user(
            f"Extracted data:\n{map_results}\n\n\n Please Remember combine the fragments and output one well-structured JSON format like: {output_example}"
        ),
    ]

#####################################################################################


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