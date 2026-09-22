"""Deterministic, bounded query expansion for public buyer-intent research.

This module only plans search strings. It does not grant a source, read a page,
log in, or send a message. Source permissions and the shared search budget stay
with the research runtime.
"""
from __future__ import annotations

import re


_SECRET = re.compile(
    r"(?i)(?:\b(?:api[_ -]?key|access[_ -]?token|authorization|password|secret)\b\s*[:=]\s*\S+"
    r"|\bbearer\s+\S+|\bsk-[A-Za-z0-9_-]{16,})"
)
_DEFAULT_ACTIONS = (
    "询价", "找供应商", "求方案", "招募团队", "外包开发", "采购需求",
)


def _invalid() -> None:
    raise ValueError("invalid query portfolio input")


def _terms(value: object, *, maximum: int) -> list[str]:
    if type(value) is not list or len(value) > maximum:
        _invalid()
    result: list[str] = []
    for item in value:
        if type(item) is not str or not 1 <= len(item.strip()) <= 160:
            _invalid()
        item = " ".join(item.split())
        if not item or _SECRET.search(item) or any(ord(char) < 32 for char in item):
            _invalid()
        if item not in result:
            result.append(item)
    return result


def build_query_portfolio(*, query_seeds: list[str], intent_signals: list[str],
                          exclusions: list[str] | None = None, region: str = "",
                          max_queries: int = 24) -> list[str]:
    """Return stable, diverse buyer-intent queries within a small hard bound.

    The first pass preserves explicit user signals. A second pass adds negative
    exclusions so vendor/recruitment noise is reduced without making every query
    over-constrained. The caller still owns pagination, retries, and source
    capability checks.
    """
    seeds = _terms(query_seeds, maximum=20)
    signals = _terms(intent_signals, maximum=20)
    excluded = _terms(exclusions or [], maximum=25)
    if not 1 <= max_queries <= 64:
        _invalid()
    if not seeds:
        seeds = ["公开需求"]
    if type(region) is not str or len(region.strip()) > 80:
        _invalid()
    region = " ".join(region.split())
    if _SECRET.search(region) or any(ord(char) < 32 for char in region):
        _invalid()

    actions = signals or list(_DEFAULT_ACTIONS)
    fallback_actions = [action for action in _DEFAULT_ACTIONS if action not in actions]
    candidates: list[str] = []

    def add(seed: str, action: str, negative: bool = False) -> None:
        parts = [part for part in (region, seed, action) if part]
        if negative and excluded:
            parts.extend(f"-{item}" for item in excluded[:4])
        query = " ".join(parts)
        if len(query) <= 512 and query not in candidates:
            candidates.append(query)

    for seed in seeds:
        for action in actions:
            add(seed, action)
    for seed in seeds:
        for action in actions:
            add(seed, action, negative=True)
    for seed in seeds:
        for action in fallback_actions:
            add(seed, action)
    for seed in seeds:
        for action in fallback_actions:
            add(seed, action, negative=True)
    for seed in seeds:
        add(seed, "", negative=True)
    return candidates[:max_queries]
