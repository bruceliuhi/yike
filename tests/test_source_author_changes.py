"""Pure author-reply change projection tests; every observation is synthetic."""
from datetime import UTC, datetime, timedelta
from contextlib import contextmanager
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from pilot.auth import issue_token, verify_token_claims
from pilot.opportunity_brief import OpportunityBriefService
from pilot.source_content_changes import SourceContentChangeError, project_source_content_changes
from pilot.opportunity_research import OpportunityResearchService
from pilot.web import build_app
from tests.test_candidate_review_postgres import SECRET, seed
from tests.test_confirmed_strategy_review_postgres import (
    databases, env, execution_databases, execution_env, raw_databases, raw_env,
    real_review, real_strategy_env,
)
from tests.test_opportunity_evidence_postgres import include
from tests.test_opportunity_research_postgres import bound


BASE = datetime(2026, 9, 12, 0, tzinfo=UTC)
URL = "https://www.v2ex.com/t/1232232"


_DEFAULT = object()


def context(*replies, expected=_DEFAULT, read=None, complete=None):
    count = len(replies) if read is None else read
    expected = count if expected is _DEFAULT else expected
    complete = expected is not None and expected == count if complete is None else complete
    return {
        "schema_version": "v2ex-author-context-v1",
        "replies_expected": expected,
        "replies_read": count,
        "replies_complete": complete,
        "supplements_read": False,
        "author_replies": list(replies),
    }


def reply(identifier, body, published=1):
    return {
        "id": identifier,
        "body": body,
        "published_at": (BASE + timedelta(minutes=published)).isoformat().replace("+00:00", "Z"),
    }


def row(identifier, version, minutes, *, author="author-1", source_context=None, body="主帖正文", received=None):
    content = {
        "public_url": URL,
        "author_public_id": author,
        "body": body,
        "title": "项目需求",
        "published_at": (BASE - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
    }
    if source_context is not None:
        content["source_context"] = source_context
    return {
        "observation_id": identifier,
        "version_id": version,
        "observed_at": BASE + timedelta(minutes=minutes),
        "received_at": BASE + timedelta(minutes=minutes if received is None else received),
        "content": content,
    }


def project(rows, *, include=True, anchor=0):
    item = rows[anchor]
    return project_source_content_changes(
        rows,
        anchor_observation_id=item["observation_id"],
        anchor_version_id=item["version_id"],
        anchor_observed_at=item["observed_at"],
        anchor_received_at=item["received_at"],
        source_url=URL,
        anchor_body=item["content"]["body"],
        include_author_changes=include,
    )


def test_opt_in_projects_new_modified_once_and_enriches_versions():
    rows = [
        row("o0", "v0", 2, source_context=context()),
        row("o1", "v1", 4, source_context=context(reply("10", "还在选供应商"))),
        row("o2", "v2", 6, received=7, source_context=context(reply("10", "预算调整，先做一个部门"))),
        row("o3", "v2", 8, source_context=context(reply("10", "预算调整，先做一个部门"))),
    ]

    result = project(rows)

    assert result["schemaVersion"] == 3
    assert result["versions"][0]["authorPublicId"] == "author-1"
    assert result["versions"][0]["sourceContext"] == context()
    assert [(event["kind"], event["replyId"]) for event in result["authorChanges"]] == [
        ("OBSERVED_NEW", "10"),
        ("MODIFIED", "10"),
    ]
    observed, modified = result["authorChanges"]
    assert observed["label"] == "首次观察到作者回复"
    assert observed["from"] is None
    assert observed["to"] == {"sourceUrl": URL, "evidenceVersion": "v1", "quote": "还在选供应商"}
    assert modified["label"] == "观察到作者回复正文变化"
    assert modified["from"] == {"sourceUrl": URL, "evidenceVersion": "v1", "quote": "还在选供应商"}
    assert modified["to"] == {"sourceUrl": URL, "evidenceVersion": "v2", "quote": "预算调整，先做一个部门"}
    assert modified["detectedAt"] == "2026-09-12T00:07:00.000Z"
    assert modified["occurredAt"] is None
    assert project(rows)["authorChanges"] == result["authorChanges"]


def test_default_projection_is_exact_legacy_shape_and_gap():
    rows = [row("o0", "v0", 2, source_context=context()),
            row("o1", "v1", 4, source_context=context(reply("10", "新回复")))]

    legacy = project(rows, include=False)

    assert "schemaVersion" not in legacy
    assert "authorChanges" not in legacy
    assert all("authorPublicId" not in item and "sourceContext" not in item for item in legacy["versions"])
    assert legacy["gaps"] == ["作者回复或读取范围发生变化，请重新查看原文；本视图尚未生成作者更新的定向变化记录。"]


def test_partial_previous_scope_still_allows_first_observed_reply_and_reduction_only_gaps():
    rows = [
        row("o0", "v0", 2, source_context=context(expected=None, read=0, complete=False)),
        row("o1", "v1", 4, source_context=context(reply("10", "新读到"), expected=None, read=1, complete=False)),
        row("o2", "v2", 6, source_context=context(expected=None, read=0, complete=False)),
    ]

    result = project(rows)

    assert [(event["kind"], event["replyId"]) for event in result["authorChanges"]] == [("OBSERVED_NEW", "10")]
    assert any("不代表已删除" in gap for gap in result["gaps"])


def test_reply_order_counts_and_third_party_main_body_changes_do_not_create_author_events():
    first = context(reply("10", "A"), reply("11", "B"), expected=None, read=5, complete=False)
    reordered = context(reply("11", "B"), reply("10", "A"), expected=None, read=7, complete=False)
    rows = [row("o0", "v0", 2, source_context=first),
            row("o1", "v1", 4, source_context=reordered, body="第三方计数或主帖正文变化")]

    assert project(rows)["authorChanges"] == []


@pytest.mark.parametrize(
    "rows",
    [
        [row("o0", "v0", 2, author="author-1", source_context=context()),
         row("o1", "v1", 4, author="author-2", source_context=context(reply("10", "X")))],
        [row("o0", "v0", 2), row("o1", "v1", 4, source_context=context(reply("10", "X")))],
    ],
)
def test_changed_or_missing_author_context_never_forges_change(rows):
    result = project(rows)
    assert result["authorChanges"] == []
    assert result["gaps"]


def test_invalid_author_evidence_fails_closed_instead_of_returning_invalid_v3():
    rows = [row("o0", "v0", 2, author="", source_context=context()),
            row("o1", "v1", 4, author="", source_context=context(reply("10", "X")))]
    with pytest.raises(SourceContentChangeError, match="invalid author evidence"):
        project(rows)


def test_two_ordinary_versions_without_author_context_have_no_author_gap():
    result = project([row("o0", "v0", 2), row("o1", "v1", 4, body="新主帖正文")])
    assert result["authorChanges"] == []
    assert not any("作者" in gap for gap in result["gaps"])


def test_equal_millisecond_conflict_resets_author_baseline_without_guessing_direction():
    rows = [
        row("o0", "v0", 2, source_context=context()),
        row("o1", "v1", 4, source_context=context(reply("10", "A"))),
        row("o2", "v2", 4, received=5, source_context=context(reply("10", "B"))),
        row("o3", "v3", 6, source_context=context(reply("10", "C"))),
        row("o4", "v4", 8, source_context=context(reply("10", "D"))),
    ]

    result = project(rows)

    assert [(event["fromObservationId"], event["toObservationId"]) for event in result["authorChanges"]] == [("o3", "o4")]
    assert any("同一观察时间" in gap and "作者" in gap for gap in result["gaps"])


def test_pre_anchor_author_reply_does_not_create_change():
    rows = [
        row("pre", "vp", 0, source_context=context(reply("9", "锚点前", published=-1))),
        row("anchor", "v0", 2, source_context=context()),
        row("same", "v1", 4, source_context=context()),
    ]
    assert project(rows, anchor=1)["authorChanges"] == []


def test_impossible_author_times_fail_closed_without_changes():
    too_early = reply("10", "早于原文", published=-2)
    too_late = reply("11", "晚于观察", published=10)
    rows = [
        row("anchor", "v0", 2, source_context=context()),
        row("early", "v1", 4, source_context=context(too_early)),
        row("late", "v2", 6, source_context=context(too_late)),
    ]

    with pytest.raises(SourceContentChangeError, match="invalid author evidence"):
        project(rows)


def test_author_change_limit_fails_closed():
    first = tuple(reply(str(index), f"回复 {index}") for index in range(1, 101))
    second = tuple(reply(str(index), f"第一次修改 {index}") for index in range(1, 101))
    third = tuple(reply(str(index), f"第二次修改 {index}") for index in range(1, 101))
    rows = [row("o0", "v0", 2, source_context=context()),
            row("o1", "v1", 4, source_context=context(*first)),
            row("o2", "v2", 6, source_context=context(*second)),
            row("o3", "v3", 8, source_context=context(*third))]

    with pytest.raises(SourceContentChangeError, match="author change limit"):
        project(rows)


def test_research_timeline_only_opts_into_author_projection_for_schema_three(monkeypatch):
    class Cursor:
        def execute(self, *_args): pass
        def fetchone(self): return (0,)

    service = OpportunityResearchService.__new__(OpportunityResearchService)
    service._binding = lambda binding: binding
    service._recognized = lambda *_args: {"source": {}}

    @contextmanager
    def snapshot(_claims):
        yield Cursor(), "tenant-1", BASE + timedelta(minutes=10)

    service._snapshot = snapshot
    calls = []

    def load(*_args, **kwargs):
        calls.append(kwargs.get("include_author_changes", False))
        base = {"anchorObservationId":"o0", "versions":[], "observations":[],
                "changes":[], "gaps":[]}
        return ({"schemaVersion":3, **base, "authorChanges":[]} if calls[-1] else base)

    monkeypatch.setattr("pilot.source_content_changes.load_source_content_changes", load)
    claims = SimpleNamespace(user_id="user-1")

    legacy = service.timeline(claims, {"opportunityId":"legacy"})
    current = service.timeline(claims, {"opportunityId":"current"}, 3)

    assert calls == [False, True]
    assert legacy["schemaVersion"] == 2 and "authorChanges" not in legacy
    assert current["schemaVersion"] == 3 and current["authorChanges"] == []
    with pytest.raises(Exception, match="invalid_request"):
        service.timeline(claims, {}, 1)


def test_restricted_pg_http_v3_author_update_brief_and_owner_isolation(real_strategy_env, tmp_path):
    env = real_strategy_env
    review = real_review(env)
    now = datetime.now(UTC).replace(microsecond=0)
    source_published = now - timedelta(days=1)
    initial_observed = now - timedelta(seconds=10)
    changed_observed = now - timedelta(seconds=5)
    initial_context = context()
    source = {
        "kind":"PAGE", "external_source_id":"1232232", "external_comment_id":None,
        "public_url":URL, "author_public_id":"author-1", "normalizer_version":"v2ex-author-page-v1",
        "published_at":source_published.isoformat().replace("+00:00", "Z"),
        "observed_at":initial_observed.isoformat().replace("+00:00", "Z"),
        "source_context":initial_context,
    }
    _, candidate, _, _, _, _, opportunity_id = include(env, service=review, **source)
    detail = env.store.get_opportunity(env.claims.user_id, opportunity_id)
    update_context = context({"id":"10", "body":"预算调整，先做一个部门",
                              "published_at":(now-timedelta(seconds=30)).isoformat().replace("+00:00", "Z")})
    update = seed(env, **(source | {
        "observed_at":changed_observed.isoformat().replace("+00:00", "Z"),
        "source_context":update_context,
    }))
    assert update["candidateId"] == candidate["candidateId"]

    app = build_app(env.store, auth_secret=SECRET, candidate_review=review,
                    research_strategies=env.strategies,
                    opportunity_brief=OpportunityBriefService(env.db))
    client = TestClient(app, base_url="https://pilot.example")
    client.headers["Authorization"] = "Bearer " + issue_token(env.claims.user_id, SECRET)
    binding = bound(env, opportunity_id, candidate["sourceVersionId"], detail["public_url"])

    legacy = client.post("/api/ui/opportunity-research/timeline", json={"binding":binding})
    assert legacy.status_code == 200, legacy.text
    assert legacy.json()["schemaVersion"] == 2
    assert "authorChanges" not in legacy.json()
    assert all("sourceContext" not in item for item in legacy.json()["versions"])

    response = client.post("/api/ui/opportunity-research/timeline",
                           json={"binding":binding, "timelineSchemaVersion":3})
    assert response.status_code == 200, response.text
    timeline = response.json()
    assert timeline["schemaVersion"] == 3
    assert timeline["versions"][-1]["sourceContext"] == update_context
    assert timeline["versions"][-1]["authorPublicId"] == "author-1"
    assert len(timeline["authorChanges"]) == 1
    event = timeline["authorChanges"][0]
    assert event["kind"] == "OBSERVED_NEW" and event["replyId"] == "10"
    assert event["to"]["evidenceVersion"] == update["sourceVersionId"]
    assert event["to"]["quote"] == "预算调整，先做一个部门"
    exported = tmp_path / "author-change-v3-response.json"
    exported.write_text(json.dumps(timeline, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    brief = client.post("/api/ui/opportunity-brief/query", json={
        "contractVersion":1, "requestId":str(uuid4()), "userId":env.claims.user_id,
        "accountScopeId":env.tenant, "scopeVersion":1, "profileId":env.profile,
        "profileVersion":env.profile_number, "businessDate":now.date().isoformat(), "timezone":"UTC",
    })
    assert brief.status_code == 200, brief.text
    changes = brief.json()["groups"]["changes"]
    assert changes["total"] == 1
    assert changes["items"][0]["basis"] == {
        "recordId":event["id"], "version":event["toObservationId"],
        "excerpt":"预算调整，先做一个部门", "kind":"VERIFIED_CHANGE",
        "verifiedAt":event["detectedAt"],
    }
    assert "作者回复" in changes["items"][0]["reason"]
    assert "项目已关闭" not in changes["items"][0]["reason"]

    other_user = env.users[1]
    client.headers["Authorization"] = "Bearer " + issue_token(other_user, SECRET)
    other_binding = binding | {"userId":other_user}
    hidden = client.post("/api/ui/opportunity-research/timeline",
                         json={"binding":other_binding, "timelineSchemaVersion":3})
    assert hidden.status_code == 409
    listed = client.get("/api/ui/opportunity-research")
    assert listed.status_code == 200
    assert all(item["opportunity"]["id"] != opportunity_id for item in listed.json()["records"])

    with env.admin.connect() as connection:
        connection.execute("DELETE FROM pilot_opportunity_evidence WHERE tenant_id=%s AND opportunity_id=%s",
                           (env.tenant, opportunity_id))
    legacy_shared = client.get("/api/ui/opportunity-research")
    assert legacy_shared.status_code == 200
    assert any(item["opportunity"]["id"] == opportunity_id for item in legacy_shared.json()["records"])
