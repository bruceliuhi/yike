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


def test_reviewed_bundle_requires_reopenable_evidence_and_imports_each_lead():
    store = Store()
    bundle = {
        "review_status": "APPROVED",
        "bundle_id": "run-2026-09-08",
        "leads": [{
            "lead_id": "lead-1", "title": "寻找展台搭建团队", "buyer": "企业采购负责人",
            "summary": "秋季展会需要方案与搭建", "public_url": "https://example.invalid/post/1",
            "source_platform": "xiaohongshu", "source_external_id": "post-1",
            "source_published_at": "2026-09-07T09:00:00Z", "contact_path": "原帖评论",
            "draft_comment": "方便了解城市和面积吗？", "draft_dm": "项目还在评估吗？",
        }],
    }
    result = import_reviewed_bundle(store, "user-1", "profile-1", bundle)
    assert result == [{"opportunity_id": "run-2026-09-08:lead-1", "created": True}]
    assert store.calls[0][2] == "run-2026-09-08:lead-1"


def test_bundle_validation_is_atomic_and_requires_url_hostname():
    store = Store()
    bundle = {"review_status": "APPROVED", "bundle_id": "run-atomic", "leads": [
        {"lead_id": "ok", "title": "t", "buyer": "b", "summary": "s", "public_url": "https://example.invalid/1", "source_platform": "x", "source_external_id": "1", "source_published_at": "2026-09-07T09:00:00Z", "contact_path": "评论", "draft_comment": "c", "draft_dm": "d"},
        {"lead_id": "bad", "title": "t", "buyer": "b", "summary": "s", "public_url": "https://", "source_platform": "x", "source_external_id": "2", "source_published_at": "2026-09-07T09:00:00Z", "contact_path": "评论", "draft_comment": "c", "draft_dm": "d"},
    ]}
    with pytest.raises(ValueError, match="有效主机"):
        import_reviewed_bundle(store, "user-1", "profile-1", bundle)
    assert store.calls == []


def test_sensitive_url_query_is_rejected_before_any_write():
    store = Store()
    bundle = {"review_status": "APPROVED", "bundle_id": "run-sensitive", "leads": [{
        "lead_id": "lead-1", "title": "t", "buyer": "b", "summary": "s",
        "public_url": "https://example.invalid/post/1?xsec_token=secret", "source_platform": "x",
        "source_external_id": "1", "source_published_at": "2026-09-07T09:00:00Z", "contact_path": "评论",
        "draft_comment": "c", "draft_dm": "d",
    }]}
    with pytest.raises(ValueError, match="会话凭据"):
        import_reviewed_bundle(store, "user-1", "profile-1", bundle)
    assert store.calls == []
