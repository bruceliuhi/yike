import sqlite3

import pytest

from app.db import connect, migrate
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
    "human_reviews",
    "draft_runs",
    "outreach_actions",
    "response_events",
    "interviews",
    "quote_opportunities",
    "daily_snapshots",
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


def test_only_one_active_run_is_allowed(repository):
    repository.create_run(["bili", "dy"])
    with pytest.raises(ActiveRunError):
        repository.create_run(["bili", "dy"])


@pytest.mark.parametrize("platforms", [[], ["bili"], ["dy"], ["dy", "bili"], ["bili", "bili"], ["bili", "other"]])
def test_run_requires_exact_bili_and_dy_platform_scope(repository, platforms):
    with pytest.raises(ValueError, match="exactly"):
        repository.create_run(platforms)


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
        INSERT INTO score_runs (score_run_id, mvp_run_id, signal_id, status)
        VALUES ('score-1', ?, ?, 'SUCCEEDED')
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
