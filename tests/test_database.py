import sqlite3
from dataclasses import replace

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
    "human_reviews",
    "draft_runs",
    "outreach_actions",
    "response_events",
    "interviews",
    "quote_opportunities",
    "daily_snapshots",
    "risk_events",
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
    )


def insert_run(
    connection,
    run_id: str,
    *,
    state: str = "FINALIZED",
    revision_of_run_id: str | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO mvp_runs (
            mvp_run_id, revision_of_run_id, state, authorization_basis,
            platform_scope_json, started_at, day14_due_at
        ) VALUES (?, ?, ?, 'USER_ATTESTED_PLATFORM_AUTHORIZATION',
                  '["bili","dy"]', '2026-08-12T00:00:00Z',
                  '2026-08-26T00:00:00Z')
        """,
        (run_id, revision_of_run_id, state),
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
            attempt, backend, state
        ) VALUES ('collection-1', ?, 'campaign-1', 'bili', 1,
                  'MEDIACRAWLER_AUTHORIZED', 'QUEUED')
        """,
        (run_id,),
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
    connection.execute(
        """
        INSERT INTO human_reviews (
            review_id, mvp_run_id, signal_id, presented_score_run_id, label,
            reason, completed_at
        ) VALUES ('review-1', ?, ?, 'score-1', 'HIGH_INTENT',
                  '有明确采购信号', '2026-08-12T00:00:00Z')
        """,
        (run_id, signal_id),
    )
    connection.execute(
        """
        INSERT INTO draft_runs (
            draft_run_id, mvp_run_id, signal_id, body, status, created_at
        ) VALUES ('draft-1', ?, ?, '请问您目前如何筛选线索？', 'SUCCEEDED',
                  '2026-08-12T00:00:00Z')
        """,
        (run_id, signal_id),
    )
    connection.execute(
        """
        INSERT INTO outreach_actions (
            outreach_action_id, mvp_run_id, signal_id, review_id, score_run_id,
            draft_run_id, platform, subject_key, approved_text, sent_at,
            source_url, source_link_opened, status, created_at
        ) VALUES ('outreach-1', ?, ?, 'review-1', 'score-1', 'draft-1',
                  'bili', 'subject-1', '人工批准文本',
                  '2026-08-12T00:00:00Z',
                  'https://www.bilibili.com/video/BV1', 1,
                  'SENT_VERIFIED', '2026-08-12T00:00:00Z')
        """,
        (run_id, signal_id),
    )
    connection.execute(
        """
        INSERT INTO response_events (
            response_event_id, mvp_run_id, outreach_action_id,
            responder_subject_key, response_type
        ) VALUES ('response-1', ?, 'outreach-1', 'subject-1', 'VALID')
        """,
        (run_id,),
    )
    connection.execute(
        """
        INSERT INTO interviews (interview_id, mvp_run_id, response_event_id)
        VALUES ('interview-1', ?, 'response-1')
        """,
        (run_id,),
    )
    connection.execute(
        """
        INSERT INTO quote_opportunities (
            quote_opportunity_id, mvp_run_id, response_event_id, scope_summary
        ) VALUES ('quote-1', ?, 'response-1', '销售线索筛选')
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
        "DISCOVERY_FACT_STORE_V5",
        "9b4f4bfbebd4de4938d230514a2a3e5455241f377e937b02e2313a9b537c3eb5",
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
                started_at, day14_due_at
            ) VALUES ('bad-scope', 'DRAFT', 'USER_ATTESTED_PLATFORM_AUTHORIZATION',
                      '["dy","bili"]', '2026-08-12T00:00:00Z',
                      '2026-08-26T00:00:00Z')
            """
        )


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
    connection.execute(
        """
        INSERT INTO human_reviews (
            review_id, mvp_run_id, signal_id, presented_score_run_id, label
        ) VALUES ('first-review', ?, ?, 'first-score', 'HIGH_INTENT')
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

    connection.execute(
        """
        INSERT INTO human_reviews (
            review_id, mvp_run_id, signal_id, presented_score_run_id,
            label, reason, completed_at, supersedes_review_id
        ) VALUES ('review-2', ?, ?, 'score-1', 'POSSIBLE',
                  '有效修订', '2026-08-12T01:00:00Z', 'review-1')
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
        "subject_key": "subject-1",
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
            ) VALUES ('cross-run-follow-up', ?, ?, 'bili', 'subject-1',
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
            source_url, source_link_opened, status, parent_outreach_action_id,
            created_at
        ) VALUES ('follow-up-1', ?, ?, 'review-1', 'score-1', 'draft-1',
                  'bili', 'subject-1', '人工跟进', '2026-08-13T00:00:00Z',
                  'https://www.bilibili.com/video/BV1', 1, 'SENT_VERIFIED',
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
                approved_text, sent_at, source_url, source_link_opened, status,
                parent_outreach_action_id, created_at
            ) VALUES ('follow-up-2', ?, ?, 'review-1', 'score-1', 'draft-1',
                      'bili', 'subject-1', '再次人工跟进',
                      '2026-08-14T00:00:00Z',
                      'https://www.bilibili.com/video/BV1', 1,
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
        "approved_text": "人工批准文本",
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
                approved_text, sent_at, source_url, source_link_opened,
                status, created_at
            ) VALUES ('invalid-manual-outreach', ?, ?, 'review-1', 'score-1',
                      'draft-1', 'bili', 'subject-2', ?, ?, ?, ?,
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

    connection.execute(
        f"UPDATE {table} SET state = 'RUNNING' WHERE {key_column} = ?", (key_value,)
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
                attempt, backend, state
            ) VALUES ('wrong-platform-collection', ?, 'campaign-1', 'dy', 2,
                      'MEDIACRAWLER_AUTHORIZED', 'QUEUED')
            """,
            (facts["run_id"],),
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
    connection.execute(
        """
        INSERT INTO human_reviews (
            review_id, mvp_run_id, signal_id, presented_score_run_id, label,
            supersedes_review_id
        ) VALUES ('incomplete-review', ?, ?, 'score-1', 'POSSIBLE', 'review-1')
        """,
        (facts["run_id"], facts["signal_id"]),
    )
    connection.execute(
        """
        INSERT INTO draft_runs (
            draft_run_id, mvp_run_id, signal_id, body, status, created_at
        ) VALUES ('failed-draft', ?, ?, 'draft', 'FAILED',
                  '2026-08-12T00:00:00Z')
        """,
        (facts["run_id"], facts["signal_id"]),
    )
    with pytest.raises(sqlite3.IntegrityError, match="OUTREACH_BINDING_NOT_READY"):
        connection.execute(
            """
            INSERT INTO outreach_actions (
                outreach_action_id, mvp_run_id, signal_id, review_id,
                score_run_id, draft_run_id, platform, subject_key,
                approved_text, sent_at, source_url, source_link_opened,
                status, created_at
            ) VALUES ('incomplete-outreach', ?, ?, 'incomplete-review',
                      'pending-score', 'failed-draft', 'bili', 'subject-2',
                      '人工批准文本', '2026-08-12T00:00:00Z',
                      'https://www.bilibili.com/video/BV1', 1,
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
                attempt, backend, state
            ) VALUES ('active-collection', ?, 'active-campaign', 'bili', 1,
                      'MEDIACRAWLER_AUTHORIZED', 'QUEUED')
            """,
            (active_run,),
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
        ) VALUES ('risk-1', ?, 'RATE_LIMIT', 'LOW', '平台提示降低频率',
                  '2026-08-12T00:00:00Z', 0)
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
            ) VALUES ('risk-2', ?, 'RATE_LIMIT', 'LOW', 'late',
                      '2026-08-12T00:00:00Z', 0)
            """,
            (run_id,),
        )


def test_finalized_run_rejects_new_fact(repository):
    run_id = repository.create_run(["bili", "dy"])
    repository.finalize_run(run_id, "REVISE_MVP", {"unique_signals": 0})

    with pytest.raises(FinalizedRunError):
        repository.import_signal(run_id, signal())


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
