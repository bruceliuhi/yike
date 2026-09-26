"""Pure search planning shared by the customer product and Lead Radar.

Inputs are confirmed search conditions. This module has no database, source
catalog, credentials, network, or pricing dependency; a plan grants no execution.
"""
from __future__ import annotations

from itertools import zip_longest
import re
import unicodedata


VERSION = "radar-search-directions-v1"
_SECRET = re.compile(
    r"(?i)(?:\b(?:api[_ -]?key|access[_ -]?token|authorization|password|secret)\b\s*[:=]\s*\S+"
    r"|\bbearer\s+\S+|\bsk-[A-Za-z0-9_-]{16,})"
)


SYNONYMS: dict[str, tuple[str, ...]] = {
    "AI客服": ("AI客服", "智能客服", "客服机器人"),
    "企业知识库": ("企业知识库", "内部知识库", "文档问答"),
    "智能体": ("智能体", "Agent", "业务助手"),
    "AI工作流": ("AI工作流", "自动化工作流", "业务自动化"),
    "数字人": ("数字人", "虚拟人", "数字员工"),
    "找服务商": ("找服务商", "寻找团队", "找供应商"),
    "定制开发": ("定制开发", "定制", "开发落地"),
    "采购": ("采购", "寻求采购", "招标采购"),
    "预算": ("预算", "报价", "项目预算"),
    "外包": ("外包", "合作开发", "项目外包"),
    "落地": ("落地", "实施", "上线"),
}

SYNONYMS_EN: dict[str, tuple[str, ...]] = {
    "AI customer service": ("AI customer service", "AI support agent", "customer service automation"),
    "enterprise knowledge base": ("enterprise knowledge base", "internal knowledge base", "document Q&A"),
    "AI agent": ("AI agent", "business agent", "copilot"),
    "workflow automation": ("workflow automation", "business automation", "process automation"),
    "digital human": ("digital human", "virtual human", "digital employee"),
    "looking for vendor": ("looking for vendor", "seeking a provider", "vendor search"),
    "custom development": ("custom development", "bespoke software", "implementation partner"),
    "procurement": ("procurement", "purchasing", "buying"),
    "budget": ("budget", "project budget", "pricing"),
    "implementation": ("implementation", "deployment", "rollout"),
}


def _terms(values: object, maximum: int) -> list[str]:
    if type(values) is not list or len(values) > maximum:
        raise ValueError("invalid_search_directions")
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if (type(value) is not str or not 1 <= len(value) <= 160 or not value.strip()
                or any(unicodedata.category(char) in {"Cc", "Cf", "Cs", "Zl", "Zp"} for char in value)
                or _SECRET.search(value)):
            raise ValueError("invalid_search_directions")
        clean = " ".join(value.split())
        if clean.casefold() not in seen:
            result.append(clean)
            seen.add(clean.casefold())
    return result


def _alternatives(term: str) -> list[str]:
    # Expand only an exact supplied term; no generic AI-industry fallback.
    synonyms = {key.casefold(): values for key, values in (SYNONYMS | SYNONYMS_EN).items()}
    return [value for value in synonyms.get(term.casefold(), ())
            if value.casefold() != term.casefold()]


def build_search_directions(*, query_seeds: list[str], intent_signals: list[str],
                            exclusions: list[str] | None = None, region: str = "",
                            max_queries: int = 24,
                            business_terms: list[str] | None = None) -> dict:
    """Compile three inspectable directions from the current confirmed terms.

    Cover each explicit seed before spending the remaining bound on narrower
    checks and lexical alternatives. Empty groups remain empty when the user
    supplied no extra condition; that is preferable to invented search targets.
    All queries are editable plans, not discovered demand or authorized tools.
    """
    seeds = _terms(query_seeds, 20)
    signals = _terms(intent_signals, 20)
    excluded = _terms([] if exclusions is None else exclusions, 25)
    businesses = _terms([] if business_terms is None else business_terms, 20)
    if (type(max_queries) is not int or not 1 <= max_queries <= 64
            or type(region) is not str or len(region) > 160):
        raise ValueError("invalid_search_directions")
    region = _terms([region], 1)[0] if region else ""
    stages = [
        {"id": "quick", "name": "快速搜索", "purpose": "先查找直接表达需求的内容", "queries": []},
        {"id": "condition", "name": "条件核验", "purpose": "结合已确认条件减少无关结果", "queries": []},
        {"id": "broad", "name": "扩展搜索", "purpose": "用相关表达补查可能遗漏的需求", "queries": []},
    ]
    candidates: list[list[str]] = [[], [], []]

    def query(seed: str, signal: str = "", *, constrained: bool = False,
              business: str = "") -> str:
        # Do not repeat an action that the customer already included in a seed.
        action = "" if signal.casefold() in seed.casefold() else signal
        parts = [part for part in (region, seed, action, business) if part]
        if constrained:
            parts.extend('-"' + value.replace('"', '') + '"' if " " in value
                         else "-" + value for value in excluded[:4])
        return " ".join(parts)

    def add(stage: int, value: str) -> None:
        if value and len(value) <= 512 and value not in candidates[stage]:
            candidates[stage].append(value)

    for seed in seeds:
        add(0, query(seed, signals[0] if signals else ""))
    for signal in signals or [""]:
        for seed in seeds:
            for business in businesses[:2] or [""]:
                add(1, query(seed, signal, constrained=True, business=business))
    # Round-robin alternatives avoid exhausting the bound on the first seed.
    seed_alternatives = [_alternatives(seed) for seed in seeds]
    for alternatives in zip_longest(*seed_alternatives):
        for alternative in alternatives:
            if alternative is not None:
                add(2, query(alternative, signals[0] if signals else ""))
    for signal in signals:
        for alternative in _alternatives(signal):
            for seed in seeds:
                add(2, query(seed, alternative))
    for seed in seeds:
        add(2, query(seed))

    queries: list[str] = []
    seen: set[str] = set()

    def select(stage: int, value: str | None) -> None:
        if value is not None and len(queries) < max_queries and value.casefold() not in seen:
            queries.append(value)
            stages[stage]["queries"].append(value)
            seen.add(value.casefold())

    for value in candidates[0]:
        select(0, value)
    for condition, broad in zip_longest(candidates[1], candidates[2]):
        select(1, condition)
        select(2, broad)
    return {"version": VERSION, "strategies": stages, "queries": queries}
