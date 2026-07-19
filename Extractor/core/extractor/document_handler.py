import os
import re
import tiktoken
from pydantic import BaseModel
from dataclasses import dataclass
from semantic_text_splitter import TextSplitter
from typing import List, Optional

# 【修改点1】改为直接引用 pip 安装的官方包
import pymupdf4llm

os.environ["TIKTOKEN_CACHE_DIR"] = "__pycache__"

FENCES = ["`" * 3, "~" * 3]
MAX_HEADING_LEVEL = 6


@dataclass
class Document:
    parent_headings: List[Optional[str]]
    heading: str
    text: List[str]


class Line(BaseModel):
    line: str
    heading_level: int = 0
    heading_title: Optional[str] = None

    def __init__(self, line):
        super().__init__(line=line)
        self._detect_heading(line)

    def _detect_heading(self, line):
        self.heading_level = 0
        self.heading_title = None
        result = re.search("^[ ]{0,3}(#+)(.*)", line)
        if result is not None and (len(result[1]) <= MAX_HEADING_LEVEL):
            title = result[2]
            if len(title) > 0 and not (title.startswith(" ") or title.startswith("\t")):
                return
            self.heading_level = len(result[1])
            title = title.strip().rstrip("#").rstrip()
            self.heading_title = title

    def is_fence(self):
        for fence in FENCES:
            if self.line.startswith(fence):
                return True
        return False

    def is_heading(self):
        return self.heading_level > 0


def split_by_heading(text, max_level):
    curr_parent_headings = [None] * MAX_HEADING_LEVEL
    curr_heading_line = None
    curr_lines = []
    within_fence = False

    for next_line in text.splitlines():
        next_line = Line(line=next_line)
        if next_line.is_fence():
            within_fence = not within_fence

        is_chapter_finished = (
                not within_fence
                and next_line.is_heading()
                and next_line.heading_level <= max_level
        )

        if is_chapter_finished:
            if len(curr_lines) > 0:
                parents = __get_parents(curr_parent_headings, curr_heading_line)
                yield Document(parents, curr_heading_line, curr_lines)

                if curr_heading_line is not None:
                    curr_level = curr_heading_line.heading_level
                    curr_parent_headings[curr_level - 1] = curr_heading_line.heading_title
                    for level in range(curr_level, MAX_HEADING_LEVEL):
                        curr_parent_headings[level] = None

            curr_heading_line = next_line
            curr_lines = []

        curr_lines.append(next_line.line)

    parents = __get_parents(curr_parent_headings, curr_heading_line)
    yield Document(parents, curr_heading_line, curr_lines)


def __get_parents(parent_headings, heading_line):
    if heading_line is None:
        return []
    max_level = heading_line.heading_level
    trunc = list(parent_headings)[: (max_level - 1)]
    return [h for h in trunc if h is not None]


class MdTextSplitter(BaseModel):
    max_level: int = 3
    max_tokens: int = 1024

    def _split_by_token(self, text: str, max_tokens: int = 1024) -> List[str]:
        splitter = TextSplitter.from_tiktoken_model("gpt-4o", max_tokens)
        chunks = splitter.chunks(text)
        return chunks

    def split(self, md_text: str) -> List[str]:
        documents = list(split_by_heading(md_text, self.max_level))
        str_list: List[str] = ["\n".join(doc.text) for doc in documents]
        splitted: List[str] = []
        for text in str_list:
            splitted.extend(self._split_by_token(text, self.max_tokens))
        return splitted


class DocumentHandler(BaseModel):
    max_level: int = 3
    max_tokens: int = 1024

    def process(self, filepath: str = None) -> List[str]:
        md_text = self._read_file(filepath)
        md_text = md_text.replace("**\u200c**", "").replace("\u200c", "").replace("\u202c", "").replace("\u202d", "")
        splitter = MdTextSplitter(max_level=self.max_level, max_tokens=self.max_tokens)
        text_splitted: List[str] = splitter.split(md_text)
        return self._merge_documents(self.max_tokens, text_splitted)

    def _read_file(self, filepath: str) -> str:
        extname = os.path.splitext(filepath)[1].lower()
        if extname == ".pdf":
            # 【修改点2】使用官方库的方法调用
            md_text = pymupdf4llm.to_markdown(filepath)
        elif extname == ".md" or extname == ".txt":
            with open(filepath, "r", encoding="utf-8") as f:
                md_text = f.read()
        else:
            raise ValueError(f"不支持的文件格式: {extname}")
        return md_text

    def _calc_token_length(self, text: str) -> int:
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))

    def _merge_documents(self, context_length: int, documents: List[str]) -> List[str]:
        if not documents:
            return []
        current_chunk = []
        current_length = 0
        merged = []

        for doc in documents:
            doc_length = self._calc_token_length(doc)
            if not current_chunk:
                current_chunk.append(doc)
                current_length = doc_length
                continue

            if current_length + doc_length >= context_length:
                if current_length < (context_length / 3):
                    current_chunk.append(doc)
                    current_length += doc_length
                else:
                    merged.append(current_chunk)
                    current_chunk = [doc]
                    current_length = doc_length
            else:
                current_chunk.append(doc)
                current_length += doc_length

        if current_chunk:
            merged.append(current_chunk)

        return ["\n".join(chunk) for chunk in merged]