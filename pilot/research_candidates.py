"""Internal research results persisted as owner-private raw candidate evidence."""
from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import re

import psycopg
from pydantic import ValidationError

from pilot.candidate_contract import CandidateRecord
from pilot.candidate_ingestion import _persist_records
from pilot.execution_contract import ExecutionRuntimeError, canonical_uuid
from pilot.research_public_reader import (ENDPOINT as _ENDPOINT,
    _INPUT_SHA as _INPUT_SHA256, read_public_index)
from pilot.research_resources import _event


_SHA256 = re.compile(r"[0-9a-f]{64}")
_EVENT_KEYS = {"schema_version", "reservation_id", "task_id", "run_id", "action_id",
    "permit_id", "research_generation", "resource", "input_sha256", "status",
    "output_sha256", "issued_at", "deadline_at", "finished_at"}


def _json(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ExecutionRuntimeError("invalid_request", 422) from None


def _time(value):
    try:
        parsed = datetime.fromisoformat(value)
        if type(value) is not str or parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
        return parsed.astimezone(UTC)
    except (TypeError, ValueError, OverflowError):
        raise ExecutionRuntimeError("invalid_request", 422) from None


def _validated_event(value):
    if type(value) is not dict or set(value) != _EVENT_KEYS:
        raise ExecutionRuntimeError("invalid_request", 422)
    if value.get("schema_version") != "research-resource-v1" \
            or type(value.get("research_generation")) is not int \
            or value["research_generation"] != 1 \
            or value.get("resource") != "SOURCE_READ" \
            or value.get("input_sha256") != _INPUT_SHA256 \
            or value.get("status") not in ("ISSUED", "SUCCEEDED"):
        raise ExecutionRuntimeError("invalid_request", 422)
    for key in ("reservation_id", "task_id", "run_id", "action_id", "permit_id"):
        canonical_uuid(value.get(key))
    _time(value.get("issued_at")); _time(value.get("deadline_at"))
    if value["status"] == "ISSUED":
        if value.get("output_sha256") is not None or value.get("finished_at") is not None:
            raise ExecutionRuntimeError("invalid_request", 422)
    elif type(value.get("output_sha256")) is not str \
            or not _SHA256.fullmatch(value["output_sha256"]) or value.get("finished_at") is None:
        raise ExecutionRuntimeError("invalid_request", 422)
    if value.get("finished_at") is not None:
        _time(value["finished_at"])
    return value


def _records(result, output_sha256, event, *, now):
    if type(output_sha256) is not str or not _SHA256.fullmatch(output_sha256):
        raise ExecutionRuntimeError("invalid_request", 422)
    try:
        encoded = _json(result).encode("utf-8")
    except UnicodeEncodeError:
        raise ExecutionRuntimeError("invalid_request", 422) from None
    if len(encoded) > 1_048_576 or hashlib.sha256(encoded).hexdigest() != output_sha256:
        raise ExecutionRuntimeError("request_conflict", 409)
    if type(result) is not dict or set(result) != {
            "source_url", "sample_kind", "observed_at", "observed_count", "topics"}:
        raise ExecutionRuntimeError("invalid_request", 422)
    if result["source_url"] != _ENDPOINT or result["sample_kind"] != "LATEST_TOPIC_INDEX":
        raise ExecutionRuntimeError("invalid_request", 422)
    observed = _time(result["observed_at"])
    if not _time(event["issued_at"]) <= observed <= now.astimezone(UTC) \
            or observed >= _time(event["deadline_at"]):
        raise ExecutionRuntimeError("request_conflict", 409)
    topics = result["topics"]
    if type(topics) is not list or type(result["observed_count"]) is not int \
            or not 0 <= result["observed_count"] <= 100 \
            or result["observed_count"] != len(topics):
        raise ExecutionRuntimeError("invalid_request", 422)
    observed_text = observed.strftime("%Y-%m-%dT%H:%M:%SZ")
    valid, seen = [], set()
    for topic in topics:
        if type(topic) is not dict or set(topic) != {"id", "title", "content", "created", "url"}:
            raise ExecutionRuntimeError("invalid_request", 422)
        identity, created = topic["id"], topic["created"]
        if type(identity) is not int or type(created) is not int \
                or not 1 <= identity <= 9_007_199_254_740_991 or identity in seen \
                or not 0 < created <= observed.timestamp() \
                or topic["url"] != f"https://www.v2ex.com/t/{identity}" \
                or type(topic["title"]) is not str or type(topic["content"]) is not str:
            raise ExecutionRuntimeError("invalid_request", 422)
        seen.add(identity)
        try:
            valid.append(CandidateRecord.model_validate(dict(kind="PAGE",
                external_source_id=str(identity), external_comment_id=None,
                public_url=topic["url"], title=topic["title"], author_public_id=None,
                body=topic["content"],
                published_at=datetime.fromtimestamp(created, UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                observed_at=observed_text, parent=None, collector_version="v2ex-latest-v1",
                normalizer_version="research-v2ex-index-v1", query=None)))
        except (ValidationError, ValueError, OverflowError):
            # A source record is either preserved exactly or omitted. Never truncate it.
            continue
    return valid, observed


def _same_immutable_event(incoming, stored):
    keys = _EVENT_KEYS - {"status", "output_sha256", "finished_at"}
    return all(incoming[key] == stored[key] for key in keys)


class ResearchCandidateStore:
    def __init__(self, resources):
        self.resources = resources

    @property
    def runtime(self):
        return self.resources.runtime

    def commit_index(self, claims, *, event, result, output_sha256):
        event = _validated_event(event)
        try:
            with self.runtime.database.connect() as connection, connection.cursor() as cursor:
                tenant = self.runtime._active(cursor, claims)
                cursor.execute("SELECT clock_timestamp()")
                valid, _ = _records(result, output_sha256, event, now=cursor.fetchone()[0])
                task, run, platforms = self.runtime._locks(cursor, claims, tenant, event["task_id"])
                if run is None or run["run_id"] != event["run_id"] or len(platforms) != 1:
                    raise ExecutionRuntimeError("request_conflict", 409)
                platform = platforms[0]
                if (task["device_id"], task["profile_version_id"], run["device_id"],
                        run["profile_version_id"], platform["device_id"],
                        platform["profile_version_id"], platform["run_id"], platform["platform"],
                        platform["access_mode"], platform["connection_id"],
                        platform["connection_version"]) != (
                        task["device_id"], task["profile_version_id"], task["device_id"],
                        task["profile_version_id"], task["device_id"],
                        task["profile_version_id"], run["run_id"], "PUBLIC_WEB",
                        "PUBLIC_ANONYMOUS", None, None):
                    raise ExecutionRuntimeError("request_conflict", 409)
                credential = platform["credential_version"]
                if type(credential) is not int or not 1 <= credential <= 2_147_483_647:
                    raise ExecutionRuntimeError("request_conflict", 409)
                row = self.resources._select(cursor, tenant, claims.user_id, event["task_id"],
                    event["run_id"], event["action_id"], lock=True)
                if row is None:
                    raise ExecutionRuntimeError("request_not_found", 404)
                stored = _event(row)
                if not _same_immutable_event(event, stored):
                    raise ExecutionRuntimeError("request_conflict", 409)
                if event["status"] == "SUCCEEDED" and event != stored:
                    raise ExecutionRuntimeError("request_conflict", 409)

                cursor.execute("SELECT fingerprint,receipt,execution_context FROM pilot_candidate_batches "
                    "WHERE tenant_id=%s AND owner_user_id=%s AND platform_run_id=%s AND request_id=%s",
                    (tenant, claims.user_id, platform["platform_run_id"], event["action_id"]))
                previous = cursor.fetchone()
                if stored["status"] != "ISSUED":
                    previous_context = previous[2] if previous is not None else None
                    if stored["status"] == "SUCCEEDED" and stored["output_sha256"] == output_sha256 \
                            and previous is not None and type(previous_context) is dict \
                            and previous_context.get("output_sha256") == output_sha256 \
                            and previous_context.get("observed_count") == result["observed_count"] \
                            and previous[0] == hashlib.sha256(_json(previous_context).encode()).hexdigest():
                        self.runtime._active(cursor, claims)
                        return stored
                    raise ExecutionRuntimeError("request_conflict", 409)
                if event["status"] != "ISSUED" or previous is not None:
                    raise ExecutionRuntimeError("request_conflict", 409)

                remaining = max(0, task["max_records"] - sum(p["records_used"] for p in platforms))
                selected = valid[:remaining]
                context = dict(kind="research-resource-v1", device_id=task["device_id"],
                    task_id=task["task_id"], run_id=run["run_id"],
                    platform_run_id=platform["platform_run_id"], credential_version=credential,
                    access_mode="PUBLIC_ANONYMOUS", connection_id=None, connection_version=None,
                    reservation_id=stored["reservation_id"], action_id=stored["action_id"],
                    permit_id=stored["permit_id"], research_generation=1,
                    resource="SOURCE_READ", input_sha256=stored["input_sha256"],
                    output_sha256=output_sha256, observed_count=result["observed_count"],
                    accepted_count=len(selected), skipped_invalid_count=len(result["topics"])-len(valid),
                    skipped_budget_count=len(valid)-len(selected))
                fingerprint = hashlib.sha256(_json(context).encode()).hexdigest()
                cursor.execute("SELECT clock_timestamp()")
                received = cursor.fetchone()[0]
                items = _persist_records(cursor, tenant=tenant, user=claims.user_id,
                    platform="PUBLIC_WEB", profile_version_id=task["profile_version_id"],
                    strategy_version_id=task["strategy_version_id"],
                    platform_run_id=platform["platform_run_id"], request_id=event["action_id"],
                    records=enumerate(selected), received=received)
                receipt = dict(schema_version="candidate-receipt-v1", request_id=event["action_id"],
                    platform_run_id=platform["platform_run_id"], task_id=task["task_id"],
                    run_id=run["run_id"], accepted_count=len(selected),
                    received_at=received.isoformat(), items=items)
                cursor.execute("UPDATE pilot_collection_platform_runs SET records_used=records_used+%s "
                    "WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s AND run_id=%s AND platform_run_id=%s",
                    (len(selected), tenant, claims.user_id, task["task_id"], run["run_id"],
                     platform["platform_run_id"]))
                cursor.execute("INSERT INTO pilot_candidate_batches(tenant_id,owner_user_id,platform_run_id,"
                    "request_id,task_id,run_id,fingerprint,accepted_count,received_at,receipt,platform,"
                    "profile_version_id,strategy_version_id,execution_context) VALUES "
                    "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s::jsonb)",
                    (tenant, claims.user_id, platform["platform_run_id"], event["action_id"],
                     task["task_id"], run["run_id"], fingerprint, len(selected), received,
                     _json(receipt), "PUBLIC_WEB", task["profile_version_id"],
                     task["strategy_version_id"], _json(context)))
                cursor.execute("UPDATE pilot_research_resource_events SET status='SUCCEEDED',"
                    "output_sha256=%s,finished_at=clock_timestamp() WHERE tenant_id=%s AND owner_user_id=%s "
                    "AND task_id=%s AND run_id=%s AND action_id=%s RETURNING "
                    "reservation_id,task_id,run_id,action_id,permit_id,research_generation,resource,"
                    "input_sha256,status,output_sha256,issued_at,deadline_at,finished_at",
                    (output_sha256, tenant, claims.user_id, task["task_id"], run["run_id"], event["action_id"]))
                final = _event(cursor.fetchone())
                self.runtime._active(cursor, claims)
                return final
        except ExecutionRuntimeError:
            raise
        except psycopg.Error:
            raise ExecutionRuntimeError("resource_unavailable", 503) from None

    def get_receipt(self, claims, *, task_id, run_id, action_id):
        task_id, run_id, action_id = map(canonical_uuid, (task_id, run_id, action_id))
        try:
            with self.runtime.database.connect() as connection, connection.cursor() as cursor:
                tenant = self.runtime._active(cursor, claims)
                cursor.execute("SELECT b.receipt FROM pilot_candidate_batches b "
                    "JOIN pilot_research_resource_events e ON e.tenant_id=b.tenant_id "
                    "AND e.owner_user_id=b.owner_user_id AND e.task_id=b.task_id AND e.run_id=b.run_id "
                    "AND e.action_id=b.request_id WHERE b.tenant_id=%s AND b.owner_user_id=%s "
                    "AND b.task_id=%s AND b.run_id=%s AND b.request_id=%s "
                    "AND b.execution_context->>'kind'='research-resource-v1' AND e.status='SUCCEEDED'",
                    (tenant, claims.user_id, task_id, run_id, action_id))
                row = cursor.fetchone()
                self.runtime._active(cursor, claims)
                return row[0] if row else None
        except ExecutionRuntimeError:
            raise
        except psycopg.Error:
            raise ExecutionRuntimeError("resource_unavailable", 503) from None

    def read_public(self, claims, *, task_id, run_id, action_id, fetcher=None):
        result = read_public_index(self.resources, claims, task_id=task_id, run_id=run_id,
            action_id=action_id, fetcher=fetcher, on_success=lambda event, value, digest:
                self.commit_index(claims, event=event, result=value, output_sha256=digest))
        receipt = self.get_receipt(claims, task_id=task_id, run_id=run_id, action_id=action_id)
        if result["event"]["status"] == "SUCCEEDED" and receipt is None:
            raise ExecutionRuntimeError("resource_unavailable", 503)
        return {"event": result["event"], "receipt": receipt, "replayed": result["replayed"]}
