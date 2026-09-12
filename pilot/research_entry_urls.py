"""Strict transport contract for host-derived public research entries."""
from __future__ import annotations

import json

from pilot.open_web_reader import PublicReadError, normalize_public_url

_MAX_ENTRY_URLS = 20
_MAX_TRANSPORT_BYTES = 45 * 1024


def _invalid() -> None:
    raise ValueError("invalid_entry_urls")


def validate_entry_urls(value) -> tuple[str, ...]:
    if type(value) not in (list, tuple) or len(value) > _MAX_ENTRY_URLS:
        _invalid()
    entries = []
    for item in value:
        if type(item) is not str:
            _invalid()
        try:
            normalized = normalize_public_url(item)
        except PublicReadError:
            _invalid()
        if normalized != item or normalized in entries:
            _invalid()
        entries.append(normalized)
    return tuple(entries)


def decode_entry_urls_json(raw) -> tuple[str, ...]:
    if type(raw) is not str:
        _invalid()
    try:
        encoded = raw.encode("utf-8")
    except UnicodeEncodeError:
        _invalid()
    if len(encoded) > _MAX_TRANSPORT_BYTES:
        _invalid()
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, RecursionError):
        _invalid()
    if type(value) is not list:
        _invalid()
    return validate_entry_urls(value)
