"""Explicit connector catalog for the Lead Radar integration surface.

The catalog is deliberately declarative. It tells a workspace what a
connector would be allowed to do and what evidence is still required before
it can be used. It never turns an environment variable, a UI click, or a
stored credential into a fake READY state.
"""
from __future__ import annotations

from typing import Any


_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "id": "feishu_official",
        "name": {"zh-CN": "飞书官方连接器", "en-US": "Feishu official connector"},
        "category": "writeback",
        "status": "REQUIRES_AUTH",
        "auth_method": "oauth",
        "user_login_required": True,
        "server_secret_required": True,
        "capabilities": ["READ_WORKSPACE", "CREATE_TASK_DRAFT", "WRITE_BACK_APPROVED"],
        "allowed_fields": ["title", "description", "source_url", "evidence_summary", "owner", "due_at"],
        "blocked_fields": ["private_phone", "private_email", "session_cookie", "password"],
        "approval": "每次回写前需要人工批准；退订和禁触达状态优先。",
        "evidence_required": [
            "用户 OAuth 授权和 scope 清单",
            "字段映射与脱敏规则",
            "写入幂等、回读、撤销和审计记录",
        ],
        "next_step": "完成飞书应用授权后，先用测试租户验证草稿写入和幂等回读。",
    },
    {
        "id": "wecom_official",
        "name": {"zh-CN": "企业微信官方连接器", "en-US": "WeCom official connector"},
        "category": "writeback",
        "status": "REQUIRES_AUTH",
        "auth_method": "oauth_or_app_authorization",
        "user_login_required": True,
        "server_secret_required": True,
        "capabilities": ["READ_CONTACT_SCOPE", "CREATE_FOLLOWUP_DRAFT", "WRITE_BACK_APPROVED"],
        "allowed_fields": ["title", "description", "source_url", "evidence_summary", "owner", "due_at"],
        "blocked_fields": ["private_phone", "private_email", "session_cookie", "password"],
        "approval": "只生成待确认跟进任务；不会自动发送私聊、群消息或好友申请。",
        "evidence_required": [
            "企业微信应用身份和授权 scope",
            "联系人/客户字段最小化映射",
            "禁触达、退订、转人工和回写失败处理",
        ],
        "next_step": "先验收企业内部任务回写，不开放陌生联系人自动触达。",
    },
    {
        "id": "crm_official",
        "name": {"zh-CN": "CRM 官方连接器", "en-US": "CRM official connector"},
        "category": "writeback",
        "status": "REQUIRES_AUTH",
        "auth_method": "oauth_or_api_key",
        "user_login_required": True,
        "server_secret_required": True,
        "capabilities": ["READ_ACCOUNT_SCOPE", "UPSERT_OPPORTUNITY_DRAFT", "WRITE_BACK_APPROVED"],
        "allowed_fields": ["account_name", "opportunity_title", "source_url", "evidence_summary", "stage", "owner"],
        "blocked_fields": ["unverified_contact", "private_phone", "private_email", "session_cookie"],
        "approval": "仅在证据可重开、实体已确认且人工批准后写入商机草稿。",
        "evidence_required": [
            "客户 CRM 的授权和对象 scope",
            "账户/商机字段映射与去重键",
            "幂等 upsert、回读和审计证据",
        ],
        "next_step": "用沙箱 CRM 验证账户去重和重复重试不产生重复商机。",
    },
    {
        "id": "authorized_search",
        "name": {"zh-CN": "授权搜索连接器", "en-US": "Authorized search connector"},
        "category": "search",
        "status": "REQUIRES_PROOF",
        "auth_method": "server_managed_provider",
        "user_login_required": False,
        "server_secret_required": True,
        "capabilities": ["SEARCH", "RETURN_SOURCE_METADATA", "REOPEN_ORIGINAL"],
        "allowed_fields": ["query", "title", "url", "snippet", "published_at", "source_kind"],
        "blocked_fields": ["cookie", "password", "private_contact"],
        "approval": "搜索结果只进入 REVIEW；原文重开和来源权利验证通过后才可升级。",
        "evidence_required": [
            "提供商和 endpoint 证明",
            "来源权利、发布时间、限流和保存期限",
            "原文重开率 100% 的验收样本",
        ],
        "next_step": "登记 source proof 和 approved source right 后执行小批量搜索验收。",
    },
    {
        "id": "signed_webhook",
        "name": {"zh-CN": "签名 Webhook", "en-US": "Signed webhook"},
        "category": "automation",
        "status": "REQUIRES_AUTH",
        "auth_method": "workspace_secret_or_mtls",
        "user_login_required": False,
        "server_secret_required": True,
        "capabilities": ["EXPORT_APPROVED_RECORDS", "DELIVER_AUDIT_EVENT"],
        "allowed_fields": ["opportunity_id", "status", "source_url", "evidence_summary", "entity_id"],
        "blocked_fields": ["private_phone", "private_email", "raw_cookie", "password"],
        "approval": "只推送用户批准的证据字段；每次投递带 request_id 和幂等键。",
        "evidence_required": [
            "接收端身份、签名验证和重放保护",
            "字段白名单与数据保留期限",
            "失败重试、死信和撤回流程",
        ],
        "next_step": "先接入内部测试端点，验证签名、重试和字段白名单。",
    },
)


def list_integrations(language: str = "zh-CN") -> list[dict[str, Any]]:
    normalized = str(language or "zh-CN").strip()
    if normalized not in {"zh-CN", "en-US"}:
        raise ValueError("language_not_supported")
    result: list[dict[str, Any]] = []
    for item in _CATALOG:
        copy = dict(item)
        copy["name"] = item["name"][normalized]
        copy["language"] = normalized
        copy["configured"] = False
        result.append(copy)
    return result

