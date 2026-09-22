"""API key issuance and request authentication for the local Lead Radar service.

Secrets are returned only when a key is created. The database stores a SHA-256
digest and a short prefix for support work; request logs never contain the raw
secret.
"""
from __future__ import annotations

import hashlib
import secrets
from typing import Any


API_KEY_PREFIX = "lr_live_"
DEFAULT_SCOPE = "business_api"
ALLOWED_SCOPES = {"business_api", "read", "write"}


class ApiAccessError(ValueError):
    def __init__(self, code: str, message: str, status: int = 401) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def normalize_api_key(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ApiAccessError("api_key_required", "请通过 X-API-Key 或 Authorization Bearer 提供 API Key。")
    value = value.strip()
    if len(value) > 200 or not value.startswith(API_KEY_PREFIX):
        raise ApiAccessError("api_key_invalid", "API Key 格式无效。")
    return value


def api_key_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def issue_api_key() -> tuple[str, str, str]:
    secret = f"{API_KEY_PREFIX}{secrets.token_urlsafe(32)}"
    return secret, secret[:16], api_key_hash(secret)


def normalize_scopes(value: Any) -> list[str]:
    if value is None:
        return [DEFAULT_SCOPE]
    if not isinstance(value, list) or not value:
        raise ApiAccessError("scopes_invalid", "scopes 必须是非空数组。", 400)
    scopes = []
    for raw in value:
        if not isinstance(raw, str) or raw.strip() not in ALLOWED_SCOPES:
            raise ApiAccessError("scope_invalid", "scopes 含有不受支持的权限。", 400)
        scope = raw.strip()
        if scope not in scopes:
            scopes.append(scope)
    if DEFAULT_SCOPE not in scopes:
        scopes.insert(0, DEFAULT_SCOPE)
    return scopes
