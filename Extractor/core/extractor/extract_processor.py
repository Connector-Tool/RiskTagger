import os
import json
import yaml
from typing import List
from loguru import logger

from extractor.document_handler import DocumentHandler
from extractor.map_reducer import MapReducer
from core.models import Report
from core.invoker import CHUNK_LENGTH


class ExtractProcessor:
    def __init__(self, target: str, output_dir: str, config_path: str):
        self.filepath = target
        self.output_dir = output_dir
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        self.context_length = CHUNK_LENGTH

    def run(self):
        logger.info(f"开始提取文件: {self.filepath}")

        chunks = self._parse_file(self.filepath)
        if not chunks:
            logger.error("文件解析失败或文件内容为空。")
            return

        map_reducer = MapReducer()
        map_reduce_result = map_reducer.map_reduce(chunks, self.context_length)

        if map_reduce_result is None:
            logger.warning("MapReduce 失败返回了 None，提前退出。")
            return

        logger.info(f"提取完成！共找到 {len(map_reduce_result.findings)} 条攻击发现信息。")

        report = Report(
            path=self.filepath,
            project_info=map_reduce_result.project_info,
            findings=map_reduce_result.findings,
        )

        self._save_report(report)

    def _parse_file(self, filepath: str) -> List[str]:
        max_heading_level = self.config.get("extractor", {}).get("max_heading_level", 3)
        doc_handler = DocumentHandler(
            max_level=max_heading_level,
            max_tokens=self.context_length
        )
        return doc_handler.process(filepath=filepath)

    def _save_report(self, report: Report):
        os.makedirs(self.output_dir, exist_ok=True)
        filename = os.path.basename(self.filepath) + ".json"
        output_path = os.path.join(self.output_dir, filename)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report.model_dump(), f, indent=4, ensure_ascii=False)
        logger.info(f"报告已成功保存至: {output_path}")