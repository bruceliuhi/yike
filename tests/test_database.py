import hashlib
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.db import UnsupportedSchemaError, connect, migrate
from app.repository import (
    ActiveRunError,
    FinalizedRunError,
    NormalizedSignal,
    Repository,
    SignalIdentityConflict,
)


FACT_TABLES = {
    "mvp_runs",
    "keyword_versions",
    "campaigns",
    "collection_runs",
    "sources",
    "signals",
    "mvp_run_signals",
    "signal_observations",
    "score_runs",
    "score_presentations",
    "activity_sessions",
    "activity_events",
    "human_reviews",
    "draft_runs",
    "outreach_actions",
    "response_events",
    "interviews",
    "quote_opportunities",
    "daily_snapshots",
    "risk_events",
    "model_availability_events",
}


@pytest.fixture
def connection(tmp_path):
    connection = connect(tmp_path / "data" / "discovery.sqlite3")
    migrate(connection)
    yield connection
    connection.close()


@pytest.fixture
def repository(connection):
    return Repository(connection)


def signal(
    *,
    platform: str = "bili",
    external_comment_id: str | None = "comment-1",
    body: str = "需要线索筛选",
    comment_url: str = "https://www.bilibili.com/read/comment-1",
    author_public_id: str = "author-1",
    verifiable: bool = False,
) -> NormalizedSignal:
    return NormalizedSignal(
        platform=platform,
        external_source_id="source-1",
        source_title="销售获客讨论",
        source_url="https://www.bilibili.com/video/BV1",
        external_comment_id=external_comment_id,
        comment_url=comment_url,
        author_public_id=author_public_id,
        body=body,
        raw_sha256="a" * 64,
        verifiable=verifiable,
    )


def insert_completed_activity(
    connection,
    *,
    activity_id: str,
    run_id: str,
    signal_id: str,
    kind: str,
    started_at: str,
    completed_at: str,
) -> None:
    connection.execute(
        """
        INSERT INTO activity_sessions (
            activity_session_id, mvp_run_id, signal_id, activity_kind,
            state, started_at
        ) VALUES (?, ?, ?, ?, 'OPEN', ?)
        """,
        (activity_id, run_id, signal_id, kind, started_at),
    )
    for sequence, event_kind, received_at in (
        (1, "START", started_at),
        (2, "COMPLETE", completed_at),
    ):
        connection.execute(
            """
            INSERT INTO activity_events (
                activity_event_id, activity_session_id, mvp_run_id, signal_id,
                activity_kind, sequence_no, event_kind, received_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"{activity_id}-event-{sequence}", activity_id, run_id, signal_id,
                kind, sequence, event_kind, received_at,
            ),
        )
    seconds = int(
        (datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
         - datetime.fromisoformat(started_at.replace("Z", "+00:00"))).total_seconds()
    )
    connection.execute(
        "UPDATE activity_sessions SET state = 'COMPLETED', completed_at = ?, "
        "active_seconds = ? WHERE activity_session_id = ?",
        (completed_at, seconds, activity_id),
    )


def insert_run(
    connection,
    run_id: str,
    *,
    state: str = "FINALIZED",
    revision_of_run_id: str | None = None,
) -> None:
    initial_state = "ACTIVE" if state == "FINALIZED" else state
    connection.execute(
        """
        INSERT INTO mvp_runs (
            mvp_run_id, revision_of_run_id, state, authorization_basis,
            platform_scope_json, query_set_sha256, prompt_version,
            schema_version, thresholds_sha256, started_at, day14_due_at
        ) VALUES (?, ?, ?, 'USER_ATTESTED_PLATFORM_AUTHORIZATION',
                  '["bili","dy"]', ?, 'run-prompt-v1', 'run-schema-v1', ?,
                  '2026-08-12T00:00:00Z',
                  '2026-08-26T00:00:00Z')
        """,
        (run_id, revision_of_run_id, initial_state, "a" * 64, "b" * 64),
    )
    if state == "FINALIZED":
        connection.execute(
            """
            UPDATE mvp_runs
            SET state = 'FINALIZED', finalized_at = '2026-08-26T00:00:00Z',
                conclusion = 'REVISE_MVP', conclusion_facts_json = '{}',
                conclusion_facts_sha256 = ?, final_report_sha256 = ?
            WHERE mvp_run_id = ?
            """,
            ("c" * 64, "d" * 64, run_id),
        )


def seed_fact_graph(connection, repository):
    run_id = repository.create_run(["bili", "dy"])
    imported = repository.import_signal(run_id, signal())
    signal_id = imported.signal_id
    source_id = connection.execute(
        "SELECT source_id FROM signals WHERE signal_id = ?", (signal_id,)
    ).fetchone()[0]
    connection.execute(
        """
        INSERT INTO keyword_versions (
            keyword_version_id, mvp_run_id, version, query_cluster,
            query_text, content_sha256, created_at
        ) VALUES ('keyword-1', ?, 'v1', 'sales', '线索', ?, '2026-08-12T00:00:00Z')
        """,
        (run_id, "b" * 64),
    )
    connection.execute(
        """
        INSERT INTO campaigns (
            campaign_id, mvp_run_id, platform, query_cluster, query_text,
            state, created_at
        ) VALUES ('campaign-1', ?, 'bili', 'sales', '线索', 'QUEUED',
                  '2026-08-12T00:00:00Z')
        """,
        (run_id,),
    )
    connection.execute(
        """
        INSERT INTO collection_runs (
            collection_run_id, mvp_run_id, campaign_id, platform,
            attempt, backend, started_by, runtime_lock_sha256, state
        ) VALUES ('collection-1', ?, 'campaign-1', 'bili', 1,
                  'MEDIACRAWLER_AUTHORIZED', 'test-operator', ?, 'QUEUED')
        """,
        (run_id, "a" * 64),
    )
    connection.execute(
        """
        INSERT INTO score_runs (
            score_run_id, mvp_run_id, signal_id, provider, model,
            prompt_version, schema_version, dimension_scores_json,
            total_score, grade, confidence, reason_json, status
        ) VALUES ('score-1', ?, ?, 'test-provider', 'test-model', 'p1', 's1',
                  '{}', 8, 'B', 0.8, '{}', 'SUCCEEDED')
        """,
        (run_id, signal_id),
    )
    connection.execute(
        """
        INSERT INTO score_presentations (
            presentation_id, mvp_run_id, signal_id, score_run_id, presented_at
        ) VALUES ('presentation-1', ?, ?, 'score-1', '2026-08-12T00:00:00Z')
        """,
        (run_id, signal_id),
    )
    for activity_id, kind in (
        ("review-activity-1", "REVIEW"),
        ("draft-activity-1", "DRAFT"),
    ):
        insert_completed_activity(
            connection, activity_id=activity_id, run_id=run_id,
            signal_id=signal_id, kind=kind,
            started_at="2026-08-12T00:00:00Z",
            completed_at="2026-08-12T00:01:00Z",
        )
    connection.execute(
        """
        INSERT INTO human_reviews (
            review_id, mvp_run_id, signal_id, presented_score_run_id, label,
            reason, activity_session_id, started_at, completed_at, active_seconds
        ) VALUES ('review-1', ?, ?, 'score-1', 'HIGH_INTENT',
                  '有明确采购信号', 'review-activity-1',
                  '2026-08-12T00:00:00Z', '2026-08-12T00:01:00Z', 60)
        """,
        (run_id, signal_id),
    )
    connection.execute(
        """
        INSERT INTO draft_runs (
            draft_run_id, mvp_run_id, signal_id, provider, prompt_version,
            draft_kind, body, status, activity_session_id, created_at
        ) VALUES ('draft-1', ?, ?, 'human', 'HUMAN_DRAFT_V1',
                  'HUMAN_EDITED', '需要线索筛选，请问您目前如何筛选线索？', 'SUCCEEDED',
                  'draft-activity-1',
                  '2026-08-12T00:00:00Z')
        """,
        (run_id, signal_id),
    )
    connection.execute(
        """
        INSERT INTO outreach_actions (
            outreach_action_id, mvp_run_id, signal_id, review_id, score_run_id,
            draft_run_id, platform, subject_key, approved_text, sent_at,
            source_url, context_evidence, evidence_summary,
            source_link_opened, status, created_at
        ) VALUES ('outreach-1', ?, ?, 'review-1', 'score-1', 'draft-1',
                  'bili', 'bili:author-1', '需要线索筛选，人工批准文本',
                  '2026-08-12T00:02:00Z',
                  'https://www.bilibili.com/video/BV1', '需要线索筛选',
                  '需要线索筛选', 1,
                  'SENT_VERIFIED', '2026-08-12T00:02:00Z')
        """,
        (run_id, signal_id),
    )
    connection.execute(
        """
        INSERT INTO response_events (
            response_event_id, mvp_run_id, outreach_action_id,
            responder_subject_key, response_type, summary, occurred_at,
            verified_at, evidence_summary, recorded_at
        ) VALUES ('response-1', ?, 'outreach-1', 'bili:author-1', 'VALID',
                  '愿意沟通', '2026-08-12T00:03:00Z',
                  '2026-08-12T00:04:00Z', '回复说明当前流程',
                  '2026-08-12T00:04:00Z')
        """,
        (run_id,),
    )
    connection.execute(
        """
        INSERT INTO interviews (
            interview_id, mvp_run_id, response_event_id, scheduled_at, completed_at,
            summary_json, solution_fit, next_step, recorded_at
        ) VALUES (
            'interview-1', ?, 'response-1', '2026-08-12T00:05:00Z',
            '2026-08-12T00:06:00Z',
            '{"customer_source_and_sales_process":"内容营销","weekly_lead_volume_and_loss_point":"每周二百条","most_manual_step":"人工判断","current_tools":"CRM","minimum_agent_scenario_and_decision_process":"先试排序"}',
            'SOLVABLE', '试点', '2026-08-12T00:06:00Z'
        )
        """,
        (run_id,),
    )
    connection.execute(
        """
        INSERT INTO quote_opportunities (
            quote_opportunity_id, mvp_run_id, response_event_id, scope_summary,
            agreed_to_receive_pricing_at, verified_at, recorded_at
        ) VALUES ('quote-1', ?, 'response-1', '销售线索筛选',
                  '2026-08-12T00:07:00Z', '2026-08-12T00:08:00Z',
                  '2026-08-12T00:08:00Z')
        """,
        (run_id,),
    )
    connection.execute(
        """
        INSERT INTO daily_snapshots (
            daily_snapshot_id, mvp_run_id, local_date, fact_counts_json, created_at
        ) VALUES ('snapshot-1', ?, '2026-08-12', '{}', '2026-08-12T00:00:00Z')
        """,
        (run_id,),
    )
    return {
        "run_id": run_id,
        "signal_id": signal_id,
        "source_id": source_id,
        "observation_id": imported.observation_id,
    }


def set_seed_collection_active_state(connection, state: str) -> None:
    first_state = "WAITING_LOGIN" if state == "WAITING_LOGIN" else "RUNNING"
    connection.execute(
        "UPDATE collection_runs SET state = ?, started_at = ? "
        "WHERE collection_run_id = 'collection-1'",
        (first_state, "2026-08-12T00:00:00Z"),
    )
    if state == "IMPORTING":
        connection.execute(
            "UPDATE collection_runs SET state = 'IMPORTING' "
            "WHERE collection_run_id = 'collection-1'"
        )


def assert_active_collection_slot_can_be_released(repository, run_id: str) -> None:
    repository.finish_collection(
        "collection-1",
        state="CANCELLED",
        raw_count=0,
        unique_count=0,
        error_code="COLLECTION_CANCELLED",
    )
    repository.cancel_run(run_id)
    next_run_id = repository.create_run(["bili", "dy"])
    repository.begin_collection(
        run_id=next_run_id,
        collection_run_id="collection-after-rejected-run-cancel",
        platform="dy",
        query_cluster="sales",
        query_text="新线索",
        max_contents=1,
        max_comments_per_content=1,
        started_by="test-operator",
        runtime_lock_sha256="a" * 64,
    )
    assert repository.connection.execute(
        "SELECT state FROM collection_runs WHERE collection_run_id = ?",
        ("collection-after-rejected-run-cancel",),
    ).fetchone()[0] == "RUNNING"


def test_migration_from_empty_file_creates_all_fact_tables_and_enables_pragmas(tmp_path):
    database = tmp_path / "empty.sqlite3"
    database.touch()
    connection = connect(database)
    try:
        migrate(connection)
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert FACT_TABLES <= tables
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    finally:
        connection.close()


def test_migration_enables_foreign_keys_for_a_bare_sqlite_connection(tmp_path):
    connection = sqlite3.connect(tmp_path / "bare.sqlite3")
    try:
        migrate(connection)
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        connection.close()


def test_migration_rejects_unversioned_legacy_schema_without_modifying_it(tmp_path):
    connection = sqlite3.connect(tmp_path / "legacy.sqlite3")
    connection.execute("CREATE TABLE mvp_runs (mvp_run_id TEXT PRIMARY KEY)")
    connection.commit()

    with pytest.raises(UnsupportedSchemaError, match="UNSUPPORTED_SCHEMA"):
        migrate(connection)

    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE name = 'schema_meta'"
    ).fetchone() is None
    assert connection.in_transaction is False
    connection.close()


def test_current_schema_migration_is_idempotent(connection):
    migrate(connection)
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    marker = connection.execute(
        "SELECT version, signature FROM schema_meta WHERE schema_key = 'discovery'"
    ).fetchone()
    assert tuple(marker) == (
        "DISCOVERY_FACT_STORE_V16",
        "d448df7461d21d729a0ab105e60d6b82152cdbcaa2aad1a00c69934e6bf09f9f",
    )


@pytest.mark.parametrize(
    ("core_column", "core_value"),
    [
        ("dimension_scores_json", "{}"),
        ("total_score", 12),
        ("grade", "A"),
        ("confidence", 0.9),
        ("reason_json", "{}"),
        ("token_usage_json", "{}"),
    ],
)
def test_failed_score_rows_reject_nonnull_scoring_core(
    connection, repository, core_column, core_value
):
    run_id = repository.create_run(["bili", "dy"])
    signal_id = repository.import_signal(run_id, signal()).signal_id

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            f"""
            INSERT INTO score_runs (
                score_run_id, mvp_run_id, signal_id, prompt_version,
                schema_version, status, error_code, {core_column}
            ) VALUES ('invalid-failed', ?, ?, 'p1', 's1', 'FAILED',
                      'MODEL_OUTPUT_INVALID', ?)
            """,
            (run_id, signal_id, core_value),
        )


def test_failed_score_rows_require_a_stable_model_error(connection, repository):
    run_id = repository.create_run(["bili", "dy"])
    signal_id = repository.import_signal(run_id, signal()).signal_id

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO score_runs (
                score_run_id, mvp_run_id, signal_id, prompt_version,
                schema_version, status, error_code
            ) VALUES ('invalid-error', ?, ?, 'p1', 's1', 'FAILED', 'OTHER')
            """,
            (run_id, signal_id),
        )


@pytest.mark.parametrize(
    "invalid_override",
    [
        {"dimension_scores_json": None},
        {"total_score": None},
        {"total_score": 13},
        {"total_score": 8.5},
        {"grade": None},
        {"grade": "E"},
        {"confidence": None},
        {"confidence": 1.1},
        {"reason_json": None},
        {"error_code": "MODEL_OUTPUT_INVALID"},
    ],
)
def test_successful_score_rows_require_valid_core_and_no_error(
    connection, repository, invalid_override
):
    run_id = repository.create_run(["bili", "dy"])
    signal_id = repository.import_signal(run_id, signal()).signal_id
    values = {
        "dimension_scores_json": "{}",
        "total_score": 8,
        "grade": "B",
        "confidence": 0.8,
        "reason_json": "{}",
        "error_code": None,
    }
    values.update(invalid_override)

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO score_runs (
                score_run_id, mvp_run_id, signal_id, provider, model,
                prompt_version, schema_version, dimension_scores_json,
                total_score, grade, confidence, reason_json, status, error_code
            ) VALUES ('invalid-success', ?, ?, 'provider', 'model', 'p1', 's1',
                      ?, ?, ?, ?, ?, 'SUCCEEDED', ?)
            """,
            (
                run_id,
                signal_id,
                values["dimension_scores_json"],
                values["total_score"],
                values["grade"],
                values["confidence"],
                values["reason_json"],
                values["error_code"],
            ),
        )


def test_database_rejects_noncanonical_platform_scope(connection):
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO mvp_runs (
                mvp_run_id, state, authorization_basis, platform_scope_json,
                query_set_sha256, prompt_version, schema_version,
                thresholds_sha256, started_at, day14_due_at
            ) VALUES ('bad-scope', 'DRAFT', 'USER_ATTESTED_PLATFORM_AUTHORIZATION',
                      '["dy","bili"]', ?, 'prompt-v1', 'schema-v1', ?,
                      '2026-08-12T00:00:00Z',
                      '2026-08-26T00:00:00Z')
            """,
            ("a" * 64, "b" * 64),
        )


def test_database_rejects_noncanonical_authorization_basis(connection):
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO mvp_runs (
                mvp_run_id, state, authorization_basis, platform_scope_json,
                query_set_sha256, prompt_version, schema_version,
                thresholds_sha256, started_at, day14_due_at
            ) VALUES ('bad-authorization', 'DRAFT', 'SELF_ASSERTED',
                      '["bili","dy"]', ?, 'prompt-v1', 'schema-v1', ?,
                      '2026-08-12T00:00:00Z',
                      '2026-08-26T00:00:00Z')
            """,
            ("a" * 64, "b" * 64),
        )


def test_database_rejects_an_initial_finalized_run_without_a_snapshot(connection):
    with pytest.raises(sqlite3.IntegrityError, match="RUN_INITIAL_STATE_INVALID"):
        connection.execute(
            """
            INSERT INTO mvp_runs (
                mvp_run_id, state, authorization_basis, platform_scope_json,
                query_set_sha256, prompt_version, schema_version,
                thresholds_sha256, started_at, day14_due_at
            ) VALUES ('forged-finalized', 'FINALIZED',
                      'USER_ATTESTED_PLATFORM_AUTHORIZATION', '["bili","dy"]',
                      ?, 'prompt-v1', 'schema-v1', ?,
                      '2026-08-12T00:00:00Z', '2026-08-26T15:59:59Z')
            """,
            ("a" * 64, "b" * 64),
        )


def test_repository_rejects_backdated_import_and_collection_after_day14(connection):
    now = [datetime(2026, 8, 12, tzinfo=UTC)]
    repository = Repository(connection, now=lambda: now[0])
    run_id = repository.create_run(["bili", "dy"])
    now[0] += timedelta(days=8)
    imported = repository.import_signal(
        run_id,
        replace(signal(), collected_at="2026-08-13T00:00:00Z"),
    )
    membership_time = connection.execute(
        "SELECT added_at FROM mvp_run_signals WHERE mvp_run_id = ? AND signal_id = ?",
        (run_id, imported.signal_id),
    ).fetchone()[0]
    observation_time = connection.execute(
        "SELECT observed_at FROM signal_observations WHERE observation_id = ?",
        (imported.observation_id,),
    ).fetchone()[0]
    assert (membership_time, observation_time) == (
        "2026-08-20T00:00:00Z", "2026-08-13T00:00:00Z"
    )
    now[0] += timedelta(days=7)

    with pytest.raises(ValueError, match="Day 14"):
        repository.import_signal(
            run_id,
            signal(
                external_comment_id="late-comment",
                comment_url="https://www.bilibili.com/read/late-comment",
                author_public_id="late-author",
            ),
        )
    with pytest.raises(ValueError, match="Day 14"):
        repository.begin_collection(
            run_id=run_id,
            collection_run_id="late-collection",
            platform="bili",
            query_cluster="sales",
            query_text="线索",
            max_contents=1,
            max_comments_per_content=1,
            started_by="test-operator",
            runtime_lock_sha256="a" * 64,
        )

    assert repository.count_signals(run_id) == 1
    assert connection.execute(
        "SELECT count(*) FROM collection_runs WHERE mvp_run_id = ?", (run_id,)
    ).fetchone()[0] == 0


def test_migration_rejects_an_existing_transaction_without_committing_it(tmp_path):
    connection = sqlite3.connect(tmp_path / "transaction.sqlite3")
    try:
        connection.execute("BEGIN")
        with pytest.raises(RuntimeError, match="transaction"):
            migrate(connection)
        assert connection.in_transaction is True
    finally:
        connection.rollback()
        connection.close()


def test_only_one_active_run_is_allowed(repository):
    repository.create_run(["bili", "dy"])
    with pytest.raises(ActiveRunError):
        repository.create_run(["bili", "dy"])


def test_only_one_collection_can_be_running(repository):
    run_id = repository.create_run(["bili", "dy"])
    parameters = {
        "run_id": run_id,
        "platform": "bili",
        "query_cluster": "sales",
        "query_text": "线索",
        "max_contents": 5,
        "max_comments_per_content": 20,
        "started_by": "test-operator",
        "runtime_lock_sha256": "a" * 64,
    }
    repository.begin_collection(collection_run_id="collection-running-1", **parameters)

    with pytest.raises(sqlite3.IntegrityError):
        repository.begin_collection(
            collection_run_id="collection-running-2", **parameters
        )

    repository.finish_collection(
        "collection-running-1",
        state="FAILED",
        raw_count=0,
        unique_count=0,
        error_code="COLLECTION_PROCESS_FAILED",
    )
    repository.begin_collection(collection_run_id="collection-running-2", **parameters)


def test_only_one_collection_can_be_active_while_importing(repository):
    run_id = repository.create_run(["bili", "dy"])
    parameters = {
        "run_id": run_id,
        "platform": "bili",
        "query_cluster": "sales",
        "query_text": "线索",
        "max_contents": 1,
        "max_comments_per_content": 1,
        "started_by": "test-operator",
        "runtime_lock_sha256": "a" * 64,
    }
    repository.begin_collection(
        collection_run_id="collection-importing-1", **parameters
    )
    repository.connection.execute(
        "UPDATE collection_runs SET state = 'IMPORTING' "
        "WHERE collection_run_id = 'collection-importing-1'"
    )
    repository.connection.commit()

    with pytest.raises(sqlite3.IntegrityError):
        repository.begin_collection(
            collection_run_id="collection-importing-2", **parameters
        )


def test_waiting_login_occupies_global_collection_slot_and_can_run(
    connection, repository
):
    facts = seed_fact_graph(connection, repository)
    connection.execute(
        """
        UPDATE collection_runs
        SET state = 'WAITING_LOGIN', started_at = '2026-08-12T00:00:00Z'
        WHERE collection_run_id = 'collection-1'
        """
    )
    connection.commit()

    with pytest.raises(sqlite3.IntegrityError):
        repository.begin_collection(
            run_id=facts["run_id"],
            collection_run_id="waiting-login-contender",
            platform="dy",
            query_cluster="sales",
            query_text="线索",
            max_contents=1,
            max_comments_per_content=1,
            started_by="test-operator",
            runtime_lock_sha256="a" * 64,
        )

    connection.execute(
        "UPDATE collection_runs SET state = 'RUNNING' "
        "WHERE collection_run_id = 'collection-1'"
    )
    assert connection.execute(
        "SELECT state FROM collection_runs WHERE collection_run_id = 'collection-1'"
    ).fetchone()[0] == "RUNNING"


@pytest.mark.parametrize(
    ("terminal_state", "error_code"),
    [
        ("FAILED", "COLLECTION_PROCESS_FAILED"),
        ("CANCELLED", "COLLECTION_CANCELLED"),
        ("BLOCKED_INPUT", "PLATFORM_AUTH_REQUIRED"),
    ],
)
def test_waiting_login_can_finish_in_approved_terminal_states(
    connection, repository, terminal_state, error_code
):
    seed_fact_graph(connection, repository)
    connection.execute(
        """
        UPDATE collection_runs
        SET state = 'WAITING_LOGIN', started_at = '2026-08-12T00:00:00Z'
        WHERE collection_run_id = 'collection-1'
        """
    )

    repository.finish_collection(
        "collection-1",
        state=terminal_state,
        raw_count=0,
        unique_count=0,
        error_code=error_code,
    )

    assert connection.execute(
        "SELECT state FROM collection_runs WHERE collection_run_id = 'collection-1'"
    ).fetchone()[0] == terminal_state


def test_waiting_login_rejects_unapproved_transitions(connection, repository):
    seed_fact_graph(connection, repository)
    connection.execute(
        """
        UPDATE collection_runs
        SET state = 'WAITING_LOGIN', started_at = '2026-08-12T00:00:00Z'
        WHERE collection_run_id = 'collection-1'
        """
    )

    with pytest.raises(
        sqlite3.IntegrityError, match="COLLECTION_STATE_TRANSITION_INVALID"
    ):
        connection.execute(
            "UPDATE collection_runs SET state = 'IMPORTING' "
            "WHERE collection_run_id = 'collection-1'"
        )

    with pytest.raises(
        sqlite3.IntegrityError, match="COLLECTION_STATE_TRANSITION_INVALID"
    ):
        connection.execute(
            """
            UPDATE collection_runs
            SET state = 'SUCCEEDED', finished_at = '2026-08-12T00:01:00Z',
                raw_count = 1, unique_count = 1, error_code = NULL,
                output_manifest_sha256 = ?
            WHERE collection_run_id = 'collection-1'
            """,
            ("b" * 64,),
        )


@pytest.mark.parametrize("active_state", ["WAITING_LOGIN", "RUNNING", "IMPORTING"])
def test_finalization_rejects_active_collection(
    connection, repository, active_state
):
    facts = seed_fact_graph(connection, repository)
    connection.execute(
        "UPDATE collection_runs SET state = ?, started_at = ? "
        "WHERE collection_run_id = 'collection-1'",
        (
            "WAITING_LOGIN" if active_state == "WAITING_LOGIN" else "RUNNING",
            "2026-08-12T00:00:00Z",
        ),
    )
    if active_state == "IMPORTING":
        connection.execute(
            "UPDATE collection_runs SET state = 'IMPORTING' "
            "WHERE collection_run_id = 'collection-1'"
        )

    with pytest.raises(sqlite3.IntegrityError, match="ACTIVE_COLLECTION"):
        repository.finalize_run(facts["run_id"], "REVISE_MVP", {})

    assert connection.execute(
        "SELECT state FROM mvp_runs WHERE mvp_run_id = ?", (facts["run_id"],)
    ).fetchone()[0] == "ACTIVE"


@pytest.mark.parametrize("active_state", ["WAITING_LOGIN", "RUNNING", "IMPORTING"])
def test_repository_rejects_run_cancellation_with_active_collection(
    connection, repository, active_state
):
    facts = seed_fact_graph(connection, repository)
    set_seed_collection_active_state(connection, active_state)
    before = tuple(
        connection.execute(
            "SELECT run.state, collection.state FROM mvp_runs run "
            "JOIN collection_runs collection "
            "ON collection.mvp_run_id = run.mvp_run_id "
            "WHERE run.mvp_run_id = ?",
            (facts["run_id"],),
        ).fetchone()
    )

    with pytest.raises(FinalizedRunError, match="active collection"):
        repository.cancel_run(facts["run_id"])

    after = tuple(
        connection.execute(
            "SELECT run.state, collection.state FROM mvp_runs run "
            "JOIN collection_runs collection "
            "ON collection.mvp_run_id = run.mvp_run_id "
            "WHERE run.mvp_run_id = ?",
            (facts["run_id"],),
        ).fetchone()
    )
    assert after == before == ("ACTIVE", active_state)
    assert_active_collection_slot_can_be_released(repository, facts["run_id"])


@pytest.mark.parametrize("active_state", ["WAITING_LOGIN", "RUNNING", "IMPORTING"])
def test_sql_rejects_run_cancellation_with_active_collection(
    connection, repository, active_state
):
    facts = seed_fact_graph(connection, repository)
    set_seed_collection_active_state(connection, active_state)

    with pytest.raises(
        sqlite3.IntegrityError,
        match="ACTIVE_COLLECTION_PREVENTS_CANCELLATION",
    ):
        connection.execute(
            "UPDATE mvp_runs SET state = 'CANCELLED' WHERE mvp_run_id = ?",
            (facts["run_id"],),
        )

    assert tuple(
        connection.execute(
            "SELECT run.state, collection.state FROM mvp_runs run "
            "JOIN collection_runs collection "
            "ON collection.mvp_run_id = run.mvp_run_id "
            "WHERE run.mvp_run_id = ?",
            (facts["run_id"],),
        ).fetchone()
    ) == ("ACTIVE", active_state)
    assert_active_collection_slot_can_be_released(repository, facts["run_id"])


@pytest.mark.parametrize("reactivated_state", ["WAITING_LOGIN", "RUNNING"])
def test_sql_rejects_queued_collection_reactivation_after_run_cancellation(
    connection, repository, reactivated_state
):
    run_id = repository.create_run(["bili", "dy"])
    connection.execute(
        """
        INSERT INTO campaigns (
            campaign_id, mvp_run_id, platform, query_cluster, query_text,
            max_contents, max_comments_per_content, state, created_at
        ) VALUES (
            'queued-reactivation-campaign', ?, 'bili', 'sales', '线索',
            1, 1, 'ACTIVE', '2026-08-12T00:00:00Z'
        )
        """,
        (run_id,),
    )
    connection.execute(
        """
        INSERT INTO collection_runs (
            collection_run_id, mvp_run_id, campaign_id, platform,
            attempt, backend, started_by, runtime_lock_sha256, state
        ) VALUES (
            'queued-reactivation', ?, 'queued-reactivation-campaign', 'bili', 1,
            'MEDIACRAWLER_AUTHORIZED', 'test-operator', ?, 'QUEUED'
        )
        """,
        (run_id, "a" * 64),
    )
    assert tuple(
        connection.execute(
            "SELECT run.state, collection.state, collection.started_at "
            "FROM mvp_runs run JOIN collection_runs collection "
            "ON collection.mvp_run_id = run.mvp_run_id "
            "WHERE collection.collection_run_id = 'queued-reactivation'"
        ).fetchone()
    ) == ("ACTIVE", "QUEUED", None)
    connection.commit()

    repository.cancel_run(run_id)
    assert connection.execute(
        "SELECT state FROM mvp_runs WHERE mvp_run_id = ?", (run_id,)
    ).fetchone()[0] == "CANCELLED"

    with pytest.raises(sqlite3.IntegrityError, match="COLLECTION_REQUIRES_ACTIVE_RUN"):
        connection.execute(
            "UPDATE collection_runs SET state = ?, started_at = ? "
            "WHERE collection_run_id = 'queued-reactivation'",
            (reactivated_state, "2026-08-12T00:00:00Z"),
        )

    assert tuple(
        connection.execute(
            "SELECT state, started_at FROM collection_runs "
            "WHERE collection_run_id = 'queued-reactivation'"
        ).fetchone()
    ) == ("QUEUED", None)
    next_run_id = repository.create_run(["bili", "dy"])
    repository.begin_collection(
        run_id=next_run_id,
        collection_run_id=f"active-after-rejected-{reactivated_state.lower()}",
        platform="dy",
        query_cluster="sales",
        query_text="新线索",
        max_contents=1,
        max_comments_per_content=1,
        started_by="test-operator",
        runtime_lock_sha256="a" * 64,
    )
    assert repository.connection.execute(
        "SELECT state FROM collection_runs WHERE collection_run_id = ?",
        (f"active-after-rejected-{reactivated_state.lower()}",),
    ).fetchone()[0] == "RUNNING"


def test_collection_attempt_is_unique_within_campaign(connection, repository):
    facts = seed_fact_graph(connection, repository)

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO collection_runs (
                collection_run_id, mvp_run_id, campaign_id, platform,
                attempt, backend, started_by, runtime_lock_sha256, state
            ) VALUES (
                'duplicate-attempt', ?, 'campaign-1', 'bili', 1,
                'MEDIACRAWLER_AUTHORIZED', 'test-operator', ?, 'QUEUED'
            )
            """,
            (facts["run_id"], "a" * 64),
        )


def test_collection_requires_campaign(connection, repository):
    run_id = repository.create_run(["bili", "dy"])

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO collection_runs (
                collection_run_id, mvp_run_id, campaign_id, platform,
                attempt, backend, started_by, runtime_lock_sha256, state
            ) VALUES (
                'missing-campaign', ?, NULL, 'bili', 1,
                'MEDIACRAWLER_AUTHORIZED', 'test-operator', ?, 'QUEUED'
            )
            """,
            (run_id, "a" * 64),
        )


@pytest.mark.parametrize(
    ("max_contents", "max_comments_per_content"),
    [
        (None, 20),
        (0, 20),
        (11, 20),
        (5, None),
        (5, 0),
        (5, 51),
    ],
)
def test_sql_rejects_invalid_campaign_limits(
    connection, repository, max_contents, max_comments_per_content
):
    run_id = repository.create_run(["bili", "dy"])

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO campaigns (
                campaign_id, mvp_run_id, platform, query_cluster, query_text,
                max_contents, max_comments_per_content, state, created_at
            ) VALUES (
                'invalid-limits', ?, 'bili', 'sales', '线索', ?, ?,
                'ACTIVE', '2026-08-12T00:00:00Z'
            )
            """,
            (run_id, max_contents, max_comments_per_content),
        )


@pytest.mark.parametrize(
    ("max_contents", "max_comments_per_content"),
    [(1.5, 20), (5, 1.5)],
)
def test_sql_rejects_fractional_campaign_limits(
    connection, repository, max_contents, max_comments_per_content
):
    run_id = repository.create_run(["bili", "dy"])

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO campaigns (
                campaign_id, mvp_run_id, platform, query_cluster, query_text,
                max_contents, max_comments_per_content, state, created_at
            ) VALUES (
                'fractional-limits', ?, 'bili', 'sales', '线索', ?, ?,
                'ACTIVE', '2026-08-12T00:00:00Z'
            )
            """,
            (run_id, max_contents, max_comments_per_content),
        )


def test_sql_rejects_fractional_collection_attempt(connection, repository):
    run_id = repository.create_run(["bili", "dy"])
    connection.execute(
        """
        INSERT INTO campaigns (
            campaign_id, mvp_run_id, platform, query_cluster, query_text,
            state, created_at
        ) VALUES (
            'fractional-attempt-campaign', ?, 'bili', 'sales', '线索',
            'ACTIVE', '2026-08-12T00:00:00Z'
        )
        """,
        (run_id,),
    )

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO collection_runs (
                collection_run_id, mvp_run_id, campaign_id, platform,
                attempt, backend, started_by, runtime_lock_sha256, state
            ) VALUES (
                'fractional-attempt', ?, 'fractional-attempt-campaign',
                'bili', 1.5, 'SIMULATION_ONLY', 'test-operator', ?, 'QUEUED'
            )
            """,
            (run_id, "a" * 64),
        )


def test_repository_collection_backend_defaults_to_simulation_only(repository):
    run_id = repository.create_run(["bili", "dy"])
    repository.begin_collection(
        run_id=run_id,
        collection_run_id="safe-default-backend",
        platform="bili",
        query_cluster="sales",
        query_text="线索",
        max_contents=1,
        max_comments_per_content=1,
        started_by="test-operator",
        runtime_lock_sha256="a" * 64,
    )

    backend = repository.connection.execute(
        "SELECT backend FROM collection_runs WHERE collection_run_id = ?",
        ("safe-default-backend",),
    ).fetchone()[0]
    assert backend == "SIMULATION_ONLY"


def test_sql_rejects_unknown_collection_backend(connection, repository):
    run_id = repository.create_run(["bili", "dy"])
    campaign_id = repository.begin_collection(
        run_id=run_id,
        collection_run_id="known-backend",
        platform="bili",
        query_cluster="sales",
        query_text="线索",
        max_contents=1,
        max_comments_per_content=1,
        started_by="test-operator",
        runtime_lock_sha256="a" * 64,
    )

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO collection_runs (
                collection_run_id, mvp_run_id, campaign_id, platform,
                attempt, backend, started_by, runtime_lock_sha256, state
            ) VALUES (
                'unknown-backend', ?, ?, 'bili', 2, 'FIXTURE_BUT_REAL',
                'test-operator', ?, 'QUEUED'
            )
            """,
            (run_id, campaign_id, "a" * 64),
        )


def test_collection_cannot_be_inserted_directly_in_a_terminal_state(
    connection, repository
):
    run_id = repository.create_run(["bili", "dy"])
    connection.execute(
        """
        INSERT INTO campaigns (
            campaign_id, mvp_run_id, platform, query_cluster, query_text,
            max_contents, max_comments_per_content, state, created_at
        ) VALUES (
            'terminal-insert-campaign', ?, 'bili', 'sales', '线索',
            1, 1, 'ACTIVE', '2026-08-12T00:00:00Z'
        )
        """,
        (run_id,),
    )

    with pytest.raises(sqlite3.IntegrityError, match="COLLECTION_INITIAL_STATE_INVALID"):
        connection.execute(
            """
            INSERT INTO collection_runs (
                collection_run_id, mvp_run_id, campaign_id, platform,
                attempt, backend, started_by, runtime_lock_sha256, state,
                started_at, finished_at, raw_count, unique_count,
                output_manifest_sha256
            ) VALUES (
                'terminal-insert', ?, 'terminal-insert-campaign', 'bili', 1,
                'MEDIACRAWLER_AUTHORIZED', 'test-operator', ?, 'SUCCEEDED',
                '2026-08-12T00:00:00Z', '2026-08-12T00:01:00Z', 1, 1, ?
            )
            """,
            (run_id, "a" * 64, "b" * 64),
        )


@pytest.mark.parametrize("platforms", [[], ["bili"], ["dy"], ["dy", "bili"], ["bili", "bili"], ["bili", "other"]])
def test_run_requires_exact_bili_and_dy_platform_scope(repository, platforms):
    with pytest.raises(ValueError, match="exactly"):
        repository.create_run(platforms)


def test_revision_requires_a_finalized_base(repository):
    base_run_id = repository.create_run(["bili", "dy"])

    with pytest.raises(ValueError, match="FINALIZED"):
        repository.create_run(["bili", "dy"], revision_of_run_id=base_run_id)


def test_base_run_allows_only_one_revision(repository):
    base_run_id = repository.create_run(["bili", "dy"])
    repository.finalize_run(base_run_id, "REVISE_MVP", {})
    revision_id = repository.create_run(
        ["bili", "dy"], revision_of_run_id=base_run_id
    )
    repository.finalize_run(revision_id, "REVISE_MVP", {})

    with pytest.raises(ValueError, match="one revision"):
        repository.create_run(["bili", "dy"], revision_of_run_id=base_run_id)


def test_revision_cannot_be_revised_again(repository):
    base_run_id = repository.create_run(["bili", "dy"])
    repository.finalize_run(base_run_id, "REVISE_MVP", {})
    revision_id = repository.create_run(
        ["bili", "dy"], revision_of_run_id=base_run_id
    )
    repository.finalize_run(revision_id, "REVISE_MVP", {})

    with pytest.raises(ValueError, match="revision cannot be revised"):
        repository.create_run(["bili", "dy"], revision_of_run_id=revision_id)


def test_sql_rejects_self_revision(connection):
    with pytest.raises(sqlite3.IntegrityError, match="RUN_REVISION_SELF"):
        insert_run(
            connection,
            "self-revision",
            state="DRAFT",
            revision_of_run_id="self-revision",
        )


def test_sql_requires_finalized_revision_parent(connection):
    insert_run(connection, "draft-base", state="DRAFT")

    with pytest.raises(
        sqlite3.IntegrityError, match="RUN_REVISION_PARENT_NOT_FINALIZED"
    ):
        insert_run(
            connection,
            "draft-child",
            state="DRAFT",
            revision_of_run_id="draft-base",
        )


def test_sql_rejects_second_revision_and_revision_chain(connection):
    insert_run(connection, "base")
    insert_run(connection, "revision-1", revision_of_run_id="base")

    with pytest.raises(sqlite3.IntegrityError):
        insert_run(connection, "revision-2", revision_of_run_id="base")
    with pytest.raises(
        sqlite3.IntegrityError, match="RUN_REVISION_CHAIN_NOT_ALLOWED"
    ):
        insert_run(
            connection,
            "revision-chain",
            revision_of_run_id="revision-1",
        )


def test_duplicate_signal_reuses_fact_and_adds_observation(repository):
    run_id = repository.create_run(["bili", "dy"])
    first = repository.import_signal(run_id, signal(external_comment_id="42"))
    second = repository.import_signal(run_id, signal(external_comment_id="42"))

    assert first.signal_id == second.signal_id
    assert first.created is True
    assert second.created is False
    assert first.observation_id != second.observation_id
    assert repository.count_signals(run_id) == 1
    assert repository.count_observations(run_id) == 2


def test_fallback_canonical_key_deduplicates_without_external_comment_id(repository):
    run_id = repository.create_run(["bili", "dy"])
    item = signal(external_comment_id=None)

    first = repository.import_signal(run_id, item)
    second = repository.import_signal(run_id, item)

    assert first.signal_id == second.signal_id
    assert repository.count_signals(run_id) == 1
    assert repository.count_observations(run_id) == 2


def test_same_external_id_with_different_body_is_identity_conflict(repository):
    run_id = repository.create_run(["bili", "dy"])
    repository.import_signal(run_id, signal(external_comment_id="42", body="第一版正文"))

    with pytest.raises(SignalIdentityConflict, match="SIGNAL_IDENTITY_CONFLICT"):
        repository.import_signal(run_id, signal(external_comment_id="42", body="不同正文"))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("external_comment_id", "   ", "external comment ID"),
        ("body", " \t ", "body"),
        ("comment_url", "  ", "comment URL"),
        ("author_public_id", "\n", "author public ID"),
    ],
)
def test_import_signal_rejects_blank_identity_fields(
    repository, field, value, message
):
    run_id = repository.create_run(["bili", "dy"])

    with pytest.raises(ValueError, match=message):
        repository.import_signal(run_id, replace(signal(), **{field: value}))


def test_membership_is_isolated_by_mvp_run(repository):
    first_run = repository.create_run(["bili", "dy"])
    first = repository.import_signal(first_run, signal(external_comment_id="same"))
    repository.finalize_run(first_run, "REVISE_MVP", {"unique_signals": 1})
    second_run = repository.create_run(["bili", "dy"])
    second = repository.import_signal(second_run, signal(external_comment_id="same"))

    assert first.signal_id == second.signal_id
    assert repository.count_signals(first_run) == 1
    assert repository.count_signals(second_run) == 1
    assert repository.count_observations(first_run) == 1
    assert repository.count_observations(second_run) == 1


def test_score_and_review_composite_foreign_keys_cannot_cross_runs(connection, repository):
    first_run = repository.create_run(["bili", "dy"])
    first_signal = repository.import_signal(first_run, signal(external_comment_id="first"))
    connection.execute(
        """
        INSERT INTO score_runs (
            score_run_id, mvp_run_id, signal_id, provider, model,
            prompt_version, schema_version, dimension_scores_json,
            total_score, grade, confidence, reason_json, status
        ) VALUES ('score-1', ?, ?, 'test-provider', 'test-model', 'p1', 's1',
                  '{}', 8, 'B', 0.8, '{}', 'SUCCEEDED')
        """,
        (first_run, first_signal.signal_id),
    )
    repository.finalize_run(first_run, "REVISE_MVP", {})
    second_run = repository.create_run(["bili", "dy"])
    second_signal = repository.import_signal(second_run, signal(external_comment_id="second"))
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO human_reviews
                (review_id, mvp_run_id, signal_id, presented_score_run_id, label)
            VALUES ('review-cross-run', ?, ?, 'score-1', 'HIGH_INTENT')
            """,
            (second_run, second_signal.signal_id),
        )


def test_review_requires_a_successful_presented_score(connection, repository):
    run_id = repository.create_run(["bili", "dy"])
    imported = repository.import_signal(run_id, signal())
    connection.execute(
        """
        INSERT INTO score_runs (
            score_run_id, mvp_run_id, signal_id, prompt_version,
            schema_version, status, error_code
        ) VALUES ('failed-score', ?, ?, 'p1', 's1', 'FAILED',
                  'MODEL_OUTPUT_INVALID')
        """,
        (run_id, imported.signal_id),
    )

    with pytest.raises(
        sqlite3.IntegrityError, match="PRESENTED_SCORE_NOT_SUCCEEDED"
    ):
        connection.execute(
            """
            INSERT INTO human_reviews (
                review_id, mvp_run_id, signal_id, presented_score_run_id, label
            ) VALUES ('invalid-review', ?, ?, 'failed-score', 'HIGH_INTENT')
            """,
            (run_id, imported.signal_id),
        )


def test_superseding_review_must_match_run_and_signal(connection, repository):
    first_run = repository.create_run(["bili", "dy"])
    first_signal = repository.import_signal(first_run, signal())
    connection.execute(
        """
        INSERT INTO score_runs (
            score_run_id, mvp_run_id, signal_id, provider, model,
            prompt_version, schema_version, dimension_scores_json,
            total_score, grade, confidence, reason_json, status
        ) VALUES ('first-score', ?, ?, 'test-provider', 'test-model', 'p1', 's1',
                  '{}', 8, 'B', 0.8, '{}', 'SUCCEEDED')
        """,
        (first_run, first_signal.signal_id),
    )
    connection.execute(
        """
        INSERT INTO score_presentations (
            presentation_id, mvp_run_id, signal_id, score_run_id, presented_at
        ) VALUES ('first-presentation', ?, ?, 'first-score', '2026-08-12T00:00:00Z')
        """,
        (first_run, first_signal.signal_id),
    )
    insert_completed_activity(
        connection, activity_id="first-review-activity", run_id=first_run,
        signal_id=first_signal.signal_id, kind="REVIEW",
        started_at="2026-08-12T00:00:00Z",
        completed_at="2026-08-12T00:01:00Z",
    )
    connection.execute(
        """
        INSERT INTO human_reviews (
            review_id, mvp_run_id, signal_id, presented_score_run_id, label,
            activity_session_id, started_at, completed_at, active_seconds
        ) VALUES ('first-review', ?, ?, 'first-score', 'HIGH_INTENT',
                  'first-review-activity', '2026-08-12T00:00:00Z',
                  '2026-08-12T00:01:00Z', 60)
        """,
        (first_run, first_signal.signal_id),
    )
    second_signal = repository.import_signal(
        first_run,
        signal(
            external_comment_id="comment-2",
            comment_url="https://www.bilibili.com/read/comment-2",
        ),
    )
    connection.execute(
        """
        INSERT INTO score_runs (
            score_run_id, mvp_run_id, signal_id, provider, model,
            prompt_version, schema_version, dimension_scores_json,
            total_score, grade, confidence, reason_json, status
        ) VALUES ('second-score', ?, ?, 'test-provider', 'test-model', 'p1', 's1',
                  '{}', 8, 'B', 0.8, '{}', 'SUCCEEDED')
        """,
        (first_run, second_signal.signal_id),
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO human_reviews (
                review_id, mvp_run_id, signal_id, presented_score_run_id,
                label, supersedes_review_id
            ) VALUES ('wrong-signal-review', ?, ?, 'second-score',
                      'POSSIBLE', 'first-review')
            """,
            (first_run, second_signal.signal_id),
        )

    repository.finalize_run(first_run, "REVISE_MVP", {})
    second_run = repository.create_run(["bili", "dy"])
    repository.import_signal(second_run, signal())
    connection.execute(
        """
        INSERT INTO score_runs (
            score_run_id, mvp_run_id, signal_id, provider, model,
            prompt_version, schema_version, dimension_scores_json,
            total_score, grade, confidence, reason_json, status
        ) VALUES ('other-run-score', ?, ?, 'test-provider', 'test-model',
                  'p1', 's1', '{}', 8, 'B', 0.8, '{}', 'SUCCEEDED')
        """,
        (second_run, first_signal.signal_id),
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO human_reviews (
                review_id, mvp_run_id, signal_id, presented_score_run_id,
                label, supersedes_review_id
            ) VALUES ('wrong-run-review', ?, ?, 'other-run-score',
                      'POSSIBLE', 'first-review')
            """,
            (second_run, first_signal.signal_id),
        )


def test_review_history_has_one_root_and_cannot_branch(connection, repository):
    facts = seed_fact_graph(connection, repository)

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO human_reviews (
                review_id, mvp_run_id, signal_id, presented_score_run_id,
                label, reason, completed_at
            ) VALUES ('second-root', ?, ?, 'score-1', 'POSSIBLE',
                      '断根改标', '2026-08-12T01:00:00Z')
            """,
            (facts["run_id"], facts["signal_id"]),
        )

    insert_completed_activity(
        connection, activity_id="review-activity-2", run_id=facts["run_id"],
        signal_id=facts["signal_id"], kind="REVIEW",
        started_at="2026-08-12T01:00:00Z",
        completed_at="2026-08-12T01:01:00Z",
    )
    connection.execute(
        """
        INSERT INTO human_reviews (
            review_id, mvp_run_id, signal_id, presented_score_run_id,
            label, reason, activity_session_id, started_at, completed_at,
            active_seconds, supersedes_review_id
        ) VALUES ('review-2', ?, ?, 'score-1', 'POSSIBLE',
                  '有效修订', 'review-activity-2', '2026-08-12T01:00:00Z',
                  '2026-08-12T01:01:00Z', 60, 'review-1')
        """,
        (facts["run_id"], facts["signal_id"]),
    )

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO human_reviews (
                review_id, mvp_run_id, signal_id, presented_score_run_id,
                label, reason, completed_at, supersedes_review_id
            ) VALUES ('branch-review', ?, ?, 'score-1', 'NOT_LEAD',
                      '不允许分叉', '2026-08-12T02:00:00Z', 'review-1')
            """,
            (facts["run_id"], facts["signal_id"]),
        )


@pytest.mark.parametrize(
    ("override_column", "override_value"),
    [("signal_id", "second-signal"), ("platform", "dy"), ("subject_key", "other")],
)
def test_follow_up_parent_must_match_signal_platform_and_subject(
    connection, repository, override_column, override_value
):
    facts = seed_fact_graph(connection, repository)
    if override_column == "signal_id":
        override_value = repository.import_signal(
            facts["run_id"],
            signal(
                external_comment_id="second-signal",
                comment_url="https://www.bilibili.com/read/second-signal",
            ),
        ).signal_id
    values = {
        "signal_id": facts["signal_id"],
        "platform": "bili",
        "subject_key": "bili:author-1",
    }
    values[override_column] = override_value

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO outreach_actions (
                outreach_action_id, mvp_run_id, signal_id, platform,
                subject_key, status, parent_outreach_action_id, created_at
            ) VALUES ('invalid-follow-up', ?, ?, ?, ?, 'SENT_VERIFIED',
                      'outreach-1', '2026-08-12T00:00:00Z')
            """,
            (
                facts["run_id"],
                values["signal_id"],
                values["platform"],
                values["subject_key"],
            ),
        )


def test_follow_up_parent_cannot_cross_runs(connection, repository):
    facts = seed_fact_graph(connection, repository)
    repository.finalize_run(facts["run_id"], "REVISE_MVP", {})
    second_run = repository.create_run(["bili", "dy"])
    repository.import_signal(second_run, signal())

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO outreach_actions (
                outreach_action_id, mvp_run_id, signal_id, platform,
                subject_key, status, parent_outreach_action_id, created_at
            ) VALUES ('cross-run-follow-up', ?, ?, 'bili', 'bili:author-1',
                      'SENT_VERIFIED', 'outreach-1', '2026-08-12T00:00:00Z')
            """,
            (second_run, facts["signal_id"]),
        )


def test_follow_up_parent_must_be_the_root_first_contact(connection, repository):
    facts = seed_fact_graph(connection, repository)
    connection.execute(
        """
        INSERT INTO outreach_actions (
            outreach_action_id, mvp_run_id, signal_id, review_id, score_run_id,
            draft_run_id, platform, subject_key, approved_text, sent_at,
            source_url, context_evidence, evidence_summary, source_link_opened,
            status, parent_outreach_action_id,
            created_at
        ) VALUES ('follow-up-1', ?, ?, 'review-1', 'score-1', 'draft-1',
                  'bili', 'bili:author-1', '需要线索筛选，人工跟进',
                  '2026-08-13T00:00:00Z',
                  'https://www.bilibili.com/video/BV1', '需要线索筛选',
                  '需要线索筛选', 1, 'SENT_VERIFIED',
                  'outreach-1', '2026-08-13T00:00:00Z')
        """,
        (facts["run_id"], facts["signal_id"]),
    )

    with pytest.raises(sqlite3.IntegrityError, match="FOLLOW_UP_PARENT_NOT_ROOT"):
        connection.execute(
            """
            INSERT INTO outreach_actions (
                outreach_action_id, mvp_run_id, signal_id, review_id,
                    score_run_id, draft_run_id, platform, subject_key,
                    approved_text, sent_at, source_url, context_evidence,
                    evidence_summary, source_link_opened, status,
                    parent_outreach_action_id, created_at
                ) VALUES ('follow-up-2', ?, ?, 'review-1', 'score-1', 'draft-1',
                          'bili', 'bili:author-1', '需要线索筛选，再次人工跟进',
                          '2026-08-14T00:00:00Z',
                          'https://www.bilibili.com/video/BV1', '需要线索筛选',
                          '需要线索筛选', 1,
                      'SENT_VERIFIED', 'follow-up-1',
                      '2026-08-14T00:00:00Z')
            """,
            (facts["run_id"], facts["signal_id"]),
        )


@pytest.mark.parametrize(
    "invalid_override",
    [
        {"source_link_opened": 0},
        {"approved_text": "   "},
        {"sent_at": ""},
        {"source_url": "\n"},
    ],
)
def test_sent_outreach_requires_complete_manual_confirmation(
    connection, repository, invalid_override
):
    facts = seed_fact_graph(connection, repository)
    values = {
        "approved_text": "需要线索筛选，人工批准文本",
        "sent_at": "2026-08-13T00:00:00Z",
        "source_url": "https://www.bilibili.com/video/BV1",
        "source_link_opened": 1,
    }
    values.update(invalid_override)

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO outreach_actions (
                outreach_action_id, mvp_run_id, signal_id, review_id,
                    score_run_id, draft_run_id, platform, subject_key,
                    approved_text, sent_at, source_url, context_evidence,
                    evidence_summary, source_link_opened,
                    status, created_at
            ) VALUES ('invalid-manual-outreach', ?, ?, 'review-1', 'score-1',
                      'draft-1', 'bili', 'subject-2', ?, ?, ?,
                      '需要线索筛选', '需要线索筛选', ?,
                      'SENT_VERIFIED', '2026-08-13T00:00:00Z')
            """,
            (
                facts["run_id"],
                facts["signal_id"],
                values["approved_text"],
                values["sent_at"],
                values["source_url"],
                values["source_link_opened"],
            ),
        )


@pytest.mark.parametrize(
    ("table", "key_column", "key_name", "mutable_column", "replacement"),
    [
        ("sources", "source_id", "source_id", "title", "changed"),
        ("signals", "signal_id", "signal_id", "body", "changed"),
        ("keyword_versions", "keyword_version_id", None, "rationale", "changed"),
        ("mvp_run_signals", "signal_id", "signal_id", "added_at", "changed"),
        (
            "signal_observations",
            "observation_id",
            "observation_id",
            "raw_sha256",
            "changed",
        ),
        ("score_runs", "score_run_id", None, "error_code", "changed"),
        (
            "score_presentations",
            "presentation_id",
            None,
            "presented_at",
            "changed",
        ),
        ("human_reviews", "review_id", None, "note", "changed"),
        ("draft_runs", "draft_run_id", None, "body", "changed"),
        ("outreach_actions", "outreach_action_id", None, "status", "changed"),
        ("response_events", "response_event_id", None, "summary", "changed"),
        ("interviews", "interview_id", None, "next_step", "changed"),
        (
            "quote_opportunities",
            "quote_opportunity_id",
            None,
            "scope_summary",
            "changed",
        ),
        ("daily_snapshots", "daily_snapshot_id", None, "risk_summary", "changed"),
    ],
)
def test_historical_facts_are_append_only_while_run_is_active(
    connection,
    repository,
    table,
    key_column,
    key_name,
    mutable_column,
    replacement,
):
    facts = seed_fact_graph(connection, repository)
    key_value = facts[key_name] if key_name else {
        "keyword_versions": "keyword-1",
        "score_runs": "score-1",
        "score_presentations": "presentation-1",
        "human_reviews": "review-1",
        "draft_runs": "draft-1",
        "outreach_actions": "outreach-1",
        "response_events": "response-1",
        "interviews": "interview-1",
        "quote_opportunities": "quote-1",
        "daily_snapshots": "snapshot-1",
    }[table]

    with pytest.raises(sqlite3.IntegrityError, match="APPEND_ONLY_FACT"):
        connection.execute(
            f"UPDATE {table} SET {mutable_column} = ? WHERE {key_column} = ?",
            (replacement, key_value),
        )
    with pytest.raises(sqlite3.IntegrityError, match="APPEND_ONLY_FACT"):
        connection.execute(f"DELETE FROM {table} WHERE {key_column} = ?", (key_value,))


@pytest.mark.parametrize("table", ["campaigns", "collection_runs"])
def test_mutable_collection_records_allow_state_changes_but_not_delete(
    connection, repository, table
):
    seed_fact_graph(connection, repository)
    key_column = "campaign_id" if table == "campaigns" else "collection_run_id"
    key_value = "campaign-1" if table == "campaigns" else "collection-1"

    assignment = (
        "state = 'RUNNING', started_at = '2026-08-12T00:00:00Z'"
        if table == "collection_runs"
        else "state = 'RUNNING'"
    )
    connection.execute(
        f"UPDATE {table} SET {assignment} WHERE {key_column} = ?", (key_value,)
    )
    assert (
        connection.execute(
            f"SELECT state FROM {table} WHERE {key_column} = ?", (key_value,)
        ).fetchone()[0]
        == "RUNNING"
    )
    with pytest.raises(sqlite3.IntegrityError, match="APPEND_ONLY_FACT"):
        connection.execute(f"DELETE FROM {table} WHERE {key_column} = ?", (key_value,))


@pytest.mark.parametrize(
    ("table", "assignment"),
    [
        ("campaigns", "query_text = 'rewritten'"),
        ("collection_runs", "backend = 'rewritten'"),
    ],
)
def test_collection_lifecycle_update_cannot_rewrite_identity_or_config(
    connection, repository, table, assignment
):
    seed_fact_graph(connection, repository)
    key_column = "campaign_id" if table == "campaigns" else "collection_run_id"
    key_value = "campaign-1" if table == "campaigns" else "collection-1"

    with pytest.raises(sqlite3.IntegrityError, match="FACT_IDENTITY_IMMUTABLE"):
        connection.execute(
            f"UPDATE {table} SET {assignment} WHERE {key_column} = ?", (key_value,)
        )


def test_collection_and_signal_platforms_must_match_their_parents(
    connection, repository
):
    facts = seed_fact_graph(connection, repository)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO collection_runs (
                collection_run_id, mvp_run_id, campaign_id, platform,
                attempt, backend, started_by, runtime_lock_sha256, state
            ) VALUES ('wrong-platform-collection', ?, 'campaign-1', 'dy', 2,
                      'MEDIACRAWLER_AUTHORIZED', 'test-operator', ?, 'QUEUED')
            """,
            (facts["run_id"], "a" * 64),
        )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO signals (
                signal_id, source_id, platform, external_comment_id,
                normalized_comment_url, author_public_id, body, body_sha256
            ) VALUES ('wrong-platform-signal', ?, 'dy', 'dy-comment',
                      'https://douyin.com/comment/dy-comment', 'author', 'body', ?)
            """,
            (facts["source_id"], "c" * 64),
        )


@pytest.mark.parametrize(
    "invalid_binding",
    ["missing", "incomplete"],
)
def test_outreach_requires_completed_successful_fact_bindings(
    connection, repository, invalid_binding
):
    facts = seed_fact_graph(connection, repository)
    if invalid_binding == "missing":
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO outreach_actions (
                    outreach_action_id, mvp_run_id, signal_id, platform,
                    subject_key, status, created_at
                ) VALUES ('unbound-outreach', ?, ?, 'bili', 'subject-2',
                          'SENT_VERIFIED', '2026-08-12T00:00:00Z')
                """,
                (facts["run_id"], facts["signal_id"]),
            )
        return

    connection.execute(
        """
        INSERT INTO score_runs (
            score_run_id, mvp_run_id, signal_id, prompt_version,
            schema_version, status, error_code
        ) VALUES ('pending-score', ?, ?, 'p1', 's1', 'FAILED',
                  'MODEL_UNAVAILABLE')
        """,
        (facts["run_id"], facts["signal_id"]),
    )
    # Reuse the completed current review; the deliberately failed score and
    # draft below are enough to exercise the outreach binding failure.
    connection.execute(
        """
        INSERT INTO draft_runs (
            draft_run_id, mvp_run_id, signal_id, prompt_version, draft_kind,
            body, status, error_code, created_at
        ) VALUES ('failed-draft', ?, ?, 'p1', 'GENERATED', NULL, 'FAILED',
                  'MODEL_UNAVAILABLE',
                  '2026-08-12T00:00:00Z')
        """,
        (facts["run_id"], facts["signal_id"]),
    )
    with pytest.raises(
        sqlite3.IntegrityError,
        match="OUTREACH_(BINDING_NOT_READY|SCORE_REVIEW_MISMATCH)",
    ):
        connection.execute(
            """
            INSERT INTO outreach_actions (
                outreach_action_id, mvp_run_id, signal_id, review_id,
                score_run_id, draft_run_id, platform, subject_key,
                approved_text, sent_at, source_url, context_evidence,
                evidence_summary, source_link_opened,
                status, created_at
            ) VALUES ('incomplete-outreach', ?, ?, 'review-1',
                          'pending-score', 'failed-draft', 'bili', 'bili:author-1',
                      '需要线索筛选，人工批准文本', '2026-08-12T00:00:00Z',
                      'https://www.bilibili.com/video/BV1', '需要线索筛选',
                      '需要线索筛选', 1,
                      'SENT_VERIFIED', '2026-08-12T00:00:00Z')
            """,
            (facts["run_id"], facts["signal_id"]),
        )


@pytest.mark.parametrize("table", ["campaigns", "collection_runs"])
def test_mutable_collection_records_cannot_move_into_a_finalized_run(
    connection, repository, table
):
    finalized_run = repository.create_run(["bili", "dy"])
    connection.execute(
        """
        INSERT INTO campaigns (
            campaign_id, mvp_run_id, platform, query_cluster, query_text,
            state, created_at
        ) VALUES ('final-campaign', ?, 'bili', 'sales', '线索', 'DONE',
                  '2026-08-12T00:00:00Z')
        """,
        (finalized_run,),
    )
    repository.finalize_run(finalized_run, "REVISE_MVP", {})
    active_run = repository.create_run(["bili", "dy"])
    connection.execute(
        """
        INSERT INTO campaigns (
            campaign_id, mvp_run_id, platform, query_cluster, query_text,
            state, created_at
        ) VALUES ('active-campaign', ?, 'bili', 'sales', '线索', 'QUEUED',
                  '2026-08-12T00:00:00Z')
        """,
        (active_run,),
    )
    if table == "collection_runs":
        connection.execute(
            """
            INSERT INTO collection_runs (
                collection_run_id, mvp_run_id, campaign_id, platform,
                attempt, backend, started_by, runtime_lock_sha256, state
            ) VALUES ('active-collection', ?, 'active-campaign', 'bili', 1,
                      'MEDIACRAWLER_AUTHORIZED', 'test-operator', ?, 'QUEUED')
            """,
            (active_run, "a" * 64),
        )

    with pytest.raises(sqlite3.IntegrityError, match="RUN_SCOPE_IMMUTABLE"):
        if table == "campaigns":
            connection.execute(
                "UPDATE campaigns SET mvp_run_id = ? WHERE campaign_id = 'active-campaign'",
                (finalized_run,),
            )
        else:
            connection.execute(
                """
                UPDATE collection_runs
                SET mvp_run_id = ?, campaign_id = 'final-campaign'
                WHERE collection_run_id = 'active-collection'
                """,
                (finalized_run,),
            )


def test_append_only_fact_cannot_move_into_a_finalized_run(connection, repository):
    finalized_run = repository.create_run(["bili", "dy"])
    repository.finalize_run(finalized_run, "REVISE_MVP", {})
    active_run = repository.create_run(["bili", "dy"])
    connection.execute(
        """
        INSERT INTO keyword_versions (
            keyword_version_id, mvp_run_id, version, query_cluster,
            query_text, content_sha256, created_at
        ) VALUES ('movable-keyword', ?, 'v1', 'sales', '线索', ?,
                  '2026-08-12T00:00:00Z')
        """,
        (active_run, "b" * 64),
    )

    with pytest.raises(sqlite3.IntegrityError, match="APPEND_ONLY_FACT"):
        connection.execute(
            """
            UPDATE keyword_versions SET mvp_run_id = ?
            WHERE keyword_version_id = 'movable-keyword'
            """,
            (finalized_run,),
        )


def test_risk_events_are_run_scoped_append_only_and_frozen(connection, repository):
    run_id = repository.create_run(["bili", "dy"])
    connection.execute(
        """
        INSERT INTO risk_events (
            risk_event_id, mvp_run_id, event_type, severity, summary,
            verified_at, forces_stop
        ) VALUES ('risk-1', ?, 'PLATFORM_PENALTY', 'CONFIRMED', '平台处罚',
                  '2026-08-12T00:00:00Z', 1)
        """,
        (run_id,),
    )
    with pytest.raises(sqlite3.IntegrityError, match="APPEND_ONLY_FACT"):
        connection.execute(
            "UPDATE risk_events SET summary = 'changed' WHERE risk_event_id = 'risk-1'"
        )
    with pytest.raises(sqlite3.IntegrityError, match="APPEND_ONLY_FACT"):
        connection.execute("DELETE FROM risk_events WHERE risk_event_id = 'risk-1'")

    repository.finalize_run(run_id, "REVISE_MVP", {})
    with pytest.raises(sqlite3.IntegrityError, match="FINALIZED_RUN_IMMUTABLE"):
        connection.execute(
            """
            INSERT INTO risk_events (
                risk_event_id, mvp_run_id, event_type, severity, summary,
                verified_at, forces_stop
            ) VALUES ('risk-2', ?, 'PLATFORM_PENALTY', 'CONFIRMED', 'late',
                      '2026-08-12T00:00:00Z', 1)
            """,
            (run_id,),
        )


def test_finalized_run_rejects_new_fact(repository):
    run_id = repository.create_run(["bili", "dy"])
    repository.finalize_run(run_id, "REVISE_MVP", {"unique_signals": 0})

    with pytest.raises(FinalizedRunError):
        repository.import_signal(run_id, signal())


def test_verifiable_signal_requires_complete_collection_provenance(repository):
    run_id = repository.create_run(["bili", "dy"])

    with pytest.raises(ValueError, match="VERIFIABLE_PROVENANCE_REQUIRED"):
        repository.import_signal(run_id, signal(verifiable=True))


def test_collection_and_signal_provenance_hashes_must_be_sha256(repository):
    run_id = repository.create_run(["bili", "dy"])
    with pytest.raises(ValueError, match="runtime lock SHA-256"):
        repository.begin_collection(
            run_id=run_id,
            collection_run_id="invalid-runtime-hash",
            platform="bili",
            query_cluster="sales",
            query_text="销售线索",
            max_contents=1,
            max_comments_per_content=1,
            started_by="test-operator",
            runtime_lock_sha256="z" * 64,
        )

    repository.begin_collection(
        run_id=run_id,
        collection_run_id="valid-runtime-hash",
        platform="bili",
        query_cluster="sales",
        query_text="销售线索",
        max_contents=1,
        max_comments_per_content=1,
        started_by="test-operator",
        runtime_lock_sha256="a" * 64,
    )
    with pytest.raises(ValueError, match="VERIFIABLE_PROVENANCE_REQUIRED"):
        repository.import_signal(
            run_id,
            replace(
                signal(verifiable=True),
                collection_run_id="valid-runtime-hash",
                query_cluster="sales",
                query_text="销售线索",
                envelope_sha256="z" * 64,
                normalizer_version="test-normalizer-v1",
            ),
        )

    assert repository.count_signals(run_id) == 0


def test_verifiable_signal_cannot_reuse_a_source_without_a_canonical_url(repository):
    run_id = repository.create_run(["bili", "dy"])
    repository.import_signal(
        run_id,
        replace(signal(), source_url=None),
    )
    repository.begin_collection(
        run_id=run_id,
        collection_run_id="complete-collection",
        platform="bili",
        query_cluster="sales",
        query_text="销售线索",
        max_contents=1,
        max_comments_per_content=1,
        started_by="test-operator",
        runtime_lock_sha256="a" * 64,
    )

    with pytest.raises(ValueError, match="VERIFIABLE_PROVENANCE_REQUIRED"):
        repository.import_signal(
            run_id,
            replace(
                signal(
                    external_comment_id="comment-2",
                    comment_url="https://www.bilibili.com/read/comment-2",
                    verifiable=True,
                ),
                collection_run_id="complete-collection",
                query_cluster="sales",
                query_text="销售线索",
                envelope_sha256="b" * 64,
                normalizer_version="test-normalizer-v1",
            ),
        )


def test_sql_rejects_verifiable_signal_with_incomplete_source_provenance(
    connection, repository
):
    repository.create_run(["bili", "dy"])
    connection.execute(
        """
        INSERT INTO sources (source_id, platform, external_source_id)
        VALUES ('incomplete-source', 'bili', 'external-source')
        """
    )

    with pytest.raises(sqlite3.IntegrityError, match="VERIFIABLE_PROVENANCE_REQUIRED"):
        connection.execute(
            """
            INSERT INTO signals (
                signal_id, source_id, platform, external_comment_id,
                normalized_comment_url, author_public_id, body, body_sha256,
                verifiable, normalizer_version
            ) VALUES (
                'invalid-verifiable-signal', 'incomplete-source', 'bili',
                'external-comment', 'https://www.bilibili.com/reply',
                'author', 'body', ?, 1, 'test-normalizer-v1'
            )
            """,
            (hashlib.sha256(b"body").hexdigest(),),
        )


@pytest.mark.parametrize("whitespace", ["\n", "\t", "\r", "\u3000"])
def test_sql_rejects_whitespace_only_verifiable_source_provenance(
    connection, repository, whitespace
):
    repository.create_run(["bili", "dy"])
    connection.execute(
        "INSERT INTO sources (source_id, platform, external_source_id, canonical_url) "
        "VALUES ('whitespace-source', 'bili', ?, ?)",
        (whitespace, whitespace),
    )
    body = "valid signal body"

    with pytest.raises(sqlite3.IntegrityError, match="VERIFIABLE_PROVENANCE_REQUIRED"):
        connection.execute(
            """
            INSERT INTO signals (
                signal_id, source_id, platform, external_comment_id,
                normalized_comment_url, author_public_id, body, body_sha256,
                verifiable, normalizer_version
            ) VALUES (
                'whitespace-source-signal', 'whitespace-source', 'bili',
                'valid-comment', 'https://www.bilibili.com/reply/valid',
                'valid-author', ?, ?, 1, 'test-normalizer-v1'
            )
            """,
            (body, hashlib.sha256(body.encode()).hexdigest()),
        )


def test_verifiable_observation_query_must_match_its_collection_campaign(repository):
    run_id = repository.create_run(["bili", "dy"])
    repository.begin_collection(
        run_id=run_id,
        collection_run_id="campaign-bound-collection",
        platform="bili",
        query_cluster="campaign-cluster",
        query_text="campaign-query",
        max_contents=1,
        max_comments_per_content=1,
        started_by="test-operator",
        runtime_lock_sha256="a" * 64,
    )

    with pytest.raises(ValueError, match="VERIFIABLE_PROVENANCE_REQUIRED"):
        repository.import_signal(
            run_id,
            replace(
                signal(verifiable=True),
                collection_run_id="campaign-bound-collection",
                query_cluster="fabricated-cluster",
                query_text="fabricated-query",
                envelope_sha256="b" * 64,
                normalizer_version="test-normalizer-v1",
            ),
        )

    assert repository.count_signals(run_id) == 0


@pytest.mark.parametrize("field", ["query_cluster", "query_text", "started_by"])
def test_collection_rejects_whitespace_only_identity(repository, field):
    run_id = repository.create_run(["bili", "dy"])
    values = {
        "run_id": run_id,
        "collection_run_id": f"whitespace-{field}",
        "platform": "bili",
        "query_cluster": "sales",
        "query_text": "销售线索",
        "max_contents": 1,
        "max_comments_per_content": 1,
        "started_by": "test-operator",
        "runtime_lock_sha256": "a" * 64,
    }
    values[field] = "\n"

    with pytest.raises(ValueError, match="required"):
        repository.begin_collection(**values)


def test_sql_rejects_whitespace_only_collection_identity(connection, repository):
    run_id = repository.create_run(["bili", "dy"])
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO campaigns (
                campaign_id, mvp_run_id, platform, query_cluster, query_text,
                max_contents, max_comments_per_content, state, created_at
            ) VALUES (
                'whitespace-campaign', ?, 'bili', '\n', '\t', 1, 1,
                'ACTIVE', '2026-08-12T00:00:00Z'
            )
            """,
            (run_id,),
        )


@pytest.mark.parametrize(
    "collected_at",
    ["2099-01-01T00:00:00Z", "2026-08-12T08:00:00+00:00"],
)
def test_verifiable_observation_cannot_be_recorded_in_the_future(
    connection, collected_at
):
    now = datetime(2026, 8, 12, 8, tzinfo=UTC)
    repository = Repository(connection, now=lambda: now)
    run_id = repository.create_run(["bili", "dy"])
    repository.begin_collection(
        run_id=run_id,
        collection_run_id="future-observation-collection",
        platform="bili",
        query_cluster="sales",
        query_text="销售线索",
        max_contents=1,
        max_comments_per_content=1,
        started_by="test-operator",
        runtime_lock_sha256="a" * 64,
    )

    with pytest.raises(ValueError, match="VERIFIABLE_PROVENANCE_REQUIRED"):
        repository.import_signal(
            run_id,
            replace(
                signal(verifiable=True),
                collection_run_id="future-observation-collection",
                query_cluster="sales",
                query_text="销售线索",
                collected_at=collected_at,
                envelope_sha256="b" * 64,
                normalizer_version="test-normalizer-v1",
            ),
        )

    assert repository.count_signals(run_id) == 0


def test_sql_rejects_noncanonical_observation_timestamp(connection, repository):
    run_id = repository.create_run(["bili", "dy"])
    repository.begin_collection(
        run_id=run_id,
        collection_run_id="sql-invalid-time-collection",
        platform="bili",
        query_cluster="sales",
        query_text="销售线索",
        max_contents=1,
        max_comments_per_content=1,
        started_by="test-operator",
        runtime_lock_sha256="a" * 64,
    )
    imported = repository.import_signal(
        run_id,
        replace(
            signal(verifiable=True),
            collection_run_id="sql-invalid-time-collection",
            query_cluster="sales",
            query_text="销售线索",
            envelope_sha256="b" * 64,
            normalizer_version="test-normalizer-v1",
        ),
    )

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO signal_observations (
                observation_id, mvp_run_id, collection_run_id, signal_id,
                query_cluster, query_text, observed_at, raw_sha256,
                envelope_sha256
            ) VALUES (
                'sql-invalid-time-observation', ?, 'sql-invalid-time-collection', ?,
                'sales', '销售线索', 'not-a-timestamp', ?, ?
            )
            """,
            (run_id, imported.signal_id, "c" * 64, "d" * 64),
        )


def test_sql_rejects_future_verifiable_observation(connection, repository):
    run_id = repository.create_run(["bili", "dy"])
    repository.begin_collection(
        run_id=run_id,
        collection_run_id="sql-future-collection",
        platform="bili",
        query_cluster="sales",
        query_text="销售线索",
        max_contents=1,
        max_comments_per_content=1,
        started_by="test-operator",
        runtime_lock_sha256="a" * 64,
    )
    imported = repository.import_signal(
        run_id,
        replace(
            signal(verifiable=True),
            collection_run_id="sql-future-collection",
            query_cluster="sales",
            query_text="销售线索",
            envelope_sha256="b" * 64,
            normalizer_version="test-normalizer-v1",
        ),
    )

    with pytest.raises(sqlite3.IntegrityError, match="VERIFIABLE_PROVENANCE_REQUIRED"):
        connection.execute(
            """
            INSERT INTO signal_observations (
                observation_id, mvp_run_id, collection_run_id, signal_id,
                query_cluster, query_text, observed_at, raw_sha256,
                envelope_sha256
            ) VALUES (
                'sql-future-observation', ?, 'sql-future-collection', ?,
                'sales', '销售线索', '2099-01-01T00:00:00Z', ?, ?
            )
            """,
            (run_id, imported.signal_id, "c" * 64, "d" * 64),
        )


def test_sql_rejects_observation_query_that_differs_from_collection_campaign(
    connection, repository
):
    run_id = repository.create_run(["bili", "dy"])
    repository.begin_collection(
        run_id=run_id,
        collection_run_id="sql-campaign-bound-collection",
        platform="bili",
        query_cluster="campaign-cluster",
        query_text="campaign-query",
        max_contents=1,
        max_comments_per_content=1,
        started_by="test-operator",
        runtime_lock_sha256="a" * 64,
    )
    connection.execute(
        """
        INSERT INTO sources (
            source_id, platform, external_source_id, canonical_url
        ) VALUES (
            'sql-source', 'bili', 'sql-external-source',
            'https://www.bilibili.com/video/BV-sql'
        )
        """
    )
    connection.execute(
        """
        INSERT INTO signals (
            signal_id, source_id, platform, external_comment_id,
            normalized_comment_url, author_public_id, body, body_sha256,
            verifiable, normalizer_version
        ) VALUES (
            'sql-signal', 'sql-source', 'bili', 'sql-comment',
            'https://www.bilibili.com/video/BV-sql#reply',
            'sql-author', 'sql body', ?, 1, 'test-normalizer-v1'
        )
        """,
        (hashlib.sha256(b"sql body").hexdigest(),),
    )
    connection.execute(
        """
        INSERT INTO mvp_run_signals (mvp_run_id, signal_id, added_at)
        VALUES (?, 'sql-signal', '2026-08-12T00:00:00Z')
        """,
        (run_id,),
    )

    with pytest.raises(sqlite3.IntegrityError, match="VERIFIABLE_PROVENANCE_REQUIRED"):
        connection.execute(
            """
            INSERT INTO signal_observations (
                observation_id, mvp_run_id, collection_run_id, signal_id,
                query_cluster, query_text, observed_at, raw_sha256,
                envelope_sha256
            ) VALUES (
                'sql-observation', ?, 'sql-campaign-bound-collection',
                'sql-signal', 'fabricated-cluster', 'fabricated-query',
                '2026-08-12T00:00:00Z', ?, ?
            )
            """,
            (run_id, "c" * 64, "d" * 64),
        )


@pytest.mark.parametrize(
    ("signal_platform", "query_cluster", "query_text"),
    [
        ("bili", "fabricated-cluster", "fabricated-query"),
        ("dy", "campaign-cluster", "campaign-query"),
    ],
)
def test_linked_nonverifiable_observation_requires_relational_provenance(
    connection, repository, signal_platform, query_cluster, query_text
):
    run_id = repository.create_run(["bili", "dy"])
    imported = repository.import_signal(
        run_id,
        NormalizedSignal(
            platform=signal_platform,
            external_source_id=f"diagnostic-source-{signal_platform}",
            source_url=f"https://example.test/{signal_platform}/source",
            external_comment_id=f"diagnostic-comment-{signal_platform}",
            comment_url=f"https://example.test/{signal_platform}/comment",
            author_public_id=f"diagnostic-author-{signal_platform}",
            body="diagnostic observation",
            verifiable=False,
        ),
    )
    repository.begin_collection(
        run_id=run_id,
        collection_run_id="diagnostic-linked-collection",
        platform="bili",
        query_cluster="campaign-cluster",
        query_text="campaign-query",
        max_contents=1,
        max_comments_per_content=1,
        started_by="test-operator",
        runtime_lock_sha256="a" * 64,
    )
    observed_at = connection.execute(
        "SELECT started_at FROM collection_runs WHERE collection_run_id = ?",
        ("diagnostic-linked-collection",),
    ).fetchone()[0]

    with pytest.raises(
        sqlite3.IntegrityError, match="OBSERVATION_COLLECTION_PROVENANCE_INVALID"
    ):
        connection.execute(
            """
            INSERT INTO signal_observations (
                observation_id, mvp_run_id, collection_run_id, signal_id,
                query_cluster, query_text, observed_at, raw_sha256
            ) VALUES (
                'invalid-diagnostic-link', ?, 'diagnostic-linked-collection', ?,
                ?, ?, ?, ?
            )
            """,
            (
                run_id,
                imported.signal_id,
                query_cluster,
                query_text,
                observed_at,
                "c" * 64,
            ),
        )


@pytest.mark.parametrize(
    ("comment_url", "author_public_id", "body", "body_sha256"),
    [
        ("", "", "", "not-a-sha256"),
        ("\n", "\t", "\r", hashlib.sha256(b"\r").hexdigest()),
        (
            "https://www.bilibili.com/video/BV-invalid-core#reply",
            "invalid-core-author",
            "mismatched body",
            "a" * 64,
        ),
    ],
)
def test_sql_rejects_verifiable_signal_with_invalid_core_evidence(
    connection, repository, comment_url, author_public_id, body, body_sha256
):
    repository.create_run(["bili", "dy"])
    connection.execute(
        """
        INSERT INTO sources (
            source_id, platform, external_source_id, canonical_url
        ) VALUES (
            'invalid-core-source', 'bili', 'invalid-core-external',
            'https://www.bilibili.com/video/BV-invalid-core'
        )
        """
    )

    with pytest.raises(sqlite3.IntegrityError, match="VERIFIABLE_SIGNAL_INVALID"):
        connection.execute(
            """
            INSERT INTO signals (
                signal_id, source_id, platform, external_comment_id,
                normalized_comment_url, author_public_id, body, body_sha256,
                verifiable, normalizer_version
            ) VALUES (
                'invalid-core-signal', 'invalid-core-source', 'bili',
                'invalid-core-comment', ?, ?, ?, ?, 1,
                'test-normalizer-v1'
            )
            """,
            (comment_url, author_public_id, body, body_sha256),
        )


def test_collection_success_requires_complete_terminal_evidence(repository):
    run_id = repository.create_run(["bili", "dy"])
    repository.begin_collection(
        run_id=run_id,
        collection_run_id="incomplete-terminal",
        platform="bili",
        query_cluster="sales",
        query_text="销售线索",
        max_contents=1,
        max_comments_per_content=1,
        started_by="test-operator",
        runtime_lock_sha256="a" * 64,
    )

    with pytest.raises(sqlite3.IntegrityError, match="COLLECTION_TERMINAL_INVALID"):
        repository.connection.execute(
            """
            UPDATE collection_runs
            SET state = 'SUCCEEDED', raw_count = 1, unique_count = 1,
                output_manifest_sha256 = ?
            WHERE collection_run_id = 'incomplete-terminal'
            """,
            ("b" * 64,),
        )


def test_collection_state_must_be_known(repository):
    run_id = repository.create_run(["bili", "dy"])
    repository.begin_collection(
        run_id=run_id,
        collection_run_id="invalid-state",
        platform="bili",
        query_cluster="sales",
        query_text="销售线索",
        max_contents=1,
        max_comments_per_content=1,
        started_by="test-operator",
        runtime_lock_sha256="a" * 64,
    )

    with pytest.raises(sqlite3.IntegrityError, match="COLLECTION_STATE_INVALID"):
        repository.connection.execute(
            "UPDATE collection_runs SET state = 'UNKNOWN' "
            "WHERE collection_run_id = 'invalid-state'"
        )


def test_repository_rejects_unknown_collection_terminal_error_code(repository):
    run_id = repository.create_run(["bili", "dy"])
    repository.begin_collection(
        run_id=run_id,
        collection_run_id="repository-unknown-error",
        platform="bili",
        query_cluster="sales",
        query_text="销售线索",
        max_contents=1,
        max_comments_per_content=1,
        started_by="test-operator",
        runtime_lock_sha256="a" * 64,
    )

    with pytest.raises(ValueError, match="error code"):
        repository.finish_collection(
            "repository-unknown-error",
            state="FAILED",
            raw_count=0,
            unique_count=0,
            error_code="MADE_UP_FAILURE",
        )

    assert repository.connection.execute(
        "SELECT state FROM collection_runs WHERE collection_run_id = ?",
        ("repository-unknown-error",),
    ).fetchone()[0] == "RUNNING"


def test_sql_rejects_unknown_collection_terminal_error_code(repository):
    run_id = repository.create_run(["bili", "dy"])
    repository.begin_collection(
        run_id=run_id,
        collection_run_id="sql-unknown-error",
        platform="bili",
        query_cluster="sales",
        query_text="销售线索",
        max_contents=1,
        max_comments_per_content=1,
        started_by="test-operator",
        runtime_lock_sha256="a" * 64,
    )

    with pytest.raises(sqlite3.IntegrityError):
        repository.connection.execute(
            """
            UPDATE collection_runs
            SET state = 'FAILED', finished_at = '2099-01-01T00:01:00Z',
                error_code = 'MADE_UP_FAILURE'
            WHERE collection_run_id = 'sql-unknown-error'
            """
        )


@pytest.mark.parametrize(
    ("state", "error_code"),
    [
        ("BLOCKED_INPUT", "COLLECTION_PROCESS_FAILED"),
        ("FAILED", "PLATFORM_AUTH_REQUIRED"),
        ("CANCELLED", "COLLECTION_PARSE_FAILED"),
    ],
)
def test_repository_binds_terminal_error_code_to_state(
    repository, state, error_code
):
    run_id = repository.create_run(["bili", "dy"])
    repository.begin_collection(
        run_id=run_id,
        collection_run_id="repository-state-error-mismatch",
        platform="bili",
        query_cluster="sales",
        query_text="销售线索",
        max_contents=1,
        max_comments_per_content=1,
        started_by="test-operator",
        runtime_lock_sha256="a" * 64,
    )
    before = tuple(
        repository.connection.execute(
            "SELECT state, finished_at, raw_count, unique_count, error_code, "
            "output_manifest_sha256 FROM collection_runs "
            "WHERE collection_run_id = 'repository-state-error-mismatch'"
        ).fetchone()
    )

    with pytest.raises(ValueError, match="terminal error code"):
        repository.finish_collection(
            "repository-state-error-mismatch",
            state=state,
            raw_count=0,
            unique_count=0,
            error_code=error_code,
        )

    assert tuple(
        repository.connection.execute(
            "SELECT state, finished_at, raw_count, unique_count, error_code, "
            "output_manifest_sha256 FROM collection_runs "
            "WHERE collection_run_id = 'repository-state-error-mismatch'"
        ).fetchone()
    ) == before == ("RUNNING", None, 0, 0, None, None)


@pytest.mark.parametrize(
    ("state", "error_code"),
    [
        ("BLOCKED_INPUT", "COLLECTION_PROCESS_FAILED"),
        ("FAILED", "PLATFORM_AUTH_REQUIRED"),
        ("CANCELLED", "COLLECTION_PARSE_FAILED"),
    ],
)
def test_sql_binds_terminal_error_code_to_state(repository, state, error_code):
    run_id = repository.create_run(["bili", "dy"])
    repository.begin_collection(
        run_id=run_id,
        collection_run_id="sql-state-error-mismatch",
        platform="bili",
        query_cluster="sales",
        query_text="销售线索",
        max_contents=1,
        max_comments_per_content=1,
        started_by="test-operator",
        runtime_lock_sha256="a" * 64,
    )
    before = tuple(
        repository.connection.execute(
            "SELECT state, finished_at, raw_count, unique_count, error_code, "
            "output_manifest_sha256 FROM collection_runs "
            "WHERE collection_run_id = 'sql-state-error-mismatch'"
        ).fetchone()
    )

    with pytest.raises(
        sqlite3.IntegrityError, match="COLLECTION_TERMINAL_INVALID"
    ):
        repository.connection.execute(
            "UPDATE collection_runs SET state = ?, finished_at = started_at, "
            "error_code = ? WHERE collection_run_id = ?",
            (state, error_code, "sql-state-error-mismatch"),
        )

    assert tuple(
        repository.connection.execute(
            "SELECT state, finished_at, raw_count, unique_count, error_code, "
            "output_manifest_sha256 FROM collection_runs "
            "WHERE collection_run_id = 'sql-state-error-mismatch'"
        ).fetchone()
    ) == before == ("RUNNING", None, 0, 0, None, None)


def test_collection_terminal_evidence_cannot_be_rewritten(repository):
    run_id = repository.create_run(["bili", "dy"])
    repository.begin_collection(
        run_id=run_id,
        collection_run_id="immutable-terminal",
        platform="bili",
        query_cluster="sales",
        query_text="销售线索",
        max_contents=1,
        max_comments_per_content=1,
        started_by="test-operator",
        runtime_lock_sha256="a" * 64,
    )
    repository.finish_collection(
        "immutable-terminal",
        state="SUCCEEDED",
        raw_count=1,
        unique_count=1,
        error_code=None,
        output_manifest_sha256="b" * 64,
    )

    with pytest.raises(KeyError, match="unknown running collection"):
        repository.finish_collection(
            "immutable-terminal",
            state="FAILED",
            raw_count=0,
            unique_count=0,
            error_code="COLLECTION_PROCESS_FAILED",
        )

    row = repository.connection.execute(
        "SELECT state, raw_count, unique_count, output_manifest_sha256 "
        "FROM collection_runs WHERE collection_run_id = 'immutable-terminal'"
    ).fetchone()
    assert tuple(row) == ("SUCCEEDED", 1, 1, "b" * 64)


def test_repository_rejects_no_data_terminal_when_collection_has_observations(
    repository,
):
    run_id = repository.create_run(["bili", "dy"])
    repository.begin_collection(
        run_id=run_id,
        collection_run_id="repository-no-data-with-observation",
        backend="MEDIACRAWLER_AUTHORIZED",
        platform="bili",
        query_cluster="sales",
        query_text="销售线索",
        max_contents=1,
        max_comments_per_content=1,
        started_by="test-operator",
        runtime_lock_sha256="a" * 64,
    )
    repository.import_signal(
        run_id,
        replace(
            signal(verifiable=True),
            collection_run_id="repository-no-data-with-observation",
            query_cluster="sales",
            query_text="销售线索",
            envelope_sha256="b" * 64,
            normalizer_version="test-normalizer-v1",
        ),
    )
    before = tuple(
        repository.connection.execute(
            "SELECT state, finished_at, raw_count, unique_count, error_code, "
            "output_manifest_sha256 FROM collection_runs "
            "WHERE collection_run_id = 'repository-no-data-with-observation'"
        ).fetchone()
    )

    with pytest.raises(ValueError, match="SUCCEEDED_NO_DATA_HAS_OBSERVATIONS"):
        repository.finish_collection(
            "repository-no-data-with-observation",
            state="SUCCEEDED_NO_DATA",
            raw_count=0,
            unique_count=0,
            error_code=None,
            output_manifest_sha256="c" * 64,
        )

    assert tuple(
        repository.connection.execute(
            "SELECT state, finished_at, raw_count, unique_count, error_code, "
            "output_manifest_sha256 FROM collection_runs "
            "WHERE collection_run_id = 'repository-no-data-with-observation'"
        ).fetchone()
    ) == before == ("RUNNING", None, 0, 0, None, None)


def test_sql_rejects_no_data_terminal_when_collection_has_observations(repository):
    run_id = repository.create_run(["bili", "dy"])
    repository.begin_collection(
        run_id=run_id,
        collection_run_id="sql-no-data-with-observation",
        backend="MEDIACRAWLER_AUTHORIZED",
        platform="bili",
        query_cluster="sales",
        query_text="销售线索",
        max_contents=1,
        max_comments_per_content=1,
        started_by="test-operator",
        runtime_lock_sha256="a" * 64,
    )
    repository.import_signal(
        run_id,
        replace(
            signal(verifiable=True),
            collection_run_id="sql-no-data-with-observation",
            query_cluster="sales",
            query_text="销售线索",
            envelope_sha256="b" * 64,
            normalizer_version="test-normalizer-v1",
        ),
    )
    before = tuple(
        repository.connection.execute(
            "SELECT state, finished_at, raw_count, unique_count, error_code, "
            "output_manifest_sha256 FROM collection_runs "
            "WHERE collection_run_id = 'sql-no-data-with-observation'"
        ).fetchone()
    )

    with pytest.raises(
        sqlite3.IntegrityError, match="SUCCEEDED_NO_DATA_HAS_OBSERVATIONS"
    ):
        repository.connection.execute(
            "UPDATE collection_runs SET state = 'SUCCEEDED_NO_DATA', "
            "finished_at = started_at, raw_count = 0, unique_count = 0, "
            "error_code = NULL, output_manifest_sha256 = ? "
            "WHERE collection_run_id = 'sql-no-data-with-observation'",
            ("c" * 64,),
        )

    assert tuple(
        repository.connection.execute(
            "SELECT state, finished_at, raw_count, unique_count, error_code, "
            "output_manifest_sha256 FROM collection_runs "
            "WHERE collection_run_id = 'sql-no-data-with-observation'"
        ).fetchone()
    ) == before == ("RUNNING", None, 0, 0, None, None)


@pytest.mark.parametrize("terminal_run_state", ["CANCELLED", "FINALIZED"])
def test_sql_rejects_collection_insert_for_non_active_run_without_taking_slot(
    repository, terminal_run_state
):
    run_id = repository.create_run(["bili", "dy"])
    campaign_id = repository.begin_collection(
        run_id=run_id,
        collection_run_id=f"{terminal_run_state.lower()}-seed-collection",
        platform="bili",
        query_cluster="sales",
        query_text="销售线索",
        max_contents=1,
        max_comments_per_content=1,
        started_by="test-operator",
        runtime_lock_sha256="a" * 64,
    )
    repository.finish_collection(
        f"{terminal_run_state.lower()}-seed-collection",
        state="SUCCEEDED_NO_DATA",
        raw_count=0,
        unique_count=0,
        error_code=None,
        output_manifest_sha256="b" * 64,
    )
    if terminal_run_state == "CANCELLED":
        repository.cancel_run(run_id)
    else:
        repository.finalize_run(run_id, "REVISE_MVP", {"unique_signals": 0})

    with pytest.raises(sqlite3.IntegrityError, match="COLLECTION_REQUIRES_ACTIVE_RUN"):
        repository.connection.execute(
            "INSERT INTO collection_runs ("
            "collection_run_id, mvp_run_id, campaign_id, platform, attempt, "
            "backend, started_by, runtime_lock_sha256, state, started_at"
            ") VALUES (?, ?, ?, 'bili', 2, 'SIMULATION_ONLY', "
            "'test-operator', ?, 'RUNNING', '2026-08-25T00:00:00Z')",
            (
                f"{terminal_run_state.lower()}-illegal-collection",
                run_id,
                campaign_id,
                "a" * 64,
            ),
        )
    repository.connection.rollback()

    assert repository.connection.execute(
        "SELECT count(*) FROM collection_runs WHERE collection_run_id = ?",
        (f"{terminal_run_state.lower()}-illegal-collection",),
    ).fetchone()[0] == 0
    next_run_id = repository.create_run(["bili", "dy"])
    repository.begin_collection(
        run_id=next_run_id,
        collection_run_id=f"active-after-{terminal_run_state.lower()}",
        platform="dy",
        query_cluster="sales",
        query_text="新线索",
        max_contents=1,
        max_comments_per_content=1,
        started_by="test-operator",
        runtime_lock_sha256="a" * 64,
    )
    assert repository.connection.execute(
        "SELECT state FROM collection_runs WHERE collection_run_id = ?",
        (f"active-after-{terminal_run_state.lower()}",),
    ).fetchone()[0] == "RUNNING"


def test_collection_cannot_finish_after_day14_cutoff(connection):
    now = [datetime(2026, 8, 12, 8, tzinfo=UTC)]
    repository = Repository(connection, now=lambda: now[0])
    run_id = repository.create_run(["bili", "dy"])
    repository.begin_collection(
        run_id=run_id,
        collection_run_id="late-terminal",
        platform="bili",
        query_cluster="sales",
        query_text="销售线索",
        max_contents=1,
        max_comments_per_content=1,
        started_by="test-operator",
        runtime_lock_sha256="a" * 64,
    )
    now[0] = datetime(2026, 8, 27, 16, tzinfo=UTC)

    with pytest.raises(ValueError, match="Day 14"):
        repository.finish_collection(
            "late-terminal",
            state="SUCCEEDED_NO_DATA",
            raw_count=0,
            unique_count=0,
            error_code=None,
            output_manifest_sha256="b" * 64,
        )

    row = connection.execute(
        "SELECT state, finished_at FROM collection_runs "
        "WHERE collection_run_id = 'late-terminal'"
    ).fetchone()
    assert tuple(row) == ("RUNNING", None)


def test_finalized_run_rejects_fact_insert_update_and_delete(connection, repository):
    run_id = repository.create_run(["bili", "dy"])
    imported = repository.import_signal(run_id, signal())
    repository.finalize_run(run_id, "REVISE_MVP", {"unique_signals": 1})

    with pytest.raises(sqlite3.IntegrityError, match="FINALIZED_RUN_IMMUTABLE"):
        connection.execute(
            """
            INSERT INTO signal_observations
                (observation_id, mvp_run_id, signal_id, observed_at, raw_sha256)
            VALUES ('new-observation', ?, ?, '2026-08-12T00:00:00Z', ?)
            """,
            (run_id, imported.signal_id, "b" * 64),
        )
    with pytest.raises(sqlite3.IntegrityError, match="FINALIZED_RUN_IMMUTABLE"):
        connection.execute(
            "UPDATE signal_observations SET raw_sha256 = ? WHERE observation_id = ?",
            ("c" * 64, imported.observation_id),
        )
    with pytest.raises(sqlite3.IntegrityError, match="FINALIZED_RUN_IMMUTABLE"):
        connection.execute(
            "DELETE FROM signal_observations WHERE observation_id = ?",
            (imported.observation_id,),
        )
