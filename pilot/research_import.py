from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl, urlparse


_REQUIRED = (
    "lead_id", "title", "buyer", "summary", "public_url", "source_platform",
    "source_external_id", "source_published_at", "contact_path", "public_excerpt",
    "match_reason", "action_signal", "value_judgment", "risk", "draft_comment", "draft_dm",
)


def import_reviewed_bundle(store, user_id: str, profile_version_id: str, bundle: dict, *, now: datetime | None = None) -> list[dict]:
    """Import only a human-approved, evidence-bearing research bundle."""
    if not isinstance(bundle, dict):
        raise ValueError("研究包必须是对象")
    if bundle.get("review_status") != "APPROVED":
        raise ValueError("研究包必须先完成人工复核")
    bundle_id = bundle.get("bundle_id")
    leads = bundle.get("leads")
    if not isinstance(bundle_id, str) or not bundle_id.strip() or not isinstance(leads, list):
        raise ValueError("研究包缺少 bundle_id 或 leads")
    if bundle.get("profile_version_id") != profile_version_id:
        raise ValueError("研究包目标画像不匹配")
    if bundle.get("audience") != "CUSTOMER":
        raise ValueError("研究包 audience 必须是 CUSTOMER")
    reviewer_id = bundle.get("reviewer_id")
    reviewed_at_text = bundle.get("reviewed_at")
    if not isinstance(reviewer_id, str) or not reviewer_id.strip() or not isinstance(reviewed_at_text, str) or not reviewed_at_text.strip():
        raise ValueError("研究包缺少复核人或复核时间")
    now_utc = (now or datetime.now(UTC)).astimezone(UTC)
    try:
        reviewed_at = datetime.strptime(reviewed_at_text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as error:
        raise ValueError("reviewed_at 必须是 UTC 时间") from error
    if reviewed_at > now_utc:
        raise ValueError("reviewed_at 不能是未来时间")
    validated = []
    for lead in leads:
        if not isinstance(lead, dict) or any(not isinstance(lead.get(key), str) or not lead[key].strip() for key in _REQUIRED):
            raise ValueError("线索必须包含可重开的来源、时间、联系路径和独立草稿")
        parsed = urlparse(lead["public_url"])
        if parsed.scheme not in ("https", "http") or not parsed.hostname:
            raise ValueError("来源链接必须包含有效主机")
        if parsed.username or parsed.password:
            raise ValueError("来源链接不能包含用户信息凭据")
        if parsed.fragment:
            raise ValueError("来源链接不能包含片段凭据")
        sensitive_markers = ("token", "cookie", "session", "authorization", "signature", "password", "secret")
        if any(any(marker in part.lower() for marker in sensitive_markers) for pair in parse_qsl(parsed.query, keep_blank_values=True) for part in pair):
            raise ValueError("来源链接不能包含会话凭据或访问令牌")
        try:
            published_at = datetime.strptime(lead["source_published_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        except ValueError as error:
            raise ValueError("source_published_at 必须是 UTC 时间") from error
        if published_at > now_utc:
            raise ValueError("source_published_at 不能是未来时间")
        if lead["draft_comment"].strip() == lead["draft_dm"].strip():
            raise ValueError("公开评论和私信草稿必须分别撰写")
        if now_utc - published_at > timedelta(days=60):
            raise ValueError("source_published_at 必须在最近 60 天内")
        validated.append({**lead, "reviewed_by": reviewer_id, "reviewed_at": reviewed_at_text})
    results = []
    for lead in validated:
        data = {key: lead[key] for key in _REQUIRED if key != "lead_id"}
        data["reviewed_by"] = lead["reviewed_by"]
        data["reviewed_at"] = lead["reviewed_at"]
        results.append(store.import_opportunity(user_id, profile_version_id, f"{bundle_id}:{lead['lead_id']}", data))
    return results
