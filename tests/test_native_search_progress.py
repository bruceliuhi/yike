import copy
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
import psycopg
from nacl.signing import SigningKey
from psycopg import sql
from pydantic import ValidationError

from pilot.auth import issue_token, verify_token_claims
from pilot.candidate_ingestion import CandidateIngestionStore
from pilot.db import PilotDatabase
from pilot.device_credentials import DeviceCredentialStore
from pilot.execution_contract import ExecutionOperation, ExecutionRuntimeError
from pilot.execution_runtime import ExecutionRuntime, execution_signing_payload
from pilot.foreground_collection import configured_collection_policy
from pilot.monitor_plans import MonitorPlanStore
from pilot.monitor_runtime import MonitorRuntime
from pilot.native_search_cursor import advance_cursor
from pilot.research_strategies import ResearchStrategyStore
from pilot.store import PilotStore
from tests.test_execution_api import operation_payload
from tests.test_candidate_contract import NOW, batch
from tests.test_public_sampling_progress import _authenticated_https_client, _support_client
from tests.test_execution_api import auth_headers
from tests.test_candidate_ingestion_postgres import submit
from tests.test_device_credentials_postgres import RoleDatabase, bind
from tests.test_device_keys import encoded
from tests.test_monitor_runtime_postgres import force_due_window, runtime_pulse
from tests.test_research_strategies_postgres import configuration, confirm_body, prepare_body


def native_batch_progress(**changes):
    value = {
        "schema_version": "native-search-progress-v1",
        "adapter_version": "bili-search-items-v1",
        "claim_request_id": str(uuid4()),
        "queries": [{
            "query": "采购线索",
            "revision": 0,
            "base_batch_request_id": None,
            "before": {"page": 1, "consumed_ids": [], "refresh_next": False},
            "after": {"page": 1, "consumed_ids": [], "refresh_next": True},
            "page_ids": ["1"],
            "processed_ids": ["1"],
            "has_more": False,
            "comments_scope": "BOUNDED_SAMPLE",
        }],
    }
    value.update(changes)
    return value


def xhs_native_batch_progress(**changes):
    value = native_batch_progress()
    value["adapter_version"] = "xhs-search-items-v1"
    value["queries"][0].update(
        before={"page": 1, "search_id": "search-1", "consumed_ids": [], "refresh_next": False},
        after={"page": 1, "search_id": "search-1", "consumed_ids": [], "refresh_next": True},
        page_ids=["note-1"], processed_ids=["note-1"],
    )
    value.update(changes)
    return value


def test_legacy_claim_bytes_remain_unchanged():
    body = operation_payload("CLAIM")
    operation = ExecutionOperation.model_validate(body)
    before = operation.model_dump(mode="json")

    assert before == body
    assert "native_progress_version" not in before
    assert "native_progress" not in before


def test_legacy_batch_bytes_and_fingerprint_remain_unchanged():
    from pilot.candidate_contract import batch_fingerprint, validate_candidate_batch

    parsed = validate_candidate_batch(batch(), now=NOW)

    assert parsed.model_dump(mode="json") == batch()
    assert batch_fingerprint(parsed) == "7b9308176c6656c399d67ac5c24893cc56ab74bbb14e9d090b9bdcce5cc2cfb3"


def test_native_version_is_claim_only_exact_and_mutually_exclusive():
    body = operation_payload("CLAIM") | {"native_progress_version": 1}

    assert ExecutionOperation.model_validate(body).model_dump(mode="json") == body
    for value in (None, True, 0, 2, "1"):
        with pytest.raises((ValidationError, ExecutionRuntimeError)):
            ExecutionOperation.model_validate(operation_payload("CLAIM") | {"native_progress_version": value})
    with pytest.raises((ValidationError, ExecutionRuntimeError)):
        ExecutionOperation.model_validate(body | {"public_sampling_version": 1})
    for name in ("START", "RENEW", "CANCEL", "FINISH"):
        with pytest.raises((ValidationError, ExecutionRuntimeError)):
            ExecutionOperation.model_validate(operation_payload(name) | {"native_progress_version": 1})


def test_batch_native_progress_is_signed_and_round_trips_exactly():
    from pilot.candidate_contract import batch_fingerprint, validate_candidate_batch

    payload = batch(native_progress=native_batch_progress())
    parsed = validate_candidate_batch(payload, now=NOW)

    assert parsed.model_dump(mode="json") == payload
    assert batch_fingerprint(parsed) != "7b9308176c6656c399d67ac5c24893cc56ab74bbb14e9d090b9bdcce5cc2cfb3"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update(schema_version="wrong"),
        lambda value: value.update(adapter_version="wrong"),
        lambda value: value.update(claim_request_id="not-a-uuid"),
        lambda value: value.update(queries=[]),
        lambda value: value["queries"].append(copy.deepcopy(value["queries"][0])),
        lambda value: value["queries"][0].update(query=""),
        lambda value: value["queries"][0].update(query=" 前后空格"),
        lambda value: value["queries"][0].update(query="逗号,拆词"),
        lambda value: value["queries"][0].update(revision=True),
        lambda value: value["queries"][0].update(revision=0, base_batch_request_id="batch-1"),
        lambda value: value["queries"][0].update(revision=1, base_batch_request_id=None),
        lambda value: value["queries"][0].update(processed_ids=[]),
        lambda value: value["queries"][0].update(after={"page": 2, "consumed_ids": [], "refresh_next": True}),
        lambda value: value["queries"][0].update(comments_scope="FULL_TREE"),
        lambda value: value["queries"][0].update(extra=True),
    ],
)
def test_batch_native_progress_rejects_invalid_shapes_and_cursor_math(mutate):
    from pilot.candidate_contract import CandidateContractError, validate_candidate_batch

    progress = native_batch_progress()
    mutate(progress)
    with pytest.raises(CandidateContractError, match="INVALID_BATCH"):
        validate_candidate_batch(batch(native_progress=progress), now=NOW)


def test_batch_native_progress_is_supported_for_account_platforms_only():
    from pilot.candidate_contract import CandidateContractError, validate_candidate_batch
    from tests.test_candidate_contract import anonymous_execution

    with pytest.raises(CandidateContractError, match="INVALID_BATCH"):
        validate_candidate_batch(batch(
            platform="DOUYIN", records=[], native_progress=native_batch_progress()
        ), now=NOW)
    with pytest.raises(CandidateContractError, match="INVALID_BATCH"):
        validate_candidate_batch(batch(
            platform="PUBLIC_WEB", execution=anonymous_execution(), records=[],
            native_progress=native_batch_progress(),
        ), now=NOW)
    assert validate_candidate_batch(batch(
        platform="XIAOHONGSHU", records=[], native_progress=xhs_native_batch_progress(),
    ), now=NOW).native_progress.adapter_version == "xhs-search-items-v1"


def test_xhs_cursor_preserves_search_id_across_page_and_refresh():
    before = {"page": 2, "search_id": "search-1", "consumed_ids": [], "refresh_next": False}
    assert advance_cursor(before, ["note-1", "note-2"], ["note-1"], True) == {
        "page": 2, "search_id": "search-1", "consumed_ids": ["note-1"], "refresh_next": True,
    }
    assert advance_cursor(
        {"page": 2, "search_id": "search-1", "consumed_ids": ["note-1"], "refresh_next": True},
        ["note-1", "note-2"], ["note-1", "note-2"], True,
    ) == {"page": 2, "search_id": "search-1", "consumed_ids": ["note-1"], "refresh_next": False}
    assert advance_cursor(
        {"page": 2, "search_id": "search-1", "consumed_ids": ["note-1"], "refresh_next": False},
        ["note-1", "note-2"], ["note-2"], True,
    ) == {"page": 3, "search_id": "search-1", "consumed_ids": [], "refresh_next": True}


@pytest.mark.parametrize("mode", [
    "three-platform-monitor-v1",
    "four-platform-monitor-v1",
    "four-platform-public-monitor-v1",
    "four-platform-public-sampling-monitor-v1",
    "four-platform-public-node-monitor-v1",
    "four-platform-public-project-monitor-v1",
    "four-platform-public-bili-links-monitor-v1",
])
def test_support_advertises_native_progress_only_for_existing_search_monitor_policies(mode):
    client, _ = _support_client(mode)

    legacy = client.get("/api/ui/execution-support", headers=auth_headers()).json()
    negotiated = client.get(
        "/api/ui/execution-support?native_progress_version=1", headers=auth_headers()
    )

    assert negotiated.status_code == 200
    assert negotiated.json() == legacy | {"native_progress": ["BILIBILI", "XIAOHONGSHU"]}


def test_support_does_not_advertise_native_progress_for_once():
    mode = "four-platform-foreground-v1"
    client, _ = _support_client(mode)

    legacy = client.get("/api/ui/execution-support", headers=auth_headers()).json()
    response = client.get(
        "/api/ui/execution-support?native_progress_version=1", headers=auth_headers()
    )

    assert response.status_code == 200
    assert response.json() == legacy


@pytest.mark.parametrize("query", [
    "native_progress_version=2",
    "native_progress_version=1&native_progress_version=1",
    "native_progress_version=1&sampling_version=1",
])
def test_support_rejects_non_exact_native_progress_queries(query):
    client, _ = _support_client("four-platform-monitor-v1")

    response = client.get("/api/ui/execution-support?" + query, headers=auth_headers())

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_request"


def test_cursor_accepts_only_exact_plain_json_shape():
    from pilot.native_search_cursor import checked_cursor

    value = {"page": 7, "consumed_ids": ["1", "20"], "refresh_next": True}
    result = checked_cursor(value)

    assert result == value
    assert result is not value
    assert result["consumed_ids"] is not value["consumed_ids"]
    assert type(result) is dict and type(result["consumed_ids"]) is list


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {"page": 1, "consumed_ids": [], "refresh_next": False, "extra": 1},
        {"page": True, "consumed_ids": [], "refresh_next": False},
        {"page": 0, "consumed_ids": [], "refresh_next": False},
        {"page": 1001, "consumed_ids": [], "refresh_next": False},
        {"page": 1, "consumed_ids": (), "refresh_next": False},
        {"page": 1, "consumed_ids": ["0"], "refresh_next": False},
        {"page": 1, "consumed_ids": ["01"], "refresh_next": False},
        {"page": 1, "consumed_ids": ["1", "1"], "refresh_next": False},
        {"page": 1, "consumed_ids": ["1" * 21], "refresh_next": False},
        {"page": 1, "consumed_ids": [str(index + 1) for index in range(21)], "refresh_next": False},
        {"page": 1, "consumed_ids": [], "refresh_next": 1},
    ],
)
def test_cursor_rejects_invalid_values(value):
    from pilot.native_search_cursor import checked_cursor

    with pytest.raises(ValueError):
        checked_cursor(value)


def test_continue_keeps_partial_page_and_uses_page_order_for_consumed_ids():
    from pilot.native_search_cursor import advance_cursor

    before = {"page": 3, "consumed_ids": ["3", "1"], "refresh_next": False}

    assert advance_cursor(before, ["1", "2", "3", "4"], ["2"], True) == {
        "page": 3,
        "consumed_ids": ["1", "2", "3"],
        "refresh_next": True,
    }


def test_continue_advances_only_after_whole_page_is_consumed_and_resets_at_end():
    from pilot.native_search_cursor import advance_cursor

    assert advance_cursor(
        {"page": 4, "consumed_ids": ["1"], "refresh_next": False},
        ["1", "2"],
        ["2"],
        True,
    ) == {"page": 5, "consumed_ids": [], "refresh_next": True}
    assert advance_cursor(
        {"page": 4, "consumed_ids": [], "refresh_next": False}, [], [], False
    ) == {"page": 1, "consumed_ids": [], "refresh_next": True}
    assert advance_cursor(
        {"page": 1000, "consumed_ids": [], "refresh_next": False}, ["9"], ["9"], True
    ) == {"page": 1, "consumed_ids": [], "refresh_next": True}


def test_refresh_preserves_continuation_position_and_only_flips_phase():
    from pilot.native_search_cursor import advance_cursor

    before = {"page": 8, "consumed_ids": ["7", "8"], "refresh_next": True}

    assert advance_cursor(before, ["100", "101"], ["100", "101"], True) == {
        "page": 8,
        "consumed_ids": ["7", "8"],
        "refresh_next": False,
    }


@pytest.mark.parametrize(
    "before,page_ids,processed_ids,has_more",
    [
        ({"page": 1, "consumed_ids": [], "refresh_next": False}, ["1"], [], False),
        ({"page": 1, "consumed_ids": [], "refresh_next": False}, ["1", "2"], ["2"], False),
        ({"page": 1, "consumed_ids": ["1"], "refresh_next": False}, ["1", "2"], ["1"], False),
        ({"page": 1, "consumed_ids": [], "refresh_next": True}, ["1", "2"], ["2"], False),
        ({"page": 1, "consumed_ids": [], "refresh_next": True}, ["1"], [], False),
        ({"page": 1, "consumed_ids": [], "refresh_next": False}, [], [], True),
        ({"page": 1, "consumed_ids": [], "refresh_next": False}, ["1", "1"], ["1"], False),
        ({"page": 1, "consumed_ids": [], "refresh_next": False}, ["1"], ["1", "1"], False),
        ({"page": 1, "consumed_ids": [], "refresh_next": False}, ["1"], ["1"], 1),
        ({"page": 1, "consumed_ids": [], "refresh_next": False}, [str(i) for i in range(1, 22)], ["1"], True),
        ({"page": 1, "consumed_ids": [], "refresh_next": False}, [str(i) for i in range(1, 7)], [str(i) for i in range(1, 7)], True),
    ],
)
def test_advance_rejects_invalid_page_and_processing_claims(before, page_ids, processed_ids, has_more):
    from pilot.native_search_cursor import advance_cursor

    with pytest.raises(ValueError):
        advance_cursor(before, page_ids, processed_ids, has_more)


@pytest.fixture(scope="module")
def native_databases():
    value = os.environ.get("YIKE_NATIVE_PROGRESS_TEST_DATABASE_URL")
    if not value:
        pytest.skip("dedicated native-progress PostgreSQL required")
    url = urlsplit(value)
    assert url.hostname == "127.0.0.1" and url.path == "/yike_native_progress_task1"
    admin = PilotDatabase(value)
    admin.migrate()
    admin.migrate()
    role = "native_progress_" + uuid4().hex
    root = Path(__file__).parents[1]
    with admin.connect() as connection:
        connection.execute(sql.SQL(
            "CREATE ROLE {} NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION"
        ).format(sql.Identifier(role)))
        connection.execute("SELECT set_config('yike.app_role',%s,true)", (role,))
        for line in (root / "deploy/grant_runtime.sql").read_text().splitlines():
            if line.startswith("\\ir "):
                grant = root / "deploy" / line.split()[1]
                connection.execute(grant.read_text())
    yield admin, RoleDatabase(admin, role), role
    with admin.connect() as connection:
        connection.execute(sql.SQL("DROP OWNED BY {}") .format(sql.Identifier(role)))
        connection.execute(sql.SQL("DROP ROLE {}") .format(sql.Identifier(role)))


def _native_env(databases, *, tenant=None, label="main", max_records=10, platform="BILIBILI"):
    admin, database, _ = databases
    provisioner = PilotStore(admin)
    tenant = tenant or provisioner.provision_tenant("synthetic-native-progress-" + label)
    user = provisioner.provision_user(tenant, f"{uuid4()}@example.invalid")
    token = issue_token(user, "synthetic-public-sampling")
    claims = verify_token_claims(token, "synthetic-public-sampling")
    store = PilotStore(database)
    device = store.register_device(user, "synthetic-native-progress")["device_id"]
    key = SigningKey.generate()
    bind(SimpleNamespace(service=DeviceCredentialStore(database), claims=claims, device=device), key)
    connection = store.connect_platform(user, platform, device, "synthetic-account", "vault://synthetic")
    with admin.connect() as db:
        db.execute("UPDATE pilot_platform_connections SET status='CONNECTED' WHERE connection_id=%s",
                   (connection["connection_id"],))
        connection["connection_version"] = db.execute(
            "SELECT connection_version FROM pilot_platform_connections WHERE connection_id=%s",
            (connection["connection_id"],),
        ).fetchone()[0]
    profile = provisioner.save_profile(user, {"description": "合成" + platform + "进度"})["version_id"]
    provisioner.confirm_profile(user, profile)
    schedule = {
        "kind": "interval", "times": [], "interval": 1, "start": "00:00", "end": "23:59",
        "timezone": "UTC", "policyVersion": 1,
    }
    config = configuration(
        name="合成" + platform + "进度", mode="monitor", schedule=schedule,
        keywords=["全局词"], exclusions=[],
        platformQueries={"version": "platform-queries-v1", "items": [{
            "platform": platform, "keywords": ["设备采购", "工厂改造"],
        }]},
    )
    strategies = ResearchStrategyStore(database)
    seed = SimpleNamespace(profile=profile)
    prepared = strategies.prepare(claims, prepare_body(
        seed, configuration=config, platforms=[platform], max_records=max_records,
    ))
    confirmed = strategies.confirm(claims, confirm_body(prepared))
    plans = MonitorPlanStore(database, strategy_resolver=strategies.resolve)
    plan = plans.create(claims, {
        "schema_version": "monitor-plans-v1", "request_id": str(uuid4()),
        "profile_version_id": profile, "strategy_version_id": confirmed["strategy_version_id"],
        "human_confirmed": True,
    })["plan"]
    execution = ExecutionRuntime(
        database, strategy_resolver=strategies.resolve,
        capability_check=configured_collection_policy({
            "YIKE_PILOT_COLLECTION_MODE": "three-platform-monitor-v1",
        }),
    )
    monitor = MonitorRuntime(database, execution)
    execution.monitor_runtime = monitor
    target = {
        "platform": platform, "access_mode": "PLATFORM_ACCOUNT",
        "connection_id": connection["connection_id"],
        "connection_version": connection["connection_version"],
    }
    return SimpleNamespace(
        admin=admin, db=database, store=store, tenant=tenant, user=user, token=token,
        claims=claims, device=device, key=key, profile=profile, snapshot=confirmed["snapshot"],
        plan=plan, execution=execution, monitor=monitor, target=target,
    )


def _signed_apply(env, body):
    operation = ExecutionOperation.model_validate(body)
    signature = encoded(env.key.sign(execution_signing_payload(
        tenant_id=env.tenant, claims=env.claims, operation=operation,
    ).encode()).signature)
    return env.execution.apply(env.claims, operation, signature)


def _begin_native_claim(env, *, client=None):
    session = str(uuid4())
    env.monitor.pulse(env.claims, runtime_pulse(env, monitor_session_id=session))
    force_due_window(env)
    ready = env.monitor.pulse(env.claims, runtime_pulse(env, monitor_session_id=session))
    begun = _signed_apply(env, ready["occurrence"]["start_request"])
    request = {
        "schema_version": "execution-runtime-v1", "request_id": str(uuid4()),
        "operation": "CLAIM", "device_id": env.device, "credential_version": 1,
        "profile_version_id": None, "strategy_version_id": None,
        "configuration_sha256": None, "targets": None,
        "task_id": begun["task_id"], "platform_run_id": begun["platform_runs"][0]["platform_run_id"],
        "lease_id": None, "execution_generation": None, "native_progress_version": 1,
    }
    if client is None:
        return begun, request, _signed_apply(env, request)
    operation = ExecutionOperation.model_validate(request)
    signature = encoded(env.key.sign(execution_signing_payload(
        tenant_id=env.tenant, claims=env.claims, operation=operation,
    ).encode()).signature)
    response = client.post("/api/ui/execution-operations", json={"request": request, "signature": signature})
    assert response.status_code == 200, response.text
    return begun, request, response.json()


def _native_batch(env, begun, lease, *, request_id=None, query_count=1, page_ids=("1",), processed_ids=("1",), has_more=False):
    queries = []
    for frozen in lease["native_progress"]["queries"][:query_count]:
        after = advance_cursor(frozen["cursor"], list(page_ids), list(processed_ids), has_more)
        queries.append({
            "query": frozen["query"], "revision": frozen["revision"],
            "base_batch_request_id": frozen["base_batch_request_id"],
            "before": frozen["cursor"], "after": after,
            "page_ids": list(page_ids), "processed_ids": list(processed_ids),
            "has_more": has_more, "comments_scope": "BOUNDED_SAMPLE",
        })
    return {
        "schema_version": "candidate-upload-v1", "request_id": request_id or str(uuid4()),
        "platform": env.target["platform"], "profile_version_id": env.profile,
        "strategy_version_id": env.snapshot["strategy_version_id"],
        "execution": {
            "device_id": env.device, "task_id": begun["task_id"], "run_id": begun["run_id"],
            "platform_run_id": lease["platform_run_id"], "lease_id": lease["lease_id"],
            "credential_version": 1, "execution_generation": lease["execution_generation"],
            "access_mode": "PLATFORM_ACCOUNT", "connection_id": env.target["connection_id"],
            "connection_version": env.target["connection_version"],
        },
        "records": [],
        "native_progress": {
            "schema_version": "native-search-progress-v1",
            "adapter_version": "bili-search-items-v1" if env.target["platform"] == "BILIBILI" else "xhs-search-items-v1",
            "claim_request_id": lease["request_id"], "queries": queries,
        },
    }


def _finish_native(env, begun, lease, upload_request_id):
    return _signed_apply(env, {
        "schema_version": "execution-runtime-v1", "request_id": str(uuid4()), "operation": "FINISH",
        "device_id": env.device, "credential_version": 1, "profile_version_id": None,
        "strategy_version_id": None, "configuration_sha256": None, "targets": None,
        "task_id": begun["task_id"], "platform_run_id": lease["platform_run_id"],
        "lease_id": lease["lease_id"], "execution_generation": lease["execution_generation"],
        "upload_request_id": upload_request_id,
    })


@pytest.fixture(scope="module")
def native_env(native_databases):
    return _native_env(native_databases)


@pytest.fixture(scope="module")
def native_xhs_env(native_databases):
    return _native_env(native_databases, label="xhs", platform="XIAOHONGSHU")


def test_real_pg_claim_empty_batch_head_commit_replay_and_next_claim(native_env):
    env = native_env
    begun0, request0, lease0 = _begin_native_claim(env)
    assert lease0["native_progress"] == {
        "schema_version": "native-search-progress-v1", "adapter_version": "bili-search-items-v1",
        "plan_id": env.plan["plan_id"], "queries": [
            {"query": query, "revision": 0, "base_batch_request_id": None,
             "cursor": {"page": 1, "consumed_ids": [], "refresh_next": False}}
            for query in ("设备采购", "工厂改造")
        ],
    }
    assert _signed_apply(env, request0) == lease0
    first = _native_batch(env, begun0, lease0)
    receipt0 = submit(env, CandidateIngestionStore(env.db, env.execution), first)
    assert receipt0["accepted_count"] == 0
    assert receipt0["native_progress"] == first["native_progress"]
    assert submit(env, CandidateIngestionStore(env.db, env.execution), first) == receipt0
    assert env.execution.get_task(env.claims, begun0["task_id"])["status"] == "RUNNING"
    with env.admin.connect() as connection:
        assert connection.execute(
            "SELECT revision,head_batch_request_id,cursor FROM pilot_native_search_progress "
            "WHERE tenant_id=%s AND owner_user_id=%s",
            (env.tenant, env.user),
        ).fetchone() == (1, first["request_id"], first["native_progress"]["queries"][0]["after"])
    _finish_native(env, begun0, lease0, first["request_id"])
    begun1, _, lease1 = _begin_native_claim(env)
    assert lease1["native_progress"]["queries"][0] == {
        "query": "设备采购", "revision": 1, "base_batch_request_id": first["request_id"],
        "cursor": first["native_progress"]["queries"][0]["after"],
    }
    assert lease1["native_progress"]["queries"][1]["revision"] == 0
    second = _native_batch(env, begun1, lease1, page_ids=("9",), processed_ids=("9",))
    receipt1 = submit(env, CandidateIngestionStore(env.db, env.execution), second)
    assert receipt1["native_progress"] == second["native_progress"]
    _finish_native(env, begun1, lease1, second["request_id"])


def test_real_pg_xhs_claim_commit_keeps_search_id_across_restart(native_xhs_env):
    env = native_xhs_env
    begun0, _, lease0 = _begin_native_claim(env)
    assert lease0["native_progress"]["adapter_version"] == "xhs-search-items-v1"
    first_cursor = lease0["native_progress"]["queries"][0]["cursor"]
    assert first_cursor["search_id"] and first_cursor["page"] == 1
    first = _native_batch(env, begun0, lease0, page_ids=("note-1",), processed_ids=("note-1",), has_more=True)
    receipt0 = submit(env, CandidateIngestionStore(env.db, env.execution), first)
    assert receipt0["native_progress"]["adapter_version"] == "xhs-search-items-v1"
    _finish_native(env, begun0, lease0, first["request_id"])
    begun1, _, lease1 = _begin_native_claim(env)
    resumed = lease1["native_progress"]["queries"][0]["cursor"]
    assert resumed["search_id"] == first_cursor["search_id"]
    assert resumed["page"] == 2 and resumed["refresh_next"] is True
    second = _native_batch(env, begun1, lease1, page_ids=("note-2",), processed_ids=("note-2",), has_more=False)
    assert submit(env, CandidateIngestionStore(env.db, env.execution), second)["accepted_count"] == 0
    _finish_native(env, begun1, lease1, second["request_id"])


def test_real_pg_same_head_concurrent_batches_only_one_commits(native_env):
    env = native_env
    begun, _, lease = _begin_native_claim(env)
    values = [_native_batch(env, begun, lease, request_id=str(uuid4())) for _ in range(2)]
    store = CandidateIngestionStore(env.db, env.execution)

    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(submit, env, store, value) for value in values]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(("ok", future.result(timeout=20)))
            except ExecutionRuntimeError as error:
                outcomes.append((error.code, None))
    assert sorted(kind for kind, _ in outcomes) == ["native_progress_conflict", "ok"]
    winner = next(receipt for kind, receipt in outcomes if kind == "ok")
    with env.admin.connect() as connection:
        assert connection.execute(
            "SELECT revision,head_batch_request_id FROM pilot_native_search_progress "
            "WHERE tenant_id=%s AND owner_user_id=%s AND query='设备采购'",
            (env.tenant, env.user),
        ).fetchone() == (3, winner["request_id"])
        assert connection.execute(
            "SELECT count(*) FROM pilot_candidate_batches WHERE tenant_id=%s AND owner_user_id=%s "
            "AND platform_run_id=%s",
            (env.tenant, env.user, lease["platform_run_id"]),
        ).fetchone() == (1,)
    _finish_native(env, begun, lease, winner["request_id"])


def test_real_pg_final_fence_failure_rolls_back_batch_and_head(native_env):
    env = native_env
    begun, _, lease = _begin_native_claim(env)
    value = _native_batch(env, begun, lease)
    before = lease["native_progress"]["queries"][0]
    original = env.execution.recheck_submission_fence

    def fail_after_writes(cursor, claims, *, batch):
        raise ExecutionRuntimeError("synthetic_final_fence", 409)

    env.execution.recheck_submission_fence = fail_after_writes
    try:
        with pytest.raises(ExecutionRuntimeError, match="synthetic_final_fence"):
            submit(env, CandidateIngestionStore(env.db, env.execution), value)
    finally:
        env.execution.recheck_submission_fence = original
    with env.admin.connect() as connection:
        assert connection.execute(
            "SELECT revision,head_batch_request_id,cursor FROM pilot_native_search_progress "
            "WHERE tenant_id=%s AND owner_user_id=%s AND query=%s",
            (env.tenant, env.user, before["query"]),
        ).fetchone() == (before["revision"], before["base_batch_request_id"], before["cursor"])
        assert connection.execute(
            "SELECT count(*) FROM pilot_candidate_batches WHERE tenant_id=%s AND platform_run_id=%s",
            (env.tenant, lease["platform_run_id"]),
        ).fetchone() == (0,)
        for table in ("pilot_collection_tasks", "pilot_collection_runs", "pilot_collection_platform_runs"):
            connection.execute(
                f"UPDATE {table} SET status='CANCELED' "
                "WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s",
                (env.tenant, env.user, begun["task_id"]),
            )
    env.monitor.pulse(env.claims, runtime_pulse(env, monitor_session_id=str(uuid4())))


def test_real_pg_rls_acl_and_owner_isolation(native_databases, native_env):
    env = native_env
    other = _native_env(native_databases, tenant=env.tenant, label="other-owner")
    _, _, other_lease = _begin_native_claim(other)
    assert all(item["revision"] == 0 for item in other_lease["native_progress"]["queries"])
    _, database, role = native_databases
    with database.connect() as connection:
        assert connection.execute(
            "SELECT row_security_active('pilot_native_search_progress'::regclass)"
        ).fetchone() == (True,)
        assert connection.execute(
            "SELECT has_table_privilege(current_user,'pilot_native_search_progress','DELETE')"
        ).fetchone() == (False,)
        assert connection.execute(
            "SELECT has_column_privilege(current_user,'pilot_native_search_progress','plan_id','UPDATE')"
        ).fetchone() == (False,)
        assert connection.execute(
            "SELECT has_column_privilege(current_user,'pilot_native_search_progress','cursor','UPDATE')"
        ).fetchone() == (True,)
        connection.execute("SELECT set_config('yike.tenant_id',%s,true)", (env.tenant,))
        connection.execute("SELECT set_config('yike.user_id',%s,true)", (other.user,))
        assert connection.execute("SELECT count(*) FROM pilot_native_search_progress").fetchone() == (0,)


def test_authenticated_local_https_artifact(native_env, tmp_path):
    env = native_env
    with _authenticated_https_client(env, tmp_path) as client:
        begun, claim_request, claim_receipt = _begin_native_claim(env, client=client)
        candidate_request = _native_batch(env, begun, claim_receipt)
        prepared_response = client.post(
            "/api/ui/candidate-submission-signing-payload", json={"batch": candidate_request}
        )
        assert prepared_response.status_code == 200, prepared_response.text
        prepared = prepared_response.json()
        signature = encoded(env.key.sign(prepared["signing_payload"].encode()).signature)
        uploaded = client.post(
            "/api/ui/candidate-batches", json={"batch": candidate_request, "signature": signature}
        )
        assert uploaded.status_code == 200, uploaded.text
        candidate_receipt = uploaded.json()
        finish_request = {
            "schema_version": "execution-runtime-v1", "request_id": str(uuid4()), "operation": "FINISH",
            "device_id": env.device, "credential_version": 1, "profile_version_id": None,
            "strategy_version_id": None, "configuration_sha256": None, "targets": None,
            "task_id": begun["task_id"], "platform_run_id": claim_receipt["platform_run_id"],
            "lease_id": claim_receipt["lease_id"],
            "execution_generation": claim_receipt["execution_generation"],
            "upload_request_id": candidate_request["request_id"],
        }
        operation = ExecutionOperation.model_validate(finish_request)
        finish_signature = encoded(env.key.sign(execution_signing_payload(
            tenant_id=env.tenant, claims=env.claims, operation=operation,
        ).encode()).signature)
        finished = client.post(
            "/api/ui/execution-operations", json={"request": finish_request, "signature": finish_signature}
        )
        assert finished.status_code == 200, finished.text
        _, next_claim_request, next_claim_receipt = _begin_native_claim(env, client=client)
    artifact = {"events": [
        {"kind": "execution", "request": claim_request, "receipt": claim_receipt},
        {"kind": "candidate", "request": candidate_request,
         "prepared": {"batch_fingerprint": prepared["batch_fingerprint"]},
         "receipt": candidate_receipt},
        {"kind": "execution", "request": next_claim_request, "receipt": next_claim_receipt},
    ]}
    Path("/tmp/yike-native-progress-http.json").write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    assert "signature" not in json.dumps(artifact).lower()
    assert "token" not in json.dumps(artifact).lower()


def test_real_pg_rejects_non_prefix_query_order_without_writes(native_databases):
    env = _native_env(native_databases, label="query-prefix")
    begun, _, lease = _begin_native_claim(env)
    value = _native_batch(env, begun, lease, query_count=2)
    value["native_progress"]["queries"].reverse()

    with pytest.raises(ExecutionRuntimeError, match="native_progress_conflict"):
        submit(env, CandidateIngestionStore(env.db, env.execution), value)
    with env.admin.connect() as connection:
        assert connection.execute(
            "SELECT count(*) FROM pilot_native_search_progress WHERE tenant_id=%s AND owner_user_id=%s",
            (env.tenant, env.user),
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT count(*) FROM pilot_candidate_batches WHERE tenant_id=%s AND owner_user_id=%s",
            (env.tenant, env.user),
        ).fetchone() == (0,)


def test_real_pg_rejects_processed_ids_above_task_record_upper_bound(native_databases):
    env = _native_env(native_databases, label="small-budget", max_records=1)
    begun, _, lease = _begin_native_claim(env)
    value = _native_batch(
        env, begun, lease, page_ids=("1", "2"), processed_ids=("1", "2"), has_more=False,
    )

    with pytest.raises(ExecutionRuntimeError, match="native_progress_conflict"):
        submit(env, CandidateIngestionStore(env.db, env.execution), value)
    with env.admin.connect() as connection:
        assert connection.execute(
            "SELECT count(*) FROM pilot_native_search_progress WHERE tenant_id=%s AND owner_user_id=%s",
            (env.tenant, env.user),
        ).fetchone() == (0,)
