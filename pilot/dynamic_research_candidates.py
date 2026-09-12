"""Publish successful dynamic READ journal facts as original candidates."""
from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json

import psycopg
from pydantic import ValidationError

from pilot.candidate_contract import CandidateRecord
from pilot.candidate_ingestion import _persist_records
from pilot.execution_contract import ExecutionRuntimeError, canonical_uuid
from pilot.research_effect_contract import canonical_effect_sha256, effect_result
from pilot.research_resources import _event
from pilot.research_runtime_config import dynamic_research_snapshot
from pilot.research_page_selection import validate_page_selection


_SELECTION_OMITTED = object()


def _json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _record(entry):
    evidence = entry["result"]["evidence"]
    observed = datetime.fromisoformat(evidence["observed_at"]).astimezone(UTC)
    try:
        return CandidateRecord.model_validate({
            "kind": "PAGE",
            "external_source_id": hashlib.sha256(
                evidence["url"].encode("utf-8")
            ).hexdigest(),
            "external_comment_id": None,
            "public_url": evidence["url"],
            "title": evidence["title"],
            "author_public_id": None,
            "body": evidence["text"],
            "published_at": None,
            "observed_at": observed.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "parent": None,
            "collector_version": "public-web-agent-v1",
            "normalizer_version": "dynamic-public-read-v1",
            "query": None,
        })
    except (ValidationError, ValueError, UnicodeError, OverflowError):
        # A successful read remains in the durable journal. Candidate storage
        # never truncates an original to make it fit the narrower contract.
        return None


class DynamicResearchCandidateStore:
    def __init__(self, journal):
        self.journal = journal
        self.resources = journal.resources
        self.runtime = journal.runtime

    def publish(self, claims, *, task_id, run_id, sequence, generation,
                coordinator_owner, context_binding, selection=_SELECTION_OMITTED):
        task_id, run_id = map(canonical_uuid, (task_id, run_id))
        owner = canonical_uuid(coordinator_owner)
        if type(sequence) is not int or not 1 <= sequence <= 1000 \
                or type(generation) is not int or not 1 <= generation <= 2_147_483_647 \
                or type(context_binding) is not dict:
            raise ExecutionRuntimeError("invalid_request", 422)
        binding = json.loads(json.dumps(context_binding))
        try:
            with self.runtime.database.connect() as connection, connection.cursor() as cursor:
                tenant = self.runtime._active(cursor, claims)
                # Reuse the current context/material/task checks and the same
                # resource-event -> journal lock order used by journal.finish.
                self.journal._current(
                    cursor, claims, tenant, task_id, run_id, binding
                )
                self.journal._coordinator(
                    cursor, tenant, claims.user_id, task_id, run_id,
                    generation, owner,
                )
                event_row = self.resources._select(
                    cursor, tenant, claims.user_id, task_id, run_id,
                    self._action_id(cursor, tenant, claims.user_id, task_id, run_id, sequence),
                    lock=True,
                )
                entry = self.journal._select(
                    cursor, tenant, claims.user_id, task_id, run_id, sequence,
                    lock=True,
                )
                if (entry is None or event_row is None or entry["kind"] != "READ"
                        or entry["status"] != "SUCCEEDED"
                        or entry["generation"] != generation
                        or entry["coordinator_owner"] != owner
                        or entry["context_binding"] != binding):
                    raise ExecutionRuntimeError("request_conflict", 409)
                event = _event(event_row)
                self.journal._matching_event(entry, event)
                validated = effect_result("READ", entry["payload"], entry["result"])
                if (validated != entry["result"]
                        or canonical_effect_sha256(validated) != entry["output_sha256"]):
                    raise ExecutionRuntimeError("request_conflict", 409)
                selected_page = None
                if selection is not _SELECTION_OMITTED:
                    selected_page = validate_page_selection(selection, validated["evidence"])

                task, run, platforms = self.runtime._locks(cursor, claims, tenant, task_id)
                if (run is None or run["run_id"] != run_id or len(platforms) != 1
                        or not dynamic_research_snapshot(task["configuration_snapshot"])):
                    raise ExecutionRuntimeError("request_conflict", 409)
                platform = platforms[0]
                if (platform["platform"] != "PUBLIC_WEB"
                        or platform["access_mode"] != "PUBLIC_ANONYMOUS"
                        or platform["connection_id"] is not None
                        or platform["connection_version"] is not None):
                    raise ExecutionRuntimeError("request_conflict", 409)

                cursor.execute(
                    "SELECT fingerprint,receipt,execution_context FROM pilot_candidate_batches "
                    "WHERE tenant_id=%s AND owner_user_id=%s AND platform_run_id=%s AND request_id=%s",
                    (tenant, claims.user_id, platform["platform_run_id"], entry["action_id"]),
                )
                previous = cursor.fetchone()
                if previous is not None:
                    previous_context = previous[2]
                    previous_has_selection = (type(previous_context) is dict
                                              and "page_selection" in previous_context)
                    supplied_selection = selection is not _SELECTION_OMITTED
                    if (type(previous_context) is not dict
                            or previous_context.get("output_sha256") != entry["output_sha256"]
                            or previous_context.get("permit_id") != entry["permit_id"]
                            or previous_context.get("action_id") != entry["action_id"]
                            or previous_has_selection != supplied_selection
                            or supplied_selection and previous_context.get("page_selection") != selected_page
                            or previous[0] != hashlib.sha256(
                                _json(previous_context).encode("utf-8")
                            ).hexdigest()):
                        raise ExecutionRuntimeError("request_conflict", 409)
                    self.runtime._active(cursor, claims)
                    return previous[1]

                record = (_record(entry) if selected_page is None
                          or selected_page["decision"] == "ASSESS" else None)
                remaining = max(
                    0,
                    task["max_records"] - sum(item["records_used"] for item in platforms),
                )
                selected = [record] if record is not None and remaining > 0 else []
                background = selected_page is not None and selected_page["decision"] == "BACKGROUND"
                skipped_invalid = int(record is None and not background)
                skipped_budget = int(record is not None and remaining == 0)
                context = {
                    "kind": "research-resource-v1",
                    "device_id": task["device_id"],
                    "task_id": task_id,
                    "run_id": run_id,
                    "platform_run_id": platform["platform_run_id"],
                    "credential_version": platform["credential_version"],
                    "access_mode": "PUBLIC_ANONYMOUS",
                    "connection_id": None,
                    "connection_version": None,
                    "reservation_id": event["reservation_id"],
                    "action_id": entry["action_id"],
                    "permit_id": entry["permit_id"],
                    "research_generation": 1,
                    "resource": "SOURCE_READ",
                    "input_sha256": entry["input_sha256"],
                    "output_sha256": entry["output_sha256"],
                    "observed_count": 1,
                    "accepted_count": len(selected),
                    "skipped_invalid_count": skipped_invalid,
                    "skipped_budget_count": skipped_budget,
                }
                if selected_page is not None:
                    context["page_selection"] = selected_page
                    context["skipped_background_count"] = int(background)
                fingerprint = hashlib.sha256(_json(context).encode("utf-8")).hexdigest()
                cursor.execute("SELECT clock_timestamp()")
                received = cursor.fetchone()[0]
                items = _persist_records(
                    cursor,
                    tenant=tenant,
                    user=claims.user_id,
                    platform="PUBLIC_WEB",
                    profile_version_id=task["profile_version_id"],
                    strategy_version_id=task["strategy_version_id"],
                    platform_run_id=platform["platform_run_id"],
                    request_id=entry["action_id"],
                    records=enumerate(selected),
                    received=received,
                )
                receipt = {
                    "schema_version": "candidate-receipt-v1",
                    "request_id": entry["action_id"],
                    "platform_run_id": platform["platform_run_id"],
                    "task_id": task_id,
                    "run_id": run_id,
                    "accepted_count": len(selected),
                    "received_at": received.isoformat(),
                    "items": items,
                }
                cursor.execute(
                    "UPDATE pilot_collection_platform_runs SET records_used=records_used+%s "
                    "WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s "
                    "AND run_id=%s AND platform_run_id=%s",
                    (len(selected), tenant, claims.user_id, task_id, run_id,
                     platform["platform_run_id"]),
                )
                cursor.execute(
                    "INSERT INTO pilot_candidate_batches(tenant_id,owner_user_id,platform_run_id,"
                    "request_id,task_id,run_id,fingerprint,accepted_count,received_at,receipt,platform,"
                    "profile_version_id,strategy_version_id,execution_context) VALUES "
                    "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s::jsonb)",
                    (tenant, claims.user_id, platform["platform_run_id"], entry["action_id"],
                     task_id, run_id, fingerprint, len(selected), received, _json(receipt),
                     "PUBLIC_WEB", task["profile_version_id"], task["strategy_version_id"],
                     _json(context)),
                )
                self.runtime._active(cursor, claims)
                return receipt
        except ExecutionRuntimeError:
            raise
        except (psycopg.Error, KeyError, TypeError, ValueError, UnicodeError):
            raise ExecutionRuntimeError("resource_unavailable", 503) from None

    def _action_id(self, cursor, tenant, user, task_id, run_id, sequence):
        cursor.execute(
            "SELECT action_id FROM pilot_research_effect_journal WHERE tenant_id=%s "
            "AND owner_user_id=%s AND task_id=%s AND run_id=%s AND sequence=%s",
            (tenant, user, task_id, run_id, sequence),
        )
        row = cursor.fetchone()
        if row is None:
            raise ExecutionRuntimeError("request_not_found", 404)
        return row[0]
