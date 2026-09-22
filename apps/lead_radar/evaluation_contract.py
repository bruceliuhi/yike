"""Versioned contract for importing an auditable evaluation dataset.

The contract deliberately describes evidence and rights instead of contacts.
It is a schema and release gate, not a claim that a public benchmark already
exists. Real authorized samples must still be imported and reviewed.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any
from urllib.parse import urlparse


CONTRACT_VERSION = "lead-radar-evaluation-v1"
SUPPORTED_LANGUAGES = {"zh-CN", "en-US"}


_CONTRACT: dict[str, Any] = {
    "contract_version": CONTRACT_VERSION,
    "status": "CONTRACT_READY",
    "benchmark_claim_allowed": False,
    "requires_real_authorized_samples": True,
    "name": {
        "zh-CN": "Lead Radar 可审计评测集契约",
        "en-US": "Lead Radar auditable evaluation dataset contract",
    },
    "purpose": {
        "zh-CN": "规定跨行业真实授权样本进入人工校准、重开核验和公开评测前必须具备的字段与证据。",
        "en-US": "Define the fields and evidence required before real cross-industry authorized samples enter calibration, reopen checks, and public evaluation.",
    },
    "dataset_fields": [
        {
            "name": "dataset_id",
            "type": "string",
            "required": True,
            "description": {"zh-CN": "评测集稳定标识。", "en-US": "Stable dataset identifier."},
        },
        {
            "name": "dataset_version",
            "type": "string",
            "required": True,
            "description": {"zh-CN": "不可变版本号；样本或标签规则变化必须升版。", "en-US": "Immutable version; changes to samples or labeling rules require a new version."},
        },
        {
            "name": "license_or_rights_ref",
            "type": "string",
            "required": True,
            "description": {"zh-CN": "授权、许可或用户提交权利证明的外部引用，不保存 Cookie、Token 或原始秘密。", "en-US": "External reference to the license, permission, or user-submission rights proof; never store cookies, tokens, or raw secrets."},
        },
        {
            "name": "label_policy_version",
            "type": "string",
            "required": True,
            "description": {"zh-CN": "人工金标准说明和版本。", "en-US": "Version of the human gold-label policy."},
        },
        {
            "name": "rights_approval_verified",
            "type": "boolean",
            "required": True,
            "description": {"zh-CN": "权利证明是否已经由责任人核验；仅有引用编号不能代替核验。", "en-US": "Whether a responsible operator verified the rights proof; a reference alone is not verification."},
        },
        {
            "name": "external_actions_sent",
            "type": "integer",
            "required": True,
            "description": {"zh-CN": "评测期间实际发送的外部动作数，必须为 0。", "en-US": "Number of external actions actually sent during evaluation; must be zero."},
        },
    ],
    "sample_fields": [
        {
            "name": "sample_id",
            "type": "string",
            "required": True,
            "description": {"zh-CN": "样本稳定标识，不能因重新导入而变化。", "en-US": "Stable sample identifier that must survive re-imports."},
        },
        {
            "name": "industry",
            "type": "string",
            "required": True,
            "description": {"zh-CN": "行业或业务分类。", "en-US": "Industry or business category."},
        },
        {
            "name": "source_family",
            "type": "string",
            "required": True,
            "description": {"zh-CN": "来源家族，如授权搜索、用户提交公开 URL、公开 Feed。", "en-US": "Source family, such as authorized search, user-submitted public URL, or public feed."},
        },
        {
            "name": "source_url",
            "type": "https_url",
            "required": True,
            "description": {"zh-CN": "可重新打开的 HTTPS 原文地址。", "en-US": "HTTPS original URL that can be reopened."},
        },
        {
            "name": "source_permission",
            "type": "enum",
            "required": True,
            "values": [
                "allowed",
                "authorized_api",
                "authorized_search_api",
                "search_index_proof",
                "public_url_user_supplied",
                "public_feed_user_supplied",
                "licensed_index",
            ],
            "description": {"zh-CN": "来源使用权类型；公开可见不等于服务端拥有自动搜索权。", "en-US": "Permission type; public visibility does not equal server-side permission to search automatically."},
        },
        {
            "name": "source_proof_ref",
            "type": "string",
            "required": True,
            "description": {"zh-CN": "来源证明、许可或用户提交记录的引用。", "en-US": "Reference to the source proof, license, or user-submission record."},
        },
        {
            "name": "published_at",
            "type": "datetime_or_null",
            "required": True,
            "description": {"zh-CN": "原文发布时间；无法确认时必须为 null，不能猜测。", "en-US": "Original publication time; use null when unknown instead of guessing."},
        },
        {
            "name": "snippet",
            "type": "string",
            "required": True,
            "description": {"zh-CN": "保留原文片段，用于人工复核和重开比对。", "en-US": "Original text excerpt retained for human review and reopen comparison."},
        },
        {
            "name": "system_predicted_label",
            "type": "enum",
            "required": True,
            "values": ["VALID", "INVALID", "DUPLICATE", "OBSERVE", "NEEDS_EVIDENCE"],
            "description": {"zh-CN": "导入时冻结的系统预测。", "en-US": "System prediction frozen at import time."},
        },
        {
            "name": "gold_label",
            "type": "enum",
            "required": True,
            "values": ["VALID", "INVALID", "DUPLICATE", "OBSERVE", "NEEDS_EVIDENCE"],
            "description": {"zh-CN": "人工金标准；必须有复核人和判定依据。", "en-US": "Human gold label with a reviewer and decision rationale."},
        },
        {
            "name": "reviewer",
            "type": "string",
            "required": True,
            "description": {"zh-CN": "实际完成复核的操作人或评审组标识。", "en-US": "Operator or review-group identifier that performed the review."},
        },
        {
            "name": "review_note",
            "type": "string",
            "required": True,
            "description": {"zh-CN": "说明为什么判定为该金标准。", "en-US": "Rationale for the gold-label decision."},
        },
        {
            "name": "reopen_required",
            "type": "boolean",
            "required": True,
            "description": {"zh-CN": "该样本是否必须做原文重开。", "en-US": "Whether the sample requires an original-page reopen check."},
        },
        {
            "name": "reopen_verified",
            "type": "boolean",
            "required": True,
            "description": {"zh-CN": "是否已成功重开并核对内容指纹/发布时间。", "en-US": "Whether reopen succeeded and the content fingerprint/publication time were checked."},
        },
        {
            "name": "evidence_fingerprint",
            "type": "string",
            "required": True,
            "description": {"zh-CN": "原文快照或内容指纹，支持重复导入和重开比对。", "en-US": "Original snapshot or content fingerprint for deduplication and reopen comparison."},
        },
    ],
    "accepted_gold_labels": ["VALID", "INVALID", "DUPLICATE", "OBSERVE", "NEEDS_EVIDENCE"],
    "quality_gates": {
        "minimum_sample_count": 30,
        "minimum_reviewed_ratio": 1.0,
        "minimum_reopen_rate_for_reopen_eligible": 1.0,
        "minimum_label_accuracy": 0.80,
        "maximum_false_positive_rate": 0.20,
        "required_rights_backed_sample_ratio": 1.0,
        "required_external_actions_sent": 0,
    },
    "prohibited_fields": [
        "cookie",
        "cookies",
        "password",
        "token",
        "api_key",
        "authorization",
        "phone",
        "email",
        "private_message",
    ],
    "release_outputs": [
        "versioned_manifest",
        "sample_count_and_industry_breakdown",
        "gold_label_policy",
        "rights_proof_index",
        "reopen_audit",
        "calibration_evaluation",
        "quality_gate_decision",
    ],
}


def get_evaluation_contract(language: str = "zh-CN") -> dict[str, Any]:
    normalized = str(language or "zh-CN").strip()
    if normalized not in SUPPORTED_LANGUAGES:
        raise ValueError("language_not_supported")
    contract = deepcopy(_CONTRACT)
    contract["language"] = normalized
    contract["name"] = _CONTRACT["name"][normalized]
    contract["purpose"] = _CONTRACT["purpose"][normalized]
    for group in ("dataset_fields", "sample_fields"):
        for field in contract[group]:
            field["description"] = field["description"][normalized]
    return contract


def _error(errors: list[dict[str, str]], path: str, code: str, message: str) -> None:
    errors.append({"path": path, "code": code, "message": message})


def _is_non_empty_string(value: Any, maximum: int = 500) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value.strip()) <= maximum


def _is_datetime_or_null(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _contains_prohibited_key(value: Any, path: str, errors: list[dict[str, str]]) -> None:
    prohibited = tuple(str(item).lower() for item in _CONTRACT["prohibited_fields"])
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).strip().lower()
            if any(item in normalized for item in prohibited):
                _error(errors, f"{path}.{key}" if path else str(key), "prohibited_field", f"字段 {key} 不允许进入评测集。")
            _contains_prohibited_key(nested, f"{path}.{key}" if path else str(key), errors)
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _contains_prohibited_key(nested, f"{path}[{index}]", errors)


def validate_evaluation_manifest(manifest: Any) -> dict[str, Any]:
    """Validate a dataset manifest without persisting it or contacting a source.

    A schema-valid manifest can still be blocked by the release gates. The
    returned report is intentionally explicit about that distinction so an
    importer cannot mistake field validation for a public benchmark claim.
    """

    errors: list[dict[str, str]] = []
    warnings: list[str] = []
    if not isinstance(manifest, dict):
        _error(errors, "$", "manifest_must_be_object", "评测 manifest 必须是对象。")
        return {
            "contract_version": CONTRACT_VERSION,
            "schema_valid": False,
            "benchmark_claim_allowed": False,
            "errors": errors,
            "warnings": warnings,
            "summary": {"sample_count": 0, "reviewed_count": 0},
            "quality_gate": {"status": "BLOCKED", "blocking_reasons": ["manifest_invalid"]},
        }

    _contains_prohibited_key(manifest, "", errors)
    dataset = manifest.get("dataset")
    samples = manifest.get("samples")
    if not isinstance(dataset, dict):
        _error(errors, "dataset", "dataset_required", "dataset 必须是对象。")
        dataset = {}
    if not isinstance(samples, list):
        _error(errors, "samples", "samples_required", "samples 必须是数组。")
        samples = []
    if len(samples) > 500:
        _error(errors, "samples", "sample_limit_exceeded", "单个 manifest 最多 500 条样本。")

    dataset_specs = {item["name"]: item for item in _CONTRACT["dataset_fields"]}
    for name, spec in dataset_specs.items():
        value = dataset.get(name)
        if spec["type"] == "boolean":
            if not isinstance(value, bool):
                _error(errors, f"dataset.{name}", "boolean_required", f"dataset.{name} 必须是布尔值。")
        elif spec["type"] == "integer":
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                _error(errors, f"dataset.{name}", "non_negative_integer_required", f"dataset.{name} 必须是非负整数。")
        elif not _is_non_empty_string(value):
            _error(errors, f"dataset.{name}", "field_required", f"dataset.{name} 必填。")

    if dataset.get("external_actions_sent") not in (None, 0):
        warnings.append("评测集包含外部动作计数；质量门禁会阻止公开基准资格。")

    labels = set(_CONTRACT["accepted_gold_labels"])
    permissions = set(next(item for item in _CONTRACT["sample_fields"] if item["name"] == "source_permission")["values"])
    sample_specs = {item["name"]: item for item in _CONTRACT["sample_fields"]}
    sample_ids: set[str] = set()
    industries: dict[str, int] = {}
    source_families: dict[str, int] = {}
    reviewed_count = 0
    label_count = 0
    agreement_count = 0
    false_positive_count = 0
    false_negative_count = 0
    reopen_eligible_count = 0
    reopened_count = 0
    proof_reference_count = 0

    for index, sample in enumerate(samples):
        path = f"samples[{index}]"
        if not isinstance(sample, dict):
            _error(errors, path, "sample_must_be_object", "每条样本必须是对象。")
            continue
        sample_id = sample.get("sample_id")
        if not _is_non_empty_string(sample_id, 200):
            _error(errors, f"{path}.sample_id", "field_required", "sample_id 必填。")
        elif sample_id in sample_ids:
            _error(errors, f"{path}.sample_id", "duplicate_sample_id", "sample_id 不能重复。")
        else:
            sample_ids.add(sample_id)

        for name, spec in sample_specs.items():
            value = sample.get(name)
            field_path = f"{path}.{name}"
            if spec["type"] == "boolean":
                if not isinstance(value, bool):
                    _error(errors, field_path, "boolean_required", f"{name} 必须是布尔值。")
            elif spec["type"] == "datetime_or_null":
                if not _is_datetime_or_null(value):
                    _error(errors, field_path, "datetime_required", f"{name} 必须是带时区时间或 null。")
            elif spec["type"] == "https_url":
                parsed = urlparse(value) if isinstance(value, str) else None
                if not parsed or parsed.scheme.lower() != "https" or not parsed.netloc:
                    _error(errors, field_path, "https_url_required", "source_url 必须是可重开的 HTTPS URL。")
            elif spec["type"] == "enum":
                if value not in spec["values"]:
                    _error(errors, field_path, "enum_value_invalid", f"{name} 不在允许值内。")
            elif not _is_non_empty_string(value, 20000 if name == "snippet" else 500):
                _error(errors, field_path, "field_required", f"{name} 必填。")

        industry = str(sample.get("industry", "")).strip()
        source_family = str(sample.get("source_family", "")).strip()
        if industry:
            industries[industry] = industries.get(industry, 0) + 1
        if source_family:
            source_families[source_family] = source_families.get(source_family, 0) + 1
        if _is_non_empty_string(sample.get("source_proof_ref"), 500):
            proof_reference_count += 1
        is_reviewed = (
            sample.get("gold_label") in labels
            and _is_non_empty_string(sample.get("reviewer"), 500)
            and _is_non_empty_string(sample.get("review_note"), 20000)
        )
        if is_reviewed:
            reviewed_count += 1
        predicted = sample.get("system_predicted_label")
        gold = sample.get("gold_label")
        if predicted in labels and gold in labels:
            label_count += 1
            agreement_count += predicted == gold
            false_positive_count += predicted == "VALID" and gold != "VALID"
            false_negative_count += predicted != "VALID" and gold == "VALID"
        if sample.get("reopen_required") is True:
            reopen_eligible_count += 1
            reopened_count += sample.get("reopen_verified") is True
        if sample.get("reopen_required") is True and sample.get("reopen_verified") is not True:
            _error(errors, f"{path}.reopen_verified", "reopen_required", "要求重开时必须完成原文重开核验。")

    sample_count = len(samples)
    reviewed_ratio = reviewed_count / sample_count if sample_count else 0.0
    accuracy = agreement_count / label_count if label_count else None
    false_positive_rate = false_positive_count / label_count if label_count else None
    reopen_rate = reopened_count / reopen_eligible_count if reopen_eligible_count else None
    rights_ratio = proof_reference_count / sample_count if sample_count else 0.0
    blockers: list[str] = []
    if sample_count < _CONTRACT["quality_gates"]["minimum_sample_count"]:
        blockers.append("sample_count_below_30")
    if reviewed_ratio < _CONTRACT["quality_gates"]["minimum_reviewed_ratio"]:
        blockers.append("reviewed_ratio_below_100")
    if reopen_rate is not None and reopen_rate < _CONTRACT["quality_gates"]["minimum_reopen_rate_for_reopen_eligible"]:
        blockers.append("reopen_rate_below_100")
    if accuracy is None or accuracy < _CONTRACT["quality_gates"]["minimum_label_accuracy"]:
        blockers.append("label_accuracy_below_80")
    if false_positive_rate is not None and false_positive_rate > _CONTRACT["quality_gates"]["maximum_false_positive_rate"]:
        blockers.append("false_positive_rate_above_20")
    if rights_ratio < _CONTRACT["quality_gates"]["required_rights_backed_sample_ratio"]:
        blockers.append("missing_source_proof_reference")
    if dataset.get("rights_approval_verified") is not True:
        blockers.append("rights_approval_not_verified")
    if dataset.get("external_actions_sent") != 0:
        blockers.append("external_actions_sent")
    if errors:
        blockers.append("manifest_invalid")

    return {
        "contract_version": CONTRACT_VERSION,
        "schema_valid": not errors,
        "benchmark_claim_allowed": not blockers,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "dataset_id": dataset.get("dataset_id"),
            "dataset_version": dataset.get("dataset_version"),
            "sample_count": sample_count,
            "reviewed_count": reviewed_count,
            "industry_breakdown": industries,
            "source_family_breakdown": source_families,
            "proof_reference_count": proof_reference_count,
            "rights_reference_ratio": round(rights_ratio, 4),
            "reopen_eligible_count": reopen_eligible_count,
            "reopened_count": reopened_count,
            "label_count": label_count,
            "agreement_count": agreement_count,
            "accuracy": round(accuracy, 4) if accuracy is not None else None,
            "false_positive_count": false_positive_count,
            "false_negative_count": false_negative_count,
            "false_positive_rate": round(false_positive_rate, 4) if false_positive_rate is not None else None,
            "reopen_rate": round(reopen_rate, 4) if reopen_rate is not None else None,
        },
        "quality_gate": {
            "status": "PASS" if not blockers else "BLOCKED",
            "blocking_reasons": blockers,
            "claim_allowed": not blockers,
        },
    }
