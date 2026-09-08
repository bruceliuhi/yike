from __future__ import annotations

from datetime import datetime


_REQUIRED = (
    "lead_id", "title", "buyer", "summary", "public_url", "source_platform",
    "source_external_id", "source_published_at", "contact_path", "draft_comment", "draft_dm",
)


def import_reviewed_bundle(store, user_id: str, profile_version_id: str, bundle: dict) -> list[dict]:
    """Import only a human-approved, evidence-bearing research bundle."""
    if bundle.get("review_status") != "APPROVED":
        raise ValueError("研究包必须先完成人工复核")
    bundle_id = bundle.get("bundle_id")
    leads = bundle.get("leads")
    if not isinstance(bundle_id, str) or not bundle_id.strip() or not isinstance(leads, list):
        raise ValueError("研究包缺少 bundle_id 或 leads")
    results = []
    for lead in leads:
        if not isinstance(lead, dict) or any(not isinstance(lead.get(key), str) or not lead[key].strip() for key in _REQUIRED):
            raise ValueError("线索必须包含可重开的来源、时间、联系路径和独立草稿")
        if not lead["public_url"].startswith(("https://", "http://")):
            raise ValueError("来源链接必须是可重开的 HTTP(S) 地址")
        try:
            datetime.strptime(lead["source_published_at"], "%Y-%m-%dT%H:%M:%SZ")
        except ValueError as error:
            raise ValueError("source_published_at 必须是 UTC 时间") from error
        data = {key: lead[key] for key in _REQUIRED if key != "lead_id"}
        results.append(store.import_opportunity(user_id, profile_version_id, f"{bundle_id}:{lead['lead_id']}", data))
    return results
