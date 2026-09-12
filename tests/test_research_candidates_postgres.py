"""Synthetic public reads persisted atomically in the restricted candidate inbox."""
import copy
import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import psycopg

from pilot.auth import issue_token, verify_token_claims
from pilot.candidate_contract import CandidateRecord, source_identity
from pilot.candidate_ingestion import CandidateIngestionStore
from pilot.execution_contract import ExecutionRuntimeError
from pilot.research_candidates import ResearchCandidateStore
from pilot.research_public_reader import _INPUT_SHA, _public_topics
from tests.test_confirmed_strategy_review_postgres import real_strategy_env
from tests.test_research_resources_postgres import started, store as resource_store
from tests.test_execution_runtime_postgres import SECRET, apply, batch, operation
from tests.test_candidate_ingestion_postgres import submit
from tests.test_candidate_review_postgres import (
    databases, env, execution_databases, execution_env, raw_databases, raw_env,
)


def topic(identity=17, **changes):
    return {
        "id": identity,
        "title": "合成公开话题",
        "content": "  合成原文\n不表示商机  ",
        "created": int(datetime.now(UTC).timestamp()) - 60,
        "url": f"https://www.v2ex.com/t/{identity}",
    } | changes


def canonical_result(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def admitted(env, topics=None):
    execution, _ = started(env)
    resources = resource_store(env)
    action_id = str(uuid4())
    issued = resources.begin(env.claims, task_id=execution["task_id"],
        run_id=execution["run_id"], action_id=action_id, resource="SOURCE_READ",
        input_sha256=_INPUT_SHA)["event"]
    result = _public_topics(topics if topics is not None else [topic()])
    return execution, resources, issued, result, canonical_result(result)


def test_commit_index_finishes_the_original_issued_event(real_strategy_env):
    env = real_strategy_env
    _, resources, issued, result, digest = admitted(env)
    final = ResearchCandidateStore(resources).commit_index(env.claims, event=issued,
        result=result, output_sha256=digest)
    assert final["status"] == "SUCCEEDED"


def test_node_source_cannot_commit_to_latest_frozen_task(real_strategy_env):
    from pilot.research_source_catalog import research_source
    env = real_strategy_env
    execution, _ = started(env)
    resources = resource_store(env)
    issued = resources.begin(env.claims, task_id=execution['task_id'], run_id=execution['run_id'],
        action_id=str(uuid4()), resource='SOURCE_READ',
        input_sha256=research_source('v2ex-qna-v1').input_sha)['event']
    result = _public_topics([topic(node={'name': 'qna'})], 'v2ex-qna-v1')
    with pytest.raises(ExecutionRuntimeError, match='request_conflict'):
        ResearchCandidateStore(resources).commit_index(env.claims, event=issued,
            result=result, output_sha256=canonical_result(result))
    assert resources.get(env.claims, task_id=execution['task_id'], run_id=execution['run_id'],
        action_id=issued['action_id'])['status'] == 'ISSUED'


def test_latest_source_cannot_commit_to_qna_frozen_task(real_strategy_env):
    from tests.test_research_quote_postgres import _confirmed_research
    from tests.test_research_resources_postgres import started_again
    env = real_strategy_env
    *_, env.confirmed = _confirmed_research(env, source_id='v2ex-qna-v1')
    env.snapshot = env.confirmed['snapshot']
    execution, _ = started_again(env)
    resources = resource_store(env)
    issued = resources.begin(env.claims, task_id=execution['task_id'], run_id=execution['run_id'],
        action_id=str(uuid4()), resource='SOURCE_READ', input_sha256=_INPUT_SHA)['event']
    result = _public_topics([topic()])
    with pytest.raises(ExecutionRuntimeError, match='request_conflict'):
        ResearchCandidateStore(resources).commit_index(env.claims, event=issued,
            result=result, output_sha256=canonical_result(result))


def test_actual_research_start_persists_original_candidate_and_recovers_without_fetch(real_strategy_env):
    env = real_strategy_env
    execution, _ = started(env)
    service = ResearchCandidateStore(resource_store(env))
    action_id = str(uuid4())
    calls = []
    source = topic()

    first = service.read_public(env.claims, task_id=execution["task_id"],
        run_id=execution["run_id"], action_id=action_id,
        fetcher=lambda _deadline: calls.append("read") or [source])

    assert first["event"]["status"] == "SUCCEEDED"
    assert first["receipt"]["request_id"] == action_id
    assert first["receipt"]["accepted_count"] == 1
    inbox = CandidateIngestionStore(env.db)
    page = inbox.list_candidates(env.claims, task_id=execution["task_id"])
    assert page["total"] == 1
    detail = inbox.get_candidate(env.claims, page["items"][0]["candidate_id"])
    current = detail["candidate"]["current_version"]
    assert current["body"] == "  合成原文\n不表示商机  "
    assert current["title"] == "合成公开话题"
    assert current["public_url"] == "https://www.v2ex.com/t/17"
    assert current["published_at"] == datetime.fromtimestamp(
        source["created"], UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert detail["candidate"]["status"] == "UNVERIFIED"
    assert detail["candidate"]["external_source_id"] == "17"
    equivalent_normal_record = CandidateRecord.model_validate(dict(kind="PAGE",
        external_source_id="17", external_comment_id=None, public_url=current["public_url"],
        title=current["title"], author_public_id=None, body=current["body"],
        published_at=current["published_at"], observed_at="2026-01-01T00:00:00Z",
        parent=None, collector_version="normal-v1", normalizer_version="normal-v1", query=None))
    assert source_identity(equivalent_normal_record, "PUBLIC_WEB") == detail["candidate"]["source_identity"]
    context = detail["observations"]["items"][0]["execution_context"]
    assert context["kind"] == "research-resource-v1"
    assert "lease_id" not in context and "execution_generation" not in context

    recovered = service.read_public(env.claims, task_id=execution["task_id"],
        run_id=execution["run_id"], action_id=action_id,
        fetcher=lambda _deadline: (_ for _ in ()).throw(AssertionError("must not refetch")))
    assert recovered == {"event": first["event"], "receipt": first["receipt"], "replayed": True}
    assert service.get_receipt(env.claims, task_id=execution["task_id"],
        run_id=execution["run_id"], action_id=action_id) == first["receipt"]
    assert calls == ["read"]


def test_explicit_replay_at_full_cap_returns_same_event_without_duplicates(real_strategy_env):
    env = real_strategy_env
    topics = [topic(identity) for identity in range(100, 110)]
    execution, resources, issued, result, digest = admitted(env, topics)
    service = ResearchCandidateStore(resources)
    first = service.commit_index(env.claims, event=issued, result=result, output_sha256=digest)
    assert service.commit_index(env.claims, event=issued, result=result, output_sha256=digest) == first
    assert CandidateIngestionStore(env.db).list_candidates(
        env.claims, task_id=execution["task_id"])["total"] == 10
    assert env.runtime.get_task(env.claims, execution["task_id"])["records_used"] == 10


def test_different_action_reuses_source_and_appends_observation(real_strategy_env):
    env = real_strategy_env
    execution, resources, issued, result, digest = admitted(env)
    service = ResearchCandidateStore(resources)
    service.commit_index(env.claims, event=issued, result=result, output_sha256=digest)
    action_id = str(uuid4())
    second_event = resources.begin(env.claims, task_id=execution["task_id"],
        run_id=execution["run_id"], action_id=action_id, resource="SOURCE_READ",
        input_sha256=_INPUT_SHA)["event"]
    second_result = _public_topics([topic()])
    service.commit_index(env.claims, event=second_event, result=second_result,
        output_sha256=canonical_result(second_result))
    first_receipt = service.get_receipt(env.claims, task_id=execution["task_id"],
        run_id=execution["run_id"], action_id=issued["action_id"])
    detail = CandidateIngestionStore(env.db).get_candidate(
        env.claims, first_receipt["items"][0]["candidate_id"])
    assert detail["observations"]["total"] == 2
    assert len({item["request_id"] for item in detail["observations"]["items"]}) == 2


def test_unknown_event_cannot_become_success(real_strategy_env):
    env = real_strategy_env
    execution, resources, issued, result, digest = admitted(env)
    resources.finish(env.claims, task_id=execution["task_id"], run_id=execution["run_id"],
        action_id=issued["action_id"], permit_id=issued["permit_id"], status="UNKNOWN")
    with pytest.raises(ExecutionRuntimeError, match="request_conflict"):
        ResearchCandidateStore(resources).commit_index(env.claims, event=issued,
            result=result, output_sha256=digest)
    assert CandidateIngestionStore(env.db).list_candidates(
        env.claims, task_id=execution["task_id"])["total"] == 0
    assert env.runtime.get_task(env.claims, execution["task_id"])["records_used"] == 0


def test_digest_body_conflict_and_future_observation_leave_event_issued(real_strategy_env):
    env = real_strategy_env
    execution, resources, issued, result, digest = admitted(env)
    service = ResearchCandidateStore(resources)
    changed = copy.deepcopy(result)
    changed["topics"][0]["content"] = "different"
    with pytest.raises(ExecutionRuntimeError, match="request_conflict"):
        service.commit_index(env.claims, event=issued, result=changed, output_sha256=digest)
    future = copy.deepcopy(result)
    future["observed_at"] = (datetime.now(UTC) + timedelta(minutes=1)).isoformat()
    with pytest.raises(ExecutionRuntimeError, match="request_conflict"):
        service.commit_index(env.claims, event=issued, result=future,
            output_sha256=canonical_result(future))
    assert resources.get(env.claims, task_id=execution["task_id"], run_id=execution["run_id"],
        action_id=issued["action_id"])["status"] == "ISSUED"


def test_invalid_unicode_is_fixed_invalid_request(real_strategy_env):
    env = real_strategy_env
    _, resources, issued, result, _ = admitted(env)
    result["topics"][0]["content"] = "\ud800"
    with pytest.raises(ExecutionRuntimeError) as caught:
        ResearchCandidateStore(resources).commit_index(env.claims, event=issued,
            result=result, output_sha256="a" * 64)
    assert (caught.value.code, caught.value.status) == ("invalid_request", 422)


def test_cross_owner_invisibility_and_final_session_fence_rollback(real_strategy_env, monkeypatch):
    env = real_strategy_env
    execution, resources, issued, result, digest = admitted(env)
    service = ResearchCandidateStore(resources)
    stranger = verify_token_claims(issue_token(env.users[1], SECRET), SECRET)
    assert service.get_receipt(stranger, task_id=execution["task_id"],
        run_id=execution["run_id"], action_id=issued["action_id"]) is None
    original = env.runtime._active
    def reject_after_writes(cursor, claims):
        cursor.execute("SELECT EXISTS(SELECT 1 FROM pilot_candidate_batches WHERE request_id=%s),"
            "(SELECT status FROM pilot_research_resource_events WHERE action_id=%s)",
            (issued["action_id"], issued["action_id"]))
        exists, status = cursor.fetchone()
        if exists and status == "SUCCEEDED":
            raise ExecutionRuntimeError("invalid_session", 401)
        return original(cursor, claims)
    monkeypatch.setattr(env.runtime, "_active", reject_after_writes)
    with pytest.raises(ExecutionRuntimeError, match="invalid_session"):
        service.commit_index(env.claims, event=issued, result=result, output_sha256=digest)
    monkeypatch.setattr(env.runtime, "_active", original)
    assert resources.get(env.claims, task_id=execution["task_id"], run_id=execution["run_id"],
        action_id=issued["action_id"])["status"] == "ISSUED"
    assert CandidateIngestionStore(env.db).list_candidates(
        env.claims, task_id=execution["task_id"])["total"] == 0
    assert env.runtime.get_task(env.claims, execution["task_id"])["records_used"] == 0


def test_cancelled_admitted_action_can_record_fact_without_new_authority(real_strategy_env):
    env = real_strategy_env
    execution, resources, issued, result, digest = admitted(env)
    apply(env, operation(env, "CANCEL", execution))
    final = ResearchCandidateStore(resources).commit_index(env.claims, event=issued,
        result=result, output_sha256=digest)
    assert final["status"] == "SUCCEEDED"
    assert env.runtime.get_task(env.claims, execution["task_id"])["status"] == "CANCELED"
    assert CandidateIngestionStore(env.db).list_candidates(
        env.claims, task_id=execution["task_id"])["total"] == 1


def test_record_cap_and_invalid_entries_are_accounted_without_truncating(real_strategy_env):
    env = real_strategy_env
    topics = [topic(identity) for identity in range(200, 213)]
    topics[1]["content"] = "   "
    topics[2]["title"] = "题" * 513
    execution, resources, issued, result, digest = admitted(env, topics)
    service = ResearchCandidateStore(resources)
    service.commit_index(env.claims, event=issued, result=result, output_sha256=digest)
    receipt = service.get_receipt(env.claims, task_id=execution["task_id"],
        run_id=execution["run_id"], action_id=issued["action_id"])
    assert receipt["accepted_count"] == 10
    with env.admin.connect() as connection:
        context = connection.execute("SELECT execution_context FROM pilot_candidate_batches "
            "WHERE tenant_id=%s AND request_id=%s", (env.tenant, issued["action_id"])).fetchone()[0]
    assert context["observed_count"] == 13
    assert context["accepted_count"] == 10
    assert context["skipped_invalid_count"] == 2
    assert context["skipped_budget_count"] == 1
    assert [item["index"] for item in receipt["items"]] == list(range(10))
    assert context["observed_count"] == sum(context[key] for key in
        ("accepted_count", "skipped_invalid_count", "skipped_budget_count"))


def test_ordinary_signed_upload_remains_rejected_for_research_task(real_strategy_env):
    env = real_strategy_env
    execution, _ = started(env)
    forged = {"platform_run_id": execution["platform_runs"][0]["platform_run_id"],
        "lease_id": str(uuid4()), "execution_generation": 1}
    value = batch(env, execution, forged).model_dump(mode="json")
    with pytest.raises(ExecutionRuntimeError, match="capability_unavailable"):
        submit(env, CandidateIngestionStore(env.db, env.runtime), value)


def test_failed_read_has_no_receipt_and_never_becomes_candidate(real_strategy_env):
    env = real_strategy_env
    execution, _ = started(env)
    service = ResearchCandidateStore(resource_store(env))
    action_id = str(uuid4())
    result = service.read_public(env.claims, task_id=execution["task_id"],
        run_id=execution["run_id"], action_id=action_id, fetcher=lambda _deadline: {})
    assert result["event"]["status"] == "UNKNOWN"
    assert result["receipt"] is None and result["replayed"] is False
    assert CandidateIngestionStore(env.db).list_candidates(
        env.claims, task_id=execution["task_id"])["total"] == 0


@pytest.mark.parametrize("tamper", ["kind", "action", "permit", "digest"])
def test_database_rejects_research_batch_that_dodges_event_binding(real_strategy_env, tamper):
    env = real_strategy_env
    execution, resources, _, _, _ = admitted(env)
    action_id = str(uuid4())
    issued = resources.begin(env.claims, task_id=execution["task_id"],
        run_id=execution["run_id"], action_id=action_id, resource="SOURCE_READ",
        input_sha256=_INPUT_SHA)["event"]
    output_sha256 = "b" * 64
    succeeded = resources.finish(env.claims, task_id=execution["task_id"],
        run_id=execution["run_id"], action_id=action_id, permit_id=issued["permit_id"],
        status="SUCCEEDED", output_sha256=output_sha256)
    with env.admin.connect() as connection:
        task = connection.execute("SELECT t.device_id,t.profile_version_id,t.strategy_version_id,"
            "p.platform_run_id,p.credential_version FROM pilot_collection_tasks t "
            "JOIN pilot_collection_platform_runs p USING(tenant_id,owner_user_id,task_id) "
            "WHERE t.tenant_id=%s AND t.task_id=%s", (env.tenant, execution["task_id"])).fetchone()
    context = dict(kind="research-resource-v1", device_id=task[0], task_id=execution["task_id"],
        run_id=execution["run_id"], platform_run_id=task[3], credential_version=task[4],
        access_mode="PUBLIC_ANONYMOUS", connection_id=None, connection_version=None,
        reservation_id=succeeded["reservation_id"], action_id=action_id,
        permit_id=succeeded["permit_id"], research_generation=1, resource="SOURCE_READ",
        input_sha256=_INPUT_SHA, output_sha256=output_sha256, observed_count=0,
        accepted_count=0, skipped_invalid_count=0, skipped_budget_count=0)
    if tamper == "kind":
        context["other_kind"] = context.pop("kind")
    elif tamper == "action":
        context["action_id"] = str(uuid4())
    elif tamper == "permit":
        context["permit_id"] = str(uuid4())
    else:
        context["output_sha256"] = "c" * 64
    receipt = dict(schema_version="candidate-receipt-v1", request_id=action_id,
        platform_run_id=task[3], task_id=execution["task_id"], run_id=execution["run_id"],
        accepted_count=0, received_at=datetime.now(UTC).isoformat(), items=[])
    with pytest.raises(psycopg.errors.RaiseException, match="research candidate binding mismatch"):
        with env.admin.connect() as connection:
            connection.execute("INSERT INTO pilot_candidate_batches(tenant_id,owner_user_id,"
                "platform_run_id,request_id,task_id,run_id,fingerprint,accepted_count,received_at,"
                "receipt,platform,profile_version_id,strategy_version_id,execution_context) VALUES "
                "(%s,%s,%s,%s,%s,%s,%s,0,clock_timestamp(),%s::jsonb,'PUBLIC_WEB',%s,%s,%s::jsonb)",
                (env.tenant, env.claims.user_id, task[3], action_id, execution["task_id"],
                 execution["run_id"], "d" * 64, json.dumps(receipt), task[1], task[2],
                 json.dumps(context)))
