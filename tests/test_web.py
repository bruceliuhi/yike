import csv
from datetime import UTC, datetime
import io

from fastapi.testclient import TestClient

from app.config import Settings
from app.db import connect, migrate
from app.exporter import SIGNAL_EXPORT_FIELDS
from app.model_contract import ScoreDecision
from app.repository import NormalizedSignal, Repository
from app.web import create_app
from app.workflow import Workflow
from tests.support import collect_verified_signal


def settings_for(tmp_path):
    return Settings(data_dir=tmp_path / "data", runtime_dir=tmp_path / "runtime")


def facts(settings):
    connection = connect(settings.data_dir / "discovery.sqlite3")
    migrate(connection)
    clock = lambda: datetime(2026, 8, 12, 8, tzinfo=UTC)
    repository = Repository(connection, now=clock)
    run_id = repository.create_run(["bili", "dy"])
    first = collect_verified_signal(
        repository,
        run_id,
        NormalizedSignal(
            platform="bili",
            external_source_id="av-web",
            source_title="销售获客讨论",
            source_url="https://www.bilibili.com/video/av-web",
            source_author_public_id="source-web",
            external_comment_id="web-comment",
            parent_body="我们需要改善获客",
            comment_url="https://www.bilibili.com/video/av-web#reply-web",
            author_public_id="lead-web",
            body="团队正在筛选销售线索，人工筛选效率低",
            query_cluster="sales-agent",
            query_text="销售线索筛选",
        ),
    )
    second = repository.import_signal(
        run_id,
        NormalizedSignal(
            platform="dy",
            external_source_id="dy-web",
            source_title="普通讨论",
            source_url="https://www.douyin.com/video/dy-web",
            source_author_public_id="source-dy",
            external_comment_id="dy-comment",
            comment_url="https://www.douyin.com/video/dy-web",
            author_public_id="lead-dy",
            body="普通评论",
            query_cluster="other",
            query_text="其他",
        ),
    ).signal_id
    decision = ScoreDecision.model_validate(
        {
            "grade": "A",
            "score": 10,
            "confidence": 0.88,
            "explicit_industry": "B2B 销售",
            "business_context": "团队筛选销售线索",
            "pain_summary": "人工筛选效率低",
            "intent_summary": "希望改善筛选",
            "evidence_snippets": ["团队正在筛选销售线索"],
            "dimension_scores": {
                "business_team_context": 2,
                "offer_fit": 2,
                "action_intent": 3,
                "buying_signal": 1,
                "contact_context": 1,
                "evidence_completeness": 1,
            },
            "exclusion_reasons": [],
            "recommended_question": "每周需要筛选多少条线索？",
        },
        context={"source_text": "销售获客讨论\n我们需要改善获客\n团队正在筛选销售线索，人工筛选效率低"},
    )
    repository.append_score_success(
        score_run_id="web-score",
        run_id=run_id,
        signal_id=first,
        provider="private-provider",
        model="private-model",
        prompt_version="private-prompt",
        schema_version="schema-v1",
        decision=decision,
        token_usage={"total_tokens": 10},
    )
    return connection, repository, Workflow(repository, now=clock), run_id, first, second


def completed_session(workflow, run_id, signal_id, kind):
    session_id = workflow.start_activity(run_id, signal_id, kind)
    workflow.record_activity(session_id, "COMPLETE")
    return session_id


def test_empty_database_renders_exact_five_operator_surfaces(tmp_path):
    settings = settings_for(tmp_path)
    with TestClient(create_app(settings)) as client:
        responses = [
            client.get("/runs"),
            client.get("/signals"),
            client.get("/signals/missing-signal"),
            client.get("/followups"),
            client.get("/metrics"),
        ]

    assert [response.status_code for response in responses] == [200, 200, 200, 200, 200]
    for response in responses:
        for label in ("运行", "线索", "证据详情", "跟进", "指标"):
            assert label in response.text
    assert "手工登记，不自动发送" in responses[3].text


def test_runs_post_creates_one_active_run_and_redirects(tmp_path):
    settings = settings_for(tmp_path)
    with TestClient(create_app(settings)) as client:
        first = client.post("/runs", follow_redirects=False)
        second = client.post("/runs", follow_redirects=False)

    connection = connect(settings.data_dir / "discovery.sqlite3")
    assert (first.status_code, second.status_code) == (303, 303)
    assert connection.execute("SELECT COUNT(*) FROM mvp_runs WHERE state = 'ACTIVE'").fetchone()[0] == 1
    assert connection.execute("SELECT platform_scope_json FROM mvp_runs").fetchone()[0] == '["bili","dy"]'
    connection.close()


def test_runs_page_creates_one_revision_from_eligible_finalized_base(tmp_path):
    settings = settings_for(tmp_path)
    with TestClient(create_app(settings)) as client:
        client.post("/runs", follow_redirects=False)
        connection = connect(settings.data_dir / "discovery.sqlite3")
        base_run_id = connection.execute(
            "SELECT mvp_run_id FROM mvp_runs WHERE state = 'ACTIVE'"
        ).fetchone()[0]
        connection.close()

        client.post(f"/runs/{base_run_id}/cancel", follow_redirects=False)
        eligible = client.get("/runs")
        created = client.post(
            "/runs",
            data={"revision_of_run_id": base_run_id},
            follow_redirects=False,
        )
        active = client.get("/runs")

    connection = connect(settings.data_dir / "discovery.sqlite3")
    base = connection.execute(
        "SELECT revision_of_run_id, state FROM mvp_runs WHERE mvp_run_id = ?",
        (base_run_id,),
    ).fetchone()
    revision = connection.execute(
        "SELECT revision_of_run_id, state FROM mvp_runs "
        "WHERE revision_of_run_id = ?",
        (base_run_id,),
    ).fetchone()
    connection.close()
    assert eligible.text.count("创建第二轮修订实验") == 1
    assert f'name="revision_of_run_id" value="{base_run_id}"' in eligible.text
    assert created.status_code == 303
    assert (base["revision_of_run_id"], base["state"]) == (None, "FINALIZED")
    assert (revision["revision_of_run_id"], revision["state"]) == (
        base_run_id,
        "ACTIVE",
    )
    assert "创建第二轮修订实验" not in active.text


def test_runs_post_returns_existing_active_without_creating_requested_revision(tmp_path):
    settings = settings_for(tmp_path)
    with TestClient(create_app(settings)) as client:
        client.post("/runs", follow_redirects=False)
        connection = connect(settings.data_dir / "discovery.sqlite3")
        active_run_id = connection.execute(
            "SELECT mvp_run_id FROM mvp_runs WHERE state = 'ACTIVE'"
        ).fetchone()[0]
        connection.close()
        repeated = client.post(
            "/runs",
            data={"revision_of_run_id": "must-not-be-created"},
            follow_redirects=False,
        )

    connection = connect(settings.data_dir / "discovery.sqlite3")
    assert repeated.status_code == 303
    assert f"run_id={active_run_id}" in repeated.headers["location"]
    assert "status=existing" in repeated.headers["location"]
    assert connection.execute("SELECT COUNT(*) FROM mvp_runs").fetchone()[0] == 1
    connection.close()


def test_runs_revision_post_rejects_unknown_or_nonfinalized_base(tmp_path):
    settings = settings_for(tmp_path)
    connection = connect(settings.data_dir / "discovery.sqlite3")
    migrate(connection)
    repository = Repository(connection)
    cancelled_run_id = repository.create_run(["bili", "dy"])
    repository.cancel_run(cancelled_run_id)
    connection.close()

    with TestClient(create_app(settings)) as client:
        unknown = client.post(
            "/runs",
            data={"revision_of_run_id": "missing-base"},
            follow_redirects=False,
        )
        nonfinalized = client.post(
            "/runs",
            data={"revision_of_run_id": cancelled_run_id},
            follow_redirects=False,
        )

    assert (unknown.status_code, nonfinalized.status_code) == (400, 400)


def test_runs_never_offers_or_creates_revision_chain_or_second_child(tmp_path):
    settings = settings_for(tmp_path)
    with TestClient(create_app(settings)) as client:
        client.post("/runs", follow_redirects=False)
        connection = connect(settings.data_dir / "discovery.sqlite3")
        base_run_id = connection.execute(
            "SELECT mvp_run_id FROM mvp_runs WHERE state = 'ACTIVE'"
        ).fetchone()[0]
        connection.close()
        client.post(f"/runs/{base_run_id}/cancel", follow_redirects=False)
        client.post(
            "/runs",
            data={"revision_of_run_id": base_run_id},
            follow_redirects=False,
        )
        connection = connect(settings.data_dir / "discovery.sqlite3")
        revision_run_id = connection.execute(
            "SELECT mvp_run_id FROM mvp_runs WHERE revision_of_run_id = ?",
            (base_run_id,),
        ).fetchone()[0]
        connection.close()
        client.post(f"/runs/{revision_run_id}/cancel", follow_redirects=False)

        page = client.get("/runs")
        second_child = client.post(
            "/runs",
            data={"revision_of_run_id": base_run_id},
            follow_redirects=False,
        )
        revision_chain = client.post(
            "/runs",
            data={"revision_of_run_id": revision_run_id},
            follow_redirects=False,
        )

    connection = connect(settings.data_dir / "discovery.sqlite3")
    assert "创建第二轮修订实验" not in page.text
    assert (second_child.status_code, revision_chain.status_code) == (400, 400)
    assert connection.execute("SELECT COUNT(*) FROM mvp_runs").fetchone()[0] == 2
    connection.close()


def test_signal_filters_use_persisted_score_review_query_and_outreach(tmp_path):
    settings = settings_for(tmp_path)
    connection, repository, workflow, run_id, first, _ = facts(settings)
    workflow.present_score(run_id, first, "web-score")
    review_id = workflow.complete_review(
        run_id=run_id,
        signal_id=first,
        label="HIGH_INTENT",
        reason="企业场景明确",
        note=None,
        activity_session_id=completed_session(workflow, run_id, first, "REVIEW"),
    )
    draft_id = workflow.create_draft(
        run_id=run_id, signal_id=first,
        body="人工筛选效率低，想了解每周线索量。",
        activity_session_id=completed_session(workflow, run_id, first, "DRAFT"),
    )
    workflow.register_outreach(
        run_id=run_id,
        signal_id=first,
        review_id=review_id,
        draft_run_id=draft_id,
        platform="bili",
        subject_key="bili:lead-web",
        approved_text="人工筛选效率低，想了解每周线索量。",
        context_evidence="人工筛选效率低",
        sent_at="2026-08-12T08:00:00Z",
        source_url="https://www.bilibili.com/video/av-web#reply-web",
        source_link_opened=True,
    )
    connection.close()

    with TestClient(create_app(settings)) as client:
        response = client.get(
            "/signals",
            params={
                "platform": "bili",
                "grade": "A",
                "review": "HIGH_INTENT",
                "industry": "B2B 销售",
                "query_cluster": "sales-agent",
                "outreach": "SENT_VERIFIED",
            },
        )
        mismatch = client.get("/signals", params={"platform": "dy", "grade": "A"})

    assert response.status_code == 200
    assert "人工筛选效率低" in response.text
    assert "普通评论" not in response.text
    assert "人工筛选效率低" not in mismatch.text


def test_detail_posts_review_draft_and_manual_outreach_then_redirects(tmp_path, monkeypatch):
    settings = settings_for(tmp_path)
    connection, _, _, run_id, signal_id, _ = facts(settings)
    clock = lambda: datetime(2026, 8, 12, 8, tzinfo=UTC)
    monkeypatch.setattr("app.workflow._system_now", clock)
    workflow = Workflow(Repository(connection, now=clock), now=clock)
    review_session = completed_session(workflow, run_id, signal_id, "REVIEW")
    draft_session = completed_session(workflow, run_id, signal_id, "DRAFT")
    connection.close()
    with TestClient(create_app(settings)) as client:
        detail = client.get(f"/signals/{signal_id}", params={"run_id": run_id})
        acknowledged = client.post(
            f"/signals/{signal_id}/score-presentations",
            data={"run_id": run_id, "score_run_id": "web-score"},
        )
        reviewed = client.post(
            f"/signals/{signal_id}/reviews",
            data={
                "run_id": run_id,
                "score_run_id": "web-score",
                "label": "HIGH_INTENT",
                "reason": "企业需求明确",
                "note": "人工确认",
                "activity_session_id": review_session,
            },
            follow_redirects=False,
        )
        drafted = client.post(
            f"/signals/{signal_id}/drafts",
            data={"run_id": run_id, "body": "人工筛选效率低，想了解每周线索筛选量。",
                  "activity_session_id": draft_session},
            follow_redirects=False,
        )

    connection = connect(settings.data_dir / "discovery.sqlite3")
    review_id = connection.execute("SELECT review_id FROM human_reviews").fetchone()[0]
    draft_id = connection.execute("SELECT draft_run_id FROM draft_runs").fetchone()[0]
    connection.close()
    with TestClient(create_app(settings)) as client:
        outreach = client.post(
            f"/signals/{signal_id}/outreach",
            data={
                "run_id": run_id,
                "review_id": review_id,
                "draft_run_id": draft_id,
                "platform": "bili",
                "subject_key": "bili:lead-web",
                "approved_text": "人工筛选效率低，想了解一下每周线索筛选量。",
                "context_evidence": "人工筛选效率低",
                "sent_at": "2026-08-12T08:00:00Z",
                "source_url": "https://www.bilibili.com/video/av-web#reply-web",
                "source_link_opened": "yes",
            },
            follow_redirects=False,
        )

    connection = connect(settings.data_dir / "discovery.sqlite3")
    assert "web-score" in detail.text
    assert acknowledged.status_code == 200
    assert (reviewed.status_code, drafted.status_code, outreach.status_code) == (303, 303, 303)
    assert connection.execute("SELECT COUNT(*) FROM human_reviews").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM draft_runs").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM outreach_actions").fetchone()[0] == 1
    connection.close()


def test_followup_posts_response_interview_and_quote_facts(tmp_path):
    settings = settings_for(tmp_path)
    connection, _, workflow, run_id, signal_id, _ = facts(settings)
    workflow.present_score(run_id, signal_id, "web-score")
    review_id = workflow.complete_review(
        run_id=run_id, signal_id=signal_id, label="HIGH_INTENT", reason="明确",
        note=None,
        activity_session_id=completed_session(workflow, run_id, signal_id, "REVIEW"),
    )
    draft_id = workflow.create_draft(
        run_id=run_id, signal_id=signal_id, body="人工筛选效率低，想进一步沟通。",
        activity_session_id=completed_session(workflow, run_id, signal_id, "DRAFT"),
    )
    outreach_id = workflow.register_outreach(
        run_id=run_id, signal_id=signal_id, review_id=review_id,
        draft_run_id=draft_id, platform="bili", subject_key="bili:lead-web",
        approved_text="人工筛选效率低，想进一步沟通。",
        context_evidence="人工筛选效率低", sent_at="2026-08-12T08:00:00Z",
        source_url="https://www.bilibili.com/video/av-web#reply-web", source_link_opened=True,
    )
    connection.close()
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/followups/responses",
            data={"run_id": run_id, "outreach_action_id": outreach_id,
                  "responder_subject_key": "bili:lead-web", "response_type": "VALID",
                  "summary": "愿意沟通", "occurred_at": "2026-08-12T10:00:00Z",
                  "verified_at": "2026-08-12T10:01:00Z",
                  "evidence_summary": "愿意进一步沟通"}, follow_redirects=False,
        )
    connection = connect(settings.data_dir / "discovery.sqlite3")
    response_id = connection.execute("SELECT response_event_id FROM response_events").fetchone()[0]
    connection.close()
    with TestClient(create_app(settings)) as client:
        interview = client.post(
            "/followups/interviews",
            data={"run_id": run_id, "response_event_id": response_id,
                  "scheduled_at": "2026-08-13T01:00:00Z",
                  "completed_at": "2026-08-13T01:30:00Z",
                  "customer_source_and_sales_process": "内容营销进入销售",
                  "weekly_lead_volume_and_loss_point": "每周二百条",
                  "most_manual_step": "人工判断",
                  "current_tools": "CRM",
                  "minimum_agent_scenario_and_decision_process": "先试排序",
                  "solution_fit": "SOLVABLE", "next_step": "报价"}, follow_redirects=False,
        )
    connection = connect(settings.data_dir / "discovery.sqlite3")
    interview_id = connection.execute("SELECT interview_id FROM interviews").fetchone()[0]
    connection.close()
    with TestClient(create_app(settings)) as client:
        quote = client.post(
            "/followups/quotes",
            data={"run_id": run_id, "response_event_id": response_id,
                  "interview_id": interview_id, "scope_summary": "筛选试点",
                  "agreed_to_receive_pricing_at": "2026-08-13T01:31:00Z",
                  "verified_at": "2026-08-13T01:32:00Z"}, follow_redirects=False,
        )
    assert (response.status_code, interview.status_code, quote.status_code) == (303, 303, 303)


def test_csv_export_has_visible_facts_and_no_model_or_secret_columns(tmp_path):
    settings = settings_for(tmp_path)
    connection, _, workflow, run_id, signal_id, _ = facts(settings)
    workflow.present_score(run_id, signal_id, "web-score")
    connection.close()
    with TestClient(create_app(settings)) as client:
        response = client.get("/export.csv", params={"run_id": run_id})

    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert response.status_code == 200
    assert tuple(rows[0]) == SIGNAL_EXPORT_FIELDS
    assert rows[0]["body"] == "团队正在筛选销售线索，人工筛选效率低"
    lowered = response.text.lower()
    for forbidden in ("cookie", "token_usage", "api_key", "private-provider", "private-model", "private-prompt"):
        assert forbidden not in lowered


def test_metrics_page_ignores_browser_supplied_counts_and_decision(tmp_path):
    settings = settings_for(tmp_path)
    connection, _, _, run_id, _, _ = facts(settings)
    connection.close()
    with TestClient(create_app(settings)) as client:
        response = client.get(
            "/metrics",
            params={"run_id": run_id, "unique_verifiable_signals": "999999",
                    "decision": "PROCEED_TO_V03_REVIEW"},
        )
    assert response.status_code == 200
    assert "999999" not in response.text
    assert "PROCEED_TO_V03_REVIEW" not in response.text
    assert "RUNNING" in response.text
