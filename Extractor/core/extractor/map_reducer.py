import re
import json
import time
import tiktoken

from typing import List, Literal
from loguru import logger
from pydantic import BaseModel, TypeAdapter

# 【修改点3】改为直接引用 pip 安装的官方包
import commentjson
from core.models import MapReduceResult, Context
from core.invoker import invoke_map, invoke_reduce, MAX_RETRIES, INTERVAL, CONFIG

MODE: Literal["strict", "normal"] = CONFIG["extractor"]["mode"]


class MapReducer(BaseModel):
    class Config:
        arbitrary_types_allowed = True

    @logger.catch
    def map_reduce(self, documents: List[str], context_length: int) -> MapReduceResult:
        logger.info(f"以 {MODE} 模式启动。")
        logger.info("开始进行 Map (片段提取)...")
        context_list: List[Context] = self._map(documents)
        logger.info("开始进行 Reduce (结果融合洗钱与攻击数据)...")
        return self._reduce(context_list, context_length)

    def _map(self, documents: List[str]) -> List[Context]:
        context_list: List[Context] = []

        for i in range(len(documents)):
            context = Context(index=i, document=documents[i], length=0)
            retry = 0
            while retry < MAX_RETRIES:
                try:
                    map_result = self._parse_answer(invoke_map(context.document))
                    context.response = map_result
                    length = self._calc_token_length(map_result)
                    context.length = length
                    context_list.append(context)
                    break
                except Exception as e:
                    retry += 1
                    backoff_time = INTERVAL * retry
                    logger.error(
                        f"处理第 {i} 个片段时报错: {str(e)}\n"
                        f"将在 {backoff_time} 秒后重试 ({retry}/{MAX_RETRIES})."
                    )
                    if retry < MAX_RETRIES:
                        time.sleep(backoff_time)

            if retry == MAX_RETRIES:
                context.response = ""
                context.length = 0
                context_list.append(context)
        return context_list

    def _reduce(self, context_list: List[Context], context_length: int) -> MapReduceResult:
        reduce_messages = []
        reduce_tokens = 0
        part_results: List[MapReduceResult] = []

        for context in context_list:
            if not context.response or context.response == "None" or context.response == "Answer: None":
                continue

            msg = f"Fragment {context.index}:\n{context.response}\n"

            if not reduce_messages:
                reduce_messages.append(msg)
                reduce_tokens += context.length
                continue

            if reduce_tokens + context.length >= context_length:
                logger.info(f"当前聚合 Token={reduce_tokens}，触发一次 Reduce...")
                resp_parsed = self._do_reduce_call(reduce_messages)
                if resp_parsed:
                    part_results.append(resp_parsed)

                reduce_messages = [msg]
                reduce_tokens = context.length
            else:
                reduce_messages.append(msg)
                reduce_tokens += context.length

        if reduce_messages:
            logger.info(f"清理剩余的 Token={reduce_tokens}，触发最后一次 Reduce...")
            resp_parsed = self._do_reduce_call(reduce_messages)
            if resp_parsed:
                part_results.append(resp_parsed)

        return self._merge_results(part_results)

    def _do_reduce_call(self, reduce_messages: List[str]) -> MapReduceResult:
        retry = 0
        while retry < MAX_RETRIES:
            try:
                resp = invoke_reduce("\n".join(reduce_messages))
                resp_parsed = self._parse_json(resp, MapReduceResult)
                if resp_parsed:
                    return resp_parsed

                retry += 1
                logger.warning(f"JSON 格式解析失败. 重试: {retry}/{MAX_RETRIES}")
            except Exception as e:
                retry += 1
                logger.error(f"聚合请求失败: {str(e)}. 重试: {retry}/{MAX_RETRIES}")
                if retry < MAX_RETRIES:
                    time.sleep(INTERVAL * retry)
        return None

    def _merge_results(self, partial: List[MapReduceResult]) -> MapReduceResult:
        partial = [p for p in partial if p is not None]
        if not partial:
            return MapReduceResult()

        result = MapReduceResult()
        index = 0

        for p in partial:
            event_name = p.project_info.event_name
            date = p.project_info.date
            urls = p.project_info.source_report_url

            if result.project_info.event_name == "n/a" or not result.project_info.event_name:
                result.project_info.event_name = event_name
            if result.project_info.date == "n/a" or not result.project_info.date:
                result.project_info.date = date

            if urls and urls != ["n/a"]:
                for url in urls:
                    if url != "n/a" and url not in result.project_info.source_report_url:
                        result.project_info.source_report_url.append(url)

            valid_findings = []
            for finding in p.findings:
                if (not finding.attack_vector or finding.attack_vector == ["n/a"]) and \
                        (not finding.laundering_methods or finding.laundering_methods == ["n/a"]):
                    continue

                finding.id = index
                index += 1
                valid_findings.append(finding)

            result.findings.extend(valid_findings)

        return result

    def _calc_token_length(self, text: str) -> int:
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))

    def _parse_answer(self, response: str) -> str:
        PATTERN = re.compile(r"Answer:\s*(.*)", re.IGNORECASE | re.DOTALL | re.MULTILINE)
        match = PATTERN.search(response)
        if match and len(match.group(1).strip("\n")) > 3:
            return match.group(1)
        return response

    def _parse_json(self, response: str, schema: BaseModel) -> BaseModel:
        PATTERN = re.compile(r"`{3}(?:json\s+)?(\W.*?)`{3}", re.IGNORECASE | re.DOTALL | re.MULTILINE)
        match = PATTERN.search(response)

        try:
            if match:
                json_str = match.group(1)
                json_dict = commentjson.loads(json_str)
                validated = TypeAdapter(schema).validate_json(json.dumps(json_dict))
                return validated
            else:
                alt_pattern = re.compile(r'\{.*\}', re.DOTALL)
                alt_match = alt_pattern.search(response)
                if alt_match:
                    json_dict = commentjson.loads(alt_match.group(0))
                    return TypeAdapter(schema).validate_json(json.dumps(json_dict))
                return None
        except Exception as e:
            logger.error(f"提取阶段的 JSON 解析出错: {str(e)}")
            return None