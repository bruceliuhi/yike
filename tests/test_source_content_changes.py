"""Pure bounded source-observation projection tests; all records synthetic."""
from datetime import UTC, datetime, timedelta
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pilot.auth import issue_token
from pilot.opportunity_brief import OpportunityBriefService
from pilot.source_content_changes import SourceContentChangeError, project_source_content_changes
from pilot.web import build_app
from tests.test_candidate_review_postgres import SECRET, seed
from tests.test_confirmed_strategy_review_postgres import (
    databases, env, execution_databases, execution_env, raw_databases, raw_env,
    real_review, real_strategy_env,
)
from tests.test_opportunity_evidence_postgres import include
from tests.test_opportunity_research_postgres import bound


BASE=datetime(2026,9,11,0,tzinfo=UTC); URL="https://example.invalid/source"


def row(identifier,version,body,minutes,received=None,**metadata):
    return {"observation_id":identifier,"version_id":version,"observed_at":BASE+timedelta(minutes=minutes),
        "received_at":BASE+timedelta(minutes=received if received is not None else minutes),
        "content":{"public_url":URL,"body":body,"title":metadata.get("title","title"),"published_at":None}}


def project(rows,anchor=0):
    item=rows[anchor]
    return project_source_content_changes(rows,anchor_observation_id=item["observation_id"],
        anchor_version_id=item["version_id"],anchor_observed_at=item["observed_at"],
        anchor_received_at=item["received_at"],source_url=URL,anchor_body=item["content"]["body"])


def test_anchor_not_last_and_a_b_a_keep_two_versions_three_observations_two_changes():
    rows=[row("o1","vA","正文A",0),row("o2","vB","正文B",10),row("o3","vA","正文A",20)]
    result=project(rows)
    assert result["anchorObservationId"]=="o1"
    assert [item["id"] for item in result["versions"]]==["vA","vB"]
    assert [item["versionId"] for item in result["observations"]]==["vA","vB","vA"]
    assert [(item["fromObservationId"],item["toObservationId"],item["occurredAt"]) for item in result["changes"]]==[("o1","o2",None),("o2","o3",None)]
    assert all(item["kind"]=="CONTENT" and item["from"]["field"]==item["to"]["field"]=="source.body" for item in result["changes"])


def test_repeat_body_metadata_and_early_late_upload_do_not_create_post_anchor_change():
    rows=[row("early","v0","更早正文",-10,received=30),row("anchor","vA","正文A",0),
        row("same","vMeta","正文A",10,title="changed"),row("changed","vB","正文B",20)]
    result=project(rows,1)
    assert [(item["fromObservationId"],item["toObservationId"]) for item in result["changes"]]==[("same","changed")]
    assert result["changes"][0]["detectedAt"]==(BASE+timedelta(minutes=20)).isoformat(timespec="milliseconds").replace("+00:00","Z")


def test_same_observed_time_different_body_is_gap_and_resets_direction():
    rows=[row("anchor","vA","正文A",0),row("tie1","vB","正文B",10,11),
        row("tie2","vC","正文C",10,12),row("clear","vD","正文D",20),row("next","vE","正文E",30)]
    result=project(rows)
    assert [(item["fromObservationId"],item["toObservationId"]) for item in result["changes"]]==[("clear","next")]
    assert result["gaps"]==["同一观察时间存在不同正文，无法确定变化方向。"]


def test_same_wire_millisecond_different_body_is_ambiguous_and_resets_direction():
    anchor=row("anchor","vA","正文A",0)
    anchor["observed_at"]+=timedelta(microseconds=100)
    later=row("later","vB","正文B",0)
    later["observed_at"]+=timedelta(microseconds=200)
    clear=row("clear","vC","正文C",1)
    following=row("following","vD","正文D",2)
    result=project([anchor,later,clear,following])
    assert [item["observedAt"] for item in result["observations"][:2]]==[
        "2026-09-11T00:00:00.000Z","2026-09-11T00:00:00.000Z"]
    assert [(item["fromObservationId"],item["toObservationId"]) for item in result["changes"]]==[("clear","following")]
    assert result["gaps"]==["同一观察时间存在不同正文，无法确定变化方向。"]


def test_observation_and_real_version_limits_fail_closed():
    with pytest.raises(SourceContentChangeError): project([row(f"o{i}","v", "A",i) for i in range(201)])
    with pytest.raises(SourceContentChangeError): project([row(f"o{i}",f"v{i}",str(i),i) for i in range(101)])


def test_restricted_http_projects_a_b_a_and_daily_latest_change(real_strategy_env):
    env=real_strategy_env
    review,candidate,_,_,_,_,opportunity_id=include(env,service=real_review(env))
    with env.db.connect() as connection:
        role=connection.execute("SELECT current_user").fetchone()[0]
    with env.admin.connect() as connection:
        connection.execute("SELECT set_config('yike.app_role',%s,true)",(role,))
        connection.execute((Path(__file__).parents[1]/"deploy/grant_structured_followups.sql").read_text())
    detail=env.store.get_opportunity(env.claims.user_id,opportunity_id)
    anchor_body=detail["source_evidence"]["snapshot"]["source"]["body"]
    time.sleep(1.1)
    second=seed(env,body="正文B")
    time.sleep(1.1)
    third=seed(env,body=anchor_body)
    now=datetime.now(UTC).replace(microsecond=0)
    app=build_app(env.store,auth_secret=SECRET,candidate_review=review,
        research_strategies=env.strategies,opportunity_brief=OpportunityBriefService(env.db))
    client=TestClient(app,base_url="https://pilot.example")
    client.headers["Authorization"]="Bearer "+issue_token(env.claims.user_id,SECRET)
    binding=bound(env,opportunity_id,candidate["sourceVersionId"],detail["public_url"])
    timeline=client.post("/api/ui/opportunity-research/timeline",json={"binding":binding})
    assert timeline.status_code==200, timeline.text
    payload=timeline.json()
    assert payload["schemaVersion"]==2
    assert [item["versionId"] for item in payload["observations"]][-2:]==[second["sourceVersionId"],third["sourceVersionId"]]
    assert [(item["from"]["quote"],item["to"]["quote"]) for item in payload["changes"]][-2:]==[(anchor_body,"正文B"),("正文B",anchor_body)]
    with env.admin.connect() as connection:
        version=connection.execute("SELECT version FROM business_profile_versions WHERE profile_version_id=%s",(env.profile,)).fetchone()[0]
    brief=client.post("/api/ui/opportunity-brief/query",json={"contractVersion":1,"requestId":str(__import__('uuid').uuid4()),
        "userId":env.claims.user_id,"accountScopeId":env.tenant,"scopeVersion":1,"profileId":env.profile,
        "profileVersion":version,"businessDate":now.date().isoformat(),"timezone":"UTC"})
    assert brief.status_code==200, brief.text
    change=brief.json()["groups"]["changes"]
    assert change["total"]==1 and change["items"][0]["basis"]["version"]==payload["changes"][-1]["toObservationId"]
