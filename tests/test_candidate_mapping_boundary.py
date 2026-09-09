"""Real DTO consumption of synthetic source envelopes; no live platform claims."""

from copy import deepcopy
from datetime import datetime, timezone
import importlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

from pilot.candidate_contract import (
    CandidateBatch,
    CandidateContractError,
    batch_fingerprint,
    content_version,
    source_identity,
    validate_candidate_batch,
)


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 9, 12, tzinfo=timezone.utc)


def mapper():
    assert importlib.util.find_spec("connectors.candidate_mapping") is not None, (
        "Raw comment mapping must exist before formal candidate consumption"
    )
    return importlib.import_module("connectors.candidate_mapping").build_comment_batch


def inputs(platform):
    fixture = "dy" if platform == "DOUYIN" else "bili"
    data = json.loads((ROOT / "tests" / "fixtures" / fixture / "comments.json").read_text(encoding="utf-8"))
    return {
        "platform": platform,
        "raw_records": [{"content": data["contents"][0], "comment": data["comments"][0]}],
        "request_id": "synthetic-request-1",
        "profile_version_id": "synthetic-profile-version-1",
        "strategy_version_id": "synthetic-strategy-version-1",
        "execution": {
            "device_id": "synthetic-device-1", "task_id": "synthetic-task-1",
            "run_id": "synthetic-run-1", "platform_run_id": "synthetic-platform-run-1",
            "lease_id": "synthetic-lease-1", "credential_version": 1,
            "execution_generation": 1, "access_mode": "PLATFORM_ACCOUNT",
            "connection_id": "synthetic-connection-1", "connection_version": 1,
        },
        "collector_version": "synthetic-collector-v1",
        "query": "制造业采购",
        "now": NOW,
    }


@pytest.mark.parametrize("platform", ["DOUYIN", "BILIBILI"])
def test_original_evidence_survives_real_json_dto_round_trip(platform):
    args = inputs(platform)
    comment = args["raw_records"][0]["comment"]
    comment["content"] = " \t需要设备配套方案🙂\r\n请给参数。  "
    comment["parent_content"] = "  原始讨论\n对比旧供应商\t "
    comment.pop("create_time")
    comment["verifiable"] = True
    comment["reviewer"] = "untrusted-reviewer"
    comment["status"] = "APPROVED"
    before = deepcopy(args)

    batch = mapper()(**args)
    assert isinstance(batch, CandidateBatch)
    wire = json.loads(batch.model_dump_json())
    received = validate_candidate_batch(wire, now=NOW)
    assert received == batch
    assert received.records[0].body == comment["content"]
    assert received.records[0].parent.body == comment["parent_content"]
    assert received.records[0].published_at is None
    assert received.records[0].author_public_id is None
    assert received.records[0].parent.published_at is None
    assert received.records[0].parent.author_public_id is None
    assert received.records[0].parent.public_url is None
    assert received.records[0].observed_at == comment["collected_at"]
    assert received.execution.model_dump() == args["execution"]
    assert not ({"verifiable", "reviewer", "status", "creator_hash", "raw_sha256"} & set(wire["records"][0]))
    assert args == before


@pytest.mark.parametrize("platform", ["DOUYIN", "BILIBILI"])
def test_replay_observation_and_evidence_versions_have_distinct_boundaries(platform):
    args = inputs(platform)
    original = mapper()(**args)
    assert batch_fingerprint(mapper()(**args)) == batch_fingerprint(original)
    later = deepcopy(args)
    later["raw_records"][0]["comment"]["collected_at"] = "2026-08-12T02:00:00Z"
    observed = mapper()(**later)
    assert source_identity(original.records[0], platform) == source_identity(observed.records[0], platform)
    assert content_version(original.records[0]) == content_version(observed.records[0])
    assert batch_fingerprint(original) != batch_fingerprint(observed)
    changed = deepcopy(later)
    changed["raw_records"][0]["comment"]["parent_content"] += "\n补充：需要本地交付"
    updated = mapper()(**changed)
    assert source_identity(updated.records[0], platform) == source_identity(original.records[0], platform)
    assert content_version(updated.records[0]) != content_version(original.records[0])


@pytest.mark.parametrize("platform", ["DOUYIN", "BILIBILI"])
def test_batch_passes_through_actual_duplicate_and_version_conflict_checks(platform):
    args = inputs(platform)
    args["raw_records"].append(deepcopy(args["raw_records"][0]))
    with pytest.raises(CandidateContractError) as duplicate:
        mapper()(**args)
    assert duplicate.value.code == "DUPLICATE_RECORD"
    args["raw_records"][1]["comment"]["content"] += " 新原文"
    with pytest.raises(CandidateContractError) as conflict:
        mapper()(**args)
    assert conflict.value.code == "SOURCE_VERSION_CONFLICT"


@pytest.mark.parametrize("field", ["tenant_id", "reviewer", "owner", "permissions"])
def test_execution_claim_cannot_acquire_self_reported_authority(field):
    args = inputs("BILIBILI")
    args["execution"][field] = "self-reported-authority"
    with pytest.raises(CandidateContractError) as rejected:
        mapper()(**args)
    assert rejected.value.code == "INVALID_EXECUTION_CLAIM"


def test_explicit_mapping_import_does_not_load_application_or_database():
    mapper()
    result = subprocess.run(
        [sys.executable, "-I", "-c",
         "import sys; sys.path.insert(0, sys.argv[1]); import connectors.candidate_mapping; "
         "print(sorted(n for n in sys.modules if n.split('.')[0] in {'app', 'sqlite3', 'psycopg'}))",
         str(ROOT)],
        cwd=ROOT, capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"
