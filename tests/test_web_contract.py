from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.db import connect, migrate
from app.metrics import MetricsEngine
from app.repository import NormalizedSignal, Repository
from app.web import create_app
from tests.test_scoring import valid_decision
from tests.test_web import facts, settings_for


def valid_draft():
    return {
        "body": "你提到人工筛选效率低。我们正在研究 B2B 销售 Agent 的线索流程。你们每周需要筛选多少条线索？",
        "source_snippet": "人工筛选效率低",
        "research_purpose_sentence": "我们正在研究 B2B 销售 Agent 的线索流程。",
        "diagnostic_question": "你们每周需要筛选多少条线索？",
    }


class WebModelClient:
    provider = "openai-compatible"
    model = "web-contract-model"

    def complete(self, *, source_text):
        return valid_decision(), {"total_tokens": 10}

    def generate_draft(self, *, source_text):
        return valid_draft(), {"total_tokens": 11}


def test_web_hides_and_rejects_model_and_activity_actions_after_day14(tmp_path):
    settings = settings_for(tmp_path)
    connection = connect(settings.data_dir / "discovery.sqlite3")
    migrate(connection)
    past = datetime.now(UTC) - timedelta(days=16)
    repository = Repository(connection, now=lambda: past)
    run_id = repository.create_run(["bili", "dy"])
    signal_id = repository.import_signal(
        run_id,
        NormalizedSignal(
            platform="bili", external_source_id="expired-source",
            source_url="https://www.bilibili.com/video/expired-source",
            external_comment_id="expired-comment",
            comment_url="https://www.bilibili.com/video/expired-source#reply",
            author_public_id="expired-lead", body="人工筛选效率低",
        ),
    ).signal_id
    connection.close()

    with TestClient(create_app(settings)) as client:
        listing = client.get("/signals", params={"run_id": run_id})
        scoring = client.post(
            f"/signals/{signal_id}/scores", data={"run_id": run_id}
        )
        drafting = client.post(
            f"/signals/{signal_id}/drafts/generate", data={"run_id": run_id}
        )
        activity = client.post(
            "/activity/start",
            data={
                "run_id": run_id, "signal_id": signal_id,
                "activity_kind": "REVIEW",
            },
        )

    connection = connect(settings.data_dir / "discovery.sqlite3")
    assert 'action="/signals/score-batch"' not in listing.text
    assert (scoring.status_code, drafting.status_code, activity.status_code) == (
        409, 409, 400,
    )
    assert connection.execute("SELECT count(*) FROM score_runs").fetchone()[0] == 0
    assert connection.execute("SELECT count(*) FROM draft_runs").fetchone()[0] == 0
    assert connection.execute("SELECT count(*) FROM activity_sessions").fetchone()[0] == 0
    connection.close()


def test_web_uses_configured_model_for_single_score_bounded_batch_and_generated_draft(
    tmp_path, monkeypatch
):
    settings = settings_for(tmp_path)
    connection, _, _, run_id, signal_id, second_id = facts(settings)
    connection.close()
    monkeypatch.setattr(
        "app.web.model_client_from_env", lambda: WebModelClient()
    )

    with TestClient(create_app(settings)) as client:
        scored = client.post(
            f"/signals/{signal_id}/scores",
            data={"run_id": run_id},
            follow_redirects=False,
        )
        batch = client.post(
            "/signals/score-batch",
            data={"run_id": run_id, "signal_ids": f"{signal_id},{second_id}"},
            follow_redirects=False,
        )
        generated = client.post(
            f"/signals/{signal_id}/drafts/generate",
            data={"run_id": run_id},
            follow_redirects=False,
        )
        oversized = client.post(
            "/signals/score-batch",
            data={"run_id": run_id, "signal_ids": ",".join([signal_id] * 11)},
        )

    connection = connect(settings.data_dir / "discovery.sqlite3")
    assert (scored.status_code, batch.status_code, generated.status_code) == (303, 303, 303)
    assert oversized.status_code == 400
    assert connection.execute(
        "SELECT COUNT(*) FROM score_runs WHERE model = 'web-contract-model'"
    ).fetchone()[0] == 3
    draft = connection.execute(
        "SELECT draft_kind, status, model FROM draft_runs"
    ).fetchone()
    assert tuple(draft) == ("GENERATED", "SUCCEEDED", "web-contract-model")
    connection.close()


def test_web_activity_and_operator_forms_never_accept_client_elapsed_time(tmp_path):
    settings = settings_for(tmp_path)
    connection, _, _, run_id, signal_id, _ = facts(settings)
    connection.close()

    with TestClient(create_app(settings)) as client:
        detail = client.get(f"/signals/{signal_id}", params={"run_id": run_id})
        started = client.post(
            "/activity/start",
            data={
                "run_id": run_id,
                "signal_id": signal_id,
                "activity_kind": "REVIEW",
                "active_seconds": "999999",
                "received_at": "1900-01-01T00:00:00Z",
            },
        )
        session_id = started.json()["activity_session_id"]
        resumed = client.post(
            "/activity/start",
            data={
                "run_id": run_id,
                "signal_id": signal_id,
                "activity_kind": "REVIEW",
            },
        )
        completed = client.post(
            f"/activity/{session_id}/events",
            data={
                "event_kind": "COMPLETE",
                "active_seconds": "999999",
                "received_at": "1900-01-01T00:00:00Z",
            },
        )
        reviewed = client.post(
            f"/signals/{signal_id}/reviews",
            data={
                "run_id": run_id,
                "score_run_id": "web-score",
                "label": "HIGH_INTENT",
                "reason": "企业需求明确",
                "activity_session_id": session_id,
                "active_seconds": "999999",
            },
            follow_redirects=False,
        )

    connection = connect(settings.data_dir / "discovery.sqlite3")
    review = connection.execute(
        "SELECT active_seconds, started_at FROM human_reviews"
    ).fetchone()
    assert 'name="active_seconds"' not in detail.text
    assert 'name="started_at"' not in detail.text
    assert 'name="completed_at"' not in detail.text
    assert resumed.json() == {"activity_session_id": session_id, "state": "OPEN"}
    assert (started.status_code, completed.status_code, reviewed.status_code) == (200, 200, 303)
    assert review["active_seconds"] != 999999
    assert review["started_at"] != "1900-01-01T00:00:00Z"
    connection.close()


def test_web_finalization_recomputes_server_snapshot_and_cannot_take_decision(tmp_path):
    settings = settings_for(tmp_path)
    connection, _, _, run_id, _, _ = facts(settings)
    connection.close()

    with TestClient(create_app(settings)) as client:
        early = client.post(
            f"/runs/{run_id}/finalize",
            data={"decision": "PROCEED_TO_V03_REVIEW", "facts": '{"fake":true}'},
        )
    connection = connect(settings.data_dir / "discovery.sqlite3")
    assert early.status_code == 409
    assert connection.execute(
        "SELECT state FROM mvp_runs WHERE mvp_run_id = ?", (run_id,)
    ).fetchone()[0] == "ACTIVE"
    connection.close()

    with TestClient(create_app(settings)) as client:
        cancelled = client.post(f"/runs/{run_id}/cancel", follow_redirects=False)
        finalized = cancelled
        repeated = client.post(f"/runs/{run_id}/finalize", data={})

    connection = connect(settings.data_dir / "discovery.sqlite3")
    row = connection.execute(
        "SELECT state, conclusion, conclusion_facts_sha256, final_report_sha256 "
        "FROM mvp_runs WHERE mvp_run_id = ?",
        (run_id,),
    ).fetchone()
    assert (cancelled.status_code, finalized.status_code) == (303, 303)
    assert repeated.status_code == 409
    assert tuple(row[:2]) == ("FINALIZED", "REVISE_MVP")
    assert len(row["conclusion_facts_sha256"]) == 64
    assert len(row["final_report_sha256"]) == 64
    connection.close()


def test_confirmed_incident_uses_server_time_and_forces_stop(tmp_path):
    settings = settings_for(tmp_path)
    connection, _, _, run_id, _, _ = facts(settings)
    connection.close()

    with TestClient(create_app(settings)) as client:
        unconfirmed = client.post(
            f"/runs/{run_id}/incidents",
            data={
                "event_type": "MIS_SEND", "platform": "bili",
                "summary": "误发已核验", "verified_at": "1900-01-01T00:00:00Z",
            },
        )
        confirmed = client.post(
            f"/runs/{run_id}/incidents",
            data={
                "event_type": "MIS_SEND", "platform": "bili",
                "summary": "误发已核验", "confirmed": "yes",
                "verified_at": "1900-01-01T00:00:00Z",
            },
            follow_redirects=False,
        )

    connection = connect(settings.data_dir / "discovery.sqlite3")
    row = connection.execute(
        "SELECT event_type, severity, verified_at, forces_stop FROM risk_events"
    ).fetchone()
    snapshot = MetricsEngine(connection).calculate(run_id)
    assert (unconfirmed.status_code, confirmed.status_code) == (400, 303)
    assert tuple(row[:2]) == ("MIS_SEND", "CONFIRMED")
    assert row["verified_at"].endswith("Z")
    assert row["verified_at"] != "1900-01-01T00:00:00Z"
    assert row["forces_stop"] == 1
    assert snapshot.decision == "STOP_DISCOVERY"
    connection.close()
