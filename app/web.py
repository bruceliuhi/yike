from datetime import UTC, datetime
import json
import os
from pathlib import Path
from typing import Mapping
from urllib.parse import parse_qs, urlencode
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.collector import CollectionRequest, Collector
from app.config import Settings
from app.drafter import DraftGenerator
from app.exporter import export_signals_csv
from app.metrics import MetricsEngine, MetricsSnapshot
from app.model_client import model_client_from_env
from app.repository import ActiveRunError, Repository
from app.scorer import Scorer
from app.workflow import Workflow


_FORM_LIMIT = 64 * 1024


def create_app(settings: Settings) -> FastAPI:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.runtime_dir.mkdir(parents=True, exist_ok=True)

    root = Path(__file__).resolve().parent.parent
    templates = Jinja2Templates(directory=str(root / "templates"))
    app = FastAPI(title="意客 AI DISCOVERY MVP")
    app.mount("/static", StaticFiles(directory=root / "static"), name="static")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/runs", response_class=HTMLResponse)
    def runs(request: Request) -> HTMLResponse:
        repository = Repository.from_settings(settings)
        try:
            run_rows = repository.connection.execute(
                "SELECT * FROM mvp_runs ORDER BY started_at DESC"
            ).fetchall()
            collections = repository.connection.execute(
                "SELECT * FROM collection_runs ORDER BY started_at DESC"
            ).fetchall()
            active_run = next((row for row in run_rows if _run_is_editable(row)), None)
        finally:
            repository.connection.close()
        return templates.TemplateResponse(
            request,
            "runs.html",
            {
                "settings": settings,
                "runs": run_rows,
                "collections": collections,
                "active_run": active_run,
            },
        )

    @app.post("/runs")
    def create_run() -> RedirectResponse:
        repository = Repository.from_settings(settings)
        try:
            active = repository.connection.execute(
                "SELECT mvp_run_id FROM mvp_runs WHERE state = 'ACTIVE'"
            ).fetchone()
            if active is None:
                try:
                    run_id = repository.create_run(["bili", "dy"])
                    status = "created"
                except ActiveRunError:
                    active = repository.connection.execute(
                        "SELECT mvp_run_id FROM mvp_runs WHERE state = 'ACTIVE'"
                    ).fetchone()
                    if active is None:
                        raise
                    run_id = str(active[0])
                    status = "existing"
            else:
                run_id = str(active[0])
                status = "existing"
        finally:
            repository.connection.close()
        return _redirect("/runs", run_id=run_id, status=status)

    @app.post("/runs/collect")
    async def collect(request: Request) -> RedirectResponse:
        form = await _form(request)
        run_id = _required(form, "run_id")
        platform = _required(form, "platform")
        query_cluster = _required(form, "query_cluster")
        query_text = _required(form, "query_text")
        try:
            max_contents = int(_required(form, "max_contents"))
            max_comments = int(_required(form, "max_comments_per_content"))
        except ValueError as error:
            raise HTTPException(400, "collection limits must be integers") from error
        repository = Repository.from_settings(settings)
        collection_run_id = str(uuid4())
        runtime_path = Path(
            os.getenv("YIKE_MEDIACRAWLER_PATH", settings.runtime_dir / "mediacrawler")
        )
        try:
            result = Collector(
                repository=repository,
                runtime_path=runtime_path,
                work_root=settings.runtime_dir / "runs",
            ).collect(
                CollectionRequest(
                    mvp_run_id=run_id,
                    collection_run_id=collection_run_id,
                    platform=platform,
                    query_cluster=query_cluster,
                    query_text=query_text,
                    max_contents=max_contents,
                    max_comments_per_content=max_comments,
                    started_by="local-web-operator",
                )
            )
        except (KeyError, ValueError) as error:
            raise HTTPException(400, str(error)) from error
        finally:
            repository.connection.close()
        return _redirect(
            "/runs",
            run_id=run_id,
            status=result.status,
            error_code=result.error_code or "",
        )

    @app.get("/signals", response_class=HTMLResponse)
    def signals(
        request: Request,
        run_id: str | None = None,
        platform: str | None = None,
        grade: str | None = None,
        review: str | None = None,
        industry: str | None = None,
        query_cluster: str | None = None,
        outreach: str | None = None,
    ) -> HTMLResponse:
        repository = Repository.from_settings(settings)
        try:
            selected_run = run_id or _latest_run_id(repository)
            state = repository.connection.execute(
                "SELECT state, day14_due_at FROM mvp_runs WHERE mvp_run_id = ?", (selected_run,)
            ).fetchone() if selected_run else None
            editable = _run_is_editable(state)
            rows = _filtered_signals(
                repository,
                run_id=selected_run,
                platform=platform,
                grade=grade,
                review=review,
                industry=industry,
                query_cluster=query_cluster,
                outreach=outreach,
            )
            industries = [
                row[0]
                for row in repository.connection.execute(
                    """
                    SELECT DISTINCT json_extract(reason_json, '$.explicit_industry')
                    FROM score_runs score
                    JOIN score_presentations presentation
                      ON presentation.score_run_id = score.score_run_id
                     AND presentation.mvp_run_id = score.mvp_run_id
                     AND presentation.signal_id = score.signal_id
                    WHERE score.mvp_run_id = ? AND score.status = 'SUCCEEDED'
                      AND json_extract(score.reason_json, '$.explicit_industry') IS NOT NULL
                    ORDER BY 1
                    """,
                    (selected_run,),
                ).fetchall()
            ] if selected_run else []
        finally:
            repository.connection.close()
        return templates.TemplateResponse(
            request,
            "signals.html",
            {
                "signals": rows,
                "run_id": selected_run,
                "industries": industries,
                "editable": editable,
                "filters": {
                    "platform": platform or "",
                    "grade": grade or "",
                    "review": review or "",
                    "industry": industry or "",
                    "query_cluster": query_cluster or "",
                    "outreach": outreach or "",
                },
            },
        )

    @app.get("/signals/{signal_id}", response_class=HTMLResponse)
    def signal_detail(
        request: Request, signal_id: str, run_id: str | None = None
    ) -> HTMLResponse:
        repository = Repository.from_settings(settings)
        try:
            selected_run = run_id or _signal_run_id(repository, signal_id)
            detail = _signal_detail(repository, selected_run, signal_id)
        finally:
            repository.connection.close()
        return templates.TemplateResponse(
            request,
            "signal_detail.html",
            {"signal_id": signal_id, "run_id": selected_run, **detail},
        )

    @app.post("/signals/{signal_id}/reviews")
    async def complete_review(request: Request, signal_id: str) -> RedirectResponse:
        form = await _form(request)
        repository = Repository.from_settings(settings)
        try:
            workflow = Workflow(repository)
            run_id = _required(form, "run_id")
            workflow.complete_review(
                run_id=run_id,
                signal_id=signal_id,
                label=_required(form, "label"),
                reason=_required(form, "reason"),
                note=form.get("note") or None,
                activity_session_id=_required(form, "activity_session_id"),
                supersedes_review_id=form.get("supersedes_review_id") or None,
            )
        except (KeyError, ValueError) as error:
            raise HTTPException(400, str(error)) from error
        finally:
            repository.connection.close()
        return _redirect(f"/signals/{signal_id}", run_id=run_id, saved="review")

    @app.post("/signals/{signal_id}/drafts")
    async def create_draft(request: Request, signal_id: str) -> RedirectResponse:
        form = await _form(request)
        repository = Repository.from_settings(settings)
        try:
            run_id = _required(form, "run_id")
            Workflow(repository).create_draft(
                run_id=run_id,
                signal_id=signal_id,
                body=_required(form, "body"),
                activity_session_id=_required(form, "activity_session_id"),
            )
        except (KeyError, ValueError) as error:
            raise HTTPException(400, str(error)) from error
        finally:
            repository.connection.close()
        return _redirect(f"/signals/{signal_id}", run_id=run_id, saved="draft")

    @app.post("/signals/{signal_id}/outreach")
    async def register_outreach(request: Request, signal_id: str) -> RedirectResponse:
        form = await _form(request)
        repository = Repository.from_settings(settings)
        try:
            run_id = _required(form, "run_id")
            subject = repository.connection.execute(
                """
                SELECT signal.platform || ':' || signal.author_public_id
                FROM mvp_run_signals member
                JOIN signals signal ON signal.signal_id = member.signal_id
                WHERE member.mvp_run_id = ? AND member.signal_id = ?
                """,
                (run_id, signal_id),
            ).fetchone()
            if subject is None:
                raise KeyError("unknown signal in run")
            Workflow(repository).register_outreach(
                run_id=run_id,
                signal_id=signal_id,
                review_id=_required(form, "review_id"),
                draft_run_id=_required(form, "draft_run_id"),
                platform=_required(form, "platform"),
                subject_key=str(subject[0]),
                approved_text=_required(form, "approved_text"),
                context_evidence=_required(form, "context_evidence"),
                sent_at=_required(form, "sent_at"),
                source_url=_required(form, "source_url"),
                source_link_opened=_truthy(form.get("source_link_opened")),
                parent_outreach_action_id=form.get("parent_outreach_action_id") or None,
            )
        except (KeyError, ValueError) as error:
            raise HTTPException(400, str(error)) from error
        finally:
            repository.connection.close()
        return _redirect(f"/signals/{signal_id}", run_id=run_id, saved="outreach")

    @app.get("/followups", response_class=HTMLResponse)
    def followups(request: Request, run_id: str | None = None) -> HTMLResponse:
        repository = Repository.from_settings(settings)
        try:
            selected_run = run_id or _latest_run_id(repository)
            timeline = _followup_timeline(repository, selected_run)
            state = repository.connection.execute(
                "SELECT state, day14_due_at FROM mvp_runs WHERE mvp_run_id = ?", (selected_run,)
            ).fetchone() if selected_run else None
            editable = _run_is_editable(state)
        finally:
            repository.connection.close()
        return templates.TemplateResponse(
            request,
            "followups.html",
            {
                "run_id": selected_run, "timeline": timeline,
                "outreach": timeline, "editable": editable,
            },
        )

    @app.post("/followups/responses")
    async def register_response(request: Request) -> RedirectResponse:
        form = await _form(request)
        repository = Repository.from_settings(settings)
        try:
            run_id = _required(form, "run_id")
            outreach_id = _required(form, "outreach_action_id")
            subject = repository.connection.execute(
                """
                SELECT subject_key FROM outreach_actions
                WHERE outreach_action_id = ? AND mvp_run_id = ?
                """,
                (outreach_id, run_id),
            ).fetchone()
            if subject is None:
                raise KeyError("unknown outreach in run")
            Workflow(repository).register_response(
                run_id=run_id,
                outreach_action_id=outreach_id,
                responder_subject_key=str(subject[0]),
                response_type=_required(form, "response_type"),
                summary=_required(form, "summary"),
                occurred_at=_required(form, "occurred_at"),
                verified_at=_required(form, "verified_at"),
                evidence_summary=form.get("evidence_summary") or None,
            )
        except (KeyError, ValueError) as error:
            raise HTTPException(400, str(error)) from error
        finally:
            repository.connection.close()
        return _redirect("/followups", run_id=run_id, saved="response")

    @app.post("/followups/interviews")
    async def register_interview(request: Request) -> RedirectResponse:
        form = await _form(request)
        repository = Repository.from_settings(settings)
        try:
            run_id = _required(form, "run_id")
            Workflow(repository).register_interview(
                run_id=run_id,
                response_event_id=_required(form, "response_event_id"),
                scheduled_at=_required(form, "scheduled_at"),
                completed_at=_required(form, "completed_at"),
                summary={
                    "customer_source_and_sales_process": _required(
                        form, "customer_source_and_sales_process"
                    ),
                    "weekly_lead_volume_and_loss_point": _required(
                        form, "weekly_lead_volume_and_loss_point"
                    ),
                    "most_manual_step": _required(form, "most_manual_step"),
                    "current_tools": _required(form, "current_tools"),
                    "minimum_agent_scenario_and_decision_process": _required(
                        form, "minimum_agent_scenario_and_decision_process"
                    ),
                },
                solution_fit=_required(form, "solution_fit"),
                next_step=_required(form, "next_step"),
            )
        except (KeyError, ValueError) as error:
            raise HTTPException(400, str(error)) from error
        finally:
            repository.connection.close()
        return _redirect("/followups", run_id=run_id, saved="interview")

    @app.post("/followups/quotes")
    async def register_quote(request: Request) -> RedirectResponse:
        form = await _form(request)
        repository = Repository.from_settings(settings)
        try:
            run_id = _required(form, "run_id")
            Workflow(repository).register_quote(
                run_id=run_id,
                response_event_id=form.get("response_event_id") or None,
                interview_id=form.get("interview_id") or None,
                scope_summary=_required(form, "scope_summary"),
                agreed_to_receive_pricing_at=_required(
                    form, "agreed_to_receive_pricing_at"
                ),
                verified_at=_required(form, "verified_at"),
            )
        except (KeyError, ValueError) as error:
            raise HTTPException(400, str(error)) from error
        finally:
            repository.connection.close()
        return _redirect("/followups", run_id=run_id, saved="quote")

    @app.post("/signals/{signal_id}/scores")
    async def score_signal(request: Request, signal_id: str) -> RedirectResponse:
        form = await _form(request)
        repository = Repository.from_settings(settings)
        try:
            run_id = _required(form, "run_id")
            _require_active_run(repository, run_id)
            result = Scorer(repository, model_client_from_env()).score(run_id, signal_id)
        except (KeyError, ValueError) as error:
            raise HTTPException(400, str(error)) from error
        finally:
            repository.connection.close()
        return _redirect(
            f"/signals/{signal_id}",
            run_id=run_id,
            saved="score",
            status=result.status,
            error_code=result.error_code or "",
        )

    @app.post("/signals/score-batch")
    async def score_batch(request: Request) -> RedirectResponse:
        values = await _form_values(request)
        form = {key: items[-1] for key, items in values.items()}
        run_id = _required(form, "run_id")
        signal_ids = [
            signal_id.strip()
            for value in values.get("signal_ids", [])
            for signal_id in value.split(",")
            if signal_id.strip()
        ]
        if not signal_ids or len(signal_ids) > 10 or len(set(signal_ids)) != len(signal_ids):
            raise HTTPException(400, "score batch requires 1 to 10 unique signals")
        repository = Repository.from_settings(settings)
        try:
            _require_active_run(repository, run_id)
            client = model_client_from_env()
            workflow = Workflow(repository)
            for signal_id in signal_ids:
                result = Scorer(repository, client).score(run_id, signal_id)
                if result.status == "SUCCEEDED":
                    workflow.present_score(run_id, signal_id, result.score_run_id)
        finally:
            repository.connection.close()
        return _redirect("/signals", run_id=run_id, saved="score-batch")

    @app.post("/signals/{signal_id}/drafts/generate")
    async def generate_draft(request: Request, signal_id: str) -> RedirectResponse:
        form = await _form(request)
        repository = Repository.from_settings(settings)
        try:
            run_id = _required(form, "run_id")
            _require_active_run(repository, run_id)
            result = DraftGenerator(repository, model_client_from_env()).generate(
                run_id, signal_id
            )
        except (KeyError, ValueError) as error:
            raise HTTPException(400, str(error)) from error
        finally:
            repository.connection.close()
        return _redirect(
            f"/signals/{signal_id}",
            run_id=run_id,
            saved="generated-draft",
            status=result.status,
            error_code=result.error_code or "",
        )

    @app.post("/activity/start")
    async def start_activity(request: Request) -> JSONResponse:
        form = await _form(request)
        repository = Repository.from_settings(settings)
        try:
            workflow = Workflow(repository)
            session_id = workflow.start_activity(
                _required(form, "run_id"),
                _required(form, "signal_id"),
                _required(form, "activity_kind"),
            )
            state = workflow.activity_session(session_id).state
        except (KeyError, ValueError) as error:
            raise HTTPException(400, str(error)) from error
        finally:
            repository.connection.close()
        return JSONResponse({"activity_session_id": session_id, "state": state})

    @app.post("/activity/{session_id}/events")
    async def activity_event(request: Request, session_id: str) -> JSONResponse:
        form = await _form(request)
        repository = Repository.from_settings(settings)
        try:
            result = Workflow(repository).record_activity(
                session_id, _required(form, "event_kind")
            )
        except KeyError as error:
            raise HTTPException(404, str(error)) from error
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        finally:
            repository.connection.close()
        return JSONResponse(
            {
                "activity_session_id": result.activity_session_id,
                "state": result.state,
                "active_seconds": result.active_seconds,
            }
        )

    @app.get("/metrics", response_class=HTMLResponse)
    def metrics(request: Request, run_id: str | None = None) -> HTMLResponse:
        repository = Repository.from_settings(settings)
        try:
            selected_run = run_id or _latest_run_id(repository)
            snapshot = None
            finalized = False
            if selected_run:
                frozen = repository.connection.execute(
                    "SELECT state, conclusion_facts_json, conclusion_facts_sha256 "
                    "FROM mvp_runs WHERE mvp_run_id = ?",
                    (selected_run,),
                ).fetchone()
                if frozen is None:
                    raise KeyError(f"unknown mvp run: {selected_run}")
                if frozen["state"] == "FINALIZED":
                    finalized = True
                    facts_json = str(frozen["conclusion_facts_json"])
                    if _sha256_text(facts_json) != frozen["conclusion_facts_sha256"]:
                        raise HTTPException(500, "finalized snapshot hash mismatch")
                    snapshot = MetricsSnapshot.from_facts(json.loads(facts_json))
                else:
                    snapshot = MetricsEngine(repository.connection).calculate(selected_run)
        except KeyError as error:
            raise HTTPException(404, str(error)) from error
        finally:
            repository.connection.close()
        return templates.TemplateResponse(
            request,
            "metrics.html",
            {"metrics": snapshot, "run_id": selected_run, "finalized": finalized},
        )

    @app.post("/runs/{run_id}/finalize")
    async def finalize_run(request: Request, run_id: str) -> RedirectResponse:
        repository = Repository.from_settings(settings)
        try:
            state = repository.connection.execute(
                "SELECT state FROM mvp_runs WHERE mvp_run_id = ?", (run_id,)
            ).fetchone()
            if state is None:
                raise HTTPException(404, "unknown mvp run")
            if state["state"] not in ("ACTIVE", "CANCELLED"):
                raise HTTPException(409, "run is already finalized or not terminalizable")
            repository.connection.execute("BEGIN IMMEDIATE")
            try:
                locked = repository.connection.execute(
                    "SELECT state FROM mvp_runs WHERE mvp_run_id = ?", (run_id,)
                ).fetchone()
                if locked is None or locked["state"] not in ("ACTIVE", "CANCELLED"):
                    raise HTTPException(409, "run is already finalized or not terminalizable")
                snapshot = MetricsEngine(repository.connection).calculate(run_id)
                if snapshot.decision == "RUNNING":
                    raise HTTPException(409, "run is not terminal eligible")
                repository.finalize_run(run_id, snapshot.decision, snapshot.facts())
                repository.connection.commit()
            except Exception:
                repository.connection.rollback()
                raise
        except HTTPException:
            raise
        except Exception as error:
            if "already finalized" in str(error) or "not active" in str(error):
                raise HTTPException(409, str(error)) from error
            raise
        finally:
            repository.connection.close()
        return _redirect("/metrics", run_id=run_id, saved="finalized")

    @app.post("/runs/{run_id}/incidents")
    async def register_incident(request: Request, run_id: str) -> RedirectResponse:
        form = await _form(request)
        if not _truthy(form.get("confirmed")):
            raise HTTPException(400, "confirmed incident evidence is required")
        repository = Repository.from_settings(settings)
        try:
            Workflow(repository).register_incident(
                run_id=run_id,
                event_type=_required(form, "event_type"),
                platform=form.get("platform") or None,
                summary=_required(form, "summary"),
            )
        except (KeyError, ValueError) as error:
            raise HTTPException(400, str(error)) from error
        finally:
            repository.connection.close()
        return _redirect("/metrics", run_id=run_id, saved="incident")

    @app.post("/runs/{run_id}/cancel")
    def cancel_run(run_id: str) -> RedirectResponse:
        repository = Repository.from_settings(settings)
        try:
            repository.connection.execute("BEGIN IMMEDIATE")
            repository.cancel_run(run_id)
            snapshot = MetricsEngine(repository.connection).calculate(run_id)
            repository.finalize_run(run_id, snapshot.decision, snapshot.facts())
            repository.connection.commit()
        except Exception as error:
            repository.connection.rollback()
            if "already finalized" in str(error) or "not active" in str(error):
                raise HTTPException(409, str(error)) from error
            raise
        finally:
            repository.connection.close()
        return _redirect("/metrics", run_id=run_id, saved="finalized-early")

    @app.get("/export.csv")
    @app.get("/exports/signals.csv")
    def export_csv(run_id: str | None = None) -> Response:
        repository = Repository.from_settings(settings)
        try:
            selected_run = run_id or _latest_run_id(repository)
            payload = (
                export_signals_csv(repository.connection, selected_run)
                if selected_run
                else export_signals_csv_empty()
            )
        finally:
            repository.connection.close()
        return Response(
            payload,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=discovery-signals.csv"},
        )

    return app


async def _form(request: Request) -> dict[str, str]:
    parsed = await _form_values(request)
    return {key: values[-1] for key, values in parsed.items()}


async def _form_values(request: Request) -> dict[str, list[str]]:
    body = await request.body()
    if len(body) > _FORM_LIMIT:
        raise HTTPException(413, "form body is too large")
    content_type = request.headers.get("content-type", "").split(";", 1)[0]
    if content_type != "application/x-www-form-urlencoded":
        raise HTTPException(415, "form must be application/x-www-form-urlencoded")
    parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True, strict_parsing=False)
    return parsed


def _required(form: dict[str, str], name: str) -> str:
    value = form.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _integer(form: dict[str, str], name: str) -> int:
    try:
        return int(_required(form, name))
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error


def _truthy(value: str | None) -> bool:
    return bool(value and value.lower() in {"1", "true", "yes", "on"})


def _require_active_run(repository: Repository, run_id: str) -> None:
    row = repository.connection.execute(
        "SELECT state, day14_due_at FROM mvp_runs WHERE mvp_run_id = ?", (run_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "unknown mvp run")
    if row["state"] != "ACTIVE":
        raise HTTPException(409, "operator actions require an ACTIVE mvp run")
    if not _run_is_editable(row):
        raise HTTPException(409, "operator actions are closed after the Day 14 cutoff")


def _run_is_editable(row: Mapping[str, object] | None) -> bool:
    if row is None or row["state"] != "ACTIVE":
        return False
    due_at = datetime.fromisoformat(str(row["day14_due_at"]).replace("Z", "+00:00"))
    return datetime.now(UTC) <= due_at


def _sha256_text(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _redirect(path: str, **query: object) -> RedirectResponse:
    values = {key: str(value) for key, value in query.items() if value is not None}
    target = f"{path}?{urlencode(values)}" if values else path
    return RedirectResponse(target, status_code=303)


def _latest_run_id(repository: Repository) -> str | None:
    row = repository.connection.execute(
        """
        SELECT mvp_run_id FROM mvp_runs
        ORDER BY CASE state WHEN 'ACTIVE' THEN 0 ELSE 1 END, started_at DESC
        LIMIT 1
        """
    ).fetchone()
    return str(row[0]) if row else None


def _signal_run_id(repository: Repository, signal_id: str) -> str | None:
    row = repository.connection.execute(
        """
        SELECT m.mvp_run_id FROM mvp_run_signals m
        JOIN mvp_runs r ON r.mvp_run_id = m.mvp_run_id
        WHERE m.signal_id = ?
        ORDER BY CASE r.state WHEN 'ACTIVE' THEN 0 ELSE 1 END, m.added_at DESC
        LIMIT 1
        """,
        (signal_id,),
    ).fetchone()
    return str(row[0]) if row else None


def _filtered_signals(
    repository: Repository,
    *,
    run_id: str | None,
    platform: str | None,
    grade: str | None,
    review: str | None,
    industry: str | None,
    query_cluster: str | None,
    outreach: str | None,
):
    if run_id is None:
        return []
    if platform and platform not in {"bili", "dy"}:
        raise HTTPException(400, "invalid platform filter")
    if grade and grade not in {"A", "B", "C", "D"}:
        raise HTTPException(400, "invalid grade filter")
    if review and review not in {"HIGH_INTENT", "POSSIBLE", "NOT_LEAD", "UNVERIFIABLE"}:
        raise HTTPException(400, "invalid review filter")
    if outreach and outreach not in {"NONE", "SENT_VERIFIED"}:
        raise HTTPException(400, "invalid outreach filter")
    statement = """
        WITH ranked_scores AS (
          SELECT sr.*, 1 AS rank
          FROM score_presentations presentation
          JOIN score_runs sr
            ON sr.score_run_id = presentation.score_run_id
           AND sr.mvp_run_id = presentation.mvp_run_id
           AND sr.signal_id = presentation.signal_id
        ), leaf_reviews AS (
          SELECT hr.* FROM human_reviews hr
          WHERE NOT EXISTS (
            SELECT 1 FROM human_reviews newer
            WHERE newer.supersedes_review_id = hr.review_id
              AND newer.mvp_run_id = hr.mvp_run_id
              AND newer.signal_id = hr.signal_id
          )
        )
        SELECT s.*, src.title AS source_title, src.canonical_url AS source_url,
               m.mvp_run_id, rs.grade, rs.total_score,
               json_extract(rs.reason_json, '$.explicit_industry') AS industry,
               lr.label AS review_label,
               (SELECT so.query_cluster FROM signal_observations so
                WHERE so.mvp_run_id = m.mvp_run_id AND so.signal_id = s.signal_id
                ORDER BY so.observed_at DESC, so.observation_id DESC LIMIT 1) AS query_cluster,
               CASE WHEN EXISTS (
                 SELECT 1 FROM outreach_actions oa
                 WHERE oa.mvp_run_id = m.mvp_run_id AND oa.signal_id = s.signal_id
                   AND oa.status = 'SENT_VERIFIED'
               ) THEN 'SENT_VERIFIED' ELSE 'NONE' END AS outreach_state
        FROM mvp_run_signals m
        JOIN signals s ON s.signal_id = m.signal_id
        LEFT JOIN sources src ON src.source_id = s.source_id
        LEFT JOIN ranked_scores rs
          ON rs.mvp_run_id = m.mvp_run_id AND rs.signal_id = s.signal_id AND rs.rank = 1
        LEFT JOIN leaf_reviews lr
          ON lr.mvp_run_id = m.mvp_run_id AND lr.signal_id = s.signal_id
        WHERE m.mvp_run_id = ?
    """
    parameters: list[object] = [run_id]
    if platform:
        statement += " AND s.platform = ?"
        parameters.append(platform)
    if grade:
        statement += " AND rs.grade = ?"
        parameters.append(grade)
    if review:
        statement += " AND lr.label = ?"
        parameters.append(review)
    if industry:
        statement += " AND json_extract(rs.reason_json, '$.explicit_industry') = ?"
        parameters.append(industry)
    if query_cluster:
        statement += """
          AND EXISTS (
            SELECT 1 FROM signal_observations so
            WHERE so.mvp_run_id = m.mvp_run_id AND so.signal_id = s.signal_id
              AND so.query_cluster = ?
          )
        """
        parameters.append(query_cluster)
    if outreach == "SENT_VERIFIED":
        statement += """
          AND EXISTS (
            SELECT 1 FROM outreach_actions oa
            WHERE oa.mvp_run_id = m.mvp_run_id AND oa.signal_id = s.signal_id
              AND oa.status = 'SENT_VERIFIED'
          )
        """
    elif outreach == "NONE":
        statement += """
          AND NOT EXISTS (
            SELECT 1 FROM outreach_actions oa
            WHERE oa.mvp_run_id = m.mvp_run_id AND oa.signal_id = s.signal_id
              AND oa.status = 'SENT_VERIFIED'
          )
        """
    statement += " ORDER BY m.added_at DESC, s.signal_id"
    return repository.connection.execute(statement, parameters).fetchall()


def _signal_detail(
    repository: Repository, run_id: str | None, signal_id: str
) -> dict[str, object]:
    if run_id is None:
        return {
            "signal": None,
            "scores": [],
            "successful_scores": [],
            "reviews": [],
            "current_reviews": [],
            "drafts": [],
            "human_drafts": [],
            "outreach": [],
        }
    run = repository.connection.execute(
        "SELECT state, day14_due_at FROM mvp_runs WHERE mvp_run_id = ?", (run_id,)
    ).fetchone()
    editable = _run_is_editable(run)
    signal = repository.connection.execute(
        """
        SELECT s.*, src.title AS source_title, src.canonical_url AS source_url,
               src.external_source_id, src.author_public_id AS source_author_public_id,
               m.mvp_run_id,
               (SELECT so.query_cluster FROM signal_observations so
                WHERE so.mvp_run_id = m.mvp_run_id AND so.signal_id = s.signal_id
                ORDER BY so.observed_at DESC, so.observation_id DESC LIMIT 1) AS query_cluster,
               (SELECT so.query_text FROM signal_observations so
                WHERE so.mvp_run_id = m.mvp_run_id AND so.signal_id = s.signal_id
                ORDER BY so.observed_at DESC, so.observation_id DESC LIMIT 1) AS query_text
        FROM mvp_run_signals m
        JOIN signals s ON s.signal_id = m.signal_id
        LEFT JOIN sources src ON src.source_id = s.source_id
        WHERE m.mvp_run_id = ? AND s.signal_id = ?
        """,
        (run_id, signal_id),
    ).fetchone()
    if signal is None:
        return {
            "signal": None,
            "scores": [],
            "successful_scores": [],
            "reviews": [],
            "current_reviews": [],
            "drafts": [],
            "human_drafts": [],
            "outreach": [],
        }
    presented = repository.connection.execute(
        "SELECT score_run_id FROM score_presentations "
        "WHERE mvp_run_id = ? AND signal_id = ?",
        (run_id, signal_id),
    ).fetchone()
    if editable and presented is None:
        first_visible = repository.connection.execute(
            """
            SELECT score_run_id FROM score_runs
            WHERE mvp_run_id = ? AND signal_id = ? AND status = 'SUCCEEDED'
            ORDER BY created_at DESC, score_run_id DESC LIMIT 1
            """,
            (run_id, signal_id),
        ).fetchone()
        if first_visible is not None:
            Workflow(repository).present_score(run_id, signal_id, str(first_visible[0]))
    score_rows = repository.connection.execute(
        """
        SELECT sr.*, CASE WHEN sp.score_run_id IS NULL THEN 0 ELSE 1 END AS presented
        FROM score_runs sr
        LEFT JOIN score_presentations sp
          ON sp.score_run_id = sr.score_run_id
         AND sp.mvp_run_id = sr.mvp_run_id
         AND sp.signal_id = sr.signal_id
        WHERE sr.mvp_run_id = ? AND sr.signal_id = ?
        ORDER BY sr.created_at DESC, sr.score_run_id DESC
        """,
        (run_id, signal_id),
    ).fetchall()
    scores = []
    for row in score_rows:
        item = dict(row)
        try:
            item["reason"] = json.loads(item["reason_json"]) if item["reason_json"] else None
        except json.JSONDecodeError:
            item["reason"] = None
        scores.append(item)
    reviews = repository.connection.execute(
        "SELECT * FROM human_reviews WHERE mvp_run_id = ? AND signal_id = ? ORDER BY completed_at DESC",
        (run_id, signal_id),
    ).fetchall()
    drafts = repository.connection.execute(
        "SELECT * FROM draft_runs WHERE mvp_run_id = ? AND signal_id = ? ORDER BY created_at DESC",
        (run_id, signal_id),
    ).fetchall()
    outreach = repository.connection.execute(
        "SELECT * FROM outreach_actions WHERE mvp_run_id = ? AND signal_id = ? ORDER BY created_at DESC",
        (run_id, signal_id),
    ).fetchall()
    current_reviews = repository.connection.execute(
        """
        SELECT current.* FROM human_reviews current
        WHERE current.mvp_run_id = ? AND current.signal_id = ?
          AND NOT EXISTS (
            SELECT 1 FROM human_reviews child
            WHERE child.supersedes_review_id = current.review_id
          )
        """,
        (run_id, signal_id),
    ).fetchall()
    human_drafts = [
        draft for draft in drafts
        if draft["draft_kind"] == "HUMAN_EDITED" and draft["status"] == "SUCCEEDED"
    ]
    return {
        "signal": signal,
        "scores": scores,
        "successful_scores": [score for score in scores if score["status"] == "SUCCEEDED"],
        "reviews": reviews,
        "current_reviews": current_reviews,
        "drafts": drafts,
        "human_drafts": human_drafts,
        "outreach": outreach,
        "editable": editable,
    }


def _followup_timeline(repository: Repository, run_id: str | None) -> list[dict[str, object]]:
    if run_id is None:
        return []
    outreach_rows = repository.connection.execute(
        """
        SELECT oa.*, s.body AS signal_body
        FROM outreach_actions oa
        JOIN signals s ON s.signal_id = oa.signal_id
        WHERE oa.mvp_run_id = ?
        ORDER BY oa.created_at DESC
        """,
        (run_id,),
    ).fetchall()
    timeline = []
    for outreach in outreach_rows:
        responses = repository.connection.execute(
            """
            SELECT * FROM response_events
            WHERE mvp_run_id = ? AND outreach_action_id = ?
            ORDER BY occurred_at
            """,
            (run_id, outreach["outreach_action_id"]),
        ).fetchall()
        response_items = []
        for response in responses:
            interviews = repository.connection.execute(
                """
                SELECT * FROM interviews
                WHERE mvp_run_id = ? AND response_event_id = ?
                ORDER BY completed_at
                """,
                (run_id, response["response_event_id"]),
            ).fetchall()
            quotes = repository.connection.execute(
                """
                SELECT * FROM quote_opportunities
                WHERE mvp_run_id = ? AND (
                  response_event_id = ? OR interview_id IN (
                    SELECT interview_id FROM interviews
                    WHERE mvp_run_id = ? AND response_event_id = ?
                  )
                ) ORDER BY verified_at
                """,
                (run_id, response["response_event_id"], run_id, response["response_event_id"]),
            ).fetchall()
            response_items.append(
                {"fact": response, "interviews": interviews, "quotes": quotes}
            )
        timeline.append({"fact": outreach, "responses": response_items})
    return timeline


def export_signals_csv_empty() -> str:
    from app.exporter import SIGNAL_EXPORT_FIELDS

    return ",".join(SIGNAL_EXPORT_FIELDS) + "\n"
