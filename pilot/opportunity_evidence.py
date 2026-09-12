"""Immutable public evidence projection captured at human inclusion."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import re
from uuid import UUID
from pilot.candidate_review_contract import DemandEvidence


SCHEMA_VERSION = "opportunity-source-evidence-v1"
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_DIMENSIONS = ("businessMatch", "intent", "urgency", "actionability")
_CITATION_FIELDS = {
    "title": "source.title",
    "body": "source.body",
    "parent.title": "source.container_title",
    "parent.body": "source.parent.body",
}
_TOP_LEVEL = {
    "schema_version", "opportunity_id", "captured_at", "source",
    "observation", "assessment", "verification",
}
_SOURCE_FIELDS = {
    "platform", "kind", "external_source_id", "external_comment_id", "public_url",
    "version_id", "content_sha256", "title", "container_title", "body",
    "author_public_id", "published_at", "parent",
}
_AUTHOR_SOURCE_FIELDS = _SOURCE_FIELDS | {"author_updates", "source_read_scope"}
_PARENT_FIELDS = {
    "external_comment_id", "body", "author_public_id", "published_at", "public_url",
}
_OBSERVATION_FIELDS = {"id", "observed_at", "received_at"}
_ASSESSMENT_FIELDS = {
    "id", "assessed_at", "profile_version_id", "profile_version",
    "strategy_version_id", "provider", "model", "rule_version", "rule_sha256",
    "citations", "omitted_profile_citations",
}
_VERIFICATION_FIELDS = {
    "method", "status_at_capture", "checked_at", "opening_method", "contact_method",
}
_HUMAN_VERIFICATION_FIELDS = _VERIFICATION_FIELDS | {'demandEvidence','demandEvidenceId','checkedBy'}


class OpportunityEvidenceError(ValueError):
    """A fixed public error code; never retains private payload text."""

    def __init__(self, code: str):
        self.code = code if code in {"invalid_opportunity_evidence", "corrupt_opportunity_evidence"} else "corrupt_opportunity_evidence"
        super().__init__(self.code)


def _primitive(value):
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if type(value) is dict:
        return {key: _primitive(item) for key, item in value.items()}
    if type(value) is list:
        return [_primitive(item) for item in value]
    if value is None or type(value) in (str, int, float, bool):
        return value
    raise TypeError("non-primitive evidence value")


def canonical_json(value) -> str:
    return json.dumps(
        _primitive(value), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    )


def evidence_digest(payload) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _mapping(value):
    if type(value) is not dict:
        raise ValueError
    return value


def _text(value, *, nullable=False):
    if value is None and nullable:
        return None
    if type(value) is not str or not value:
        raise ValueError
    value.encode("utf-8")
    return value


def _author_update_text(value):
    value = _text(value)
    if len(value) > 20000 or not value.strip():
        raise ValueError
    if any((ord(char) < 32 and char not in "\t\n\r") or 127 <= ord(char) <= 159 for char in value):
        raise ValueError
    return value


def _timestamp(value, *, nullable=False):
    if value is None and nullable:
        return None
    value = _primitive(value)
    value = _text(value)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError
    return value


def _bound(value, expected):
    if _primitive(value) != _primitive(expected):
        raise ValueError


def _public_source(raw):
    content = _mapping(raw["content"])
    kind = _text(raw["kind"])
    if kind not in {"POST", "COMMENT", "PAGE"}:
        raise ValueError
    external_comment_id = _text(raw.get("external_comment_id"), nullable=True)
    parent = content.get("parent")
    if (kind == "COMMENT") != (external_comment_id is not None):
        raise ValueError
    if kind != "COMMENT" and parent is not None:
        raise ValueError
    public_parent = None
    if parent is not None:
        parent = _mapping(parent)
        public_parent = {
            "external_comment_id": _text(parent["external_comment_id"]),
            "body": _text(parent.get("body"), nullable=True),
            "author_public_id": _text(parent.get("author_public_id"), nullable=True),
            "published_at": _timestamp(parent.get("published_at"), nullable=True),
            "public_url": _text(parent.get("public_url"), nullable=True),
        }
    title = _text(content.get("title"), nullable=True)
    body = _text(content["body"])
    result = {
        "platform": _text(raw["platform"]),
        "kind": kind,
        "external_source_id": _text(raw.get("external_source_id"), nullable=True),
        "external_comment_id": external_comment_id,
        "public_url": _text(content["public_url"]),
        "version_id": _text(_primitive(raw["version_id"])),
        "content_sha256": _text(raw["content_version"]),
        "title": None if kind == "COMMENT" else title,
        "container_title": title if kind == "COMMENT" else None,
        "body": body,
        "author_public_id": _text(content.get("author_public_id"), nullable=True),
        "published_at": _timestamp(content.get("published_at"), nullable=True),
        "parent": public_parent,
    }
    context = content.get("source_context")
    if context is not None:
        context = _mapping(context)
        replies = context["author_replies"]
        if type(replies) is not list:
            raise ValueError
        result["author_updates"] = [_text(_mapping(item)["body"]) for item in replies]
        result["source_read_scope"] = ("AUTHOR_REPLIES_COUNT_MATCHED_SUPPLEMENTS_UNREAD"
            if context["replies_complete"] is True else "AUTHOR_REPLIES_PARTIAL_SUPPLEMENTS_UNREAD")
    return result


def _citation_text(source, field):
    if field == "source.parent.body":
        parent = source["parent"]
        return None if parent is None else parent["body"]
    match = re.fullmatch(r"source\.author_updates\.([0-9]|[1-9][0-9])", field)
    if match:
        updates = source.get("author_updates", [])
        index = int(match.group(1))
        return updates[index] if index < len(updates) else None
    return source[field.removeprefix("source.")]


def _public_assessment(assessment, source):
    citations = []
    omitted = 0
    for dimension in _DIMENSIONS:
        block = _mapping(assessment[dimension])
        items = block["citations"]
        if type(items) is not list:
            raise ValueError
        for citation in items:
            citation = _mapping(citation)
            if set(citation) != {"field", "quote"}:
                raise ValueError
            field, quote = citation["field"], _text(citation["quote"])
            if field == "profile.description":
                omitted += 1
                continue
            public_field = (_CITATION_FIELDS.get(field) or
                ("source." + field if re.fullmatch(r"author_updates\.(?:[0-9]|[1-9][0-9])", field) else None))
            if public_field is None:
                raise ValueError
            addressed = _citation_text(source, public_field)
            if type(addressed) is not str or quote not in addressed:
                raise ValueError
            citations.append({"dimension": dimension, "field": public_field, "quote": quote})
    profile_version = assessment["profileVersion"]
    if type(profile_version) is not int or isinstance(profile_version, bool):
        raise ValueError
    rule_sha256 = _text(assessment["rule_sha256"])
    if not _DIGEST.fullmatch(rule_sha256):
        raise ValueError
    return {
        "id": _text(_primitive(assessment["id"])),
        "assessed_at": _timestamp(assessment["assessedAt"]),
        "profile_version_id": _text(assessment["profileId"]),
        "profile_version": profile_version,
        "strategy_version_id": _text(assessment["strategyVersionId"]),
        "provider": _text(assessment["provider"]),
        "model": _text(assessment["model"]),
        "rule_version": _text(assessment["rule_version"]),
        "rule_sha256": rule_sha256,
        "citations": citations,
        "omitted_profile_citations": omitted,
    }


def build_evidence(*, opportunity_id, snapshot, assessment, observation, verification, captured_at) -> dict:
    """Build one allowlisted inclusion snapshot without I/O or input mutation."""
    try:
        snapshot = _mapping(snapshot)
        binding = _mapping(snapshot["binding"])
        raw = _mapping(snapshot["raw"])
        assessment = _mapping(assessment)
        observation = _mapping(observation)
        verification = _mapping(verification)
        opportunity_id = _text(_primitive(opportunity_id))

        for actual, expected in (
            (raw["candidate_id"], binding["candidateId"]),
            (raw["version_id"], binding["sourceVersionId"]),
            (raw["profile_version_id"], binding["profileId"]),
            (raw["revision"], binding["candidateRevision"]),
            (assessment["candidateId"], binding["candidateId"]),
            (assessment["candidateRevision"], binding["candidateRevision"]),
            (assessment["sourceVersionId"], binding["sourceVersionId"]),
            (assessment["profileId"], binding["profileId"]),
            (assessment["profileVersion"], binding["profileVersion"]),
            (assessment["strategyVersionId"], raw["strategy_version_id"]),
            (observation["observation_id"], raw["current_observation_id"]),
            (observation["candidate_id"], binding["candidateId"]),
            (observation["version_id"], binding["sourceVersionId"]),
        ):
            _bound(actual, expected)
        if _primitive(verification["binding"]) != _primitive(binding):
            raise ValueError
        digest = _text(raw["content_version"])
        if not _DIGEST.fullmatch(digest) or evidence_digest(raw["content"]) != digest:
            raise ValueError

        source = _public_source(raw)
        demand = verification.get('demandEvidence')
        if demand is not None:
            DemandEvidence.model_validate(demand)
            _bound(assessment.get('demandEvidenceId'),verification['id'])
            source['author_updates'] = [demand['demandExcerpt']]
            source['source_read_scope'] = 'HUMAN_CONFIRMED_EXCERPT'
        public_assessment = _public_assessment(assessment, source)
        if verification["method"] != "HUMAN_REOPENED" or verification["status"] != "OPEN":
            raise ValueError
        result = {
            "schema_version": SCHEMA_VERSION,
            "opportunity_id": opportunity_id,
            "captured_at": _timestamp(captured_at),
            "source": source,
            "observation": {
                "id": _text(_primitive(observation["observation_id"])),
                "observed_at": _timestamp(observation["observed_at"]),
                "received_at": _timestamp(observation["received_at"]),
            },
            "assessment": public_assessment,
            "verification": {
                "method": "HUMAN_REOPENED",
                "status_at_capture": "OPEN",
                "checked_at": _timestamp(verification["checkedAt"]),
                "opening_method": _text(verification["openingMethod"]),
                "contact_method": _text(verification["contactMethod"]),
            },
        }
        if demand is not None:
            result['verification'].update(demandEvidence=demand,
                demandEvidenceId=_text(verification['id']), checkedBy=_text(verification['checkedBy']))
        return result
    except (KeyError, ValueError, TypeError, UnicodeError, RecursionError):
        pass
    raise OpportunityEvidenceError("invalid_opportunity_evidence") from None


def _validate_public_payload(payload, *, opportunity_id, profile_version_id):
    if type(payload) is not dict or set(payload) != _TOP_LEVEL:
        raise ValueError
    if payload["schema_version"] != SCHEMA_VERSION:
        raise ValueError
    _bound(payload["opportunity_id"], opportunity_id)
    _timestamp(payload["captured_at"])
    source = _mapping(payload["source"])
    observation = _mapping(payload["observation"])
    assessment = _mapping(payload["assessment"])
    verification = _mapping(payload["verification"])
    if set(source) not in (_SOURCE_FIELDS, _AUTHOR_SOURCE_FIELDS) or set(observation) != _OBSERVATION_FIELDS:
        raise ValueError
    if set(assessment) != _ASSESSMENT_FIELDS or set(verification) not in (_VERIFICATION_FIELDS,_HUMAN_VERIFICATION_FIELDS):
        raise ValueError
    if source["kind"] not in {"POST", "COMMENT", "PAGE"}:
        raise ValueError
    if source["platform"] not in {"XIAOHONGSHU", "DOUYIN", "BILIBILI", "ZHIHU", "PUBLIC_WEB"}:
        raise ValueError
    for key in ("platform", "kind", "public_url", "version_id", "body"):
        _text(source[key])
    for key in ("external_source_id", "external_comment_id", "title", "container_title", "author_public_id"):
        _text(source[key], nullable=True)
    _timestamp(source["published_at"], nullable=True)
    human = 'demandEvidence' in verification
    if human:
        demand = DemandEvidence.model_validate(verification['demandEvidence']).model_dump()
        _text(verification['demandEvidenceId'])
        _text(verification['checkedBy'])
        if (source['kind'] != 'PAGE' or source.get('source_read_scope') != 'HUMAN_CONFIRMED_EXCERPT'
                or source.get('author_updates') != [demand['demandExcerpt']]
                or any(not any(demand[key] in text for text in (source['body'], source['title'] or ''))
                    for key in ('authorExcerpt','demandExcerpt','dateExcerpt'))):
            raise ValueError
    if "author_updates" in source:
        if (source["platform"] != "PUBLIC_WEB" or source["kind"] != "PAGE"
                or (not human and (source["external_source_id"] is None or source["author_public_id"] is None))
                or type(source["author_updates"]) is not list or len(source["author_updates"]) > 100
                or source["source_read_scope"] not in {
                    "AUTHOR_REPLIES_COUNT_MATCHED_SUPPLEMENTS_UNREAD",
                    "AUTHOR_REPLIES_PARTIAL_SUPPLEMENTS_UNREAD", *(['HUMAN_CONFIRMED_EXCERPT'] if human else [])}):
            raise ValueError
        updates = [_author_update_text(update) for update in source["author_updates"]]
        if sum(len(update) for update in updates) > 20000:
            raise ValueError
    if not _DIGEST.fullmatch(_text(source["content_sha256"])):
        raise ValueError
    parent = source["parent"]
    if parent is not None and (type(parent) is not dict or set(parent) != _PARENT_FIELDS):
        raise ValueError
    if parent is not None:
        _text(parent["external_comment_id"])
        for key in ("body", "author_public_id", "public_url"):
            _text(parent[key], nullable=True)
        _timestamp(parent["published_at"], nullable=True)
    if (source["kind"] == "COMMENT") != (source["external_comment_id"] is not None):
        raise ValueError
    if source["kind"] == "COMMENT":
        if source["title"] is not None:
            raise ValueError
    elif source["container_title"] is not None or parent is not None:
        raise ValueError
    _text(observation["id"])
    _timestamp(observation["observed_at"])
    _timestamp(observation["received_at"])
    _bound(assessment["profile_version_id"], profile_version_id)
    for key in ("id", "profile_version_id", "strategy_version_id", "provider", "model", "rule_version"):
        _text(assessment[key])
    _timestamp(assessment["assessed_at"])
    if type(assessment["profile_version"]) is not int or isinstance(assessment["profile_version"], bool) or assessment["profile_version"] < 1:
        raise ValueError
    if not _DIGEST.fullmatch(_text(assessment["rule_sha256"])):
        raise ValueError
    if (type(assessment["omitted_profile_citations"]) is not int
            or isinstance(assessment["omitted_profile_citations"], bool)
            or assessment["omitted_profile_citations"] < 0):
        raise ValueError
    if type(assessment["citations"]) is not list:
        raise ValueError
    for citation in assessment["citations"]:
        if type(citation) is not dict or set(citation) != {"dimension", "field", "quote"}:
            raise ValueError
        if (citation["dimension"] not in _DIMENSIONS
                or (citation["field"] not in _CITATION_FIELDS.values()
                    and not re.fullmatch(r"source\.author_updates\.(?:[0-9]|[1-9][0-9])", citation["field"]))):
            raise ValueError
        quote = _text(citation["quote"])
        addressed = _citation_text(source, citation["field"])
        if type(addressed) is not str or quote not in addressed:
            raise ValueError
    if verification["method"] != "HUMAN_REOPENED" or verification["status_at_capture"] != "OPEN":
        raise ValueError
    _timestamp(verification["checked_at"])
    if verification["opening_method"] not in {"DIRECT", "IN_PLATFORM"}:
        raise ValueError
    if verification["contact_method"] not in {"COMMENT", "DM", "PUBLIC_CONTACT"}:
        raise ValueError


def evidence_view(payload, digest, *, opportunity_id, profile_version_id) -> dict:
    """Return a fresh verified public view, or explicit legacy unavailability."""
    if payload is None and digest is None:
        return {"status": "UNAVAILABLE", "reason": "NOT_CAPTURED"}
    try:
        payload = _primitive(payload)
        if not _DIGEST.fullmatch(_text(digest)) or evidence_digest(payload) != digest:
            raise ValueError
        _validate_public_payload(
            payload, opportunity_id=opportunity_id,
            profile_version_id=profile_version_id,
        )
        return {"status": "CAPTURED", "snapshot_sha256": digest, "snapshot": payload}
    except (KeyError, ValueError, TypeError, UnicodeError, RecursionError):
        pass
    raise OpportunityEvidenceError("corrupt_opportunity_evidence") from None
