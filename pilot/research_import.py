from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl, urlparse


_REQUIRED = (
    "lead_id", "title", "buyer", "summary", "public_url", "source_platform",
    "source_external_id", "source_published_at", "contact_path", "draft_comment", "draft_dm",
)


def import_reviewed_bundle(store, user_id: str, profile_version_id: str, bundle: dict, *, now: datetime | None = None) -> list[dict]:
    """Import only a human-approved, evidence-bearing research bundle."""
    if bundle.get("review_status") != "APPROVED":
        raise ValueError("研究包必须先完成人工复核")
    bundle_id = bundle.get("bundle_id")
    leads = bundle.get("leads")
    if not isinstance(bundle_id, str) or not bundle_id.strip() or not isinstance(leads, list):
        raise ValueError("研究包缺少 bundle_id 或 leads")
    now_utc = (now or datetime.now(UTC)).astimezone(UTC)
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
        if published_at > now_utc + timedelta(minutes=5):
            raise ValueError("source_published_at 不能是未来时间")
        if now_utc - published_at > timedelta(days=60):
            raise ValueError("source_published_at 必须在最近 60 天内")
        validated.append(lead)
    results = []
    for lead in validated:
        data = {key: lead[key] for key in _REQUIRED if key != "lead_id"}
        results.append(store.import_opportunity(user_id, profile_version_id, f"{bundle_id}:{lead['lead_id']}", data))
    return results
