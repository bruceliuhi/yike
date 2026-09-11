"""Industry task strategy contract and restricted-PG persistence; synthetic only."""
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from pilot.execution_contract import ExecutionRuntimeError
from pilot.research_strategy_contract import (
    PrepareStrategyRequest, configuration_digest, strategy_snapshot,
)
from pilot.store import PilotStore
from tests.test_material_profile_strategy import authority
from tests.test_materials_store import database, env
from tests.test_research_strategies_postgres import confirm_body, configuration, prepare_body


PROFILE = "11111111-1111-4111-8111-111111111111"
STRATEGY = "22222222-2222-4222-8222-222222222222"


def industry(**changes):
    return {"version": "industry-task-strategy-v1",
        "sourceTypes": ["SOCIAL_POST", "COMMENT"],
        "intentSignals": ["正在寻找供应商"], "counterSignals": ["同行广告"]} | changes


def request(configuration_value=None):
    return {"schema_version": "strategy-confirmation-v1", "request_id": str(uuid4()),
        "draft_id": str(uuid4()), "draft_revision": 1, "profile_version_id": PROFILE,
        "configuration": configuration() if configuration_value is None else configuration_value,
        "platforms": ["PUBLIC_WEB"], "max_records": 10, "max_runtime_seconds": 600}


def snapshot(configuration_value):
    return strategy_snapshot(PROFILE, STRATEGY, configuration_value, ["PUBLIC_WEB"], 10, 600)


def test_new_configuration_round_trips_snapshot_and_digest_while_legacy_bytes_stay_exact():
    legacy = request()
    legacy_bytes = json.dumps(legacy, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    parsed_legacy = PrepareStrategyRequest.model_validate(legacy).model_dump(mode="json")
    assert json.dumps(parsed_legacy, ensure_ascii=False, sort_keys=True, separators=(",", ":")) == legacy_bytes

    modern_configuration = configuration() | {"industryStrategy": industry()}
    modern_request = request(modern_configuration)
    parsed = PrepareStrategyRequest.model_validate(modern_request)
    assert parsed.model_dump(mode="json") == modern_request
    result = snapshot(parsed.configuration)
    assert result["configuration"] == modern_configuration
    expected = hashlib.sha256(json.dumps(result, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest()
    assert configuration_digest(result) == expected
    changed = deepcopy(modern_configuration)
    changed["industryStrategy"]["intentSignals"] = ["正在比较供应商"]
    assert configuration_digest(snapshot(changed)) != expected


@pytest.mark.parametrize("change", [
    None,
    {"version": "industry-task-strategy-v2"},
    {"sourceTypes": ["SOCIAL_POST", " social_post "]},
    {"intentSignals": [" 采购需求 ", "采购需求"]},
    {"authority": "APPROVED"},
])
def test_industry_strategy_rejects_null_unknown_duplicate_and_extra_authority(change):
    value = configuration() | {"industryStrategy": change if change is None else industry(**change)}
    with pytest.raises(ValidationError):
        PrepareStrategyRequest.model_validate(request(value))


def test_restricted_pg_preserves_strategy_and_new_revision_invalidates_old_resolve(env):
    store = authority(env)
    profile = env.profiles[0]
    PilotStore(env.admin).confirm_profile(env.users[0], profile)
    modern = configuration() | {"industryStrategy": industry()}
    body = prepare_body(SimpleNamespace(profile=profile), configuration=modern)
    prepared = store.prepare(env.claims[0], body)
    confirmed = store.confirm(env.claims[0], confirm_body(prepared))
    with env.db.connect() as connection, connection.cursor() as cursor:
        resolved = store.resolve(cursor, env.claims[0], profile, confirmed["strategy_version_id"])
    assert resolved.configuration["industryStrategy"] == industry()

    changed = deepcopy(modern)
    changed["industryStrategy"]["intentSignals"] = ["正在比较供应商"]
    newer = store.prepare(env.claims[0], body | {"request_id": str(uuid4()),
        "draft_revision": body["draft_revision"] + 1, "configuration": changed})
    assert store.get_receipt(env.claims[0], confirmed["request_id"]) == confirmed
    with env.db.connect() as connection, connection.cursor() as cursor:
        with pytest.raises(ExecutionRuntimeError, match="strategy_conflict"):
            store.resolve(cursor, env.claims[0], profile, confirmed["strategy_version_id"])
    assert newer["snapshot"]["configuration"]["industryStrategy"] == changed["industryStrategy"]
