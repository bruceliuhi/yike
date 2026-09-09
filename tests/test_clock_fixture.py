from datetime import UTC, datetime, timedelta
import sqlite3

import pytest

from app.db import connect, migrate
from app.metrics import MetricsEngine
from app.repository import NormalizedSignal, Repository
from app.web import _run_is_editable
from app.workflow import Workflow


pytestmark = pytest.mark.usefixtures("discovery_clock")


def test_discovery_fixture_aligns_sqlite_repository_and_workflow_clocks(
    tmp_path, discovery_clock
):
    connection = connect(tmp_path / "clock.sqlite3")
    migrate(connection)
    expected = discovery_clock().isoformat().replace("+00:00", "Z")
    repository = Repository(connection)
    run_id = repository.create_run(["bili", "dy"])

    assert connection.execute(
        "SELECT strftime('%Y-%m-%dT%H:%M:%SZ', 'now')"
    ).fetchone()[0] == expected
    assert connection.execute(
        "SELECT started_at FROM mvp_runs WHERE mvp_run_id = ?", (run_id,)
    ).fetchone()[0] == expected
    assert Workflow(repository)._timestamp() == expected
    connection.close()


def test_discovery_fixture_advances_existing_connections_and_default_clocks(
    tmp_path, discovery_clock
):
    connection = connect(tmp_path / "advancing-clock.sqlite3")
    migrate(connection)
    repository = Repository(connection)
    run_id = repository.create_run(["bili", "dy"])
    workflow = Workflow(repository)
    row = connection.execute(
        "SELECT state, day14_due_at FROM mvp_runs WHERE mvp_run_id = ?", (run_id,)
    ).fetchone()
    assert not MetricsEngine(connection).calculate(run_id).terminal_eligible

    discovery_clock.value = datetime.fromisoformat(row["day14_due_at"]) + timedelta(
        seconds=1
    )
    expected = discovery_clock.value.isoformat().replace("+00:00", "Z")
    assert connection.execute(
        "SELECT strftime('%Y-%m-%dT%H:%M:%SZ', 'now')"
    ).fetchone()[0] == expected
    assert repository._server_timestamp() == expected
    assert workflow._timestamp() == expected
    assert not _run_is_editable(row)
    assert MetricsEngine(connection).calculate(run_id).terminal_eligible
    connection.close()


def test_discovery_fixture_keeps_web_day14_boundary_inclusive(discovery_clock):
    cutoff = discovery_clock()
    row = {"state": "ACTIVE", "day14_due_at": cutoff.isoformat()}
    assert _run_is_editable(row)
    row["day14_due_at"] = (cutoff - timedelta(seconds=1)).isoformat()
    assert not _run_is_editable(row)


def test_sql_clock_keeps_day14_cutoff_and_rejects_backdated_writes_after(
    tmp_path, discovery_clock
):
    connection = connect(tmp_path / "sql-cutoff.sqlite3")
    migrate(connection)
    repository = Repository(connection)
    run_id = repository.create_run(["bili", "dy"])
    signal_id = repository.import_signal(
        run_id,
        NormalizedSignal(
            platform="bili", external_source_id="cutoff-source",
            source_url="https://www.bilibili.com/video/cutoff-source",
            external_comment_id="cutoff-comment",
            comment_url="https://www.bilibili.com/video/cutoff-source#reply",
            author_public_id="cutoff-author", body="人工筛选效率低",
        ),
    ).signal_id
    due_at = connection.execute(
        "SELECT day14_due_at FROM mvp_runs WHERE mvp_run_id = ?", (run_id,)
    ).fetchone()[0]
    insert = """
        INSERT INTO score_runs (
            score_run_id, mvp_run_id, signal_id, prompt_version, schema_version,
            status, error_code, created_at
        ) VALUES (?, ?, ?, 'prompt-v2', 'schema-v2', 'FAILED', 'MODEL_UNAVAILABLE', ?)
    """
    discovery_clock.value = datetime.fromisoformat(due_at)
    connection.execute(insert, ("at-cutoff", run_id, signal_id, due_at))
    connection.commit()
    discovery_clock.value += timedelta(seconds=1)
    with pytest.raises(sqlite3.IntegrityError, match="D04_FACT_OUTSIDE_RUN_WINDOW"):
        connection.execute(insert, ("backdated", run_id, signal_id, due_at))
    assert connection.execute("SELECT count(*) FROM score_runs").fetchone()[0] == 1
    connection.close()


@pytest.mark.parametrize(
    "arguments",
    [
        ("%Y-%m-%dT%H:%M:%SZ", "2026-08-12T00:00:00Z"),
        ("%s", "2026-08-12T00:00:00Z"),
        ("%Y-%m-%d", "2024-02-29", "+1 day"),
        ("%H:%M", "2026-08-12T00:00:00Z", "+8 hours"),
        ("%Y-%m-%d", 0, "unixepoch"),
        ("%Y-%m-%d", "not-a-date"),
        ("%Y-%m-%d", None),
        ("%Q", "2026-08-12"),
    ],
)
def test_discovery_fixture_preserves_native_non_now_strftime(tmp_path, arguments):
    native = sqlite3.connect(":memory:")
    connection = connect(tmp_path / "native-dates.sqlite3")
    query = f"SELECT strftime({','.join('?' for _ in arguments)})"
    assert connection.execute(query, arguments).fetchone()[0] == native.execute(
        query, arguments
    ).fetchone()[0]
    connection.close()
    native.close()


@pytest.mark.parametrize(
    "arguments",
    [("%s", "now"), ("%H:%M", "NOW", "+8 hours"), ("%Y-%m-%d",)],
)
def test_discovery_fixture_uses_native_modifiers_for_now(
    tmp_path, discovery_clock, arguments
):
    native = sqlite3.connect(":memory:")
    connection = connect(tmp_path / "now-modifiers.sqlite3")
    query = f"SELECT strftime({','.join('?' for _ in arguments)})"
    expected_arguments = (arguments[0], discovery_clock().isoformat(), *arguments[2:])
    expected_query = f"SELECT strftime({','.join('?' for _ in expected_arguments)})"
    assert connection.execute(query, arguments).fetchone()[0] == native.execute(
        expected_query, expected_arguments
    ).fetchone()[0]
    connection.close()
    native.close()


@pytest.mark.native_clock
def test_native_clock_opt_out_leaves_sqlite_and_application_clocks_real(
    tmp_path, discovery_clock
):
    assert discovery_clock is None
    before = datetime.now(UTC).replace(microsecond=0)
    connection = connect(tmp_path / "real-clock.sqlite3")
    migrate(connection)
    recorded = connection.execute(
        "SELECT strftime('%Y-%m-%dT%H:%M:%SZ', 'now')"
    ).fetchone()[0]
    after = datetime.now(UTC)
    assert before <= datetime.fromisoformat(recorded) <= after
    assert connection.execute(
        "SELECT count(*) FROM pragma_function_list WHERE name = 'strftime' AND builtin = 0"
    ).fetchone()[0] == 0
    repository = Repository(connection)
    assert before <= repository._now() <= datetime.now(UTC)
    workflow_now = datetime.fromisoformat(Workflow(repository)._timestamp())
    assert before <= workflow_now <= datetime.now(UTC)
    connection.close()
