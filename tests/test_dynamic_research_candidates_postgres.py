"""Dynamic READ journal -> original candidate on restricted PostgreSQL."""
from datetime import UTC, datetime
import hashlib
from uuid import uuid4

import pytest

from pilot.execution_contract import ExecutionRuntimeError
from tests.test_customer_research_context_postgres import (
    context_env,
    real_strategy_env,
    databases,
    env,
    execution_databases,
    execution_env,
    raw_databases,
    raw_env,
)
from tests.test_execution_runtime_postgres import apply, operation
from tests.test_research_effect_journal_postgres import journal_env


def read_result(url="https://example.com/buyer", text=None, *, title="客户需求原文"):
    text = text or "我们正在找团队建设企业知识库，需要一期报价和交付排期。"
    evidence = {
        "url": url,
        "title": title,
        "text": text,
        "observed_at": datetime.now(UTC).isoformat(),
        "content_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "read_scope": "PUBLIC_PAGE_TEXT",
    }
    return {
        "status": "READ",
        "evidence": evidence,
        "review_status": "UNREVIEWED",
        "replayed": False,
    }


def successful_read(env, *, sequence=1, value=None):
    value = value or read_result()
    begun = env.journal.begin(
        env.claims,
        task_id=env.execution["task_id"],
        run_id=env.execution["run_id"],
        sequence=sequence,
        generation=1,
        coordinator_owner=env.owner,
        context_binding=env.compiled["binding"],
        kind="READ",
        payload={"url": value["evidence"]["url"]},
    )
    return env.journal.finish(
        env.claims,
        task_id=env.execution["task_id"],
        run_id=env.execution["run_id"],
        sequence=sequence,
        permit_id=begun["entry"]["permit_id"],
        status="SUCCEEDED",
        result=value,
    )


def publish(env, *, sequence=1, **changes):
    from pilot.dynamic_research_candidates import DynamicResearchCandidateStore

    arguments = {
        "task_id": env.execution["task_id"],
        "run_id": env.execution["run_id"],
        "sequence": sequence,
        "generation": 1,
        "coordinator_owner": env.owner,
        "context_binding": env.compiled["binding"],
    } | changes
    return DynamicResearchCandidateStore(env.journal).publish(env.claims, **arguments)


def row_counts(env):
    with env.admin.connect() as connection:
        return {
            table: connection.execute(
                f"SELECT count(*) FROM {table} WHERE tenant_id=%s", (env.tenant,)
            ).fetchone()[0]
            for table in (
                "pilot_candidate_batches",
                "pilot_candidate_sources",
                "pilot_candidate_versions",
                "pilot_candidate_observations",
            )
        }


def test_publish_reads_only_stored_success_and_is_idempotent(journal_env):
    env = journal_env
    entry = successful_read(env)
    first = publish(env)
    second = publish(env)
    assert second == first
    assert first["accepted_count"] == 1
    assert len(first["items"]) == 1
    assert row_counts(env) == {
        "pilot_candidate_batches": 1,
        "pilot_candidate_sources": 1,
        "pilot_candidate_versions": 1,
        "pilot_candidate_observations": 1,
    }
    with env.admin.connect() as connection:
        platform = connection.execute(
            "SELECT records_used FROM pilot_collection_platform_runs WHERE task_id=%s",
            (env.execution["task_id"],),
        ).fetchone()[0]
        context = connection.execute(
            "SELECT execution_context FROM pilot_candidate_batches WHERE request_id=%s",
            (entry["action_id"],),
        ).fetchone()[0]
        source = connection.execute(
            "SELECT content FROM pilot_candidate_versions WHERE tenant_id=%s",
            (env.tenant,),
        ).fetchone()[0]
    assert platform == 1
    assert len(context) == 20 and context["kind"] == "research-resource-v1"
    assert context["action_id"] == entry["action_id"]
    assert source["author_public_id"] is None
    assert source["published_at"] is None


def test_search_journal_entry_cannot_be_published_as_original(journal_env):
    env = journal_env
    begun = env.journal.begin(
        env.claims,
        task_id=env.execution["task_id"],
        run_id=env.execution["run_id"],
        sequence=1,
        generation=1,
        coordinator_owner=env.owner,
        context_binding=env.compiled["binding"],
        kind="SEARCH",
        payload={"query": "企业知识库 找团队"},
    )
    from tests.test_research_effect_journal_postgres import result
    env.journal.finish(
        env.claims,
        task_id=env.execution["task_id"],
        run_id=env.execution["run_id"],
        sequence=1,
        permit_id=begun["entry"]["permit_id"],
        status="SUCCEEDED",
        result=result(),
    )
    with pytest.raises(ExecutionRuntimeError, match="request_conflict"):
        publish(env)
    assert row_counts(env)["pilot_candidate_batches"] == 0


def test_oversize_original_has_explicit_zero_receipt_without_truncation(journal_env):
    env = journal_env
    text = "需" * 20_001
    successful_read(env, value=read_result(text=text))
    receipt = publish(env)
    assert receipt["accepted_count"] == 0 and receipt["items"] == []
    assert row_counts(env) == {
        "pilot_candidate_batches": 1,
        "pilot_candidate_sources": 0,
        "pilot_candidate_versions": 0,
        "pilot_candidate_observations": 0,
    }
    with env.admin.connect() as connection:
        context = connection.execute(
            "SELECT execution_context FROM pilot_candidate_batches WHERE tenant_id=%s",
            (env.tenant,),
        ).fetchone()[0]
        records_used = connection.execute(
            "SELECT records_used FROM pilot_collection_platform_runs WHERE task_id=%s",
            (env.execution["task_id"],),
        ).fetchone()[0]
    assert context["observed_count"] == 1
    assert context["accepted_count"] == 0
    assert context["skipped_invalid_count"] == 1
    assert records_used == 0


@pytest.mark.parametrize("tamper", ["generation", "owner", "binding", "cancel"])
def test_publish_rechecks_current_context_coordinator_and_task(journal_env, tamper):
    env = journal_env
    successful_read(env)
    changes = {}
    if tamper == "generation":
        changes["generation"] = 2
    elif tamper == "owner":
        changes["coordinator_owner"] = str(uuid4())
    elif tamper == "binding":
        changes["context_binding"] = env.compiled["binding"] | {
            "context_sha256": "a" * 64
        }
    else:
        apply(env, operation(env, "CANCEL", env.execution))
    with pytest.raises(ExecutionRuntimeError):
        publish(env, **changes)
    assert row_counts(env)["pilot_candidate_batches"] == 0


@pytest.mark.parametrize("target", ["journal", "event"])
def test_tampered_journal_hash_or_resource_event_rolls_back_publication(journal_env, target):
    env = journal_env
    successful_read(env)
    with env.admin.connect() as connection:
        if target == "journal":
            connection.execute(
                "ALTER TABLE pilot_research_effect_journal DISABLE TRIGGER pilot_research_effect_guard"
            )
            connection.execute(
                "UPDATE pilot_research_effect_journal SET output_sha256=%s WHERE tenant_id=%s",
                ("b" * 64, env.tenant),
            )
            connection.execute(
                "ALTER TABLE pilot_research_effect_journal ENABLE TRIGGER pilot_research_effect_guard"
            )
        else:
            connection.execute(
                "ALTER TABLE pilot_research_resource_events DISABLE TRIGGER "
                "pilot_research_resource_transition"
            )
            connection.execute(
                "UPDATE pilot_research_resource_events SET output_sha256=%s WHERE tenant_id=%s",
                ("b" * 64, env.tenant),
            )
            connection.execute(
                "ALTER TABLE pilot_research_resource_events ENABLE TRIGGER "
                "pilot_research_resource_transition"
            )
    with pytest.raises(ExecutionRuntimeError, match="request_conflict"):
        publish(env)
    assert row_counts(env)["pilot_candidate_batches"] == 0


def test_current_context_tamper_is_rejected_in_publication_transaction(journal_env):
    env = journal_env
    successful_read(env)
    with env.admin.connect() as connection:
        connection.execute(
            "ALTER TABLE pilot_customer_research_contexts DISABLE TRIGGER "
            "pilot_customer_research_context_guard"
        )
        connection.execute(
            "UPDATE pilot_customer_research_contexts SET context="
            "jsonb_set(context,'{seller_description}','\"tampered\"'::jsonb) "
            "WHERE tenant_id=%s", (env.tenant,),
        )
        connection.execute(
            "ALTER TABLE pilot_customer_research_contexts ENABLE TRIGGER "
            "pilot_customer_research_context_guard"
        )
    with pytest.raises(ExecutionRuntimeError, match="request_conflict"):
        publish(env)
    assert row_counts(env)["pilot_candidate_batches"] == 0
