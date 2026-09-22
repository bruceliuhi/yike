"""Independent Lead Radar product catalog.

This is the product contract, separate from any CRM implementation. Each
module describes a customer outcome and its production boundary so packaging,
pricing and connector work do not become a list of UI screens.
"""
from __future__ import annotations

from typing import Any


_MODULES: tuple[dict[str, Any], ...] = (
    {
        "id": "intent_to_plan",
        "name": {"zh-CN": "意图编译与搜索计划", "en-US": "Intent compiler and search plan"},
        "phase": "DISCOVER",
        "buyer_value": {"zh-CN": "把模糊获客目标变成可审阅的查询、过滤条件和预算", "en-US": "Turn a vague growth goal into reviewable queries, filters and budget."},
        "inputs": ["natural_language_objective", "language", "template_id"],
        "outputs": ["intent_profile", "query_strategies", "cost_estimate", "source_gates"],
        "status": "AVAILABLE_LOCAL",
        "requires_external_proof": False,
    },
    {
        "id": "evidence_ledger",
        "name": {"zh-CN": "证据账本", "en-US": "Evidence ledger"},
        "phase": "VERIFY",
        "buyer_value": {"zh-CN": "每条候选都能重开原文、查看证据缺口和数据使用边界", "en-US": "Every candidate can be reopened with visible evidence gaps and data-use boundaries."},
        "inputs": ["public_url", "authorized_result", "source_right"],
        "outputs": ["opportunity", "evidence_card", "reopen_audit", "data_use"],
        "status": "AVAILABLE_LOCAL",
        "requires_external_proof": True,
    },
    {
        "id": "qualification_loop",
        "name": {"zh-CN": "人工校准与资格判断", "en-US": "Human calibration and qualification"},
        "phase": "LEARN",
        "buyer_value": {"zh-CN": "把有效、无效、重复和证据不足转成下一轮可测量的判断", "en-US": "Turn valid, invalid, duplicate and insufficient-evidence labels into measurable learning."},
        "inputs": ["opportunity", "reviewer_label", "review_note"],
        "outputs": ["feedback_event", "status_transition", "calibration_metrics"],
        "status": "AVAILABLE_LOCAL",
        "requires_external_proof": False,
    },
    {
        "id": "action_workspace",
        "name": {"zh-CN": "证据绑定动作工作台", "en-US": "Evidence-bound action workspace"},
        "phase": "ACT",
        "buyer_value": {"zh-CN": "生成可审阅的回复、邮件和任务草案，降低误触达风险", "en-US": "Generate reviewable reply, email and task drafts with lower misreach risk."},
        "inputs": ["qualified_opportunity", "approved_channel", "operator"],
        "outputs": ["action_draft", "approval_audit", "do_not_contact_lock"],
        "status": "AVAILABLE_LOCAL",
        "requires_external_proof": True,
    },
    {
        "id": "monitoring_feed",
        "name": {"zh-CN": "持续监测与变化 Feed", "en-US": "Monitoring and change feed"},
        "phase": "RETAIN",
        "buyer_value": {"zh-CN": "把新的采购、招聘、招标和官网变化按证据送回任务队列", "en-US": "Return new demand, hiring, tender and website changes to the task queue with evidence."},
        "inputs": ["schedule", "authorized_source", "change_window"],
        "outputs": ["feed_event", "deduplicated_opportunity", "review_queue"],
        "status": "AVAILABLE_LOCAL",
        "requires_external_proof": True,
    },
    {
        "id": "connector_and_audit",
        "name": {"zh-CN": "连接器与审计控制面", "en-US": "Connector and audit control plane"},
        "phase": "OPERATE",
        "buyer_value": {"zh-CN": "用最小权限把批准结果写回客户系统，并保留可追溯记录", "en-US": "Write approved outcomes back with least privilege and traceable records."},
        "inputs": ["connector_authorization", "field_mapping", "approval_policy"],
        "outputs": ["connector_run", "writeback_receipt", "usage_ledger", "audit_timeline"],
        "status": "CATALOG_ONLY",
        "requires_external_proof": True,
    },
)


def list_product_catalog(language: str = "zh-CN") -> list[dict[str, Any]]:
    normalized = str(language or "zh-CN").strip()
    if normalized not in {"zh-CN", "en-US"}:
        raise ValueError("language_not_supported")
    result: list[dict[str, Any]] = []
    for module in _MODULES:
        item = dict(module)
        item["name"] = module["name"][normalized]
        item["buyer_value"] = module["buyer_value"][normalized]
        item["language"] = normalized
        result.append(item)
    return result

