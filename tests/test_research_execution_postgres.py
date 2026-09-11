import hashlib
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import hmac
import json
from uuid import uuid4

import pytest

from pilot.auth import issue_token, verify_token_claims
from pilot.execution_contract import ExecutionRuntimeError
from pilot.execution_runtime import execution_signing_payload
from pilot.research_execution import ResearchExecutionService
from pilot.research_quote import ResearchQuoteRule, ResearchQuoteService
from tests.test_execution_runtime_postgres import SECRET, apply, batch, guard, operation, start
from tests.test_research_quote_postgres import _confirmed_research, _request
from tests.test_confirmed_strategy_review_postgres import real_strategy_env
from tests.test_candidate_review_postgres import databases, env, execution_databases, execution_env, raw_databases, raw_env
from tests.test_research_origin_postgres import _provenance, _research_config
from tests.test_research_strategies_postgres import configuration, confirm_body, prepare_body, revoke_body


WRITE_TABLES = ("pilot_research_reservations", "pilot_execution_operations",
    "pilot_collection_platform_runs", "pilot_collection_runs", "pilot_collection_tasks")


def write_counts(env):
    with env.admin.connect() as connection:
        return {table: connection.execute(
            f"SELECT count(*) FROM {table} WHERE tenant_id=%s", (env.tenant,)).fetchone()[0]
            for table in WRITE_TABLES}


def services(env):
    quote = ResearchQuoteService(env.db, env.strategies,
        rule=ResearchQuoteRule("synthetic-review-rule-v1", 100, 200, 300),
        signing_secret=b"restricted-postgres-review-key!" * 2,
        research_capability=lambda snapshot: snapshot["platforms"] == ["PUBLIC_WEB"])
    return quote, ResearchExecutionService(env.runtime, quote)


def signed_start(env, request):
    from tests.test_device_keys import encoded
    return encoded(env.key.sign(execution_signing_payload(
        tenant_id=env.tenant, claims=env.claims, operation=request).encode()).signature)


def test_atomic_start_persists_bound_reservation_and_recovers(real_strategy_env):
    env = real_strategy_env
    _, _, _, _, _, confirmed = _confirmed_research(env)
    env.snapshot = confirmed["snapshot"]
    request = start(env)
    quote_service, service = services(env)
    quote_request = _request(env, confirmed) | {"requestId": request.request_id}
    quote = quote_service.quote(env.claims, quote_request)
    result = service.start(env.claims, request, signed_start(env, request), quote["authorizationToken"])
    assert set(result) == {"schema_version", "execution", "reservation"}
    assert result["schema_version"] == "research-execution-v1"
    assert result["execution"]["request_id"] == request.request_id
    assert result["reservation"] == {
        "reservation_id": result["reservation"]["reservation_id"],
        "quote_id": quote["quoteId"],
        "strategy_version_id": confirmed["strategy_version_id"],
        "profile_version_id": confirmed["profile_version_id"],
        "configuration_sha256": confirmed["configuration_sha256"],
        "rule_version": quote["ruleVersion"], "rule_sha256": quote["ruleSha256"],
        "estimated_soubei": quote["estimatedSoubei"], "max_soubei": quote["maxSoubei"],
        "limits": quote["strategyBinding"] and confirmed["snapshot"]["configuration"]["research"]["limits"],
        "status": "RESERVED",
    }
    assert service.start(env.claims, request, signed_start(env, request), quote["authorizationToken"]) == result
    assert service.get_receipt(env.claims, request.request_id) == result
    with env.admin.connect() as conn:
        row = conn.execute("SELECT authorization_token_sha256,quote_sha256,task_id,run_id FROM pilot_research_reservations WHERE request_id=%s", (request.request_id,)).fetchone()
        assert row[0] == hashlib.sha256(quote["authorizationToken"].encode()).hexdigest()
        assert quote["authorizationToken"] not in str(row)
        assert row[2:] == (result["execution"]["task_id"], result["execution"]["run_id"])


def test_research_task_is_blocked_from_ordinary_runtime_and_upload(real_strategy_env):
    env = real_strategy_env
    _, _, _, _, _, confirmed = _confirmed_research(env)
    env.snapshot = confirmed["snapshot"]
    request = start(env)
    quote_service, service = services(env)
    quote = quote_service.quote(env.claims, _request(env, confirmed) | {"requestId": request.request_id})
    begun = service.start(env.claims, request, signed_start(env, request), quote["authorizationToken"])["execution"]
    with pytest.raises(ExecutionRuntimeError, match="capability_unavailable"):
        apply(env, operation(env, "CLAIM", begun))
    forged_lease = {"platform_run_id": begun["platform_runs"][0]["platform_run_id"],
        "lease_id": str(uuid4()), "execution_generation": 1}
    candidate = batch(env, begun, forged_lease)
    with env.db.connect() as connection, pytest.raises(ExecutionRuntimeError, match="capability_unavailable"):
        guard(env, connection.cursor(), candidate)
    with pytest.raises(ExecutionRuntimeError, match="capability_unavailable"):
        apply(env, request)


def test_quote_and_request_uniqueness_roll_back_whole_start(real_strategy_env):
    env = real_strategy_env
    _, _, _, _, _, confirmed = _confirmed_research(env)
    env.snapshot = confirmed["snapshot"]
    quote_service, service = services(env)
    with env.admin.connect() as conn:
        before = conn.execute("SELECT count(*) FROM pilot_collection_tasks WHERE tenant_id=%s", (env.tenant,)).fetchone()[0]
    first = start(env)
    second = first.model_copy(update={"request_id": str(uuid4())})
    quote_request_id = str(uuid4())
    assert quote_request_id not in (first.request_id, second.request_id)
    quote = quote_service.quote(env.claims, _request(env, confirmed) | {"requestId": quote_request_id})
    service.start(env.claims, first, signed_start(env, first), quote["authorizationToken"])
    with pytest.raises(ExecutionRuntimeError):
        service.start(env.claims, second, signed_start(env, second), quote["authorizationToken"])
    with env.admin.connect() as conn:
        assert conn.execute("SELECT count(*) FROM pilot_collection_tasks WHERE tenant_id=%s", (env.tenant,)).fetchone()[0] == before + 1


def test_concurrent_same_quote_different_request_leaves_one_complete_start(real_strategy_env):
    env = real_strategy_env
    _, _, _, _, _, confirmed = _confirmed_research(env)
    env.snapshot = confirmed["snapshot"]
    quote_service, service = services(env)
    first = start(env)
    second = first.model_copy(update={"request_id": str(uuid4())})
    quote_request_id = str(uuid4())
    assert quote_request_id not in (first.request_id, second.request_id)
    quote = quote_service.quote(env.claims, _request(env, confirmed) | {"requestId": quote_request_id})
    with env.admin.connect() as conn:
        before = conn.execute("SELECT count(*) FROM pilot_collection_tasks WHERE tenant_id=%s", (env.tenant,)).fetchone()[0]

    def run(request):
        try:
            return service.start(env.claims, request, signed_start(env, request), quote["authorizationToken"])
        except ExecutionRuntimeError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, (first, second)))
    assert sum(type(value) is dict for value in results) == 1
    assert "request_conflict" in results
    with env.admin.connect() as conn:
        assert conn.execute("SELECT count(*) FROM pilot_research_reservations WHERE quote_id=%s", (quote["quoteId"],)).fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM pilot_collection_tasks WHERE tenant_id=%s", (env.tenant,)).fetchone()[0] == before + 1


def test_final_session_fence_failure_rolls_back_reservation_task_run_and_receipt(real_strategy_env, monkeypatch):
    env = real_strategy_env
    _, _, _, _, _, confirmed = _confirmed_research(env)
    env.snapshot = confirmed["snapshot"]
    quote_service, service = services(env)
    request = start(env)
    quote = quote_service.quote(env.claims, _request(env, confirmed) | {"requestId": request.request_id})
    original = env.runtime._active

    def expire_after_all_writes(cursor, claims):
        cursor.execute("SELECT EXISTS(SELECT 1 FROM pilot_research_reservations WHERE request_id=%s),"
            "EXISTS(SELECT 1 FROM pilot_execution_operations WHERE request_id=%s)",
            (request.request_id, request.request_id))
        if cursor.fetchone() == (True, True):
            raise ExecutionRuntimeError("invalid_session", 401)
        return original(cursor, claims)

    monkeypatch.setattr(env.runtime, "_active", expire_after_all_writes)
    with pytest.raises(ExecutionRuntimeError, match="invalid_session"):
        service.start(env.claims, request, signed_start(env, request), quote["authorizationToken"])
    with env.admin.connect() as conn:
        for table in ("pilot_research_reservations", "pilot_execution_operations"):
            assert conn.execute(f"SELECT count(*) FROM {table} WHERE request_id=%s", (request.request_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM pilot_collection_tasks WHERE task_id NOT IN "
            "(SELECT task_id FROM pilot_execution_operations)").fetchone()[0] == 0


def test_new_start_rechecks_current_strategy_but_historical_recovery_does_not(real_strategy_env):
    env = real_strategy_env
    _, _, _, _, _, confirmed = _confirmed_research(env)
    env.snapshot = confirmed["snapshot"]
    quote_service, service = services(env)
    historical = start(env)
    historical_quote = quote_service.quote(env.claims,
        _request(env, confirmed) | {"requestId": historical.request_id})
    receipt = service.start(env.claims, historical, signed_start(env, historical),
                            historical_quote["authorizationToken"])
    env.strategies.revoke(env.claims, revoke_body(confirmed))
    assert service.get_receipt(env.claims, historical.request_id) == receipt
    assert service.start(env.claims, historical, signed_start(env, historical),
                         historical_quote["authorizationToken"]) == receipt
    fresh = historical.model_copy(update={"request_id": str(uuid4())})
    with pytest.raises(ExecutionRuntimeError, match="strategy_conflict"):
        service.start(env.claims, fresh, signed_start(env, fresh), historical_quote["authorizationToken"])


def test_expired_and_rule_changed_quotes_cannot_authorize_new_start(real_strategy_env):
    env = real_strategy_env
    _, _, _, _, _, confirmed = _confirmed_research(env)
    env.snapshot = confirmed["snapshot"]
    quote_service, service = services(env)
    request = start(env)
    quote = quote_service.quote(env.claims, _request(env, confirmed) | {"requestId": request.request_id})
    token = quote["authorizationToken"]
    encoded, _ = token.split(".")
    payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    expired = datetime.now(UTC) - timedelta(minutes=10)
    payload["generatedAt"] = expired.isoformat()
    payload["expiresAt"] = (expired + timedelta(seconds=300)).isoformat()
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    secret = b"restricted-postgres-review-key!" * 2
    signature = hmac.new(secret, b"yike-research-quote-v1\0" + raw, hashlib.sha256).digest()
    expired_token = (base64.urlsafe_b64encode(raw).rstrip(b"=").decode() + "." +
                     base64.urlsafe_b64encode(signature).rstrip(b"=").decode())
    with pytest.raises(ExecutionRuntimeError, match="quote_invalid"):
        service.start(env.claims, request, signed_start(env, request), expired_token)
    quote_service.rule = ResearchQuoteRule("changed-rule-v2", 100, 200, 300)
    with pytest.raises(ExecutionRuntimeError, match="quote_invalid"):
        service.start(env.claims, request, signed_start(env, request), token)


def test_start_rechecks_dedicated_research_capability(real_strategy_env):
    env = real_strategy_env
    _, _, _, _, _, confirmed = _confirmed_research(env)
    env.snapshot = confirmed["snapshot"]
    quote_service, service = services(env)
    request = start(env)
    quote = quote_service.quote(env.claims, _request(env, confirmed))
    quote_service.research_capability = lambda _snapshot: False
    with pytest.raises(ExecutionRuntimeError, match="capability_unavailable"):
        service.start(env.claims, request, signed_start(env, request), quote["authorizationToken"])
    with env.admin.connect() as conn:
        assert conn.execute("SELECT count(*) FROM pilot_research_reservations WHERE quote_id=%s", (quote["quoteId"],)).fetchone()[0] == 0


def test_research_entry_rejects_historical_ordinary_start(env):
    request = start(env)
    ordinary = apply(env, request)
    service = ResearchExecutionService(env.runtime, object())
    with pytest.raises(ExecutionRuntimeError, match="request_conflict"):
        service.start(env.claims, request, signed_start(env, request), "not-a-quote")
    assert env.runtime.get_receipt(env.claims, request.request_id) == ordinary


def test_source_revoked_after_quote_rejects_fresh_start_without_writes(real_strategy_env):
    env = real_strategy_env
    review, candidate, assessed, check, _, confirmed = _confirmed_research(env)
    env.snapshot = confirmed["snapshot"]
    quote_service, service = services(env)
    request = start(env)
    quote = quote_service.quote(env.claims, _request(env, confirmed))
    from tests.test_candidate_review_postgres import assessment, review_payload
    review.review(env.claims, review_payload(candidate, "EXCLUDE",
        assessmentId=assessed["assessment"]["id"], sourceVerificationId=check["id"],
        humanConfirmed=True, evidence=assessment()["evidence"], reason="撤销来源认可"))
    before = write_counts(env)
    with pytest.raises(ExecutionRuntimeError, match="strategy_conflict"):
        service.start(env.claims, request, signed_start(env, request), quote["authorizationToken"])
    assert write_counts(env) == before


def test_start_and_get_are_isolated_from_second_user_and_tenant(real_strategy_env):
    env = real_strategy_env
    _, _, _, _, _, confirmed = _confirmed_research(env)
    env.snapshot = confirmed["snapshot"]
    quote_service, service = services(env)
    request = start(env)
    quote = quote_service.quote(env.claims, _request(env, confirmed))
    receipt = service.start(env.claims, request, signed_start(env, request), quote["authorizationToken"])
    before = write_counts(env)
    for user in (env.users[1], env.users[2]):
        stranger = verify_token_claims(issue_token(user, SECRET), SECRET)
        with pytest.raises(ExecutionRuntimeError) as start_error:
            service.start(stranger, request, signed_start(env, request), quote["authorizationToken"])
        assert start_error.value.code in {"device_unavailable", "request_conflict"}
        with pytest.raises(ExecutionRuntimeError) as get_error:
            service.get_receipt(stranger, request.request_id)
        assert (get_error.value.code, get_error.value.status) == ("request_not_found", 404)
    assert service.get_receipt(env.claims, request.request_id) == receipt
    assert write_counts(env) == before


def test_same_request_rejects_a_second_valid_quote_and_cancel_read_remain_available(real_strategy_env):
    env = real_strategy_env
    _, _, _, _, _, confirmed = _confirmed_research(env)
    env.snapshot = confirmed["snapshot"]
    quote_service, service = services(env)
    request = start(env)
    first = quote_service.quote(env.claims, _request(env, confirmed))
    second = quote_service.quote(env.claims, _request(env, confirmed) | {"requestId": str(uuid4())})
    receipt = service.start(env.claims, request, signed_start(env, request), first["authorizationToken"])
    before = write_counts(env)
    with pytest.raises(ExecutionRuntimeError, match="request_conflict"):
        service.start(env.claims, request, signed_start(env, request), second["authorizationToken"])
    assert write_counts(env) == before
    cancelled = apply(env, operation(env, "CANCEL", receipt["execution"]))
    assert cancelled["status"] == "CANCELED" and cancelled["stop_confirmed"] is True
    assert env.runtime.get_task(env.claims, receipt["execution"]["task_id"])["status"] == "CANCELED"
    assert service.get_receipt(env.claims, request.request_id) == receipt


def test_fresh_research_snapshot_through_ordinary_entry_rolls_back(real_strategy_env):
    env = real_strategy_env
    _, _, _, _, _, confirmed = _confirmed_research(env)
    env.snapshot = confirmed["snapshot"]
    request = start(env)
    before = write_counts(env)
    with pytest.raises(ExecutionRuntimeError, match="capability_unavailable"):
        apply(env, request)
    assert write_counts(env) == before


def test_normal_strategy_with_unrelated_valid_research_quote_is_fixed_conflict_and_rollback(real_strategy_env):
    env = real_strategy_env
    _, _, _, _, _, research = _confirmed_research(env)
    quote_service, service = services(env)
    quote = quote_service.quote(env.claims, _request(env, research))
    pending = env.strategies.prepare(env.claims, prepare_body(env,
        configuration=configuration(research=None)))
    normal = env.strategies.confirm(env.claims, confirm_body(pending))
    env.snapshot = normal["snapshot"]
    request = start(env)
    before = write_counts(env)
    with pytest.raises(ExecutionRuntimeError, match="strategy_conflict"):
        service.start(env.claims, request, signed_start(env, request), quote["authorizationToken"])
    assert write_counts(env) == before
