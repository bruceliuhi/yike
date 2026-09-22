from __future__ import annotations

from typing import Any

try:
    from .search_connector import capability as authorized_search_capability
    from .source_policy import source_capability_metadata
except ImportError:  # running planner.py directly
    from search_connector import capability as authorized_search_capability
    from source_policy import source_capability_metadata


CAPABILITIES: list[dict[str, Any]] = [
    {
        "id": "manual_public_evidence",
        "name": "公开证据导入",
        "status": "READY",
        "tier": "A",
        "access": "manual",
        "can_search": False,
        "can_store_original": True,
        "can_write_back": False,
        "end_user_login_required": False,
        "server_authorization_required": False,
        "note": "可录入已由人工打开并核验的公开网页证据；不代表自动采集已接通。",
    },
    {
        "id": "public_web",
        "name": "公开网页",
        "status": "REQUIRES_PROOF",
        "tier": "B",
        "access": "controlled_http",
        "can_search": False,
        "can_store_original": False,
        "can_write_back": False,
        "end_user_login_required": False,
        "server_authorization_required": False,
        "note": "需要先完成 robots、条款、频率、发布时间和证据重开验证。",
    },
    {
        "id": "public_url_capture",
        "name": "用户指定公开 URL",
        "status": "READY",
        "tier": "B",
        "access": "controlled_http",
        "can_search": False,
        "can_store_original": False,
        "can_write_back": False,
        "end_user_login_required": False,
        "server_authorization_required": False,
        "note": "只打开用户明确提交的公开 URL，限制公网地址、大小和 HTML 类型，保存摘要与内容指纹。",
    },
    {
        "id": "xiaohongshu_public",
        "name": "小红书公开内容",
        "status": "REQUIRES_PROOF",
        "tier": "C",
        "access": "public_web_or_official_access",
        "can_search": False,
        "can_store_original": False,
        "can_write_back": False,
        **source_capability_metadata("xiaohongshu"),
        "note": "平台权限、搜索稳定性、原文重开和保存边界尚未通过生产门禁。",
    },
    {
        "id": "douyin_public",
        "name": "抖音公开内容",
        "status": "REQUIRES_PROOF",
        "tier": "C",
        "access": "public_web_or_official_access",
        "can_search": False,
        **source_capability_metadata("douyin"),
        "note": "用户无需登录即可提交公开 URL；批量搜索仍需平台权限或合规数据合作证明。",
    },
    {
        "id": "bilibili_public",
        "name": "B 站公开内容",
        "status": "REQUIRES_PROOF",
        "tier": "C",
        "access": "public_web_or_official_access",
        "can_search": False,
        **source_capability_metadata("bilibili"),
        "note": "用户无需登录即可提交公开 URL；批量搜索仍需平台权限或合规数据合作证明。",
    },
    {
        "id": "zhihu_public",
        "name": "知乎公开内容",
        "status": "REQUIRES_PROOF",
        "tier": "C",
        "access": "public_web_or_official_access",
        "can_search": False,
        **source_capability_metadata("zhihu"),
        "note": "用户无需登录即可提交公开 URL；批量搜索仍需平台权限或合规数据合作证明。",
    },
    {
        "id": "feishu_authorized",
        "name": "飞书授权数据",
        "status": "REQUIRES_AUTH",
        "tier": "A",
        "access": "oauth",
        "can_search": False,
        "can_store_original": True,
        "can_write_back": True,
        "end_user_login_required": True,
        "server_authorization_required": True,
        "note": "等待用户授权和字段级权限确认。",
    },
    {
        "id": "crm_authorized",
        "name": "客户 CRM",
        "status": "REQUIRES_AUTH",
        "tier": "A",
        "access": "oauth_or_api_key",
        "can_search": False,
        "can_store_original": True,
        "can_write_back": True,
        "end_user_login_required": True,
        "server_authorization_required": True,
        "note": "等待客户系统授权、字段映射和回写幂等验收。",
    },
]


def list_capabilities() -> list[dict[str, Any]]:
    return [dict(item) for item in CAPABILITIES] + [authorized_search_capability()]
