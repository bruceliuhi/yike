"""Bounded dynamic supervisor with real PostgreSQL authority and synthetic effects."""
from datetime import UTC, datetime, timedelta
import hashlib
from pathlib import Path
import sys
import threading
import time
import json
from uuid import uuid4

import pytest

from pilot.dynamic_research_config import DynamicResearchAgentConfiguration
from pilot.execution_contract import ExecutionRuntimeError
from pilot.research_effects import dispatch_effect
from tests.test_candidate_assessment_model import CONTENT
from tests.test_candidate_review_postgres import BoundaryModel
from tests.test_customer_research_context_postgres import (
    context_env,
    dynamic_start,
    real_strategy_env,
    databases,
    env,
    execution_databases,
    execution_env,
    raw_databases,
    raw_env,
)
from tests.test_execution_runtime_postgres import apply, operation
from tests.test_research_runtime_postgres import _grant_runtime


ROOT = Path(__file__).parents[1]


class ResearchModel(BoundaryModel):
    def assess_before(self, _deadline, **kwargs):
        value, usage = self.assess(**kwargs)
        if kwargs["content"].get("source_read_scope") == "UNATTRIBUTED_PAGE":
            value["intent"] = {"level": "UNKNOWN", "reason": "整页未确认本人归属。", "citations": []}
            value["urgency"] = {"level": "UNKNOWN", "reason": "整页未确认本人归属。", "citations": []}
        return value, usage


def agent_configuration():
    return DynamicResearchAgentConfiguration(
        codex_binary="/bin/sh",
        python_binary=sys.executable,
        api_key="synthetic-provider-key",
        model="synthetic/model-v1",
        search_api_key="synthetic-search-key",
    )


@pytest.fixture
def dynamic_env(context_env):
    from pilot.candidate_review import CandidateReviewStore
    from pilot.dynamic_research_candidates import DynamicResearchCandidateStore
    from pilot.research_assessment import ResearchAssessmentRunner
    from pilot.research_candidates import ResearchCandidateStore
    from pilot.research_effect_journal import ResearchEffectJournal
    from pilot.research_orchestrator import ResearchOrchestrator
    from pilot.research_resources import ResearchResourceStore
    from pilot.research_runtime import ResearchRuntimeService
    from tests.test_research_resources_postgres import RULE

    env = context_env
    _grant_runtime(env)
    with env.db.connect() as connection:
        role = connection.execute("SELECT current_user").fetchone()[0]
    with env.admin.connect() as connection:
        connection.execute("SELECT set_config('yike.app_role',%s,true)", (role,))
        connection.execute((ROOT / "deploy/grant_research_effect_journal.sql").read_text())
    env.execution = dynamic_start(env)
    resources = ResearchResourceStore(
        env.runtime,
        rule=RULE,
        research_capability=lambda snapshot: snapshot["configuration"].get("publicSource")
        == "public-web-agent-v1",
    )
    reviews = CandidateReviewStore(
        env.db,
        model=ResearchModel(),
        strategy_resolver=env.strategies.resolve,
        strategy_snapshot_reader=env.strategies.read_snapshot,
        research_assessment=ResearchAssessmentRunner(resources),
    )
    fixed = ResearchRuntimeService(
        ResearchOrchestrator(ResearchCandidateStore(resources), reviews)
    )
    journal = ResearchEffectJournal(resources)
    env.resources = resources
    env.reviews = reviews
    env.fixed = fixed
    env.journal = journal
    env.candidates = DynamicResearchCandidateStore(journal)
    yield env
    with env.admin.connect() as connection:
        connection.execute(
            "DELETE FROM pilot_research_effect_journal WHERE tenant_id=%s", (env.tenant,)
        )
        connection.execute(
            "DELETE FROM pilot_research_runtime WHERE tenant_id=%s", (env.tenant,)
        )


def search_result(query):
    return {
        "status": "SEARCHED",
        "query": query,
        "observed_at": datetime.now(UTC).isoformat(),
        "read_scope": "SEARCH_RESULTS",
        "results": [{
            "url": "https://example.com/buyer",
            "title": "客户需求",
            "snippet": "仅用于发现，不是候选原文",
            "date_hint": None,
            "rank": 1,
        }],
        "omitted_count": 0,
        "replayed": False,
    }


def read_result():
    text = CONTENT["body"]
    return {
        "status": "READ",
        "evidence": {
            "url": "https://example.com/buyer",
            "title": CONTENT["title"],
            "text": text,
            "observed_at": datetime.now(UTC).isoformat(),
            "content_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "read_scope": "PUBLIC_PAGE_TEXT",
        },
        "review_status": "UNREVIEWED",
        "replayed": False,
    }


def mission_completed(kwargs, evidences, *, background=False):
    from pilot.research_context import compile_research_context
    pages = [{"url": page["url"], "content_sha256": page["content_sha256"],
              "decision": "BACKGROUND" if background else "ASSESS",
              "reason": "IRRELEVANT" if background else "POSSIBLE_DEMAND",
              "quote": page["text"][:100]} for page in evidences]
    return {"status": "COMPLETED", "code": None,
            "research_binding": compile_research_context(kwargs["research_context"])["binding"],
            "summary": json.dumps({"schema_version": "research-page-selection-v1",
                                   "summary": "合成逐页筛选", "pages": pages}, ensure_ascii=False)}


def successful_mission(calls):
    def mission(_description, **kwargs):
        calls.append("mission")
        dispatcher = kwargs["effect_dispatcher"]
        query = "企业知识库 找团队"
        deadline = time.monotonic() + 20
        dispatch_effect(
            dispatcher,
            kind="SEARCH",
            payload={"query": query},
            deadline=deadline,
            perform=lambda _deadline: search_result(query),
        )
        dispatch_effect(
            dispatcher,
            kind="READ",
            payload={"url": "https://example.com/buyer"},
            deadline=deadline,
            perform=lambda _deadline: read_result(),
        )
        return mission_completed(kwargs, [read_result()["evidence"]])
    return mission


def service(env, mission, **kwargs):
    from pilot.dynamic_research_runtime import DynamicResearchRuntimeService

    dynamic = DynamicResearchRuntimeService(
        env.fixed,
        journal=env.journal,
        candidates=env.candidates,
        agent=agent_configuration(),
        mission=mission,
        **kwargs,
    )
    env.fixed.dynamic = dynamic
    return dynamic


def wait_terminal(runtime, env, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = runtime.status(env.claims, env.execution["task_id"])
        if value["phase"] != "RUNNING":
            return value
        time.sleep(0.02)
    pytest.fail("dynamic supervisor did not reach a terminal or stopped state")


def test_public_read_session_publishes_through_actual_durable_customer_journal(dynamic_env):
    from pilot.public_read_session import PublicReadSession

    page = read_result()["evidence"]
    reads = []
    class Reader:
        def read(self, url, *, deadline):
            reads.append(url)
            return page
        def close(self):
            pass
    def mission(_description, **kwargs):
        dispatcher = kwargs["effect_dispatcher"]
        deadline = time.monotonic() + 20
        dispatch_effect(dispatcher, kind="SEARCH", payload={"query":"企业知识库 找团队"},
            deadline=deadline, perform=lambda _: search_result("企业知识库 找团队"))
        session = PublicReadSession(max_reads=1, deadline=deadline,
            allowed_url=lambda url: url == page["url"], effect_dispatcher=dispatcher, reader=Reader())
        try:
            first = session.read(page["url"], deadline=deadline)
            assert first["status"] == "READ"
            assert session.read(page["url"], deadline=deadline) == first | {"replayed":True}
        finally:
            session.close()
        return mission_completed(kwargs, [page])
    runtime = service(dynamic_env, mission)
    try:
        runtime.advance(dynamic_env.claims, dynamic_env.execution["task_id"], dynamic_env.execution["run_id"])
        final = wait_terminal(runtime, dynamic_env)
        assert final["phase"] == "COMPLETED"
        assert final["acceptedOriginals"] == final["analyzedOriginals"] == 1
        assert final["discovery"]["reads"]["succeeded"] == 1
        assert final["discovery"]["reads"]["unknown"] == 0
        assert reads == [page["url"]]
    finally:
        runtime.shutdown(timeout_seconds=2)


def test_all_background_completes_without_candidate_assessment(dynamic_env):
    env = dynamic_env
    def mission(_description, **kwargs):
        value = read_result()
        dispatch_effect(kwargs["effect_dispatcher"], kind="READ",
            payload={"url": value["evidence"]["url"]}, deadline=time.monotonic()+20,
            perform=lambda _: value)
        return mission_completed(kwargs, [value["evidence"]], background=True)
    runtime = service(env, mission)
    try:
        runtime.advance(env.claims, env.execution["task_id"], env.execution["run_id"])
        final = wait_terminal(runtime, env)
        assert final["phase"] == "COMPLETED"
        assert final["acceptedOriginals"] == final["analyzedOriginals"] == 0
        assert env.reviews.model.calls == 0
        with env.admin.connect() as connection:
            assert connection.execute("SELECT count(*) FROM pilot_candidate_batches WHERE tenant_id=%s",
                                      (env.tenant,)).fetchone()[0] == 1
    finally:
        runtime.shutdown(timeout_seconds=2)


def test_trusted_entry_only_runtime_has_durable_read_and_zero_search_receipts(dynamic_env):
    env = dynamic_env
    entry = 'https://www.v2ex.com/go/outsourcing'
    def mission(_description, **kwargs):
        from pilot.research_context import compile_research_context
        assert entry in compile_research_context(kwargs['research_context'])['entry_urls']
        value = read_result()
        value['evidence']['url'] = entry
        dispatch_effect(kwargs['effect_dispatcher'], kind='READ', payload={'url':entry},
            deadline=time.monotonic()+20, perform=lambda _:value)
        return mission_completed(kwargs, [value['evidence']], background=True)
    runtime = service(env, mission)
    try:
        runtime.advance(env.claims, env.execution['task_id'], env.execution['run_id'])
        final = wait_terminal(runtime, env)
        assert final['phase'] == 'COMPLETED'
        assert final['discovery']['searches']['issued'] == 0
        assert final['discovery']['reads']['succeeded'] == 1
        assert final['acceptedOriginals'] == final['analyzedOriginals'] == 0
        assert env.reviews.model.calls == 0
        with env.admin.connect() as connection:
            assert connection.execute(
                "SELECT count(*) FROM pilot_research_effect_journal WHERE task_id=%s AND kind='SEARCH'",
                (env.execution['task_id'],)).fetchone()[0] == 0
            assert connection.execute(
                "SELECT count(*) FROM pilot_candidate_batches WHERE task_id=%s",
                (env.execution['task_id'],)).fetchone()[0] == 1
    finally:
        runtime.shutdown(timeout_seconds=2)


def test_invalid_complete_selection_stops_before_any_publication(dynamic_env):
    env = dynamic_env
    def mission(_description, **kwargs):
        value = read_result()
        dispatch_effect(kwargs["effect_dispatcher"], kind="READ",
            payload={"url": value["evidence"]["url"]}, deadline=time.monotonic()+20,
            perform=lambda _: value)
        result = mission_completed(kwargs, [])
        return result
    runtime = service(env, mission)
    try:
        runtime.advance(env.claims, env.execution["task_id"], env.execution["run_id"])
        final = wait_terminal(runtime, env)
        assert final["phase"] == "STOPPED" and final["stopCode"] == "research_selection_invalid"
        assert final["acceptedOriginals"] == 0 and env.reviews.model.calls == 0
        with env.admin.connect() as connection:
            assert connection.execute("SELECT count(*) FROM pilot_candidate_batches WHERE tenant_id=%s",
                                      (env.tenant,)).fetchone()[0] == 0
    finally:
        runtime.shutdown(timeout_seconds=2)


def test_oversized_json_integer_stops_as_selection_invalid_before_publication(dynamic_env):
    from pilot.research_context import compile_research_context
    env = dynamic_env
    def mission(_description, **kwargs):
        value = read_result()
        dispatch_effect(kwargs["effect_dispatcher"], kind="READ",
            payload={"url": value["evidence"]["url"]}, deadline=time.monotonic()+20,
            perform=lambda _: value)
        return {"status": "COMPLETED", "code": None,
                "research_binding": compile_research_context(kwargs["research_context"])["binding"],
                "summary": ('{"schema_version":"research-page-selection-v1","summary":'
                            + '1' * 5000 + ',"pages":[]}')}
    runtime = service(env, mission)
    try:
        runtime.advance(env.claims, env.execution["task_id"], env.execution["run_id"])
        final = wait_terminal(runtime, env)
        assert final["phase"] == "STOPPED" and final["stopCode"] == "research_selection_invalid"
        with env.admin.connect() as connection:
            assert connection.execute("SELECT count(*) FROM pilot_candidate_batches WHERE tenant_id=%s",
                                      (env.tenant,)).fetchone()[0] == 0
    finally:
        runtime.shutdown(timeout_seconds=2)


def test_known_failed_read_then_positive_completes_with_actual_v4_client_contract(dynamic_env):
    from pilot.public_read_session import PublicReadSession
    from pilot.open_web_reader import PublicReadError
    import json
    import shutil
    import subprocess
    from tests.test_desktop_opportunity_http_postgres import _node_environment

    env=dynamic_env; page=read_result()['evidence']; missing='https://example.com/missing'; reads=[]
    class Reader:
        def read(self,url,*,deadline):
            reads.append(url)
            if url==missing: raise PublicReadError('not_found')
            return page
        def close(self): pass
    def mission(_description,**kwargs):
        deadline=time.monotonic()+20
        dispatcher=kwargs['effect_dispatcher']
        value=search_result('企业知识库 找团队')
        value['results'].append(dict(url=missing,title='不存在的测试来源',snippet=None,date_hint=None,rank=2))
        dispatch_effect(dispatcher,kind='SEARCH',payload={'query':value['query']},deadline=deadline,perform=lambda _:value)
        session=PublicReadSession(max_reads=2,deadline=deadline,
            allowed_url=lambda url:url in (missing,page['url']),effect_dispatcher=dispatcher,reader=Reader())
        try:
            failed=session.read(missing,deadline=deadline)
            assert failed=={'status':'FAILED','code':'not_found','replayed':False}
            assert session.read(missing,deadline=deadline)==failed|{'replayed':True}
            assert session.read(page['url'],deadline=deadline)['status']=='READ'
        finally: session.close()
        return mission_completed(kwargs, [page])
    runtime=service(env,mission)
    try:
        runtime.advance(env.claims,env.execution['task_id'],env.execution['run_id'])
        final=wait_terminal(runtime,env)
        assert final['phase']=='COMPLETED', final
        assert final['acceptedOriginals']==final['analyzedOriginals']==1
        assert final['discovery']['reads']==dict(issued=2,pending=0,succeeded=1,failed=1,unknown=0)
        assert final['usage']['sourceReads']['issued']==3
        assert final['usage']['sourceReads']['failed']==1
        assert final['usage']['resourceCloseout']['state']=='RECORDED'
        assert reads==[missing,page['url']]
        assert final['discovery']['unpublishedOriginals']==0
        with env.admin.connect() as connection:
            assert connection.execute('SELECT j.status,count(*) FROM pilot_candidate_batches b '
                'JOIN pilot_research_effect_journal j ON j.action_id=b.request_id '
                'AND j.tenant_id=b.tenant_id WHERE b.tenant_id=%s GROUP BY j.status',(env.tenant,)).fetchall()==[('SUCCEEDED',1)]
        child_env=_node_environment()
        child_env['YIKE_KNOWN_READ_TEST_STATUS']=json.dumps(final)
        result=subprocess.run([shutil.which('node'),'node_modules/vitest/vitest.mjs','run',
            'tests/knownReadOutcomeCompatibility.test.ts','--maxWorkers=1'],cwd=ROOT/'desktop',
            env=child_env,capture_output=True,text=True,timeout=30)
        assert result.returncode==0, result.stdout+result.stderr
        assert '1 passed' in result.stdout and 'skipped' not in result.stdout
    finally: runtime.shutdown(timeout_seconds=2)


def test_capability_is_explicit_v4_and_fixed_capabilities_are_unchanged(dynamic_env):
    env = dynamic_env
    runtime = service(env, successful_mission([]))
    try:
        assert env.fixed.capability(env.claims) == {
            "contractVersion": 1,
            "sourceScope": "V2EX_LATEST_INDEX",
            "sourceLabel": "V2EX最新主题 · 公开单源研究",
            "maxFreshEffectsPerAdvance": 1,
            "settlementState": "PENDING",
        }
        assert env.fixed.capability(env.claims, dynamic_research_version=1) == {
            "contractVersion": 4,
            "sourceScope": "PUBLIC_WEB_AGENT",
            "sourceLabel": "公开网页自主研究",
            "sourceIds": [
                "v2ex-latest-v1",
                "v2ex-qna-v1",
                "v2ex-outsourcing-authors-v1",
                "public-web-agent-v1",
            ],
            "maxPlannedSources": 3,
            "executionMode": "SERVER_BACKGROUND",
            "limits": {
                "maxSearches": 10,
                "maxSources": 100,
                "maxModelCalls": 20,
                "maxMinutes": 30,
                "maxRuntimeSeconds": 1800,
            },
            "settlementState": "PENDING",
        }
        with pytest.raises(ExecutionRuntimeError, match="invalid_request"):
            env.fixed.capability(
                env.claims, source_catalog_version=1, dynamic_research_version=1
            )
    finally:
        runtime.shutdown(timeout_seconds=2)


def test_persisted_dynamic_task_fails_closed_when_worker_is_not_configured(dynamic_env):
    env = dynamic_env
    task_id, run_id = env.execution["task_id"], env.execution["run_id"]
    for action in (
        lambda: env.fixed.status(env.claims, task_id),
        lambda: env.fixed.advance(env.claims, task_id, run_id),
    ):
        with pytest.raises(ExecutionRuntimeError) as caught:
            action()
        assert (caught.value.code, caught.value.status) == (
            "capability_unavailable", 501
        )
    with env.admin.connect() as connection:
        assert connection.execute(
            "SELECT count(*) FROM pilot_research_runtime WHERE task_id=%s", (task_id,),
        ).fetchone()[0] == 0


def test_signed_dynamic_task_launches_once_and_finishes_persisted_path(dynamic_env):
    env = dynamic_env
    calls = []
    runtime = service(env, successful_mission(calls))
    task_id, run_id = env.execution["task_id"], env.execution["run_id"]
    try:
        queued = env.fixed.status(env.claims, task_id)
        assert queued["phase"] == "QUEUED" and queued["canAdvance"] is True
        assert queued["acceptedOriginals"] == 0
        running = env.fixed.advance(env.claims, task_id, run_id)
        assert running["phase"] in ("RUNNING", "COMPLETED")
        env.fixed.advance(env.claims, task_id, run_id)
        done = wait_terminal(runtime, env)
        assert done["phase"] == "COMPLETED"
        assert done["acceptedOriginals"] == 1
        assert done["analyzedOriginals"] == 1
        assert done["skippedOriginals"] == 0
        assert len(done["candidateIds"]) == 1
        assert done["discovery"] == {
            "searches": {"issued": 1, "pending": 0, "succeeded": 1,
                         "failed": 0, "unknown": 0},
            "reads": {"issued": 1, "pending": 0, "succeeded": 1,
                      "failed": 0, "unknown": 0},
            "unpublishedOriginals": 0,
        }
        assert done["usage"]["sourceReads"]["succeeded"] == 2
        assert calls == ["mission"]
        assert env.fixed.status(env.claims, task_id)["phase"] == "COMPLETED"
        assert env.fixed.advance(env.claims, task_id, run_id)["phase"] == "COMPLETED"
        assert calls == ["mission"]
    finally:
        runtime.shutdown(timeout_seconds=2)


@pytest.mark.parametrize('stop',['effect_unknown','effect_pending'])
def test_status_uses_strict_journal_stop_even_without_resource_counter(dynamic_env,monkeypatch,stop):
    env=dynamic_env; runtime=service(env,successful_mission([]))
    try:
        runtime.advance(env.claims,env.execution['task_id'],env.execution['run_id'])
        assert wait_terminal(runtime,env)['phase']=='COMPLETED'
        # The strict journal reader can see a corrupt/unpaired row that resource
        # counters alone cannot represent. Status must consume that same verdict.
        monkeypatch.setattr(runtime,'_effect_stop',lambda *args,**kwargs:stop)
        status=runtime.status(env.claims,env.execution['task_id'])
        assert status['phase']=='STOPPED'
        assert status['stopCode']==stop
        assert status['usage']['resourceCloseout']['state']==('UNCERTAIN' if stop=='effect_unknown' else 'DRAINING')
    finally: runtime.shutdown(timeout_seconds=2)


def test_expired_running_lease_stops_as_worker_lost_without_relaunch(dynamic_env):
    env = dynamic_env
    calls = []
    runtime = service(env, successful_mission(calls))
    task_id, run_id = env.execution["task_id"], env.execution["run_id"]
    try:
        with env.admin.connect() as connection:
            connection.execute(
                "INSERT INTO pilot_research_runtime(tenant_id,owner_user_id,task_id,run_id,"
                "generation,current_owner,lease_expires_at,phase) VALUES "
                "(%s,%s,%s,%s,1,%s,clock_timestamp()-interval '1 second','RUNNING')",
                (env.tenant, env.claims.user_id, task_id, run_id,
                 "10000000-0000-4000-8000-000000000009"),
            )
        stopped = runtime.status(env.claims, task_id)
        assert stopped["phase"] == "STOPPED"
        assert stopped["stopCode"] == "worker_lost"
        assert stopped["canAdvance"] is False and stopped["newActionsBlocked"] is True
        assert runtime.advance(env.claims, task_id, run_id)["stopCode"] == "worker_lost"
        assert calls == []
    finally:
        runtime.shutdown(timeout_seconds=2)


def test_cancelled_worker_keeps_journal_facts_but_cannot_publish_or_complete(dynamic_env):
    env = dynamic_env
    entered = threading.Event()
    release = threading.Event()

    def mission(_description, **kwargs):
        dispatcher = kwargs["effect_dispatcher"]
        deadline = time.monotonic() + 20
        dispatch_effect(
            dispatcher,
            kind="READ",
            payload={"url": "https://example.com/buyer"},
            deadline=deadline,
            perform=lambda _deadline: read_result(),
        )
        entered.set()
        release.wait(5)
        return mission_completed(kwargs, [read_result()["evidence"]])

    runtime = service(env, mission)
    task_id, run_id = env.execution["task_id"], env.execution["run_id"]
    try:
        runtime.advance(env.claims, task_id, run_id)
        assert entered.wait(3)
        apply(env, operation(env, "CANCEL", env.execution))
        release.set()
        stopped = wait_terminal(runtime, env)
        assert stopped["phase"] == "CANCELED"
        with env.admin.connect() as connection:
            assert connection.execute(
                "SELECT count(*) FROM pilot_research_effect_journal WHERE tenant_id=%s "
                "AND kind='READ' AND status='SUCCEEDED'", (env.tenant,)
            ).fetchone()[0] == 1
            assert connection.execute(
                "SELECT count(*) FROM pilot_candidate_batches WHERE tenant_id=%s",
                (env.tenant,),
            ).fetchone()[0] == 0
            statuses = connection.execute(
                "SELECT status FROM pilot_collection_tasks WHERE task_id=%s", (task_id,)
            ).fetchone()[0]
        assert statuses == "CANCELED"
    finally:
        release.set()
        runtime.shutdown(timeout_seconds=2)


def test_lost_lease_keeps_admitted_read_but_blocks_late_publication(dynamic_env):
    env = dynamic_env
    entered = threading.Event()
    release = threading.Event()

    def mission(_description, **kwargs):
        dispatch_effect(
            kwargs["effect_dispatcher"], kind="READ",
            payload={"url": "https://example.com/buyer"},
            deadline=time.monotonic() + 20,
            perform=lambda _deadline: read_result(),
        )
        entered.set()
        release.wait(5)
        return mission_completed(kwargs, [read_result()["evidence"]])

    runtime = service(env, mission)
    task_id, run_id = env.execution["task_id"], env.execution["run_id"]
    try:
        runtime.advance(env.claims, task_id, run_id)
        assert entered.wait(3)
        with env.admin.connect() as connection:
            connection.execute(
                "UPDATE pilot_research_runtime SET lease_expires_at="
                "clock_timestamp()-interval '1 second' WHERE task_id=%s", (task_id,),
            )
        release.set()
        stopped = wait_terminal(runtime, env)
        assert stopped["phase"] == "STOPPED"
        assert stopped["stopCode"] == "worker_lost"
        with env.admin.connect() as connection:
            assert connection.execute(
                "SELECT count(*) FROM pilot_research_effect_journal WHERE task_id=%s "
                "AND kind='READ' AND status='SUCCEEDED'", (task_id,),
            ).fetchone()[0] == 1
            assert connection.execute(
                "SELECT count(*) FROM pilot_candidate_batches WHERE task_id=%s", (task_id,),
            ).fetchone()[0] == 0
    finally:
        release.set()
        runtime.shutdown(timeout_seconds=2)


def test_worker_failure_before_first_effect_is_durable_and_never_relaunched(dynamic_env):
    env = dynamic_env
    calls = []

    def dies(_description, **_kwargs):
        calls.append("mission")
        raise RuntimeError("synthetic process death")

    runtime = service(env, dies)
    task_id, run_id = env.execution["task_id"], env.execution["run_id"]
    try:
        runtime.advance(env.claims, task_id, run_id)
        stopped = wait_terminal(runtime, env)
        assert stopped["phase"] == "STOPPED"
        assert stopped["stopCode"] == "advance_failed"
        assert stopped["discovery"]["searches"]["issued"] == 0
        assert runtime.advance(env.claims, task_id, run_id)["stopCode"] == "advance_failed"
        assert calls == ["mission"]
    finally:
        runtime.shutdown(timeout_seconds=2)


def test_assessment_budget_exhaustion_keeps_published_candidate_pending(dynamic_env):
    env = dynamic_env
    task_id, run_id = env.execution["task_id"], env.execution["run_id"]
    for _ in range(10):
        action_id = str(uuid4())
        granted = env.resources.begin(
            env.claims, task_id=task_id, run_id=run_id, action_id=action_id,
            resource="MODEL_CALL", input_sha256="a" * 64,
        )["event"]
        env.resources.finish(
            env.claims, task_id=task_id, run_id=run_id, action_id=action_id,
            permit_id=granted["permit_id"], status="SUCCEEDED",
            output_sha256="b" * 64,
        )
    runtime = service(env, successful_mission([]))
    try:
        runtime.advance(env.claims, task_id, run_id)
        stopped = wait_terminal(runtime, env)
        assert stopped["phase"] == "STOPPED"
        assert stopped["stopCode"] == "resource_limit_exceeded"
        assert stopped["acceptedOriginals"] == 1
        assert stopped["analyzedOriginals"] == 0
        assert len(stopped["candidateIds"]) == 1
    finally:
        runtime.shutdown(timeout_seconds=2)


@pytest.mark.parametrize("effect_status", ["ISSUED", "FAILED", "UNKNOWN"])
def test_mission_completion_cannot_override_non_successful_durable_effect(
        dynamic_env, effect_status):
    from pilot.research_context import compile_research_context

    env = dynamic_env
    calls = []
    runtime = None

    def mission(_description, **kwargs):
        calls.append("mission")
        original = read_result()
        original["evidence"]["url"] = (
            "https://example.com/buyer/" + effect_status.lower()
        )
        dispatch_effect(
            kwargs["effect_dispatcher"], kind="READ",
            payload={"url": original["evidence"]["url"]},
            deadline=time.monotonic() + 20,
            perform=lambda _deadline: original,
        )
        binding = compile_research_context(kwargs["research_context"])["binding"]
        begun = env.journal.begin(
            env.claims, task_id=env.execution["task_id"],
            run_id=env.execution["run_id"], sequence=2, generation=1,
            coordinator_owner=runtime.owner, context_binding=binding,
            kind="SEARCH", payload={"query": "第二个受控搜索"},
        )
        if effect_status != "ISSUED":
            env.journal.finish(
                env.claims, task_id=env.execution["task_id"],
                run_id=env.execution["run_id"], sequence=2,
                permit_id=begun["entry"]["permit_id"], status=effect_status,
            )
        return mission_completed(kwargs, [original["evidence"]])

    runtime = service(env, mission)
    task_id, run_id = env.execution["task_id"], env.execution["run_id"]
    expected_code = {
        "ISSUED": "effect_pending", "FAILED": "effect_failed",
        "UNKNOWN": "effect_unknown",
    }[effect_status]
    expected_counter = {
        "ISSUED": "pending", "FAILED": "failed", "UNKNOWN": "unknown",
    }[effect_status]
    try:
        runtime.advance(env.claims, task_id, run_id)
        stopped = wait_terminal(runtime, env)
        assert stopped["phase"] == "STOPPED"
        assert stopped["stopCode"] == expected_code
        assert stopped["acceptedOriginals"] == 0
        assert stopped["analyzedOriginals"] == 0
        assert stopped["discovery"]["searches"][expected_counter] == 1
        assert stopped["usage"]["sourceReads"][expected_counter] == 1
        assert stopped["effectsPending"] is (effect_status == "ISSUED")
        assert calls == ["mission"]
        with env.admin.connect() as connection:
            assert connection.execute(
                "SELECT count(*) FROM pilot_candidate_batches WHERE task_id=%s",
                (task_id,),
            ).fetchone()[0] == 0
            assert connection.execute(
                "SELECT count(*) FROM pilot_research_resource_events WHERE task_id=%s "
                "AND resource='MODEL_CALL'", (task_id,),
            ).fetchone()[0] == 0
            assert connection.execute(
                "SELECT t.status,r.status,c.phase FROM pilot_collection_tasks t "
                "JOIN pilot_collection_runs r USING(tenant_id,owner_user_id,task_id) "
                "JOIN pilot_research_runtime c USING(tenant_id,owner_user_id,task_id,run_id) "
                "WHERE t.task_id=%s", (task_id,),
            ).fetchone() == ("PENDING", "PENDING", "STOPPED")
        assert runtime.advance(env.claims, task_id, run_id)["stopCode"] == expected_code
        assert calls == ["mission"]
    finally:
        runtime.shutdown(timeout_seconds=2)


def test_final_completion_transaction_rejects_new_unknown_effect(dynamic_env, monkeypatch):
    from pilot.customer_research_context import CustomerResearchContextStore

    env = dynamic_env
    runtime = service(env, successful_mission([]))
    task_id, run_id = env.execution["task_id"], env.execution["run_id"]
    complete = env.fixed._complete
    injected = []

    def inject_before_transaction(claims, current_task, current_run, generation,
                                  **kwargs):
        compiled = CustomerResearchContextStore(env.runtime).load(
            claims, task_id=current_task, run_id=current_run
        )
        begun = env.journal.begin(
            claims, task_id=current_task, run_id=current_run, sequence=3,
            generation=generation, coordinator_owner=runtime.owner,
            context_binding=compiled["binding"], kind="SEARCH",
            payload={"query": "终态提交前竞态"},
        )
        env.journal.finish(
            claims, task_id=current_task, run_id=current_run, sequence=3,
            permit_id=begun["entry"]["permit_id"], status="UNKNOWN",
        )
        injected.append(True)
        return complete(
            claims, current_task, current_run, generation, **kwargs
        )

    monkeypatch.setattr(env.fixed, "_complete", inject_before_transaction)
    try:
        runtime.advance(env.claims, task_id, run_id)
        stopped = wait_terminal(runtime, env)
        assert injected == [True]
        assert stopped["phase"] == "STOPPED"
        assert stopped["stopCode"] == "effect_unknown"
        assert stopped["acceptedOriginals"] == 1
        assert stopped["analyzedOriginals"] == 1
        with env.admin.connect() as connection:
            assert connection.execute(
                "SELECT status FROM pilot_collection_tasks WHERE task_id=%s", (task_id,),
            ).fetchone()[0] == "PENDING"
    finally:
        runtime.shutdown(timeout_seconds=2)


def test_shutdown_during_first_assessment_blocks_second_provider_effect(dynamic_env):
    env = dynamic_env
    entered = threading.Event()
    release = threading.Event()

    class BlockingModel(ResearchModel):
        def __init__(self):
            super().__init__()
            self.started = 0

        def assess_before(self, _deadline, **kwargs):
            self.started += 1
            entered.set()
            release.wait(5)
            return super().assess_before(_deadline, **kwargs)

    model = BlockingModel()
    env.reviews.model = model

    def mission(_description, **kwargs):
        dispatcher = kwargs["effect_dispatcher"]
        first = read_result()
        second = read_result()
        second["evidence"]["url"] = "https://example.com/second-buyer"
        for result in (first, second):
            dispatch_effect(
                dispatcher, kind="READ", payload={"url": result["evidence"]["url"]},
                deadline=time.monotonic() + 20,
                perform=lambda _deadline, value=result: value,
            )
        return mission_completed(kwargs, [first["evidence"], second["evidence"]])

    runtime = service(env, mission)
    task_id, run_id = env.execution["task_id"], env.execution["run_id"]
    try:
        runtime.advance(env.claims, task_id, run_id)
        assert entered.wait(3)
        assert runtime.shutdown(timeout_seconds=0.05) is False
        release.set()
        stopped = wait_terminal(runtime, env)
        assert stopped["phase"] == "STOPPED"
        assert stopped["stopCode"] == "runtime_shutdown"
        assert stopped["acceptedOriginals"] == 2
        assert stopped["analyzedOriginals"] == 1
        assert model.started == 1 and model.calls == 1
        with env.admin.connect() as connection:
            assert connection.execute(
                "SELECT status FROM pilot_research_resource_events WHERE task_id=%s "
                "AND resource='MODEL_CALL' ORDER BY issued_at", (task_id,),
            ).fetchall() == [("SUCCEEDED",)]
            assert connection.execute(
                "SELECT status FROM pilot_collection_tasks WHERE task_id=%s", (task_id,),
            ).fetchone()[0] == "PENDING"
        with pytest.raises(ExecutionRuntimeError, match="runtime_shutdown"):
            runtime.advance(env.claims, task_id, run_id)
    finally:
        release.set()
        runtime.shutdown(timeout_seconds=2)


def test_capacity_rejection_happens_before_persisted_coordinator_election(dynamic_env):
    env = dynamic_env
    entered = threading.Event()
    release = threading.Event()

    def blocked(_description, **_kwargs):
        entered.set()
        release.wait(5)
        return {"status": "FAILED", "code": "synthetic_stop"}

    runtime = service(env, blocked, max_workers=1)
    first = env.execution
    second = dynamic_start(env)
    try:
        runtime.advance(env.claims, first["task_id"], first["run_id"])
        assert entered.wait(3)
        with env.admin.connect() as connection:
            lease, now, deadline, created, minutes = connection.execute(
                "SELECT c.lease_expires_at,clock_timestamp(),t.deadline_at,t.created_at,"
                "q.minute_limit FROM pilot_research_runtime c JOIN pilot_collection_tasks t "
                "USING(tenant_id,owner_user_id,task_id) JOIN pilot_research_reservations q "
                "USING(tenant_id,owner_user_id,task_id,run_id) WHERE c.task_id=%s",
                (first["task_id"],),
            ).fetchone()
        assert lease <= min(deadline, created + timedelta(minutes=minutes),
                            now + timedelta(seconds=1800))
        with pytest.raises(ExecutionRuntimeError, match="worker_capacity_exceeded"):
            runtime.advance(env.claims, second["task_id"], second["run_id"])
        with env.admin.connect() as connection:
            assert connection.execute(
                "SELECT count(*) FROM pilot_research_runtime WHERE task_id=%s",
                (second["task_id"],),
            ).fetchone()[0] == 0
        release.set()
        assert wait_terminal(runtime, env, timeout=3)["phase"] == "STOPPED"
        runtime.advance(env.claims, second["task_id"], second["run_id"])
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            with env.admin.connect() as connection:
                count = connection.execute(
                    "SELECT count(*) FROM pilot_research_runtime WHERE task_id=%s",
                    (second["task_id"],),
                ).fetchone()[0]
            if count:
                break
            time.sleep(0.02)
        assert count == 1
    finally:
        release.set()
        runtime.shutdown(timeout_seconds=2)


def test_shutdown_blocks_new_actions_under_current_authority(dynamic_env):
    env = dynamic_env
    runtime = service(env, successful_mission([]))
    assert runtime.shutdown(timeout_seconds=2)
    with pytest.raises(ExecutionRuntimeError, match="runtime_shutdown"):
        runtime.advance(
            env.claims, env.execution["task_id"], env.execution["run_id"]
        )


def test_shutdown_cancels_active_worker_and_persists_non_relaunchable_stop(dynamic_env):
    env = dynamic_env
    entered = threading.Event()

    def mission(_description, **kwargs):
        entered.set()
        deadline = time.monotonic() + 3
        while not kwargs["cancelled"]() and time.monotonic() < deadline:
            time.sleep(0.01)
        return {"status": "CANCELLED", "code": "cancelled"}

    runtime = service(env, mission)
    task_id, run_id = env.execution["task_id"], env.execution["run_id"]
    runtime.advance(env.claims, task_id, run_id)
    assert entered.wait(2)
    assert runtime.shutdown(timeout_seconds=2)
    stopped = runtime.status(env.claims, task_id)
    assert stopped["phase"] == "STOPPED"
    assert stopped["stopCode"] == "runtime_shutdown"
    with pytest.raises(ExecutionRuntimeError, match="runtime_shutdown"):
        runtime.advance(env.claims, task_id, run_id)
