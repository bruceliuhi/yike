"""Versioned conformance contract for external Lead Radar connectors.

The contract turns a connector claim into an auditable release gate. It validates
operator supplied evidence only; it never logs in, calls a provider, or stores
credentials. A valid schema is still not proof that the provider granted access.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any
from urllib.parse import urlparse


CONTRACT_VERSION = "lead-radar-connector-v1"
SUPPORTED_LANGUAGES = {"zh-CN", "en-US"}
CONNECTOR_KINDS = {"search", "writeback"}
ACCESS_METHODS = {"official_api", "oauth", "signed_webhook", "licensed_index"}
PROHIBITED_FIELDS = {
    "cookie", "cookies", "password", "token", "api_key", "authorization",
    "phone", "email", "private_message", "secret",
}
SEARCH_CHECKS = (
    "permission_scope_verified", "url_reopen_verified", "published_at_verified",
    "rate_limit_observed", "save_boundary_verified", "retry_idempotency_verified",
)
WRITEBACK_CHECKS = (
    "permission_scope_verified", "field_allowlist_verified",
    "retry_idempotency_verified", "writeback_readback_verified", "rollback_verified",
)
MANIFEST_KEYS = {
    "connector_id", "connector_kind", "provider", "endpoint", "access_method",
    "permission_scope_ref", "proof_artifact_ref", "proof_artifact_sha256",
    "verified_at", "allowed_fields", "checks", "reopen_sample_count",
    "published_at_sample_count", "idempotency_key_field",
}


_CONTRACT: dict[str, Any] = {
    "contract_version": CONTRACT_VERSION,
    "status": "CONTRACT_READY",
    "ready_claim_allowed": False,
    "requires_external_review": True,
    "name": {"zh-CN": "Lead Radar 连接器合规契约", "en-US": "Lead Radar connector conformance contract"},
    "purpose": {
        "zh-CN": "规定自动搜索和官方回写连接器在进入生产前必须提供的权限、数据边界、幂等和回读证据。",
        "en-US": "Define the permission, data-boundary, idempotency, and read-back evidence required before search or official writeback connectors enter production.",
    },
    "manifest_fields": [
        {"name": "connector_id", "type": "string", "required": True, "description": {"zh-CN": "稳定的连接器标识。", "en-US": "Stable connector identifier."}},
        {"name": "connector_kind", "type": "enum", "values": sorted(CONNECTOR_KINDS), "required": True, "description": {"zh-CN": "连接器用途：自动搜索或官方回写。", "en-US": "Connector purpose: automated search or official writeback."}},
        {"name": "provider", "type": "string", "required": True, "description": {"zh-CN": "服务提供方或官方产品名称。", "en-US": "Provider or official product name."}},
        {"name": "endpoint", "type": "https_url", "required": True, "description": {"zh-CN": "生产 endpoint；必须为 HTTPS。", "en-US": "Production endpoint; HTTPS is required."}},
        {"name": "access_method", "type": "enum", "values": sorted(ACCESS_METHODS), "required": True, "description": {"zh-CN": "官方 API、OAuth、签名 Webhook 或有许可的索引。", "en-US": "Official API, OAuth, signed webhook, or licensed index."}},
        {"name": "permission_scope_ref", "type": "string", "required": True, "description": {"zh-CN": "权限范围核验记录引用。", "en-US": "Reference to the verified permission scope record."}},
        {"name": "proof_artifact_ref", "type": "string", "required": True, "description": {"zh-CN": "连接器验收材料引用；不保存秘密。", "en-US": "Reference to the connector acceptance artifact; secrets are not stored."}},
        {"name": "proof_artifact_sha256", "type": "sha256", "required": True, "description": {"zh-CN": "验收材料 SHA-256 摘要。", "en-US": "SHA-256 digest of the acceptance artifact."}},
        {"name": "verified_at", "type": "datetime", "required": True, "description": {"zh-CN": "责任人完成核验的带时区时间。", "en-US": "Timezone-aware time when verification completed."}},
        {"name": "allowed_fields", "type": "string_array", "required": True, "description": {"zh-CN": "最小字段白名单；不得包含凭据或联系人字段。", "en-US": "Minimum field allowlist; credentials and contact fields are forbidden."}},
        {"name": "checks", "type": "object", "required": True, "description": {"zh-CN": "按连接器用途选择的可验证门禁。", "en-US": "Verifiable gates selected for the connector purpose."}},
    ],
    "checks": {
        "search": [
            {"name": "permission_scope_verified", "description": {"zh-CN": "权限范围与可执行操作已核验。", "en-US": "Permission scope and executable operations were verified."}},
            {"name": "url_reopen_verified", "description": {"zh-CN": "样本原文可以按 URL 重新打开。", "en-US": "Sample originals can be reopened by URL."}},
            {"name": "published_at_verified", "description": {"zh-CN": "样本发布时间来自原文或明确为未知。", "en-US": "Sample publication time comes from the original or is explicitly unknown."}},
            {"name": "rate_limit_observed", "description": {"zh-CN": "限流、重试和退避行为已观察并记录。", "en-US": "Rate limits, retries, and backoff behavior were observed and recorded."}},
            {"name": "save_boundary_verified", "description": {"zh-CN": "保存字段、原文保留和删除边界已核验。", "en-US": "Stored fields, original retention, and deletion boundaries were verified."}},
            {"name": "retry_idempotency_verified", "description": {"zh-CN": "同一幂等键重试不会重复产生结果或扣费。", "en-US": "Retrying the same idempotency key does not duplicate results or billing."}},
        ],
        "writeback": [
            {"name": "permission_scope_verified", "description": {"zh-CN": "官方回写权限与租户范围已核验。", "en-US": "Official writeback permission and tenant scope were verified."}},
            {"name": "field_allowlist_verified", "description": {"zh-CN": "写回字段只包含最小业务字段。", "en-US": "Writeback fields contain only minimum business fields."}},
            {"name": "retry_idempotency_verified", "description": {"zh-CN": "同一幂等键重试不会创建重复记录。", "en-US": "Retrying the same idempotency key does not create duplicates."}},
            {"name": "writeback_readback_verified", "description": {"zh-CN": "写回后可从官方系统回读并核对结果。", "en-US": "The result can be read back from the official system."}},
            {"name": "rollback_verified", "description": {"zh-CN": "失败、撤回和删除边界已在官方系统验证。", "en-US": "Failure, withdrawal, and deletion boundaries were verified."}},
        ],
    },
    "prohibited_fields": sorted(PROHIBITED_FIELDS),
    "release_rule": {
        "zh-CN": "只有所有必需门禁为 true、字段白名单无阻断字段且材料摘要完整时，连接器才可标记 READY；契约通过不等于平台已授权。",
        "en-US": "A connector may be marked READY only when every required gate is true, the field allowlist has no blocked fields, and the artifact digest is complete; passing this contract does not grant platform access.",
    },
}


def get_connector_contract(language: str = "zh-CN") -> dict[str, Any]:
    normalized = str(language or "zh-CN").strip()
    if normalized not in SUPPORTED_LANGUAGES:
        raise ValueError("language_not_supported")
    contract = deepcopy(_CONTRACT)
    contract["language"] = normalized
    contract["name"] = _CONTRACT["name"][normalized]
    contract["purpose"] = _CONTRACT["purpose"][normalized]
    contract["release_rule"] = _CONTRACT["release_rule"][normalized]
    for group in contract["checks"].values():
        for item in group:
            item["description"] = item["description"][normalized]
    for field in contract["manifest_fields"]:
        field["description"] = field["description"][normalized]
    return contract


def _error(errors: list[dict[str, str]], path: str, code: str, message: str) -> None:
    errors.append({"path": path, "code": code, "message": message})


def _text(value: Any, maximum: int = 500) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value.strip()) <= maximum


def _sha256(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip().lower()
    return len(normalized) == 64 and all(char in "0123456789abcdef" for char in normalized)


def _datetime(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed <= datetime.now(parsed.tzinfo)


def _contains_prohibited(value: Any, path: str, errors: list[dict[str, str]]) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).strip().lower()
            if any(item in normalized for item in PROHIBITED_FIELDS):
                _error(errors, f"{path}.{key}" if path else str(key), "prohibited_field", f"字段 {key} 不允许进入连接器 manifest。")
            _contains_prohibited(nested, f"{path}.{key}" if path else str(key), errors)
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _contains_prohibited(nested, f"{path}[{index}]", errors)


def validate_connector_manifest(manifest: Any) -> dict[str, Any]:
    """Validate connector evidence without persisting data or making network calls."""
    errors: list[dict[str, str]] = []
    warnings: list[str] = []
    if not isinstance(manifest, dict):
        _error(errors, "$", "manifest_must_be_object", "连接器 manifest 必须是对象。")
        return {"contract_version": CONTRACT_VERSION, "schema_valid": False, "ready_claim_allowed": False, "errors": errors, "warnings": warnings, "quality_gate": {"status": "BLOCKED", "blocking_reasons": ["manifest_invalid"]}}

    _contains_prohibited(manifest, "", errors)
    for key in manifest:
        if key not in MANIFEST_KEYS:
            _error(errors, str(key), "unknown_field", f"不支持的 manifest 字段：{key}。")
    for name in ("connector_id", "provider", "permission_scope_ref", "proof_artifact_ref"):
        if not _text(manifest.get(name)):
            _error(errors, name, "field_required", f"{name} 必填。")
    kind = manifest.get("connector_kind")
    if kind not in CONNECTOR_KINDS:
        _error(errors, "connector_kind", "enum_value_invalid", "connector_kind 必须是 search 或 writeback。")
    access_method = manifest.get("access_method")
    if access_method not in ACCESS_METHODS:
        _error(errors, "access_method", "enum_value_invalid", "access_method 不在允许值内。")
    endpoint = manifest.get("endpoint")
    parsed_endpoint = urlparse(endpoint) if isinstance(endpoint, str) else None
    if (
        not parsed_endpoint
        or parsed_endpoint.scheme.lower() != "https"
        or not parsed_endpoint.netloc
        or parsed_endpoint.username
        or parsed_endpoint.password
        or parsed_endpoint.query
        or parsed_endpoint.fragment
    ):
        _error(errors, "endpoint", "https_url_required", "endpoint 必须是 HTTPS URL。")
    if not _sha256(manifest.get("proof_artifact_sha256")):
        _error(errors, "proof_artifact_sha256", "sha256_required", "proof_artifact_sha256 必须是 64 位十六进制摘要。")
    if not _datetime(manifest.get("verified_at")):
        _error(errors, "verified_at", "datetime_required", "verified_at 必须是当前或过去的带时区时间。")

    fields = manifest.get("allowed_fields")
    blocked_fields: list[str] = []
    if not isinstance(fields, list) or not fields or any(not _text(item, 120) for item in fields):
        _error(errors, "allowed_fields", "string_array_required", "allowed_fields 必须是非空字符串数组。")
        fields = []
    for index, field in enumerate(fields):
        normalized = str(field).strip().lower()
        if any(item in normalized for item in PROHIBITED_FIELDS):
            blocked_fields.append(str(field))
            _error(errors, f"allowed_fields[{index}]", "prohibited_field", f"字段 {field} 不允许进入连接器白名单。")

    checks = manifest.get("checks")
    if not isinstance(checks, dict):
        _error(errors, "checks", "object_required", "checks 必须是对象。")
        checks = {}
    required_checks = SEARCH_CHECKS if kind == "search" else WRITEBACK_CHECKS if kind == "writeback" else ()
    missing_checks = [name for name in required_checks if checks.get(name) is not True]
    if missing_checks:
        warnings.append(f"尚未通过门禁：{'、'.join(missing_checks)}。")
    if kind == "search":
        if not isinstance(manifest.get("reopen_sample_count"), int) or manifest.get("reopen_sample_count", 0) < 1:
            _error(errors, "reopen_sample_count", "positive_integer_required", "搜索连接器至少需要 1 条重开样本。")
        if not isinstance(manifest.get("published_at_sample_count"), int) or manifest.get("published_at_sample_count", 0) < 1:
            _error(errors, "published_at_sample_count", "positive_integer_required", "搜索连接器至少需要 1 条发布时间样本。")
    if kind == "writeback" and not _text(manifest.get("idempotency_key_field"), 120):
        _error(errors, "idempotency_key_field", "field_required", "写回连接器必须声明幂等键字段。")

    blockers: list[str] = []
    if errors:
        blockers.append("manifest_invalid")
    if missing_checks:
        blockers.extend(missing_checks)
    if blocked_fields:
        blockers.append("blocked_fields_in_allowlist")
    if kind == "search" and access_method == "signed_webhook":
        blockers.append("search_access_method_not_supported")
    ready = not blockers
    return {
        "contract_version": CONTRACT_VERSION,
        "connector_id": manifest.get("connector_id"),
        "connector_kind": manifest.get("connector_kind"),
        "schema_valid": not errors,
        "ready_claim_allowed": ready,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "provider": manifest.get("provider"),
            "endpoint_host": parsed_endpoint.hostname if parsed_endpoint else None,
            "access_method": access_method,
            "allowed_field_count": len(fields),
            "blocked_fields": blocked_fields,
            "required_checks": list(required_checks),
            "passed_checks": [name for name in required_checks if checks.get(name) is True],
            "proof_artifact_present": _sha256(manifest.get("proof_artifact_sha256")),
        },
        "quality_gate": {"status": "READY" if ready else "BLOCKED", "blocking_reasons": blockers},
    }
