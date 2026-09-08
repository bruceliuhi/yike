from datetime import UTC, datetime, timedelta

import pytest

from pilot.research_import import import_reviewed_bundle


class Store:
    def __init__(self):
        self.calls = []

    def import_opportunity(self, user_id, profile_version_id, import_key, data):
        self.calls.append((user_id, profile_version_id, import_key, data))
        return {"opportunity_id": import_key, "created": True}


def test_unreviewed_bundle_is_rejected_without_writing():
    store = Store()
    with pytest.raises(ValueError, match="人工复核"):
        import_reviewed_bundle(store, "user-1", "profile-1", {"review_status": "PENDING", "leads": []})
    assert store.calls == []


def test_bundle_must_bind_customer_profile_and_audience():
    store = Store()
    base = {"review_status": "APPROVED", "bundle_id": "run-bound", "leads": []}
    with pytest.raises(ValueError, match="目标画像"):
        import_reviewed_bundle(store, "user-1", "profile-1", {**base, "profile_version_id": "profile-2", "audience": "CUSTOMER"})
    with pytest.raises(ValueError, match="CUSTOMER"):
        import_reviewed_bundle(store, "user-1", "profile-1", {**base, "profile_version_id": "profile-1", "audience": "SELF_USE"})


def test_reviewed_bundle_requires_reopenable_evidence_and_imports_each_lead():
    store = Store()
    bundle = {
        "review_status": "APPROVED",
        "bundle_id": "run-2026-09-08",
        "profile_version_id": "profile-1", "audience": "CUSTOMER", "reviewer_id": "reviewer-1", "reviewed_at": "2026-09-08T10:00:00Z",
        "leads": [{
            "lead_id": "lead-1", "title": "寻找展台搭建团队", "buyer": "企业采购负责人",
            "summary": "秋季展会需要方案与搭建", "public_url": "https://example.invalid/post/1",
            "source_platform": "xiaohongshu", "source_external_id": "post-1",
            "source_published_at": "2026-09-07T09:00:00Z", "contact_path": "原帖评论",
            "public_excerpt": "秋季展会寻展台设计搭建团队", "match_reason": "明确寻源且给出展会场景",
            "action_signal": "正在比较服务商", "value_judgment": "项目型服务，具备持续扩展可能", "risk": "预算未公开",
            "draft_comment": "方便了解城市和面积吗？", "draft_dm": "项目还在评估吗？",
        }],
    }
    result = import_reviewed_bundle(store, "user-1", "profile-1", bundle)
    assert result == [{"opportunity_id": "run-2026-09-08:lead-1", "created": True}]
    assert store.calls[0][2] == "run-2026-09-08:lead-1"


def test_bundle_validation_is_atomic_and_requires_url_hostname():
    store = Store()
    bundle = {"review_status": "APPROVED", "bundle_id": "run-atomic", "profile_version_id": "profile-1", "audience": "CUSTOMER", "reviewer_id": "reviewer-1", "reviewed_at": "2026-09-08T10:00:00Z", "leads": [
        {"lead_id": "ok", "title": "t", "buyer": "b", "summary": "s", "public_url": "https://example.invalid/1", "source_platform": "x", "source_external_id": "1", "source_published_at": "2026-09-07T09:00:00Z", "contact_path": "评论", "public_excerpt": "原始评论", "match_reason": "明确需求", "action_signal": "询价", "value_judgment": "项目型", "risk": "预算未知", "draft_comment": "c", "draft_dm": "d"},
        {"lead_id": "bad", "title": "t", "buyer": "b", "summary": "s", "public_url": "https://", "source_platform": "x", "source_external_id": "2", "source_published_at": "2026-09-07T09:00:00Z", "contact_path": "评论", "public_excerpt": "原始评论", "match_reason": "明确需求", "action_signal": "询价", "value_judgment": "项目型", "risk": "预算未知", "draft_comment": "c", "draft_dm": "d"},
    ]}
    with pytest.raises(ValueError, match="有效主机"):
        import_reviewed_bundle(store, "user-1", "profile-1", bundle)
    assert store.calls == []


def test_sensitive_url_query_is_rejected_before_any_write():
    store = Store()
    bundle = {"review_status": "APPROVED", "bundle_id": "run-sensitive", "profile_version_id": "profile-1", "audience": "CUSTOMER", "reviewer_id": "reviewer-1", "reviewed_at": "2026-09-08T10:00:00Z", "leads": [{
        "lead_id": "lead-1", "title": "t", "buyer": "b", "summary": "s",
        "public_url": "https://example.invalid/post/1?xsec_token=secret", "source_platform": "x",
        "source_external_id": "1", "source_published_at": "2026-09-07T09:00:00Z", "contact_path": "评论",
        "public_excerpt": "原始评论", "match_reason": "明确需求", "action_signal": "询价", "value_judgment": "项目型", "risk": "预算未知", "draft_comment": "c", "draft_dm": "d",
    }]}
    with pytest.raises(ValueError, match="会话凭据"):
        import_reviewed_bundle(store, "user-1", "profile-1", bundle)
    assert store.calls == []


@pytest.mark.parametrize("url", [
    "https://user:password@example.invalid/post/1",
    "https://example.invalid/post/1#session-token",
    "https://example.invalid/post/1?ref=access-token-value",
])
def test_url_credentials_are_rejected_before_any_write(url):
    store = Store()
    bundle = {"review_status": "APPROVED", "bundle_id": "run-sensitive-url", "profile_version_id": "profile-1", "audience": "CUSTOMER", "reviewer_id": "reviewer-1", "reviewed_at": "2026-09-08T10:00:00Z", "leads": [{
        "lead_id": "lead-1", "title": "t", "buyer": "b", "summary": "s",
        "public_url": url, "source_platform": "x", "source_external_id": "1",
        "source_published_at": "2026-09-07T09:00:00Z", "contact_path": "评论",
        "public_excerpt": "原始评论", "match_reason": "明确需求", "action_signal": "询价", "value_judgment": "项目型", "risk": "预算未知", "draft_comment": "c", "draft_dm": "d",
    }]}
    with pytest.raises(ValueError, match="凭据|用户信息|片段"):
        import_reviewed_bundle(store, "user-1", "profile-1", bundle)
    assert store.calls == []


def test_source_published_at_must_be_recent_and_not_in_future():
    now = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    base = {
        "review_status": "APPROVED", "bundle_id": "run-freshness", "profile_version_id": "profile-1", "audience": "CUSTOMER", "reviewer_id": "reviewer-1", "reviewed_at": "2026-09-08T10:00:00Z", "leads": [{
            "lead_id": "lead-1", "title": "t", "buyer": "b", "summary": "s",
            "public_url": "https://example.invalid/post/1", "source_platform": "x", "source_external_id": "1",
            "contact_path": "评论", "public_excerpt": "原始评论", "match_reason": "明确需求", "action_signal": "询价", "value_judgment": "项目型", "risk": "预算未知", "draft_comment": "c", "draft_dm": "d",
        }]}
    old = {**base, "leads": [{**base["leads"][0], "source_published_at": "2026-07-01T09:00:00Z"}]}
    future = {**base, "leads": [{**base["leads"][0], "source_published_at": "2026-09-08T12:06:00Z"}]}
    with pytest.raises(ValueError, match="60 天"):
        import_reviewed_bundle(Store(), "user-1", "profile-1", old, now=now)
    with pytest.raises(ValueError, match="未来"):
        import_reviewed_bundle(Store(), "user-1", "profile-1", future, now=now)
