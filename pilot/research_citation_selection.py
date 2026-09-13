"""Host-fragment citation choices expanded into the durable selection contract."""
from __future__ import annotations

import json
import re

from pilot.execution_contract import ExecutionRuntimeError
from pilot.research_page_selection import SCHEMA_VERSION, page_selection_schema, parse_page_selection


CITATION_SCHEMA_VERSION = "research-citation-choice-v1"
CITATION_CHOICE_INSTRUCTIONS = """# 最终逐页引用选择合同（research-citation-choice-v1）

最后一次回答必须且只能是严格 JSON，不要 Markdown 围栏、解释或尾随文本：
{"schema_version":"research-citation-choice-v1","summary":"1至2000字符总结","pages":[{"url":"成功读取页的标准化原文URL","content_sha256":"持久原文SHA-256","decision":"ASSESS或BACKGROUND","reason":"枚举值","quote_ref":"该页宿主原文片段编号，如q1"}]}
每个成功读取的唯一 (url, content_sha256) 必须且只能出现一次，且 quote_ref 必须选择该页 text_fragments 中实际存在的编号；不得返回 quote 原文、搜索摘要、未读页面、其他页编号或推断文字。
text_fragments 是宿主按原文连续切分的可逆片段，仅用于逐字引用；它本身不证明作者身份、发布时间、采购意图或审核通过。
ASSESS 的 reason 只能是 POSSIBLE_DEMAND 或 UNCERTAIN；BACKGROUND 的 reason 只能是 INDEX、VENDOR_CONTENT、NO_BUYER_SIGNAL、STALE_OR_CLOSED、IRRELEVANT。
判断不确定时选择 ASSESS/UNCERTAIN。不得仅因预算、直接联系方式或公开身份缺失而排除；混合页面含可能买方评论时选择 ASSESS。BACKGROUND 不是永久排除或零需求，ASSESS 也不是已核验商机。
总 JSON UTF-8 不超过512KiB，pages 不超过100项。
"""

_ROOT_KEYS = {"schema_version", "summary", "pages"}
_PAGE_KEYS = {"url", "content_sha256", "decision", "reason", "quote_ref"}


def _invalid():
    raise ExecutionRuntimeError("research_selection_invalid", 409)


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _invalid()
        result[key] = value
    return result


def _reject_constant(_value):
    _invalid()


def citation_fragments(text: str) -> list[dict]:
    """Split exact Python characters without normalization or truncation."""
    if type(text) is not str:
        _invalid()
    return [{"quote_ref": f"q{offset // 400 + 1}", "text": text[offset:offset + 400]}
            for offset in range(0, len(text), 400)]


def citation_choice_schema() -> dict:
    """Return a detached provider schema derived from the durable v1 shape."""
    schema = page_selection_schema()
    schema["properties"]["schema_version"]["enum"] = [CITATION_SCHEMA_VERSION]
    page = schema["properties"]["pages"]["items"]
    page["properties"]["quote_ref"] = page["properties"].pop("quote")
    page["required"] = ["quote_ref" if key == "quote" else key for key in page["required"]]
    return schema


def expand_citation_choices(summary: str, evidences: list[dict]) -> str:
    """Expand model-selected refs with host text, then enforce the original parser."""
    if type(summary) is not str or type(evidences) is not list:
        _invalid()
    try:
        if len(summary.encode("utf-8")) > 512 * 1024:
            _invalid()
        root = json.loads(summary, object_pairs_hook=_object, parse_constant=_reject_constant)
    except (ValueError, UnicodeError, RecursionError, TypeError):
        _invalid()
    if (type(root) is not dict or set(root) != _ROOT_KEYS
            or root.get("schema_version") != CITATION_SCHEMA_VERSION
            or type(root.get("summary")) is not str
            or type(root.get("pages")) is not list
            or len(root["pages"]) > 100):
        _invalid()
    unique = {}
    for evidence in evidences:
        if (type(evidence) is not dict or type(evidence.get("url")) is not str
                or type(evidence.get("content_sha256")) is not str
                or type(evidence.get("text")) is not str):
            _invalid()
        key = (evidence["url"], evidence["content_sha256"])
        prior = unique.get(key)
        if prior is not None and prior["text"] != evidence["text"]:
            _invalid()
        unique[key] = evidence
    if len(root["pages"]) != len(unique):
        _invalid()
    expanded_pages, seen = [], set()
    for page in root["pages"]:
        if (type(page) is not dict or set(page) != _PAGE_KEYS
                or any(type(page.get(key)) is not str for key in _PAGE_KEYS)):
            _invalid()
        key = (page["url"], page["content_sha256"])
        if key in seen or key not in unique or not re.fullmatch(r"q[1-9][0-9]*", page["quote_ref"]):
            _invalid()
        fragments = citation_fragments(unique[key]["text"])
        index = int(page["quote_ref"][1:]) - 1
        if not 0 <= index < len(fragments):
            _invalid()
        seen.add(key)
        expanded_pages.append({
            "url": page["url"], "content_sha256": page["content_sha256"],
            "decision": page["decision"], "reason": page["reason"],
            "quote": fragments[index]["text"],
        })
    if seen != set(unique):
        _invalid()
    expanded = json.dumps({"schema_version": SCHEMA_VERSION, "summary": root["summary"],
                           "pages": expanded_pages}, ensure_ascii=False,
                          separators=(",", ":"), allow_nan=False)
    parse_page_selection(expanded, evidences)
    return expanded
