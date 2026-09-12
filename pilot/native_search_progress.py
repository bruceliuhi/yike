"""Protocol and persistence helpers for committed native Bilibili search progress."""
from __future__ import annotations

import re
import unicodedata
import hashlib
import json
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError, field_validator, model_validator

from pilot.native_search_cursor import advance_cursor, checked_cursor
from pilot.execution_contract import ExecutionRuntimeError


SCHEMA_VERSION = "native-search-progress-v1"
ADAPTER_VERSION = "bili-search-items-v1"
_OPAQUE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", re.ASCII)


def _query(value: str) -> str:
    if (type(value) is not str or not 1 <= len(value) <= 80 or not value.strip()
            or value != value.strip() or "," in value):
        raise ValueError("invalid native search query")
    if any(unicodedata.category(char) in {"Cc", "Cf", "Cs", "Zl", "Zp"} for char in value):
        raise ValueError("invalid native search query")
    value.encode("utf-8")
    return value


def _opaque(value: str) -> str:
    if type(value) is not str or _OPAQUE.fullmatch(value) is None:
        raise ValueError("invalid native search identifier")
    return value


def _uuid(value: str) -> str:
    try:
        if type(value) is not str or str(UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ValueError("invalid native search UUID") from None
    return value


class _Frozen(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid",
                              hide_input_in_errors=True, revalidate_instances="always")


class NativeSearchClaimQuery(_Frozen):
    query: str
    revision: StrictInt = Field(ge=0, le=2_147_483_647)
    base_batch_request_id: str | None
    cursor: dict

    _query_text = field_validator("query")(_query)

    @field_validator("base_batch_request_id")
    @classmethod
    def base_id(cls, value):
        return None if value is None else _opaque(value)

    @field_validator("cursor")
    @classmethod
    def cursor_shape(cls, value):
        return checked_cursor(value)

    @model_validator(mode="after")
    def revision_base(self):
        if (self.revision == 0) != (self.base_batch_request_id is None):
            raise ValueError("invalid native search head")
        return self


class NativeSearchClaimProgress(_Frozen):
    schema_version: Literal["native-search-progress-v1"]
    adapter_version: Literal["bili-search-items-v1"]
    plan_id: str
    queries: tuple[NativeSearchClaimQuery, ...] = Field(min_length=1, max_length=20)

    _plan_id = field_validator("plan_id")(_uuid)

    @field_validator("queries", mode="before")
    @classmethod
    def freeze_queries(cls, value):
        return tuple(value) if type(value) is list else value

    @model_validator(mode="after")
    def distinct_queries(self):
        if len({item.query for item in self.queries}) != len(self.queries):
            raise ValueError("duplicate native search query")
        return self


class NativeSearchBatchQuery(_Frozen):
    query: str
    revision: StrictInt = Field(ge=0, le=2_147_483_647)
    base_batch_request_id: str | None
    before: dict
    after: dict
    page_ids: tuple[str, ...] = Field(max_length=20)
    processed_ids: tuple[str, ...] = Field(max_length=5)
    has_more: bool
    comments_scope: Literal["BOUNDED_SAMPLE"]

    _query_text = field_validator("query")(_query)

    @field_validator("base_batch_request_id")
    @classmethod
    def base_id(cls, value):
        return None if value is None else _opaque(value)

    @field_validator("before", "after")
    @classmethod
    def cursor_shape(cls, value):
        return checked_cursor(value)

    @field_validator("page_ids", "processed_ids", mode="before")
    @classmethod
    def freeze_ids(cls, value):
        return tuple(value) if type(value) is list else value

    @model_validator(mode="after")
    def consistent_delta(self):
        if (self.revision == 0) != (self.base_batch_request_id is None):
            raise ValueError("invalid native search head")
        expected = advance_cursor(
            self.before, list(self.page_ids), list(self.processed_ids), self.has_more
        )
        if self.after != expected:
            raise ValueError("invalid native search cursor advancement")
        return self


class NativeSearchBatchProgress(_Frozen):
    schema_version: Literal["native-search-progress-v1"]
    adapter_version: Literal["bili-search-items-v1"]
    claim_request_id: str
    queries: tuple[NativeSearchBatchQuery, ...] = Field(min_length=1, max_length=20)

    _claim_id = field_validator("claim_request_id")(_uuid)

    @field_validator("queries", mode="before")
    @classmethod
    def freeze_queries(cls, value):
        return tuple(value) if type(value) is list else value

    @model_validator(mode="after")
    def distinct_queries(self):
        if len({item.query for item in self.queries}) != len(self.queries):
            raise ValueError("duplicate native search query")
        return self


def validate_native_batch_progress(value) -> NativeSearchBatchProgress:
    try:
        return NativeSearchBatchProgress.model_validate(value)
    except (ValidationError, ValueError, TypeError, UnicodeError, RecursionError):
        raise ValueError("invalid native search progress") from None


def native_search_progress_supported(capability_check) -> bool:
    from pilot.foreground_collection import (
        four_platform_monitor_policy,
        four_platform_public_bili_links_monitor_policy,
        four_platform_public_monitor_policy,
        four_platform_public_node_monitor_policy,
        four_platform_public_project_monitor_policy,
        four_platform_public_sampling_monitor_policy,
        three_platform_monitor_policy,
    )
    return capability_check in (
        three_platform_monitor_policy,
        four_platform_monitor_policy,
        four_platform_public_bili_links_monitor_policy,
        four_platform_public_monitor_policy,
        four_platform_public_sampling_monitor_policy,
        four_platform_public_node_monitor_policy,
        four_platform_public_project_monitor_policy,
    )


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _row(cursor):
    value = cursor.fetchone()
    return dict(zip((column.name for column in cursor.description), value)) if value else None


def _queries(configuration) -> list[str]:
    if (type(configuration) is not dict or configuration.get("source") != "search"
            or configuration.get("mode") != "monitor" or configuration.get("links") != []
            or configuration.get("research") is not None):
        raise ExecutionRuntimeError("capability_unavailable", 409)
    schedule = configuration.get("schedule")
    if type(schedule) is not dict or schedule.get("policyVersion") != 1:
        raise ExecutionRuntimeError("capability_unavailable", 409)
    values = configuration.get("keywords")
    platform_queries = configuration.get("platformQueries")
    if platform_queries is not None:
        if (type(platform_queries) is not dict
                or platform_queries.get("version") != "platform-queries-v1"
                or type(platform_queries.get("items")) is not list):
            raise ExecutionRuntimeError("capability_unavailable", 409)
        matched = [item for item in platform_queries["items"]
                   if type(item) is dict and item.get("platform") == "BILIBILI"]
        if len(matched) > 1:
            raise ExecutionRuntimeError("capability_unavailable", 409)
        if matched:
            values = matched[0].get("keywords")
    try:
        if type(values) is not list or not 1 <= len(values) <= 20:
            raise ValueError
        result = [_query(item) for item in values]
        if len(set(result)) != len(result):
            raise ValueError
        return result
    except (ValueError, TypeError, UnicodeError):
        raise ExecutionRuntimeError("capability_unavailable", 409) from None


def _authority(cursor, *, tenant_id, owner_user_id, task_id, platform_run_id,
               capability_check):
    if not native_search_progress_supported(capability_check):
        raise ExecutionRuntimeError("capability_unavailable", 409)
    cursor.execute(
        """
        SELECT o.plan_id,t.profile_version_id,t.strategy_version_id,p.platform,
               p.access_mode,p.connection_id,p.connection_version,t.configuration_snapshot,
               t.max_records
          FROM pilot_collection_tasks t
          JOIN pilot_collection_runs r
            ON r.tenant_id=t.tenant_id AND r.owner_user_id=t.owner_user_id
           AND r.task_id=t.task_id
          JOIN pilot_collection_platform_runs p
            ON p.tenant_id=r.tenant_id AND p.owner_user_id=r.owner_user_id
           AND p.task_id=r.task_id AND p.run_id=r.run_id
          JOIN pilot_monitor_occurrences o
            ON o.tenant_id=r.tenant_id AND o.owner_user_id=r.owner_user_id
           AND o.task_id=r.task_id AND o.run_id=r.run_id AND o.status='STARTED'
          JOIN pilot_monitor_plans plan
            ON plan.tenant_id=o.tenant_id AND plan.owner_user_id=o.owner_user_id
           AND plan.plan_id=o.plan_id AND plan.revision=o.plan_revision AND plan.state='ACTIVE'
           AND plan.profile_version_id=t.profile_version_id
           AND plan.strategy_version_id=t.strategy_version_id
           AND plan.configuration_sha256=t.configuration_sha256
         WHERE t.tenant_id=%s AND t.owner_user_id=%s AND t.task_id=%s
           AND p.platform_run_id=%s
        """,
        (tenant_id, owner_user_id, task_id, platform_run_id),
    )
    authority = _row(cursor)
    if (authority is None or authority["platform"] != "BILIBILI"
            or authority["access_mode"] != "PLATFORM_ACCOUNT"
            or authority["connection_id"] is None or authority["connection_version"] is None):
        raise ExecutionRuntimeError("capability_unavailable", 409)
    snapshot = authority["configuration_snapshot"]
    configuration = snapshot.get("configuration") if type(snapshot) is dict else None
    if capability_check("BILIBILI", "PLATFORM_ACCOUNT", configuration) is not True:
        raise ExecutionRuntimeError("capability_unavailable", 409)
    authority["configuration"] = configuration
    authority["queries"] = _queries(configuration)
    authority["plan_id"] = _uuid(authority["plan_id"])
    return authority


def _scope_parameters(authority, tenant_id, owner_user_id, query):
    return (
        tenant_id, owner_user_id, authority["plan_id"], authority["profile_version_id"],
        authority["strategy_version_id"], authority["platform"], authority["connection_id"],
        authority["connection_version"], ADAPTER_VERSION, query,
    )


def claim_native_search_progress(cursor, *, tenant_id, owner_user_id, task, platform,
                                 capability_check) -> dict:
    authority = _authority(
        cursor, tenant_id=tenant_id, owner_user_id=owner_user_id,
        task_id=task["task_id"], platform_run_id=platform["platform_run_id"],
        capability_check=capability_check,
    )
    queries = []
    for query in authority["queries"]:
        cursor.execute(
            """
            SELECT cursor,revision,head_batch_request_id
              FROM pilot_native_search_progress
             WHERE tenant_id=%s AND owner_user_id=%s AND plan_id=%s
               AND profile_version_id=%s AND strategy_version_id=%s AND platform=%s
               AND connection_id=%s AND connection_version=%s AND adapter_version=%s AND query=%s
            """,
            _scope_parameters(authority, tenant_id, owner_user_id, query),
        )
        head = cursor.fetchone()
        if head is None:
            queries.append({
                "query": query, "revision": 0, "base_batch_request_id": None,
                "cursor": {"page": 1, "consumed_ids": [], "refresh_next": False},
            })
        else:
            queries.append({
                "query": query, "revision": head[1], "base_batch_request_id": head[2],
                "cursor": checked_cursor(head[0]),
            })
    return NativeSearchClaimProgress.model_validate({
        "schema_version": SCHEMA_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "plan_id": authority["plan_id"],
        "queries": queries,
    }).model_dump(mode="json")


def commit_native_search_progress(cursor, *, tenant_id, owner_user_id, batch,
                                  capability_check) -> dict | None:
    progress = batch.native_progress
    if progress is None:
        return None
    progress = validate_native_batch_progress(progress)
    execution = batch.execution
    authority = _authority(
        cursor, tenant_id=tenant_id, owner_user_id=owner_user_id,
        task_id=execution.task_id, platform_run_id=execution.platform_run_id,
        capability_check=capability_check,
    )
    cursor.execute(
        "SELECT operation,receipt FROM pilot_execution_operations "
        "WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s",
        (tenant_id, owner_user_id, progress.claim_request_id),
    )
    claim_row = cursor.fetchone()
    if claim_row is None or claim_row[0] != "CLAIM" or type(claim_row[1]) is not dict:
        raise ExecutionRuntimeError("native_progress_conflict", 409)
    claim_receipt = claim_row[1]
    try:
        claim = NativeSearchClaimProgress.model_validate(claim_receipt.get("native_progress"))
    except (ValidationError, ValueError, TypeError, UnicodeError, RecursionError):
        raise ExecutionRuntimeError("native_progress_conflict", 409) from None
    if (claim.plan_id != authority["plan_id"] or claim.schema_version != progress.schema_version
            or claim.adapter_version != progress.adapter_version
            or [item.query for item in claim.queries] != authority["queries"]):
        raise ExecutionRuntimeError("native_progress_conflict", 409)
    receipt_binding = (
        claim_receipt.get("task_id"), claim_receipt.get("run_id"),
        claim_receipt.get("platform_run_id"), claim_receipt.get("lease_id"),
        claim_receipt.get("execution_generation"),
    )
    if receipt_binding != (
        execution.task_id, execution.run_id, execution.platform_run_id,
        execution.lease_id, execution.execution_generation,
    ):
        raise ExecutionRuntimeError("native_progress_conflict", 409)

    claimed = {item.query: item for item in claim.queries}
    submitted_queries = [item.query for item in progress.queries]
    if submitted_queries != authority["queries"][:len(submitted_queries)]:
        raise ExecutionRuntimeError("native_progress_conflict", 409)
    if any(len(item.processed_ids) > min(5, authority["max_records"])
           for item in progress.queries):
        raise ExecutionRuntimeError("native_progress_conflict", 409)
    for item in sorted(progress.queries, key=lambda value: value.query):
        frozen = claimed.get(item.query)
        if (frozen is None or item.revision != frozen.revision
                or item.base_batch_request_id != frozen.base_batch_request_id
                or _json(item.before) != _json(frozen.cursor)):
            raise ExecutionRuntimeError("native_progress_conflict", 409)
        scope = _scope_parameters(authority, tenant_id, owner_user_id, item.query)
        lock = int.from_bytes(hashlib.sha256(_json(scope).encode()).digest()[:4], "big", signed=True)
        cursor.execute("SELECT pg_advisory_xact_lock(14001,%s)", (lock,))
        cursor.execute(
            """
            SELECT cursor,revision,head_batch_request_id
              FROM pilot_native_search_progress
             WHERE tenant_id=%s AND owner_user_id=%s AND plan_id=%s
               AND profile_version_id=%s AND strategy_version_id=%s AND platform=%s
               AND connection_id=%s AND connection_version=%s AND adapter_version=%s AND query=%s
             FOR UPDATE
            """,
            scope,
        )
        head = cursor.fetchone()
        current_cursor = ({"page": 1, "consumed_ids": [], "refresh_next": False}
                          if head is None else checked_cursor(head[0]))
        current_revision = 0 if head is None else head[1]
        current_batch = None if head is None else head[2]
        if (item.revision, item.base_batch_request_id, _json(item.before)) != (
                current_revision, current_batch, _json(current_cursor)):
            raise ExecutionRuntimeError("native_progress_conflict", 409)
        if current_revision >= 2_147_483_647:
            raise ExecutionRuntimeError("native_progress_exhausted", 409)
        if head is None:
            cursor.execute(
                """
                INSERT INTO pilot_native_search_progress(
                    tenant_id,owner_user_id,plan_id,profile_version_id,strategy_version_id,
                    platform,connection_id,connection_version,adapter_version,query,
                    cursor,revision,head_batch_request_id
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,1,%s)
                """,
                (*scope, _json(item.after), batch.request_id),
            )
        else:
            cursor.execute(
                """
                UPDATE pilot_native_search_progress
                   SET cursor=%s::jsonb,revision=revision+1,head_batch_request_id=%s,
                       updated_at=clock_timestamp()
                 WHERE tenant_id=%s AND owner_user_id=%s AND plan_id=%s
                   AND profile_version_id=%s AND strategy_version_id=%s AND platform=%s
                   AND connection_id=%s AND connection_version=%s AND adapter_version=%s AND query=%s
                   AND revision=%s AND head_batch_request_id=%s AND cursor=%s::jsonb
                """,
                (_json(item.after), batch.request_id, *scope, current_revision,
                 current_batch, _json(current_cursor)),
            )
            if cursor.rowcount != 1:
                raise ExecutionRuntimeError("native_progress_conflict", 409)
    return progress.model_dump(mode="json")


__all__ = [
    "SCHEMA_VERSION", "ADAPTER_VERSION", "NativeSearchClaimProgress",
    "NativeSearchBatchProgress", "validate_native_batch_progress",
    "native_search_progress_supported", "claim_native_search_progress",
    "commit_native_search_progress",
]
