"""Read-only execution feed over restricted PostgreSQL; all rows are synthetic."""
from datetime import datetime
from uuid import uuid4

import pytest

from pilot.auth import issue_token, verify_token_claims
from pilot.execution_contract import ExecutionRuntimeError
from tests.test_execution_http_postgres import http_client, send
from tests.test_execution_runtime_postgres import (
    SECRET, apply, change_strategy, databases, env, operation, start,
)


def test_feed_aggregates_start_identity_counts_and_cancel_state(env):
    change_strategy(env, configuration={"query": "synthetic", "name": "线索任务", "mode": "once"})
    request = start(env)
    begun = apply(env, request)
    platform_id = begun["platform_runs"][0]["platform_run_id"]
    with env.admin.connect() as connection:
        connection.execute(
            "UPDATE pilot_collection_platform_runs SET records_used=2 WHERE platform_run_id=%s",
            (platform_id,),
        )
    canceled = apply(env, operation(env, "CANCEL", begun))
    assert canceled["status"] == "CANCELED"
    env.store.revoke_device(env.users[0], env.device)

    page = env.runtime.get_task_feed(env.claims, limit=20, cursor=None)
    assert page["schema_version"] == "execution-task-feed-v1"
    assert page["next_cursor"] is None
    assert page["items"] == [env.runtime.get_task_feed_item(env.claims, begun["task_id"])]
    item = page["items"][0]
    assert item == {
        "task_id": begun["task_id"],
        "run_id": begun["run_id"],
        "device_id": env.device,
        "profile_version_id": env.profile,
        "strategy_version_id": env.snapshot["strategy_version_id"],
        "start_request_id": request.request_id,
        "name": "线索任务",
        "mode": "once",
        "created_at": item["created_at"],
        "deadline_at": item["deadline_at"],
        "status": "CANCELED",
        "max_records": 2,
        "records_used": 2,
        "stop_confirmed": True,
        "platform_runs": [{
            "platform_run_id": platform_id,
            "platform": "PUBLIC_WEB",
            "status": "CANCELED",
            "execution_generation": 0,
            "records_used": 2,
        }],
    }
    assert datetime.fromisoformat(item["created_at"]).tzinfo is not None
    assert datetime.fromisoformat(item["deadline_at"]).tzinfo is not None


def test_feed_is_owner_scoped_and_keyset_pagination_is_stable(env):
    begun = [apply(env, start(env)) for _ in range(3)]
    first = env.runtime.get_task_feed(env.claims, limit=2, cursor=None)
    assert [item["task_id"] for item in first["items"]] == [begun[2]["task_id"], begun[1]["task_id"]]
    assert all(item["name"] is None and item["mode"] is None for item in first["items"])
    assert first["next_cursor"]
    apply(env, start(env))  # A newer row must not shift the already-issued keyset page.
    second = env.runtime.get_task_feed(env.claims, limit=2, cursor=first["next_cursor"])
    assert [item["task_id"] for item in second["items"]] == [begun[0]["task_id"]]
    assert second["next_cursor"] is None

    for user in env.users[1:]:
        claims = verify_token_claims(issue_token(user, SECRET), SECRET)
        assert env.runtime.get_task_feed(claims, limit=20, cursor=None)["items"] == []
        with pytest.raises(ExecutionRuntimeError, match="task_not_found"):
            env.runtime.get_task_feed_item(claims, begun[0]["task_id"])


def test_feed_http_auth_parameters_unknown_fields_and_item_404(env):
    client, claims = http_client(env, env.runtime)
    begun = send(client, env, claims, start(env)).json()
    assert client.get("/api/ui/execution-task-feed").status_code == 200
    assert client.get("/api/ui/execution-task-feed/" + begun["task_id"]).status_code == 200
    for query in ("limit=0", "limit=51", "limit=text", "cursor=bad", "cursor=" + "a" * 1025,
                  "device_id=" + str(uuid4()), "unknown=x"):
        assert client.get("/api/ui/execution-task-feed?" + query).status_code == 422
    assert client.get("/api/ui/execution-task-feed/not-a-uuid").status_code == 422
    assert client.get("/api/ui/execution-task-feed/" + str(uuid4())).status_code == 404
    client.headers.pop("Authorization")
    assert client.get("/api/ui/execution-task-feed").status_code == 401
