"""Versioned contract for importing an auditable evaluation dataset.

The contract deliberately describes evidence and rights instead of contacts.
It is a schema and release gate, not a claim that a public benchmark already
exists. Real authorized samples must still be imported and reviewed.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


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
            "values": ["authorized_source", "public_url_user_supplied", "licensed_index"],
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
