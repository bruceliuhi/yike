"""One explicitly opted-in public read; synthetic identity is not customer UAT."""
import os
from uuid import uuid4

import pytest

from pilot.research_public_reader import read_public_index
from tests.test_research_resources_postgres import started, store
from tests.test_confirmed_strategy_review_postgres import real_strategy_env
from tests.test_candidate_review_postgres import (databases, env, execution_databases,
    execution_env, raw_databases, raw_env)


@pytest.mark.skipif(os.environ.get("YIKE_RESEARCH_PUBLIC_LIVE") != "1",
                    reason="explicit single public read opt-in required")
def test_one_fixed_public_read_records_result_and_recovery(real_strategy_env):
    env = real_strategy_env
    execution, _ = started(env)
    resource_store = store(env)
    binding = dict(task_id=execution["task_id"], run_id=execution["run_id"],
                   action_id=str(uuid4()))
    first = read_public_index(resource_store, env.claims, **binding)
    event = resource_store.get(env.claims, **binding)
    assert first["event"] == event
    assert first["replayed"] is False
    # Recovery is history-only. This second call must not make another read.
    def forbid_read(_deadline):
        pytest.fail("recovery attempted a second public request")
    recovered = read_public_index(resource_store, env.claims, **binding, fetcher=forbid_read)
    assert recovered == dict(event=event, result=None, replayed=True)
    result = first["result"]
    print({"live_read_status": event["status"],
           "observed_count": result["observed_count"] if result else None,
           "digest_recorded": event["output_sha256"] is not None,
           "recovery_without_read": True})
    assert event["status"] == "SUCCEEDED", "public read failed; no automatic retry"
    assert result["sample_kind"] == "LATEST_TOPIC_INDEX"
