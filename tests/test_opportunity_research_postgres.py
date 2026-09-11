"""Real restricted PG review facts; source/model inputs remain synthetic."""
from datetime import UTC, datetime
import copy
import os
from pathlib import Path
import shutil
import socket
import subprocess
import threading
import time
from uuid import uuid4

import pytest
import uvicorn

from pilot.auth import issue_token
import pilot.opportunity_research as opportunity_research
from pilot.opportunity_research import OpportunityResearchError, OpportunityResearchService
from pilot.web import build_app
from tests.test_candidate_assessment_model import assessment
from tests.test_candidate_review_postgres import review_payload, seed, verification_payload
from tests.test_confirmed_strategy_review_postgres import (
    databases, env, execution_databases, execution_env, raw_databases, raw_env,
    real_review, real_strategy_env,
)
from tests.test_opportunity_evidence_postgres import include
from tests.test_desktop_opportunity_http_postgres import _node_environment
from tests.test_execution_runtime_postgres import SECRET


def research(env, platforms=("PUBLIC_WEB",)):
    return OpportunityResearchService(env.db, supported_platforms=lambda _configuration: platforms)


def bound(env, opportunity_id, source_version, url):
    return {"userId":env.claims.user_id,"opportunityId":opportunity_id,
        "profileVersionId":env.profile,"sourceUrl":url,"evidenceVersion":source_version,
        "accountScope":{"id":env.tenant,"version":1}}


def test_same_source_across_strategies_uses_first_projection_but_keeps_sibling_comment():
    observed=datetime(2026,9,11,8,tzinfo=UTC)
    def item(candidate_id, strategy_id, comment_id):
        raw={"candidate_id":candidate_id,"strategy_version_id":strategy_id,
            "profile_version_id":"profile-1","platform":"XIAOHONGSHU","kind":"COMMENT",
            "external_source_id":"post-1","external_comment_id":comment_id,
            "latest_observed_at":observed,"version_id":"source-version-1",
            "content":{"public_url":"https://www.xiaohongshu.com/explore/66c01234abcdef0123456789"}}
        return raw,{"opportunity":{"id":candidate_id},"classification":{"category":"UNASSESSED"}}
    rows=opportunity_research._deduplicate_candidates([
        item("candidate-newest","strategy-b","comment-1"),
        item("candidate-older","strategy-a","comment-1"),
        item("candidate-sibling","strategy-a","comment-2"),
    ])
    assert [row["opportunity"]["id"] for row in rows]==["candidate-newest","candidate-sibling"]


def run_node_http(env, opportunity_id, review):
    node=os.environ.get("YIKE_RESEARCH_LIVE_NODE_BINARY") or shutil.which("node")
    if not node: pytest.skip("Node 24 required for opportunity research live contract")
    child_env=_node_environment()
    version=subprocess.run([node,"--version"],env=child_env,capture_output=True,text=True,timeout=10,check=True)
    assert version.stdout.strip().startswith("v24."),"Node 24 required"
    token=issue_token(env.claims.user_id,SECRET)
    app=build_app(env.store,auth_secret=SECRET,dev_login=True,execution_runtime=env.runtime,
        research_strategies=env.strategies,candidate_review=review)
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1",0));listener.listen(64)
        server=uvicorn.Server(uvicorn.Config(app,log_level="critical",access_log=False,lifespan="off"))
        thread=threading.Thread(target=server.run,kwargs={"sockets":[listener]},daemon=True);thread.start()
        try:
            deadline=time.monotonic()+10
            while not server.started and thread.is_alive() and time.monotonic()<deadline: time.sleep(.02)
            assert server.started and thread.is_alive()
            child_env.update(YIKE_RESEARCH_LIVE_BASE=f"http://127.0.0.1:{listener.getsockname()[1]}",
                YIKE_RESEARCH_LIVE_USER=env.claims.user_id,YIKE_RESEARCH_LIVE_TOKEN=token,
                YIKE_RESEARCH_LIVE_OPPORTUNITY=opportunity_id)
            child=subprocess.run([node,"node_modules/vitest/vitest.mjs","run",
                "tests/integration/opportunity-research-live.test.ts","--maxWorkers=1"],
                cwd=Path(__file__).parents[1]/"desktop",env=child_env,capture_output=True,text=True,timeout=50)
            output=(child.stdout+child.stderr).replace(token,"[redacted]")
            assert child.returncode==0,output
            assert "1 passed" in output and "skipped" not in output.lower(),output
        finally:
            server.should_exit=True;thread.join(timeout=10);assert not thread.is_alive()


def test_actual_assess_shape_enters_observation_and_verify_does_not_mask_it(real_strategy_env):
    env=real_strategy_env; review=real_review(env)
    value=assessment(); value["decision"]="OBSERVE"; value["grade"]=None
    review.model.assess=lambda **_kwargs:(copy.deepcopy(value),None)
    candidate=seed(env)|{"profileVersion":env.profile_number}
    assessed=review.review(env.claims,review_payload(candidate))
    review.verify_source(env.claims,candidate|{"requestId":str(uuid4()),"humanConfirmed":True,
        "status":"OPEN","openingMethod":"DIRECT","locator":"https://example.com/synthetic",
        "excerpt":"采购输送设备","contactMethod":"COMMENT"})
    row=next(r for r in research(env).list(env.claims)["records"]
        if r["opportunity"]["id"]==candidate["candidateId"])
    assert assessed["kind"]=="assessment"
    assert row["classification"]["category"]=="OBSERVATION"
    assert row["classification"]["evidence"]


def test_real_include_timeline_similar_and_withdrawal(real_strategy_env):
    env=real_strategy_env
    review,candidate,assessed,check,_,_,opportunity_id=include(env,service=real_review(env))
    detail=env.store.get_opportunity(env.claims.user_id,opportunity_id)
    evidence=detail["source_evidence"]["snapshot"]
    service=research(env); current=bound(env,opportunity_id,candidate["sourceVersionId"],detail["public_url"])
    row=next(r for r in service.list(env.claims)["records"] if r["opportunity"]["id"]==opportunity_id)
    assert row["classification"]["category"]=="OPPORTUNITY"
    assert {q["field"] for q in row["classification"]["evidence"]}=={q["field"] for q in evidence["assessment"]["citations"]}
    assert service.timeline(env.claims,current)["versions"][-1]["id"]==candidate["sourceVersionId"]
    request=str(uuid4()); first=service.similar(env.claims,current,request); again=service.similar(env.claims,current,request)
    assert first["suggestionId"]==again["suggestionId"] and first["usage"]["status"]=="UNKNOWN"
    run_node_http(env,opportunity_id,review)
    excluded=review_payload(candidate,"EXCLUDE",assessmentId=assessed["assessment"]["id"],
        sourceVerificationId=check["id"],humanConfirmed=True,evidence=assessment()["evidence"],reason="人工撤销认可")
    review.review(env.claims,excluded)
    with pytest.raises(OpportunityResearchError,match="recognition_required"):
        service.similar(env.claims,current,str(uuid4()))
    assert service.timeline(env.claims,current)["versions"][-1]["id"]==candidate["sourceVersionId"]


def test_real_later_signed_source_version_disables_similar(real_strategy_env):
    env=real_strategy_env
    _,candidate,_,_,_,_,opportunity_id=include(env,service=real_review(env))
    detail=env.store.get_opportunity(env.claims.user_id,opportunity_id)
    current=bound(env,opportunity_id,candidate["sourceVersionId"],detail["public_url"])
    service=research(env)
    changed=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    seed(env,body="采购输送设备，需求内容已变化",observed_at=changed,published_at=changed)
    with pytest.raises(OpportunityResearchError,match="recognition_required"):
        service.similar(env.claims,current,str(uuid4()))


def test_real_blocked_reverification_disables_similar(real_strategy_env):
    env=real_strategy_env; review=real_review(env)
    _,candidate,_,_,_,_,opportunity_id=include(env,service=review)
    detail=env.store.get_opportunity(env.claims.user_id,opportunity_id)
    current=bound(env,opportunity_id,candidate["sourceVersionId"],detail["public_url"])
    review.verify_source(env.claims,verification_payload(candidate,requestId=str(uuid4()),status="BLOCKED"))
    with pytest.raises(OpportunityResearchError,match="recognition_required"):
        research(env).similar(env.claims,current,str(uuid4()))


def test_constructor_is_io_free():
    class Lazy:
        def connect(self): raise AssertionError("constructor performed I/O")
    OpportunityResearchService(Lazy(),supported_platforms=())
