"""Truthful production-readiness assessment for the Lead Radar workspace."""
from __future__ import annotations

import os
from typing import Any

try:
    from .business_api import API_VERSION, BusinessApiError, _required_text
    from .search_connector import capability
    from .storage import Store
except ImportError:
    from business_api import API_VERSION, BusinessApiError, _required_text
    from search_connector import capability
    from storage import Store


def get_production_readiness(store: Store, workspace_id: str, requested_workspace: Any = None) -> dict[str, Any]:
    if requested_workspace is not None:
        normalized = _required_text(requested_workspace, "workspace_id", 120)
        if normalized != workspace_id:
            raise BusinessApiError("workspace_not_found", "工作区不存在。", 404)
    connector = capability()
    rights = store.list_source_rights(workspace_id)
    searchable_rights = [
        right
        for right in rights
        if right.get("permission_status") == "APPROVED"
        and right.get("can_search") is True
    ]
    strict_api = os.environ.get("LEAD_RADAR_REQUIRE_API_KEY", "").strip().lower() in {"1", "true", "yes", "on"}
    checks = [
        {
            "id": "authorized_search_connector",
            "status": "PASS" if connector["status"] == "READY" else "BLOCKED",
            "evidence": {
                "status": connector["status"],
                "provider": connector.get("provider"),
                "endpoint_host": connector.get("endpoint_host"),
                "can_search": connector.get("can_search"),
                "proof_reference": (connector.get("proof") or {}).get("reference"),
            },
            "required_for": "自动搜索",
        },
        {
            "id": "searchable_source_right",
            "status": "PASS" if searchable_rights else "BLOCKED",
            "evidence": {
                "approved_search_source_count": len(searchable_rights),
                "source_ids": [right.get("source_id") for right in searchable_rights],
            },
            "required_for": "来源权利可审计",
        },
        {
            "id": "strict_business_api_auth",
            "status": "PASS" if strict_api else "BLOCKED",
            "evidence": {"require_api_key": strict_api},
            "required_for": "对外 API",
        },
        {
            "id": "human_action_boundary",
            "status": "PASS",
            "evidence": {"action_drafts_only": True, "external_messages_sent": False},
            "required_for": "安全动作",
        },
        {
            "id": "official_writeback_connector",
            "status": "BLOCKED",
            "evidence": {"configured": False, "reason": "尚未完成飞书、CRM 或企业微信官方授权和回写验收。"},
            "required_for": "外部系统回写",
        },
        {
            "id": "revenue_acceptance",
            "status": "BLOCKED",
            "evidence": {"paid_pilot_count": None, "verified_revenue": False},
            "required_for": "对外商业承诺",
        },
    ]
    blockers = [check["id"] for check in checks if check["status"] == "BLOCKED"]
    return {
        "api_version": API_VERSION,
        "workspace_id": workspace_id,
        "status": "GO" if not blockers else "BLOCKED",
        "claim_allowed": not blockers,
        "checks": checks,
        "blockers": blockers,
        "claims_allowed": [
            "本地任务、证据、反馈、评测和人工动作草稿闭环",
            "用户明确提交的公开 URL 受控导入",
            "来源门禁、用量和审计状态可追溯",
        ],
        "claims_disallowed": [
            "已接通小红书、抖音或 B 站自动搜索",
            "已完成 CRM/飞书/企业微信真实回写",
            "已证明成交率、回款或跨行业效果",
        ],
        "next_required_evidence": [
            "一项经核验的授权搜索来源，包含 can_search 权利、原文重开和保存边界",
            "至少一条官方回写连接器的真实授权、幂等、回读和审计证据",
            "30 条真实候选人工校准和一批付费试点结果",
        ],
    }
