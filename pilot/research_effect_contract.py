"""Strict, persistence-safe contracts for durable research effects."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit

from pilot.execution_contract import ExecutionRuntimeError, canonical_uuid
from pilot.open_web_reader import PublicReadError, normalize_public_url, valid_page_evidence
from pilot.public_search import normalize_query, valid_search_result
from pilot.responses_bridge import BridgeError, ResponsesBridge, _alias


_MAX_BYTES = 2 * 1024 * 1024
_HEX = re.compile(r"^[0-9a-f]{64}$")
_SECRET = re.compile(
    r"(?i)(?:\b(?:api[_ -]?key|access[_ -]?token|authorization|password|secret|cookie|session|xsec[_ -]?token)\b\s*[:=]\s*\S+"
    r"|\bbearer\s+\S+|\bsk-[A-Za-z0-9_-]{16,})"
)
_SENSITIVE_KEYS = {
    "apikey", "accesskey", "accesskeyid", "secretkey", "secretaccesskey",
    "clientsecret", "credential", "credentials", "authorization", "auth",
    "token", "accesstoken", "refreshtoken", "idtoken", "password", "passwd",
    "pwd", "cookie", "session", "sessionid", "signature", "sig", "xsectoken",
}
_BINDING_KEYS = {
    "schema_version", "rule_version", "rule_sha256", "context_sha256",
    "profile_version_id", "strategy_version_id", "profile_sha256",
    "configuration_sha256",
}
_PUBLIC_TOOLS = {
    ("mcp__yike_public", "search_public_web"),
    ("mcp__yike_public", "read_public_page"),
}
_ALIASES = {_alias(*pair): pair for pair in _PUBLIC_TOOLS}
_ASSIGNMENT_KEY = re.compile(
    r"(?i)(?:\\?[\"']([a-z][a-z0-9_ -]{0,63})\\?[\"']|\b([a-z][a-z0-9_ -]{0,63})\b)\s*[:=]"
)
_PUBLIC_URL = re.compile(r"(?i)https?:(?:\\?/){2}[^\s\"'<>]+")


def _normalized_field_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _sensitive_field_name(value: str) -> bool:
    normalized = _normalized_field_name(value)
    return normalized in _SENSITIVE_KEYS or (
        normalized.startswith("x") and normalized[1:] in _SENSITIVE_KEYS)


def _string_contains_secret(value: str) -> bool:
    # Decode URL escapes once and JSON slash escapes without expanding the input.
    decoded = unquote(value).replace(r"\/", "/")
    if any(_sensitive_field_name(match.group(1) or match.group(2))
           for match in _ASSIGNMENT_KEY.finditer(decoded)):
        return True
    for match in _PUBLIC_URL.finditer(decoded):
        try:
            query = urlsplit(match.group(0)).query
            if any(_sensitive_field_name(key) for key, _value in parse_qsl(
                    query, keep_blank_values=True, max_num_fields=100)):
                return True
        except ValueError:
            return True
    return _SECRET.search(decoded) is not None


def _invalid_input() -> None:
    raise ExecutionRuntimeError("invalid_effect_input", 422)


def _invalid_result() -> None:
    raise ExecutionRuntimeError("invalid_effect_result", 422)


def _canonical(value: Any, *, result: bool = False) -> tuple[Any, bytes]:
    def safe_text(item: str) -> bool:
        return not any(
            ord(char) < 32 and char not in "\t\n\r" or 127 <= ord(char) <= 159
            for char in item)

    def safe_key(key: str) -> bool:
        if not safe_text(key):
            return False
        return not _sensitive_field_name(key)

    def plain(item: Any) -> bool:
        kind = type(item)
        if item is None or kind in (str, bool, int):
            return kind is not str or safe_text(item) and not _string_contains_secret(item)
        if kind is float:
            return math.isfinite(item)
        if kind is list:
            return all(plain(child) for child in item)
        return kind is dict and all(
            type(key) is str and safe_key(key) and plain(child)
            for key, child in item.items())
    try:
        if not plain(value):
            raise ValueError
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode("utf-8")
        if len(encoded) > _MAX_BYTES or _SECRET.search(encoded.decode("utf-8")):
            raise ValueError
        return copy.deepcopy(value), encoded
    except (RecursionError, TypeError, UnicodeError, ValueError):
        (_invalid_result if result else _invalid_input)()


def _binding(value: Any) -> dict:
    clean, _ = _canonical(value)
    try:
        if type(clean) is not dict or set(clean) != _BINDING_KEYS:
            _invalid_input()
        if clean["schema_version"] != "research-context-v2":
            _invalid_input()
        if (type(clean["rule_version"]) is not str
                or not clean["rule_version"].startswith("opportunity-research-context-v2/")):
            _invalid_input()
        for key in ("rule_sha256", "context_sha256", "profile_sha256", "configuration_sha256"):
            if type(clean[key]) is not str or _HEX.fullmatch(clean[key]) is None:
                _invalid_input()
        canonical_uuid(clean["profile_version_id"])
        canonical_uuid(clean["strategy_version_id"])
        return clean
    except ExecutionRuntimeError:
        _invalid_input()


def _model_payload(value: dict) -> dict:
    if not {"model", "input", "tools", "stream"} <= set(value):
        _invalid_input()
    if (type(value["model"]) is not str or not value["model"].strip()
            or type(value["input"]) is not list or type(value["tools"]) is not list
            or value["stream"] is not True):
        _invalid_input()
    for tool in value["tools"]:
        if (type(tool) is not dict or tool.get("type") != "function"
                or tool.get("name") not in _ALIASES):
            _invalid_input()
    for item in value["input"]:
        if type(item) is dict and item.get("type") == "function_call" and item.get("name") not in _ALIASES:
            _invalid_input()
        if type(item) is dict and isinstance(item.get("type"), str) \
                and item["type"].endswith("_call") and item["type"] != "function_call":
            _invalid_input()
    return value


def effect_input(kind, payload, context_binding) -> tuple[dict, str]:
    """Validate and bind the complete effect input without retaining caller objects."""
    try:
        if kind not in {"MODEL", "SEARCH", "READ"} or type(payload) is not dict:
            _invalid_input()
        clean, _ = _canonical(payload)
        bound = _binding(context_binding)
        if kind == "SEARCH":
            if set(clean) != {"query"} or normalize_query(clean["query"]) != clean["query"]:
                _invalid_input()
        elif kind == "READ":
            if set(clean) != {"url"} or normalize_public_url(clean["url"]) != clean["url"]:
                _invalid_input()
        else:
            _model_payload(clean)
        envelope = {"schema_version": "research-effect-input-v1", "kind": kind,
                    "payload": clean, "context_binding": bound}
        _, encoded = _canonical(envelope)
        return clean, hashlib.sha256(encoded).hexdigest()
    except (ExecutionRuntimeError, PublicReadError, ValueError, TypeError, KeyError):
        _invalid_input()


class _RestoredValidator:
    def __init__(self, allowed: set[tuple[str, str]]):
        self.allowed = allowed

    def _restore_item(self, source: Any):
        if type(source) is not dict:
            raise BridgeError("provider_error")
        item = copy.deepcopy(source)
        item_type = item.get("type")
        if isinstance(item_type, str) and item_type.endswith("_call") and item_type != "function_call":
            raise BridgeError("provider_error")
        if item_type == "function_call":
            if (item.get("namespace"), item.get("name")) not in self.allowed:
                raise BridgeError("provider_error")
        return item


def effect_result(kind, payload, result) -> dict:
    """Return only a copied, validated successful effect result."""
    try:
        clean_payload, _ = _canonical(payload)
        clean, _ = _canonical(result, result=True)
        if type(clean) is not dict:
            _invalid_result()
        if kind == "SEARCH":
            if (set(clean_payload) != {"query"} or clean.get("status") != "SEARCHED"
                    or not valid_search_result(clean, clean_payload["query"])):
                _invalid_result()
        elif kind == "READ":
            expected = {"status", "evidence", "review_status", "replayed"}
            if (set(clean_payload) != {"url"} or set(clean) != expected
                    or clean.get("status") != "READ" or clean.get("review_status") != "UNREVIEWED"
                    or type(clean.get("replayed")) is not bool
                    or not valid_page_evidence(clean.get("evidence"), clean_payload["url"])):
                _invalid_result()
        elif kind == "MODEL":
            _model_payload(clean_payload)
            if (set(clean) != {"status", "code", "body", "usage"}
                    or clean["status"] != 200 or clean["code"] != "ok"
                    or type(clean["body"]) is not str
                    or not (clean["usage"] is None or type(clean["usage"]) is dict)):
                _invalid_result()
            allowed = {_ALIASES[tool["name"]] for tool in clean_payload["tools"]}
            _body, usage = ResponsesBridge._inbound(_RestoredValidator(allowed), clean["body"].encode("utf-8"))
            if usage != clean["usage"]:
                _invalid_result()
        else:
            _invalid_result()
        return clean
    except ExecutionRuntimeError:
        raise
    except (BridgeError, KeyError, TypeError, ValueError, UnicodeError, RecursionError):
        _invalid_result()


def canonical_effect_sha256(value: Any) -> str:
    """Internal canonical digest used to verify immutable journal output."""
    _clean, encoded = _canonical(value, result=True)
    return hashlib.sha256(encoded).hexdigest()
