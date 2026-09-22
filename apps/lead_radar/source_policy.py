from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


# These are public host families only.  A match means that a submitted URL can be
# classified for provenance; it does not grant permission to crawl or search the
# platform.
PLATFORM_HOSTS: dict[str, tuple[str, ...]] = {
    "xiaohongshu": ("xiaohongshu.com", "xhslink.com"),
    "douyin": ("douyin.com", "iesdouyin.com"),
    "bilibili": ("bilibili.com", "b23.tv"),
    "zhihu": ("zhihu.com",),
}

PLATFORM_NAMES = {
    "xiaohongshu": "小红书",
    "douyin": "抖音",
    "bilibili": "B 站",
    "zhihu": "知乎",
    "web": "公开网站",
}


def _host(value: str) -> str:
    parsed = urlparse(str(value).strip())
    return (parsed.hostname or "").lower().rstrip(".")


def _matches_host(host: str, suffix: str) -> bool:
    return host == suffix or host.endswith(f".{suffix}")


def classify_public_url(value: str) -> dict[str, Any]:
    """Classify a public URL without claiming access or authorization.

    This function is intentionally pure.  It only labels provenance so the UI and
    evidence card can distinguish a public social page from a general website.
    Actual fetching remains behind the controlled URL capture and proof gates.
    """

    host = _host(value)
    platform = "web"
    for candidate, suffixes in PLATFORM_HOSTS.items():
        if any(_matches_host(host, suffix) for suffix in suffixes):
            platform = candidate
            break
    is_social = platform != "web"
    return {
        "platform": platform,
        "platform_name": PLATFORM_NAMES[platform],
        "host": host or None,
        "source_family": "social_platform" if is_social else "public_web",
        "capture_layer": "public_url_capture",
        "end_user_login_required": False,
        "server_authorization_required": is_social,
        "automated_search_status": "REQUIRES_PROOF" if is_social else "REQUIRES_PROOF",
        "rights_note": (
            "用户无需登录；平台侧权限、条款、频率、重开和保存边界仍需证明。"
            if is_social
            else "用户无需登录；只访问用户明确提交的公网 URL。"
        ),
    }


def source_capability_metadata(platform: str) -> dict[str, Any]:
    """Return the stable product contract for a public source family."""

    if platform not in PLATFORM_NAMES:
        raise ValueError("unknown_public_source_platform")
    social = platform != "web"
    return {
        "platform": platform,
        "platform_name": PLATFORM_NAMES[platform],
        "discovery_layer": "public_url_or_search_index",
        "end_user_login_required": False,
        "server_authorization_required": social,
        "automated_search_status": "REQUIRES_PROOF",
        "can_store_original": False,
        "can_write_back": False,
        "proof_gates": [
            "terms_and_robots",
            "rate_limit",
            "published_at",
            "url_reopen",
            "save_boundary",
            "retry_idempotency",
        ],
    }
