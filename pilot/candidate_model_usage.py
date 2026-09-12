"""Append-only ordinary ASSESS provider usage; no pricing or client writes."""
from __future__ import annotations

from dataclasses import dataclass
import re

import psycopg

from pilot.candidate_ingestion import _id, _json, _row
from pilot.candidate_review_contract import CandidateReviewError


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_OUTCOMES = {"SUCCEEDED", "FAILED", "UNKNOWN"}


def validated_usage(value):
    names = ("prompt_tokens", "completion_tokens", "total_tokens")
    if (type(value) is not dict or set(value) != set(names)
            or any(type(value.get(name)) is not int or not 0 <= value[name] < 2**31
                for name in names)
            or value["prompt_tokens"] + value["completion_tokens"] != value["total_tokens"]):
        return None
    return {name: value[name] for name in names}


@dataclass(frozen=True)
class CandidateModelUsageScope:
    tenant_id: str
    owner_user_id: str
    request_id: str
    snapshot_key: str


class CandidateModelUsageConflict(RuntimeError):
    pass


class CandidateModelUsageStore:
    def __init__(self, database):
        self.database = database

    @staticmethod
    def _event(cursor, scope, phase, *, outcome=None, usage=None):
        cursor.execute("""INSERT INTO pilot_candidate_model_usage_events(
            tenant_id,owner_user_id,request_id,snapshot_key,phase,outcome,usage)
            VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT(tenant_id,owner_user_id,request_id,phase) DO NOTHING
            RETURNING *""", (scope.tenant_id, scope.owner_user_id, scope.request_id,
                scope.snapshot_key, phase, outcome, None if usage is None else _json(usage)))
        row = _row(cursor)
        if row is None:
            cursor.execute("""SELECT * FROM pilot_candidate_model_usage_events
                WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s AND phase=%s""",
                (scope.tenant_id, scope.owner_user_id, scope.request_id, phase))
            row = _row(cursor)
        if (row is None or row["snapshot_key"] != scope.snapshot_key
                or row["outcome"] != outcome or row["usage"] != usage):
            raise CandidateModelUsageConflict("candidate model usage event conflict")
        return row

    def dispatch(self, cursor, *, tenant_id, owner_user_id, request_id, snapshot_key):
        if (any(type(value) is not str or not value for value in
                (tenant_id, owner_user_id, request_id, snapshot_key))
                or not _SHA256.fullmatch(snapshot_key)):
            raise CandidateReviewError("assessment_unavailable", 503)
        scope = CandidateModelUsageScope(tenant_id, owner_user_id, request_id, snapshot_key)
        try:
            self._event(cursor, scope, "DISPATCH")
            return scope
        except (psycopg.Error, CandidateModelUsageConflict):
            raise CandidateReviewError("assessment_unavailable", 503) from None

    def finish(self, scope, *, outcome, usage):
        if type(scope) is not CandidateModelUsageScope or outcome not in _OUTCOMES:
            raise CandidateReviewError("assessment_outcome_unknown", 503)
        usage = validated_usage(usage)
        try:
            with self.database.connect() as connection, connection.cursor() as cursor:
                cursor.execute("SELECT set_config('yike.user_id',%s,true)", (scope.owner_user_id,))
                cursor.execute("SELECT set_config('yike.tenant_id',%s,true)", (scope.tenant_id,))
                return self._event(cursor, scope, "FINISH", outcome=outcome, usage=usage)
        except (psycopg.Error, CandidateModelUsageConflict):
            raise CandidateReviewError("assessment_outcome_unknown", 503) from None

    def get(self, cursor, *, tenant_id, owner_user_id, request_id):
        cursor.execute("""SELECT * FROM pilot_candidate_review_requests
            WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s""",
            (tenant_id, owner_user_id, request_id))
        requested = _row(cursor)
        if requested is None:
            raise CandidateReviewError("request_not_found", 404)
        invocation_id = requested["invocation_id"] or requested["request_id"]
        cursor.execute("""SELECT * FROM pilot_candidate_review_requests
            WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s""",
            (tenant_id, owner_user_id, invocation_id))
        invocation = _row(cursor)
        if invocation is None:
            raise CandidateReviewError("request_not_found", 404)
        cursor.execute("""SELECT phase,outcome,usage,recorded_at
            FROM pilot_candidate_model_usage_events
            WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s
            ORDER BY phase""", (tenant_id, owner_user_id, invocation_id))
        events = {row[0]: row for row in cursor.fetchall()}
        finish = events.get("FINISH")
        if finish is not None:
            usage = validated_usage(finish[2])
            state = "REPORTED" if usage is not None else "UNKNOWN"
            outcome, recorded_at = finish[1], finish[3].isoformat()
        elif "DISPATCH" in events:
            cursor.execute("SELECT clock_timestamp()")
            state = "PENDING" if cursor.fetchone()[0] < invocation["deadline_at"] else "UNKNOWN"
            usage = outcome = recorded_at = None
        else:
            state = "NOT_RECORDED"
            usage = outcome = recorded_at = None
        return {
            "schema_version": "candidate-model-usage-v1",
            "requestId": requested["request_id"],
            "invocationRequestId": invocation["request_id"],
            "candidateId": str(invocation["candidate_id"]),
            "state": state,
            "usage": usage,
            "outcome": outcome,
            "recordedAt": recorded_at,
        }
