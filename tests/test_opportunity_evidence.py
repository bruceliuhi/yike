import copy
from datetime import UTC, datetime
import hashlib
import json

import pytest

from pilot.opportunity_evidence import (
    OpportunityEvidenceError,
    build_evidence,
    evidence_digest,
    evidence_view,
)


OPPORTUNITY_ID = "84e142ae-5633-48bb-9fce-dbb842b48f6c"
PROFILE_ID = "profile-version-7"
CANDIDATE_ID = "cf9ba9d4-bb80-4164-b475-e960a16d44d1"
VERSION_ID = "86ea3df6-bfdf-46d2-af72-cab804e407f2"
OBSERVATION_ID = "f6684a08-e950-457d-8403-916a8e7c186b"
ASSESSMENT_ID = "f3c97ccd-b091-4508-ae6a-e71a391d85d3"
RULE_SHA256 = "b" * 64
PRIVATE_MARKER = "PRIVATE-MARKER-MUST-NOT-LEAK"


def inputs(*, kind="COMMENT"):
    content = {
        "public_url": "https://www.bilibili.com/video/BV1public?p=1",
        "title": "食品工厂  扩产原帖",
        "author_public_id": "comment-author",
        "body": "我们工厂想采购  输送设备，月底前报价。",
        "published_at": "2026-09-09T08:00:00Z",
        "parent": {
            "external_comment_id": "parent-comment",
            "body": "父评论保留  原样文本",
            "author_public_id": "parent-author",
            "published_at": None,
            "public_url": None,
        },
    }
    if kind != "COMMENT":
        content["parent"] = None
    content_sha256 = hashlib.sha256(json.dumps(
        content, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    snapshot = {
        "binding": {
            "candidateId": CANDIDATE_ID,
            "candidateRevision": 3,
            "sourceVersionId": VERSION_ID,
            "profileId": PROFILE_ID,
            "profileVersion": 7,
        },
        "raw": {
            "candidate_id": CANDIDATE_ID,
            "platform": "BILIBILI",
            "kind": kind,
            "external_source_id": "BV1public",
            "external_comment_id": "comment-8" if kind == "COMMENT" else None,
            "profile_version_id": PROFILE_ID,
            "strategy_version_id": "strategy-version-4",
            "source_identity": "c" * 64,
            "revision": 3,
            "ambiguous": False,
            "latest_observed_at": "2026-09-09T09:00:00+00:00",
            "current_observation_id": OBSERVATION_ID,
            "version_id": VERSION_ID,
            "content_version": content_sha256,
            "content": content,
            "query": PRIVATE_MARKER,
        },
        "description": PRIVATE_MARKER,
        "strategy": {"configuration": {"private": PRIVATE_MARKER}},
        "strategyHash": "d" * 64,
    }
    assessment = {
        "id": ASSESSMENT_ID,
        "candidateId": CANDIDATE_ID,
        "candidateRevision": 3,
        "sourceVersionId": VERSION_ID,
        "profileId": PROFILE_ID,
        "profileVersion": 7,
        "strategyVersionId": "strategy-version-4",
        "assessedAt": "2026-09-09T09:10:00+00:00",
        "provider": "synthetic",
        "model": "boundary-only",
        "rule_version": "test-v1",
        "rule_sha256": RULE_SHA256,
        "businessMatch": {
            "level": "HIGH",
            "reason": PRIVATE_MARKER,
            "citations": [
                {"field": "profile.description", "quote": PRIVATE_MARKER},
                {"field": "parent.title", "quote": "食品工厂  扩产"},
            ],
        },
        "intent": {
            "level": "HIGH",
            "reason": PRIVATE_MARKER,
            "citations": [{"field": "body", "quote": "采购  输送设备"}],
        },
        "urgency": {
            "level": "UNKNOWN",
            "reason": PRIVATE_MARKER,
            "citations": [{"field": "parent.body", "quote": "父评论保留  原样"}],
        },
        "actionability": {"level": "UNKNOWN", "reason": PRIVATE_MARKER, "citations": []},
        "full_model_response": PRIVATE_MARKER,
    }
    observation = {
        "observation_id": OBSERVATION_ID,
        "candidate_id": CANDIDATE_ID,
        "version_id": VERSION_ID,
        "observed_at": datetime(2026, 9, 9, 9, 0, tzinfo=UTC),
        "received_at": datetime(2026, 9, 9, 9, 0, 2, tzinfo=UTC),
    }
    verification = {
        "id": "42e65ba8-d795-434d-8c63-fc539d1c5674",
        "method": "HUMAN_REOPENED",
        "status": "OPEN",
        "checkedAt": "2026-09-09T09:20:00+00:00",
        "openingMethod": "DIRECT",
        "contactMethod": "COMMENT",
        "locator": PRIVATE_MARKER,
        "excerpt": PRIVATE_MARKER,
        "binding": copy.deepcopy(snapshot["binding"]),
    }
    return snapshot, assessment, observation, verification


def test_comment_evidence_keeps_roles_verbatim_quotes_and_omits_private_data_without_mutation():
    snapshot, assessment, observation, verification = inputs()
    originals = copy.deepcopy((snapshot, assessment, observation, verification))

    payload = build_evidence(
        opportunity_id=OPPORTUNITY_ID,
        snapshot=snapshot,
        assessment=assessment,
        observation=observation,
        verification=verification,
        captured_at=datetime(2026, 9, 9, 9, 30, tzinfo=UTC),
    )

    assert (snapshot, assessment, observation, verification) == originals
    assert list(payload) == [
        "schema_version", "opportunity_id", "captured_at", "source",
        "observation", "assessment", "verification",
    ]
    assert payload["source"] == {
        "platform": "BILIBILI",
        "kind": "COMMENT",
        "external_source_id": "BV1public",
        "external_comment_id": "comment-8",
        "public_url": "https://www.bilibili.com/video/BV1public?p=1",
        "version_id": VERSION_ID,
        "content_sha256": snapshot["raw"]["content_version"],
        "title": None,
        "container_title": "食品工厂  扩产原帖",
        "body": "我们工厂想采购  输送设备，月底前报价。",
        "author_public_id": "comment-author",
        "published_at": "2026-09-09T08:00:00Z",
        "parent": {
            "external_comment_id": "parent-comment",
            "body": "父评论保留  原样文本",
            "author_public_id": "parent-author",
            "published_at": None,
            "public_url": None,
        },
    }
    assert payload["observation"] == {
        "id": OBSERVATION_ID,
        "observed_at": "2026-09-09T09:00:00+00:00",
        "received_at": "2026-09-09T09:00:02+00:00",
    }
    assert payload["assessment"] == {
        "id": ASSESSMENT_ID,
        "assessed_at": "2026-09-09T09:10:00+00:00",
        "profile_version_id": PROFILE_ID,
        "profile_version": 7,
        "strategy_version_id": "strategy-version-4",
        "provider": "synthetic",
        "model": "boundary-only",
        "rule_version": "test-v1",
        "rule_sha256": RULE_SHA256,
        "citations": [
            {"dimension": "businessMatch", "field": "source.container_title", "quote": "食品工厂  扩产"},
            {"dimension": "intent", "field": "source.body", "quote": "采购  输送设备"},
            {"dimension": "urgency", "field": "source.parent.body", "quote": "父评论保留  原样"},
        ],
        "omitted_profile_citations": 1,
    }
    assert payload["verification"] == {
        "method": "HUMAN_REOPENED",
        "status_at_capture": "OPEN",
        "checked_at": "2026-09-09T09:20:00+00:00",
        "opening_method": "DIRECT",
        "contact_method": "COMMENT",
    }
    assert PRIVATE_MARKER not in repr(payload)


def test_non_comment_uses_own_title_and_null_container():
    snapshot, assessment, observation, verification = inputs(kind="POST")
    assessment["businessMatch"]["citations"][1] = {"field": "title", "quote": "食品工厂  扩产"}
    assessment["urgency"]["citations"] = [{"field": "body", "quote": "月底前"}]
    payload = build_evidence(
        opportunity_id=OPPORTUNITY_ID,
        snapshot=snapshot,
        assessment=assessment,
        observation=observation,
        verification=verification,
        captured_at="2026-09-09T09:30:00+00:00",
    )
    assert payload["source"]["title"] == "食品工厂  扩产原帖"
    assert payload["source"]["container_title"] is None
    assert payload["source"]["parent"] is None
    assert payload["assessment"]["citations"][0]["field"] == "source.title"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s, a, o, v: o.update(candidate_id="other"),
        lambda s, a, o, v: o.update(version_id="other"),
        lambda s, a, o, v: a["intent"]["citations"][0].update(quote="not verbatim"),
        lambda s, a, o, v: a["intent"]["citations"][0].update(field="private.response"),
        lambda s, a, o, v: s["raw"].update(external_comment_id=None),
        lambda s, a, o, v: s["raw"]["content"].update(body="changed after hashing"),
        lambda s, a, o, v: v.update(status="BLOCKED"),
    ],
)
def test_builder_rejects_mismatched_roles_bindings_and_impossible_citations(mutate):
    snapshot, assessment, observation, verification = inputs()
    mutate(snapshot, assessment, observation, verification)
    with pytest.raises(OpportunityEvidenceError, match="invalid_opportunity_evidence"):
        build_evidence(
            opportunity_id=OPPORTUNITY_ID,
            snapshot=snapshot,
            assessment=assessment,
            observation=observation,
            verification=verification,
            captured_at="2026-09-09T09:30:00+00:00",
        )


def test_view_returns_fresh_verified_data_and_rejects_corruption_safely():
    snapshot, assessment, observation, verification = inputs()
    payload = build_evidence(
        opportunity_id=OPPORTUNITY_ID,
        snapshot=snapshot,
        assessment=assessment,
        observation=observation,
        verification=verification,
        captured_at="2026-09-09T09:30:00+00:00",
    )
    digest = evidence_digest(payload)

    first = evidence_view(payload, digest, opportunity_id=OPPORTUNITY_ID, profile_version_id=PROFILE_ID)
    assert first == {"status": "CAPTURED", "snapshot_sha256": digest, "snapshot": payload}
    first["snapshot"]["source"]["body"] = "local mutation"
    assert evidence_view(payload, digest, opportunity_id=OPPORTUNITY_ID, profile_version_id=PROFILE_ID)["snapshot"]["source"]["body"] != "local mutation"
    assert evidence_view(None, None, opportunity_id=OPPORTUNITY_ID, profile_version_id=PROFILE_ID) == {
        "status": "UNAVAILABLE", "reason": "NOT_CAPTURED"
    }

    corruptions = [
        (payload, "0" * 64, OPPORTUNITY_ID, PROFILE_ID),
        (payload | {"schema_version": "future"}, digest, OPPORTUNITY_ID, PROFILE_ID),
        (payload, digest, "other-opportunity", PROFILE_ID),
        (payload, digest, OPPORTUNITY_ID, "other-profile"),
        (None, digest, OPPORTUNITY_ID, PROFILE_ID),
    ]
    for corrupt_payload, corrupt_digest, opportunity_id, profile_id in corruptions:
        with pytest.raises(OpportunityEvidenceError, match="corrupt_opportunity_evidence") as caught:
            evidence_view(
                corrupt_payload,
                corrupt_digest,
                opportunity_id=opportunity_id,
                profile_version_id=profile_id,
            )
        assert caught.value.__context__ is None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["source"].update(public_url={"private": "value"}),
        lambda value: value["assessment"].update(provider={"private": "value"}),
        lambda value: value["observation"].update(observed_at="not-a-timestamp"),
        lambda value: value["assessment"].update(profile_version=0),
    ],
)
def test_view_rejects_rehashed_malformed_present_payload(mutate):
    snapshot, assessment, observation, verification = inputs()
    payload = build_evidence(
        opportunity_id=OPPORTUNITY_ID,
        snapshot=snapshot,
        assessment=assessment,
        observation=observation,
        verification=verification,
        captured_at="2026-09-09T09:30:00+00:00",
    )
    mutate(payload)
    with pytest.raises(OpportunityEvidenceError, match="corrupt_opportunity_evidence"):
        evidence_view(
            payload,
            evidence_digest(payload),
            opportunity_id=OPPORTUNITY_ID,
            profile_version_id=PROFILE_ID,
        )
