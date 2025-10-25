import os
import re
import ell
import json
import yaml
import time
import tiktoken

from openai import OpenAI
from typing import List
from loguru import logger
from pydantic import BaseModel, TypeAdapter
from typing import Literal
from vendor.commentjson import commentjson
from core.models import MapReduceResult, Context
from core.invoker import invoke_map, invoke_reduce, MAX_RETRIES, INTERVAL, CONFIG

MODE: Literal["strict", "normal"] = CONFIG["extractor"]["mode"]


class MapReducer(BaseModel):

    class Config:
        arbitrary_types_allowed = True

    @logger.catch
    def map_reduce(self, documents: List[str], context_length: int) -> MapReduceResult:
        logger.info("{} mode active.", MODE)
        logger.info("Start Mapping...")
        context_list: List[Context] = self._map(documents)
        logger.info("Start Reducing...")
        return self._reduce(context_list, context_length)

    def _map(self, documents: List[str]) -> List[Context]:

        context_list: List[Context] = []
        total_length = 0
        for i in range(len(documents)):
            context = Context(index=i, document=documents[i], length=0)
            retry = 0
            while retry < MAX_RETRIES:
                try:
                    map_result = self._parse_answer(invoke_map(context.document))
                    context.response = map_result
                    length = self._calc_token_length(map_result)
                    context.length = length
                    total_length += length
                    context_list.append(context)
                    break  # Success, exit retry loop
                except Exception as e:
                    retry += 1
                    backoff_time = INTERVAL * retry  # Exponential backoff
                    logger.error(
                        "Error in mapping document {}: {}\nRetrying: {}/{} after {} seconds",
                        i,
                        str(e),
                        retry,
                        MAX_RETRIES,
                        backoff_time,
                    )
                    if retry < MAX_RETRIES:
                        time.sleep(backoff_time)
                    else:
                        logger.error(
                            "Max retries reached for document {}, skipping.", i
                        )
            if retry == MAX_RETRIES:
                # Add empty context if all retries failed to avoid skipping indices
                context.response = ""
                context.length = 0
                context_list.append(context)
        return context_list

    def _reduce(
        self, context_list: List[Context], context_length: int
    ) -> MapReduceResult:

        reduce_messages = []
        reduce_tokens = 0
        part_results: List[MapReduceResult] = []
        for context in context_list:

            if not reduce_messages:
                reduce_messages.append(
                    f"Fragment {context.index}:\n{context.response}\n"
                )
                reduce_tokens += context.length
                continue
            if reduce_tokens + context.length >= context_length:
                is_appended = False
                if context.length < context_length / 3:
                    reduce_messages.append(
                        f"Fragment {context.index}:\n{context.response}\n"
                    )
                    reduce_tokens += context.length
                    is_appended = True
                logger.info("Current token: {}, start reducing...", reduce_tokens)
                retry = 0
                resp_parsed = None
                while retry < MAX_RETRIES:
                    try:
                        resp = invoke_reduce("\n".join(reduce_messages))
                        resp_parsed = self._parse_json(resp, MapReduceResult)
                        if resp_parsed:
                            break  # Successfully parsed, exit retry loop
                        # If parsing returns None but didn't throw exception
                        retry += 1
                        if len(reduce_messages) > 1:
                            reduce_messages.pop(-1)
                        logger.warning(
                            "Failed to parse response (returned None). Retry: {}/{}",
                            retry,
                            MAX_RETRIES,
                        )
                    except Exception as e:
                        retry += 1
                        logger.error(
                            "Error in reducing or parsing: {}\nRetrying: {}/{}",
                            str(e),
                            retry,
                            MAX_RETRIES,
                        )
                        if retry == MAX_RETRIES:
                            logger.error("Max retries reached, moving on.")

                if resp_parsed:
                    part_results.append(resp_parsed)
                reduce_messages = []
                reduce_tokens = 0
                if not is_appended:
                    reduce_messages.append(
                        f"Fragment {context.index}:\n{context.response}\n"
                    )
                    reduce_tokens += context.length
                continue
            else:
                reduce_messages.append(
                    f"Fragment {context.index}:\n{context.response}\n"
                )
                reduce_tokens += context.length
                continue
        if reduce_messages:
            logger.info("Current token: {}, start reducing...", reduce_tokens)
            retry = 0
            resp_parsed = None
            while retry < MAX_RETRIES:
                try:
                    resp = invoke_reduce("\n".join(reduce_messages))
                    resp_parsed = self._parse_json(resp, MapReduceResult)
                    if resp_parsed:
                        break  # Successfully parsed, exit retry loop
                    # If parsing returns None but didn't throw exception
                    retry += 1
                    logger.warning(
                        "Failed to parse response (returned None). Retry: {}/{}",
                        retry,
                        MAX_RETRIES,
                    )
                except Exception as e:
                    retry += 1
                    logger.error(
                        "Error in reducing or parsing: {}\nRetrying: {}/{}",
                        str(e),
                        retry,
                        MAX_RETRIES,
                    )
                    if retry == MAX_RETRIES:
                        logger.error("Max retries reached, moving on.")

            if resp_parsed:
                part_results.append(resp_parsed)
        return self._merge_results(part_results)

    def _merge_results(self, partial: List[MapReduceResult]) -> MapReduceResult:
        # 过滤掉 None 值
        partial = [p for p in partial if p is not None]
        
        # 如果没有有效结果，返回空的 MapReduceResult
        if not partial:
            return MapReduceResult()
        
        result = MapReduceResult()
        index = 0
        
        for p in partial:
            # 合并 project_info 字段
            event_name, date, source_report_url = (
                p.project_info.event_name,
                p.project_info.date,
                p.project_info.source_report_url,
            )
            
            # 使用第一个非空/非默认值
            if result.project_info.event_name == "n/a" or not result.project_info.event_name:
                result.project_info.event_name = event_name
            if result.project_info.date == "n/a" or not result.project_info.date:
                result.project_info.date = date
            # 合并 source_report_url 列表，去重
            if source_report_url and source_report_url != ["n/a"]:
                for url in source_report_url:
                    if url != "n/a" and url not in result.project_info.source_report_url:
                        result.project_info.source_report_url.append(url)
            
            logger.debug("Project metadata merged results: {}", result.project_info)
            
            # 过滤无效的 findings
            p.findings = [
                finding
                for finding in p.findings
                # 检查攻击向量不为空
                if finding.attack_vector and finding.attack_vector != ["n/a"]
                # 检查受影响平台不为空
                and finding.affected_platform and finding.affected_platform != "n/a"
            ]
            
            # 对于严格模式，可能需要额外的过滤条件
            if MODE == "strict":
                p.findings = [
                    finding
                    for finding in p.findings
                    # 检查被盗金额不为0
                    if finding.stolen_amount_usd and finding.stolen_amount_usd > 0
                    # 检查攻击者地址不为空
                    and finding.attacker_addresses and finding.attacker_addresses != ["n/a"]
                ]
            
            # 重新分配 ID 并添加到结果中
            for finding in p.findings:
                finding.id = index
                index += 1
                result.findings.append(finding)
            
            logger.debug(f"Partial result:\n{p}")
        
        return result

    def _calc_token_length(self, text: str) -> int:
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))

    def _parse_answer(self, response: str) -> str:
        PATTERN = re.compile(
            r"Answer:\s*(.*)", re.IGNORECASE | re.DOTALL | re.MULTILINE
        )
        action_match = PATTERN.search(response)
        if action_match:
            if len(action_match.group(1).strip("\n")) > 3:
                return action_match.group(1)
            else:
                return response

        return response

    def _parse_json(self, response: str, schema: BaseModel) -> BaseModel:###修改了
        """Extract JSON structure from LLM response text."""
        
        PATTERN = re.compile(
            r"```(?:json\s+)?(\W.*?)```", re.IGNORECASE | re.DOTALL | re.MULTILINE
        )
        action_match = PATTERN.search(response)
        
        # 记录原始响应（截断以避免日志过大）
        logger.debug("Original response: {}", response[:500] + "..." if len(response) > 500 else response)
        
        try:
            if action_match:
                json_str = action_match.group(1)
                logger.info("Extracted JSON string: {}", json_str)  # 记录提取的 JSON 字符串
                
                # 尝试解析 JSON
                json_dict = commentjson.loads(json_str)
                logger.debug("Parsed JSON dict: {}", json_dict)  # 记录解析后的字典
                
                # 尝试验证 JSON 是否符合 schema
                validated = TypeAdapter(schema).validate_json(json.dumps(json_dict))
                logger.info("Successfully validated JSON against schema")
                
                return validated
            else:
                logger.warning("No JSON code block found in response")
                # 尝试查找其他可能的 JSON 模式
                alternative_pattern = re.compile(r'\{.*\}', re.DOTALL)
                alt_match = alternative_pattern.search(response)
                if alt_match:
                    logger.info("Found alternative JSON-like pattern: {}", alt_match.group(0)[:200] + "..." if len(alt_match.group(0)) > 200 else alt_match.group(0))
                return None
        except json.JSONDecodeError as e:
            logger.error("JSON decode error at line {} column {}: {}", e.lineno, e.colno, e.msg)
            logger.error("Problematic JSON string: {}", json_str)
            # 尝试找到问题所在的具体位置
            if hasattr(e, 'pos') and e.pos is not None:
                start = max(0, e.pos - 50)
                end = min(len(json_str), e.pos + 50)
                logger.error("Context around error: ...{}...", json_str[start:end])
            return None
        except Exception as e:
            logger.error("Error parsing JSON: {}", str(e))
            logger.error("JSON string that caused error: {}", json_str)
            import traceback
            logger.error("Full traceback: {}", traceback.format_exc())
            return None
        
    # @ell.simple(model=MODEL, client=CLIENT, extra_body={"options": {"num_ctx": 8192}})
    # def _map_call(self, document: str):
    #     return [
    #         ell.system("You are Axiom, an AI expert in smart contract security."),
    #         ell.user(
    #             """You are given a document containing excerpts from various smart contract security artifacts such as audit reports or bug bounty disclosures. Your task is to extract all security vulnerabilities involved. Identify and extract the following details:\nVulnerability Title, Vulnerability Description (answer "n/a" if not provided), Severity Level (answer "n/a" if not provided), Location of Vulnerability (contract, function, etc.). \nPlease format the output clearly. Start your response with \"Answer: \" followed by the extracted details. If no relevant information is found, reply with \"Answer: None\"."""
    #         ),
    #         ell.assistant(
    #             "Yes, I understand. I am Axiom, and I will extract all relevant vulnerabilities information from the document fragment you provided."
    #         ),
    #         ell.user(f"Document fragment:\n{document}\n\n\n Please answer briefly."),
    #     ]

    # @ell.simple(model=MODEL, client=CLIENT, extra_body={"options": {"num_ctx": 8192}})
    # def _reduce_call(self, map_results: str):
    #     output_example = """```json\n{"findings": [{ "id": 0, "title": "Reentrancy in includeInReward() function", "description": "The function `includeInReward()` uses a loop to...", "severity": "Low", "location": "includeInReward()" }]}\n```"""
    #     return [
    #         ell.system("You are Axiom, an AI expert in smart contract security."),
    #         ell.user(
    #             'You are given a set of extracted vulnerability info from a smart contract audit report or bug bounty disclosure. These fragments include information about various vulnerabilities (potential duplicates or invalid entries may be present). Your task is to: \n1. Clean and deduplicate the extracted vulnerability data\n2. Generate a well-structured JSON output in the following format: \n{"findings": [ {"id":0, "title": "<Vulnerability title>", "description": "<Detailed description of the vulnerability>", "severity": "<Severity level (e.g., Low, Medium, High, Critical)>", "location": "<The contract or funtion or line where the vulnerability code is located or affected component>"},{"id": 1,...},... ] }.\n\n Use a null value "n/a" for missing fields or entries that could not be determined.'
    #         ),
    #         ell.assistant(
    #             "Yes, I understand. I am Axiom, and I will clean, deduplicate, and organize the extracted vulnerability data and source code details to generate a structured JSON output."
    #         ),
    #         ell.user(
    #             f"Extracted data:\n{map_results}\n\n\n Please Remember combine the fragments and output one well-structured JSON format like: {output_example}"
    #         ),
    #     ]


# map_reducer = MapReducer()

# test_document = """# Scope

# The code under review can be found within the [C4 Superposition repository](https://github.com/code-423n4/2024-08-superposition), and is composed of 26 smart contracts written in the Solidity programming language and includes 5248 lines of Solidity code.

# # Severity Criteria

# C4 assesses the severity of disclosed vulnerabilities based on three primary risk categories: high, medium, and low/non-critical.

# High-level considerations for vulnerabilities span the following key areas when conducting assessments:

# - Malicious Input Handling
# - Escalation of privileges
# - Arithmetic
# - Gas use

# For more information regarding the severity criteria referenced throughout the submission review process, please refer to the documentation provided on [the C4 website](https://code4rena.com), specifically our section on [Severity Categorization](https://docs.code4rena.com/awarding/judging-criteria/severity-categorization).

# # High Risk Findings (7)
# ## [[H-01] `update_emergency_council_7_D_0_C_1_C_58()` updates nft manager instead of emergency council](https://github.com/code-423n4/2024-08-superposition-findings/issues/162)
# *Submitted by [ABAIKUNANBAEV](https://github.com/code-423n4/2024-08-superposition-findings/issues/162), also found by [Q7](https://github.com/code-423n4/2024-08-superposition-findings/issues/153), [DadeKuma](https://github.com/code-423n4/2024-08-superposition-findings/issues/145), [ZanyBonzy](https://github.com/code-423n4/2024-08-superposition-findings/issues/137), [Rhaydden](https://github.com/code-423n4/2024-08-superposition-findings/issues/134), [Nikki](https://github.com/code-423n4/2024-08-superposition-findings/issues/132), [nslavchev](https://github.com/code-423n4/2024-08-superposition-findings/issues/128), [Testerbot](https://github.com/code-423n4/2024-08-superposition-findings/issues/103), [eta](https://github.com/code-423n4/2024-08-superposition-findings/issues/89), [d4r3d3v1l](https://github.com/code-423n4/2024-08-superposition-findings/issues/78), [prapandey031](https://github.com/code-423n4/2024-08-superposition-findings/issues/76), [zhaojohnson](https://github.com/code-423n4/2024-08-superposition-findings/issues/64), [oakcobalt](https://github.com/code-423n4/2024-08-superposition-findings/issues/23), [wasm\_it](https://github.com/code-423n4/2024-08-superposition-findings/issues/11), and [shaflow2](https://github.com/code-423n4/2024-08-superposition-findings/issues/7)*

# Inside of `lib.rs`, there is a function `update_emergency_council_7_D_0_C_1_C_58()` that is needed to update the emergency council that can disable the pools. However, in the current implementation, `nft_manager` is updated instead.
# """
# test_extracted_data = """**Vulnerabilities:**
# 1. **Vulnerability Title:** Debugging Code in Production
# **Vulnerability Description:** Debugging code is still present in the production environment, cluttering the codebase and potentially causing issues with the test suite.
# **Severity Level:** Low
# **Location of Vulnerability:** Various contracts in scope
# **Source Code Reference:** https://github.com/search?q=repo%3Acode-423n4%2F2024-08-superposition%20%23%5Bcfg(feature%20%3D%20%22testing-dbg%22)%5D&type=code
# 2. **Vulnerability Title:** Unused `calldata` in NFT Transfers
# **Vulnerability Description:** The `calldata` parameter is not used in `transferFrom` and `safeTransferFrom` functions, potentially causing issues with external integrations.
# **Severity Level:** Low
# **Location of Vulnerability:** `OwnershipNFTs.sol` (lines 148-157, 118-126)
# **Source Code Reference:** https://github.com/code-423n4/2024-08-superposition/blob/4528c9d2dbe1550d2660dac903a8246076044905/pkg/sol/OwnershipNFTs.sol
# 3. **Vulnerability Title:** Transfer to Self Allowed
# **Vulnerability Description:** The `transfer_position_E_E_C7_A3_C_D` function allows users to transfer tokens to themselves.
# **Severity Level:** Low
# **Location of Vulnerability:** `lib.rs` (lines 553-569)
# **Source Code Reference:** https://github.com/code-423n4/2024-08-superposition/blob/4528c9d2dbe1550d2660dac903a8246076044905/pkg/seawater/src/lib.rs
# 4. **Vulnerability Title:** Swapping Between Same Pools Allowed
# **Vulnerability Description:** The `swap_2_exact_in_41203_F1_D` function allows swapping between the same pools, potentially allowing malicious users to drain pool liquidity.
# **Severity Level:** Medium
# **Location of Vulnerability:** `lib.rs` (lines 327-336)
# **Source Code Reference:** https://github.com/code-423n4/2024-08-superposition/blob/4528c9d2dbe1550d2660dac903a8246076044905/pkg/seawater/src"""
# # resp = map_reducer.map_call(test_document)

# test_response = """
# Result:

# ```json
# {
#   "project_info": {
#     "url": "https://github.com/code-423n4/2024-08-superposition",
#     "address": "n/a",
#     "chain": "n/a"
#   },
#   "findings": [
#     {
#       "title": "[H-01] update_emergency_council_7_D_0_C_1_C_58() updates nft manager instead of emergency council",
#       "description": "The update_emergency_council_7_D_0_C_1_C_58() function in lib.rs updates nft_manager instead of the emergency council, which can lead to unintended consequences.",
#       "severity": "High",
#       "contract": "lib.rs",
#       "function": "update_emergency_council_7_D_0_C_1_C_58()",
#       "lineNumber": "n/a"
#     }
#   ]
# }
# ```
# """

# test_map_res = """              Now, I'll combine the cleaned vulnerability data and source code details
#               into a single JSON object:

#               ```json
#               {
#                   "project_info": {
#                       "url": "https://github.com/project/contracts",
#                       "address": "0x123456...",
#                       "chain": "eth"
#                   },
#                   "findings": [
#                       {
#                           "id": 0,
#                           "title": "Reentrancy",
#                           "description": "...",
#                           "severity": "High",
#                           "contract": "BankContract",
#                           "function": "withdraw",
#                           "lineNumber": 123
#                       },
#                       {
#                           "id": 1,
#                           "title": "Unprotected function",
#                           "description": "...",
#                           "severity": "Medium",
#                           "contract": "BankContract",
#                           "function": "approve",
#                           "lineNumber": 456
#                       },
#                       {
#                           "id": 2,
#                           "title": "Unused variable",
#                           "description": "...",
#                           "severity": "Low",
#                           "contract": "TokenContract",
#                           "function": "transfer",
#                           "lineNumber": 789
#                       }
#                   ]
#               }
#               ```

#               The resulting JSON object is clean, organized, and follows the specified
#               format."""

# mr = MapReducer()
# a = mr.parse_json(test_map_res, MapReduceResult)
# print(a)
# res = map_reducer.parse_json(test_response, MapReduceResult())
# doc_handler = DocumentHandler(
#     filepath="tests/test_cases/extractor/input/2024-08-superposition-findings.md"
# )

# doc_handler.read_file()
# documents = doc_handler.split_by_heading(2)
# fragments = doc_handler.merge_documents(2048, documents)

# result = map_reducer.map_reduce(fragments)
# print(result)

# res = map_reducer.reduce_call(test_extracted_data)
# print(res)

# mr = MapReducer()
# results = [
#     MapReduceResult(ProjectInfo(url="test"), [Finding(id=1)]),
#     MapReduceResult(ProjectInfo(url="test2"), [Finding(id=1, title="a"), Finding()]),
# ]
# res = mr.merge_results(results)
# print(res)

# test_str = """After cleaning and deduplicating the extracted vulnerability data and source code details, I generated a structured JSON output as follows:


#               ```
#               {
#                 "project_info": {
#                   "url": "https://github.com/BabyChickenOrg/Smart-Contract/",
#                   "commit_id": "ad7858625330b1ced0133118fc3d97287cdbeb7c",
#                   "address": "n/a",
#                   "chain": "n/a"
#                 },
#                 "findings": [
#                   {
#                     "id": 0,
#                     "title": "Out of gas",
#                     "description": "The functions use loops that can cause an OUT_OF_GAS exception if the excluded addresses list is too long.",
#                     "severity": "Low",
#                     "location": "Functions includeInReward() and _getCurrentSupply()"
#                   }
#                 ]
#               }
#               ```

#               Please let me know if this output meets your requirements or if you need
#               any further assistance!
# """

# mr = MapReducer()
# res = mr.parse_json(test_str, MapReduceResult)
# print(res)
