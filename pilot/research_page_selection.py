"""Strict, evidence-bound final page selection for dynamic research."""
from __future__ import annotations

import json
import re

from pilot.execution_contract import ExecutionRuntimeError
from pilot.open_web_reader import PublicReadError, normalize_public_url


SCHEMA_VERSION = "research-page-selection-v1"
SELECTION_INSTRUCTIONS = """# 最终逐页筛选合同（research-page-selection-v1）

最后一次回答必须且只能是严格 JSON，不要 Markdown 围栏、解释或尾随文本：
{"schema_version":"research-page-selection-v1","summary":"1至2000字符总结","pages":[{"url":"成功读取页的标准化原文URL","content_sha256":"持久原文SHA-256","decision":"ASSESS或BACKGROUND","reason":"枚举值","quote":"原文逐字片段"}]}
每个成功读取的唯一 (url, content_sha256) 必须且只能出现一次，不得使用搜索摘要、未读页面或推断文字。quote 必须为原文 text 中1至400字符的逐字片段。
ASSESS 的 reason 只能是 POSSIBLE_DEMAND 或 UNCERTAIN；BACKGROUND 的 reason 只能是 INDEX、VENDOR_CONTENT、NO_BUYER_SIGNAL、STALE_OR_CLOSED、IRRELEVANT。
判断不确定时选择 ASSESS/UNCERTAIN。不得仅因预算、直接联系方式或公开身份缺失而排除；混合页面含可能买方评论时选择 ASSESS。BACKGROUND 不是永久排除或零需求，ASSESS 也不是已核验商机。
总 JSON UTF-8 不超过512KiB，pages 不超过100项。
"""

_PAGE_KEYS = {"url", "content_sha256", "decision", "reason", "quote"}
_DECISION_KEYS = _PAGE_KEYS | {"schema_version"}
_ROOT_KEYS = {"schema_version", "summary", "pages"}
_ASSESS_REASONS = {"POSSIBLE_DEMAND", "UNCERTAIN"}
_BACKGROUND_REASONS = {"INDEX", "VENDOR_CONTENT", "NO_BUYER_SIGNAL", "STALE_OR_CLOSED", "IRRELEVANT"}


def page_selection_schema() -> dict:
    """Return a detached provider schema; semantic evidence checks stay local."""
    reasons = [
        "POSSIBLE_DEMAND", "UNCERTAIN", "INDEX", "VENDOR_CONTENT",
        "NO_BUYER_SIGNAL", "STALE_OR_CLOSED", "IRRELEVANT",
    ]
    page = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "content_sha256": {"type": "string"},
            "decision": {"type": "string", "enum": ["ASSESS", "BACKGROUND"]},
            "reason": {"type": "string", "enum": reasons},
            "quote": {"type": "string"},
        },
        "required": ["url", "content_sha256", "decision", "reason", "quote"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "schema_version": {"type": "string", "enum": [SCHEMA_VERSION]},
            "summary": {"type": "string"},
            "pages": {"type": "array", "items": page},
        },
        "required": ["schema_version", "summary", "pages"],
        "additionalProperties": False,
    }


def _invalid():
    raise ExecutionRuntimeError("research_selection_invalid", 409)


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            _invalid()
        value[key] = item
    return value


def _reject_constant(_value):
    _invalid()


def validate_page_selection(decision: dict, evidence: dict) -> dict:
    """Validate one detached versioned decision against one durable READ evidence."""
    if type(decision) is not dict or set(decision) != _DECISION_KEYS or type(evidence) is not dict:
        _invalid()
    if decision["schema_version"] != SCHEMA_VERSION:
        _invalid()
    url, digest, choice, reason, quote = (decision[key] for key in
        ("url", "content_sha256", "decision", "reason", "quote"))
    if any(type(value) is not str for value in (url, digest, choice, reason, quote)):
        _invalid()
    try:
        normalized = normalize_public_url(url)
    except PublicReadError:
        _invalid()
    evidence_text = evidence.get("text")
    if (type(evidence_text) is not str or normalized != url or url != evidence.get("url")
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or digest != evidence.get("content_sha256")
            or not 1 <= len(quote) <= 400 or not quote.strip() or quote not in evidence_text):
        _invalid()
    if choice == "ASSESS":
        if reason not in _ASSESS_REASONS:
            _invalid()
    elif choice == "BACKGROUND":
        if reason not in _BACKGROUND_REASONS:
            _invalid()
    else:
        _invalid()
    return {key: decision[key] for key in
            ("schema_version", "url", "content_sha256", "decision", "reason", "quote")}


def parse_page_selection(summary: str, evidences: list[dict]) -> list[dict]:
    """Parse a complete strict final answer and bind every unique durable page."""
    if type(summary) is not str or type(evidences) is not list:
        _invalid()
    try:
        if len(summary.encode("utf-8")) > 512 * 1024:
            _invalid()
        root = json.loads(summary, object_pairs_hook=_object, parse_constant=_reject_constant)
    except (ValueError, UnicodeError, RecursionError, TypeError):
        _invalid()
    if type(root) is not dict or set(root) != _ROOT_KEYS or root.get("schema_version") != SCHEMA_VERSION:
        _invalid()
    text = root.get("summary")
    pages = root.get("pages")
    if type(text) is not str or not 1 <= len(text) <= 2000 or not text.strip() \
            or type(pages) is not list or len(pages) > 100:
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
    if len(pages) != len(unique):
        _invalid()
    results, seen = [], set()
    for page in pages:
        if type(page) is not dict or set(page) != _PAGE_KEYS:
            _invalid()
        if type(page.get("url")) is not str or type(page.get("content_sha256")) is not str:
            _invalid()
        key = (page.get("url"), page.get("content_sha256"))
        if key in seen or key not in unique:
            _invalid()
        seen.add(key)
        results.append(validate_page_selection(
            {"schema_version": SCHEMA_VERSION, **page}, unique[key]
        ))
    if seen != set(unique):
        _invalid()
    return results
