"""Restricted-PostgreSQL checks for internal research resource permits."""
import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
import psycopg

from pilot.auth import issue_token, verify_token_claims
from pilot.execution_contract import ExecutionRuntimeError
from pilot.research_resources import ResearchResourceStore
from pilot.research_quote import ResearchQuoteRule
from tests.test_research_execution_postgres import services, signed_start
from tests.test_execution_runtime_postgres import SECRET, apply, operation, start
from tests.test_research_quote_postgres import _confirmed_research, _request
from tests.test_confirmed_strategy_review_postgres import real_strategy_env
from tests.test_candidate_review_postgres import (databases, env, execution_databases,
    execution_env, raw_databases, raw_env)


RULE = ResearchQuoteRule("synthetic-review-rule-v1", 100, 200, 300)


def started(env):
    _, _, _, _, _, confirmed = _confirmed_research(env)
    env.confirmed = confirmed
    env.snapshot = confirmed["snapshot"]
    quote_service, execution = services(env)
    request = start(env)
    quote = quote_service.quote(env.claims, _request(env, confirmed) | {"requestId": request.request_id})
    receipt = execution.start(env.claims, request, signed_start(env, request), quote["authorizationToken"])
    return receipt["execution"], receipt["reservation"]


def started_again(env):
    quote_service, execution = services(env)
    request = start(env)
    quote = quote_service.quote(env.claims, _request(env, env.confirmed) | {"requestId": request.request_id})
    receipt = execution.start(env.claims, request, signed_start(env, request), quote["authorizationToken"])
    return receipt["execution"], receipt["reservation"]


def store(env):
    return ResearchResourceStore(env.runtime, rule=RULE,
        research_capability=lambda snapshot: snapshot["platforms"] == ["PUBLIC_WEB"])


def test_begin_finish_get_and_same_action_replay(real_strategy_env):
    env = real_strategy_env
    execution, reservation = started(env)
    action_id = str(uuid4())
    input_sha256 = hashlib.sha256(b"synthetic public index read").hexdigest()

    first = store(env).begin(env.claims, task_id=execution["task_id"], run_id=execution["run_id"],
        action_id=action_id, resource="SOURCE_READ", input_sha256=input_sha256)
    assert first["created"] is True
    event = first["event"]
    assert event == {
        "schema_version": "research-resource-v1",
        "reservation_id": reservation["reservation_id"],
        "task_id": execution["task_id"], "run_id": execution["run_id"],
        "action_id": action_id, "permit_id": event["permit_id"],
        "research_generation": 1, "resource": "SOURCE_READ",
        "input_sha256": input_sha256, "status": "ISSUED", "output_sha256": None,
        "issued_at": event["issued_at"], "deadline_at": event["deadline_at"],
        "finished_at": None,
    }
    assert store(env).begin(env.claims, task_id=execution["task_id"], run_id=execution["run_id"],
        action_id=action_id, resource="SOURCE_READ", input_sha256=input_sha256) == {
            "created": False, "event": event}

    output_sha256 = hashlib.sha256(b"synthetic sanitized result").hexdigest()
    finished = store(env).finish(env.claims, task_id=execution["task_id"], run_id=execution["run_id"],
        action_id=action_id, permit_id=event["permit_id"], status="SUCCEEDED",
        output_sha256=output_sha256)
    assert finished["status"] == "SUCCEEDED"
    assert finished["output_sha256"] == output_sha256
    assert finished["finished_at"] is not None
    assert store(env).get(env.claims, task_id=execution["task_id"], run_id=execution["run_id"],
        action_id=action_id) == finished


def begin(resource_store, env, execution, resource="SOURCE_READ", action_id=None, digest=None):
    return resource_store.begin(env.claims, task_id=execution["task_id"], run_id=execution["run_id"],
        action_id=action_id or str(uuid4()), resource=resource,
        input_sha256=digest or hashlib.sha256(str(uuid4()).encode()).hexdigest())


def event_count(env):
    with env.admin.connect() as connection:
        return connection.execute("SELECT count(*) FROM pilot_research_resource_events "
            "WHERE tenant_id=%s", (env.tenant,)).fetchone()[0]


def test_source_and_model_limits_are_independent_and_unknown_still_occupies_budget(real_strategy_env):
    env = real_strategy_env
    execution, _ = started(env)
    resource_store = store(env)
    source_events = [begin(resource_store, env, execution)["event"] for _ in range(10)]
    model_events = [begin(resource_store, env, execution, "MODEL_CALL")["event"] for _ in range(10)]
    resource_store.finish(env.claims, task_id=execution["task_id"], run_id=execution["run_id"],
        action_id=source_events[-1]["action_id"], permit_id=source_events[-1]["permit_id"],
        status="UNKNOWN")
    for resource in ("SOURCE_READ", "MODEL_CALL"):
        with pytest.raises(ExecutionRuntimeError) as caught:
            begin(resource_store, env, execution, resource)
        assert (caught.value.code, caught.value.status) == ("resource_limit_exceeded", 409)


def test_concurrent_last_slot_and_same_action_are_serialized(real_strategy_env):
    env = real_strategy_env
    execution, _ = started(env)
    resource_store = store(env)
    for _ in range(9):
        begin(resource_store, env, execution)
    actions = [str(uuid4()), str(uuid4())]
    def different(action):
        try:
            return begin(resource_store, env, execution, action_id=action)
        except ExecutionRuntimeError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(different, actions))
    assert sum(type(value) is dict and value["created"] for value in results) == 1
    assert "resource_limit_exceeded" in results

    execution2, _ = started_again(env)
    action, digest = str(uuid4()), hashlib.sha256(b"same action").hexdigest()
    def same(_):
        return begin(resource_store, env, execution2, action_id=action, digest=digest)
    with ThreadPoolExecutor(max_workers=2) as pool:
        same_results = list(pool.map(same, range(2)))
    assert sorted(item["created"] for item in same_results) == [False, True]
    assert same_results[0]["event"]["permit_id"] == same_results[1]["event"]["permit_id"]


def test_finish_validation_idempotency_conflict_and_failed_null_digest(real_strategy_env):
    env = real_strategy_env
    execution, _ = started(env)
    resource_store = store(env)
    issued = begin(resource_store, env, execution)["event"]
    args = dict(task_id=execution["task_id"], run_id=execution["run_id"],
        action_id=issued["action_id"], permit_id=issued["permit_id"])
    with pytest.raises(ExecutionRuntimeError, match="invalid_request"):
        resource_store.finish(env.claims, **args, status="SUCCEEDED")
    with pytest.raises(ExecutionRuntimeError, match="invalid_request"):
        resource_store.finish(env.claims, **args, status="FAILED", output_sha256="a" * 64)
    failed = resource_store.finish(env.claims, **args, status="FAILED")
    assert failed["output_sha256"] is None
    assert resource_store.finish(env.claims, **args, status="FAILED") == failed
    with pytest.raises(ExecutionRuntimeError) as caught:
        resource_store.finish(env.claims, **args, status="UNKNOWN")
    assert (caught.value.code, caught.value.status) == ("request_conflict", 409)


def test_cross_owner_and_cross_tenant_cannot_read_or_finish(real_strategy_env):
    env = real_strategy_env
    execution, _ = started(env)
    resource_store = store(env)
    issued = begin(resource_store, env, execution)["event"]
    for user in (env.users[1], env.users[2]):
        stranger = verify_token_claims(issue_token(user, SECRET), SECRET)
        for method, kwargs in ((resource_store.get, {}), (resource_store.finish,
                {"permit_id": issued["permit_id"], "status": "FAILED"})):
            with pytest.raises(ExecutionRuntimeError) as caught:
                method(stranger, task_id=execution["task_id"], run_id=execution["run_id"],
                    action_id=issued["action_id"], **kwargs)
            assert (caught.value.code, caught.value.status) == ("request_not_found", 404)


@pytest.mark.parametrize("revocation", ["device", "strategy", "capability"])
def test_current_device_strategy_and_capability_block_new_permits_without_writes(
        real_strategy_env, revocation):
    env = real_strategy_env
    execution, _ = started(env)
    resource_store = store(env)
    before = event_count(env)
    if revocation == "device":
        with env.admin.connect() as connection:
            connection.execute("UPDATE pilot_devices SET status='REVOKED' WHERE tenant_id=%s "
                "AND owner_user_id=%s AND device_id=%s", (env.tenant, env.claims.user_id, env.device))
    elif revocation == "strategy":
        from tests.test_research_strategies_postgres import revoke_body
        env.strategies.revoke(env.claims, revoke_body(env.confirmed))
    else:
        resource_store.research_capability = lambda _snapshot: False
    with pytest.raises(ExecutionRuntimeError):
        begin(resource_store, env, execution)
    assert event_count(env) == before


def test_source_revocation_after_start_blocks_new_permit(real_strategy_env):
    env = real_strategy_env
    review, candidate, assessed, check, _, confirmed = _confirmed_research(env)
    env.snapshot = confirmed["snapshot"]
    quote_service, execution_service = services(env)
    request = start(env)
    quote = quote_service.quote(env.claims, _request(env, confirmed) | {"requestId": request.request_id})
    execution = execution_service.start(env.claims, request, signed_start(env, request),
        quote["authorizationToken"])["execution"]
    from tests.test_candidate_review_postgres import assessment, review_payload
    review.review(env.claims, review_payload(candidate, "EXCLUDE",
        assessmentId=assessed["assessment"]["id"], sourceVerificationId=check["id"],
        humanConfirmed=True, evidence=assessment()["evidence"], reason="revoke synthetic source"))
    with pytest.raises(ExecutionRuntimeError, match="strategy_conflict"):
        begin(store(env), env, execution)
    assert event_count(env) == 0


def test_each_current_target_connection_is_rechecked_before_new_permit(real_strategy_env, monkeypatch):
    env = real_strategy_env
    execution, _ = started(env)
    calls = []
    def revoked(_cursor, _claims, device_id, target):
        calls.append((device_id, target.platform, target.access_mode))
        raise ExecutionRuntimeError("connection_unavailable", 409)
    monkeypatch.setattr(env.runtime, "_connection", revoked)
    with pytest.raises(ExecutionRuntimeError, match="connection_unavailable"):
        begin(store(env), env, execution)
    assert calls == [(env.device, "PUBLIC_WEB", "PUBLIC_ANONYMOUS")]
    assert event_count(env) == 0


def test_database_rejects_reservation_bound_to_a_different_task_run(real_strategy_env):
    env = real_strategy_env
    first, first_reservation = started(env)
    second, _ = started_again(env)
    with env.admin.connect() as connection, pytest.raises(psycopg.Error):
        connection.execute("INSERT INTO pilot_research_resource_events(tenant_id,owner_user_id,reservation_id,"
            "task_id,run_id,action_id,permit_id,resource,input_sha256,deadline_at) "
            "SELECT tenant_id,owner_user_id,%s,%s,%s,%s,%s,'SOURCE_READ',%s,clock_timestamp()+interval '1 minute' "
            "FROM pilot_research_reservations WHERE reservation_id=%s",
            (first_reservation["reservation_id"], second["task_id"], second["run_id"], str(uuid4()),
             str(uuid4()), "a" * 64, first_reservation["reservation_id"]))


def test_restricted_grants_expose_only_required_event_mutation_columns(real_strategy_env):
    env = real_strategy_env
    with env.db.connect() as connection:
        role = connection.execute("SELECT current_user").fetchone()[0]
    with env.admin.connect() as connection:
        assert connection.execute("SELECT has_table_privilege(%s,'pilot_research_resource_events','SELECT,INSERT')",
            (role,)).fetchone()[0]
        for column in ("status", "output_sha256", "finished_at"):
            assert connection.execute("SELECT has_column_privilege(%s,'pilot_research_resource_events',%s,'UPDATE')",
                (role, column)).fetchone()[0]
        for column in ("tenant_id", "owner_user_id", "reservation_id", "task_id", "run_id",
                       "action_id", "permit_id", "resource", "input_sha256", "issued_at", "deadline_at"):
            assert not connection.execute("SELECT has_column_privilege(%s,'pilot_research_resource_events',%s,'UPDATE')",
                (role, column)).fetchone()[0]
        for privilege in ("DELETE", "TRUNCATE", "TRIGGER", "REFERENCES"):
            assert not connection.execute("SELECT has_table_privilege(%s,'pilot_research_resource_events',%s)",
                (role, privilege)).fetchone()[0]


def test_cancelled_and_expired_tasks_reject_begin_but_allow_finish_and_get(real_strategy_env):
    env = real_strategy_env
    execution, _ = started(env)
    resource_store = store(env)
    issued = begin(resource_store, env, execution)["event"]
    apply(env, operation(env, "CANCEL", execution))
    with pytest.raises(ExecutionRuntimeError) as caught:
        begin(resource_store, env, execution)
    assert (caught.value.code, caught.value.status) == ("task_unavailable", 409)
    finished = resource_store.finish(env.claims, task_id=execution["task_id"], run_id=execution["run_id"],
        action_id=issued["action_id"], permit_id=issued["permit_id"], status="UNKNOWN")
    assert resource_store.get(env.claims, task_id=execution["task_id"], run_id=execution["run_id"],
        action_id=issued["action_id"]) == finished

    execution2, _ = started_again(env)
    with env.admin.connect() as connection:
        connection.execute("ALTER TABLE pilot_collection_tasks DISABLE TRIGGER execution_immutable")
        connection.execute("UPDATE pilot_collection_tasks SET created_at=created_at-interval '1 day',"
            "deadline_at=deadline_at-interval '1 day' WHERE task_id=%s", (execution2["task_id"],))
        connection.execute("ALTER TABLE pilot_collection_tasks ENABLE TRIGGER execution_immutable")
    with pytest.raises(ExecutionRuntimeError) as expired:
        begin(resource_store, env, execution2)
    assert (expired.value.code, expired.value.status) == ("task_unavailable", 409)


def test_deadline_uses_minute_limit_and_task_deadline_and_mixed_task_run_is_rejected(real_strategy_env):
    env = real_strategy_env
    first, _ = started(env)
    second, _ = started_again(env)
    resource_store = store(env)
    issued = begin(resource_store, env, first)["event"]
    with env.admin.connect() as connection:
        task = connection.execute("SELECT created_at,deadline_at FROM pilot_collection_tasks WHERE task_id=%s",
            (first["task_id"],)).fetchone()
    assert datetime.fromisoformat(issued["deadline_at"]) == min(task[1], task[0] + timedelta(minutes=10))
    with pytest.raises(ExecutionRuntimeError) as caught:
        resource_store.begin(env.claims, task_id=first["task_id"], run_id=second["run_id"],
            action_id=str(uuid4()), resource="SOURCE_READ", input_sha256="a" * 64)
    assert (caught.value.code, caught.value.status) == ("task_unavailable", 409)


def test_terminal_session_fence_rolls_back_begin_and_finish(real_strategy_env, monkeypatch):
    env = real_strategy_env
    execution, _ = started(env)
    resource_store = store(env)
    original = env.runtime._active
    action_id = str(uuid4())
    def reject_insert(cursor, claims):
        cursor.execute("SELECT EXISTS(SELECT 1 FROM pilot_research_resource_events WHERE action_id=%s)",
            (action_id,))
        if cursor.fetchone()[0]:
            raise ExecutionRuntimeError("invalid_session", 401)
        return original(cursor, claims)
    monkeypatch.setattr(env.runtime, "_active", reject_insert)
    with pytest.raises(ExecutionRuntimeError, match="invalid_session"):
        begin(resource_store, env, execution, action_id=action_id)
    assert event_count(env) == 0
    monkeypatch.setattr(env.runtime, "_active", original)
    issued = begin(resource_store, env, execution)["event"]
    def reject_finish(cursor, claims):
        cursor.execute("SELECT status FROM pilot_research_resource_events WHERE action_id=%s",
            (issued["action_id"],))
        row = cursor.fetchone()
        if row and row[0] != "ISSUED":
            raise ExecutionRuntimeError("invalid_session", 401)
        return original(cursor, claims)
    monkeypatch.setattr(env.runtime, "_active", reject_finish)
    with pytest.raises(ExecutionRuntimeError, match="invalid_session"):
        resource_store.finish(env.claims, task_id=execution["task_id"], run_id=execution["run_id"],
            action_id=issued["action_id"], permit_id=issued["permit_id"], status="UNKNOWN")
    monkeypatch.setattr(env.runtime, "_active", original)
    assert resource_store.get(env.claims, task_id=execution["task_id"], run_id=execution["run_id"],
        action_id=issued["action_id"])["status"] == "ISSUED"
