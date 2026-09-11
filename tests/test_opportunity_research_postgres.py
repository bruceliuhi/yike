"""Synthetic evidence over a real isolated PostgreSQL; no platform/model proof."""
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
from uuid import uuid4

import pytest

from pilot.auth import issue_token, verify_token_claims
from pilot.db import PilotDatabase


SECRET = "research-service-test"


@pytest.fixture(scope="module")
def database():
    url = os.environ["YIKE_IDENTITY_TEST_DATABASE_URL"]
    db = PilotDatabase(url)
    db.migrate()
    return db


@pytest.fixture
def seeded(database):
    tenant = str(uuid4())
    user, other = ("research-" + uuid4().hex for _ in range(2))
    profile, strategy, draft = (str(uuid4()) for _ in range(3))
    payload = {"description": "展台设计搭建服务"}
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest()
    configuration = {"schema_version":"research-strategy-v1","name":"展台采购",
        "source":"search","keywords":["展台搭建"],"exclusions":["招聘"],"links":[],
        "mode":"once","schedule":None,"research":None}
    snapshot = {"profile_version_id":profile,"strategy_version_id":strategy,
        "configuration":configuration,"platforms":["PUBLIC_WEB"],"max_records":20,
        "max_runtime_seconds":600}
    config_digest = hashlib.sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest()
    with database.connect() as conn:
        conn.execute("INSERT INTO pilot_tenants(tenant_id,name) VALUES(%s,'synthetic')", (tenant,))
        conn.execute("INSERT INTO pilot_users(user_id,tenant_id,email) VALUES(%s,%s,%s),(%s,%s,%s)",
            (user,tenant,user+'@test.invalid',other,tenant,other+'@test.invalid'))
        conn.execute("INSERT INTO business_profiles(profile_id,tenant_id) VALUES(%s,%s)",(profile,tenant))
        conn.execute("INSERT INTO business_profile_versions(profile_version_id,tenant_id,profile_id,version,payload,content_sha256,status) VALUES(%s,%s,%s,1,%s::jsonb,%s,'CONFIRMED')",
            (profile,tenant,profile,json.dumps(payload),digest))
        conn.execute("INSERT INTO pilot_research_strategy_drafts(tenant_id,owner_user_id,draft_id,current_revision,current_version_id) VALUES(%s,%s,%s,1,%s)",(tenant,user,draft,strategy))
        conn.execute("INSERT INTO pilot_research_strategy_versions(tenant_id,owner_user_id,strategy_version_id,draft_id,draft_revision,profile_version_id,profile_sha256,configuration_sha256,snapshot) VALUES(%s,%s,%s,%s,1,%s,%s,%s,%s::jsonb)",
            (tenant,user,strategy,draft,profile,digest,config_digest,json.dumps(snapshot)))
        conn.execute("UPDATE pilot_research_strategy_versions SET state='CONFIRMED' WHERE strategy_version_id=%s",(strategy,))
    claims = verify_token_claims(issue_token(user, SECRET), SECRET)
    other_claims = verify_token_claims(issue_token(other, SECRET), SECRET)
    yield type("ResearchFixture", (), dict(database=database,tenant=tenant,user=user,other=other,
        claims=claims,other_claims=other_claims,profile=profile,strategy=strategy))()


def _candidate(env, *, comment="comment-1", body="需要展台搭建报价", owner=None):
    owner = owner or env.user
    source, version, candidate, observation = (str(uuid4()) for _ in range(4))
    content = {"public_url":"https://example.com/post/1","title":"采购咨询",
        "author_public_id":"buyer","body":body,"published_at":"2026-09-10T00:00:00Z",
        "parent":{"external_comment_id":"parent","body":"展会讨论","author_public_id":"parent",
                  "published_at":"2026-09-09T00:00:00Z","public_url":"https://example.com/post/1"}}
    digest = hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest()
    with env.database.connect() as conn:
        conn.execute("SELECT set_config('yike.user_id',%s,true),set_config('yike.tenant_id',%s,true)",(owner,env.tenant))
        conn.execute("INSERT INTO pilot_candidate_sources VALUES(%s,%s,%s,%s,'PUBLIC_WEB','COMMENT','post-1',%s)",
            (env.tenant,owner,source,hashlib.sha256((owner+comment).encode()).hexdigest(),comment))
        conn.execute("INSERT INTO pilot_candidate_versions VALUES(%s,%s,%s,%s,%s,%s::jsonb,clock_timestamp())",
            (env.tenant,owner,source,version,digest,json.dumps(content)))
        conn.execute("SET session_replication_role='replica'")
        conn.execute("INSERT INTO pilot_candidate_projections VALUES(%s,%s,%s,%s,%s,%s,%s,%s,1,false,clock_timestamp())",
            (env.tenant,owner,source,candidate,env.profile,env.strategy,version,observation))
        conn.execute("SET session_replication_role='origin'")
    return candidate, version


def test_list_keeps_distinct_comments_unassessed_and_owner_private(seeded):
    from pilot.opportunity_research import OpportunityResearchService
    first, _ = _candidate(seeded, comment="comment-1")
    second, _ = _candidate(seeded, comment="comment-2", body="还需要展台搭建报价")
    _candidate(seeded, comment="private-other", owner=seeded.other)
    service = OpportunityResearchService(seeded.database, supported_platforms=lambda _c: ["web"])
    result = service.list(seeded.claims)
    assert {r["opportunity"]["id"] for r in result["records"]} == {first, second}
    assert all(r["classification"]["category"] == "UNASSESSED" for r in result["records"])
    assert service.list(seeded.other_claims)["records"] != result["records"]
    assert result["accountScope"] == {"id":seeded.tenant,"version":1}


def test_legacy_without_fixed_evidence_is_visible_but_not_bound(seeded):
    from pilot.opportunity_research import OpportunityResearchError, OpportunityResearchService
    source, opportunity = str(uuid4()), str(uuid4())
    with seeded.database.connect() as conn:
        conn.execute("INSERT INTO pilot_sources(source_id,tenant_id,platform,external_id,public_url) VALUES(%s,%s,'PUBLIC_WEB','legacy','https://example.com/legacy')",(source,seeded.tenant))
        conn.execute("INSERT INTO pilot_opportunities(opportunity_id,tenant_id,profile_version_id,source_id,import_key,title,buyer,summary,contact_path,draft_comment,draft_dm) VALUES(%s,%s,%s,%s,'legacy','旧机会','','旧摘要','','','')",
            (opportunity,seeded.tenant,seeded.profile,source))
    service = OpportunityResearchService(seeded.database, supported_platforms=lambda _c: ["web"])
    row = next(r for r in service.list(seeded.claims)["records"] if r["opportunity"]["id"] == opportunity)
    assert row["classification"]["category"] == "UNASSESSED"
    assert "sourceEvidenceVersion" not in row["opportunity"]
    with pytest.raises(OpportunityResearchError, match="evidence_unavailable"):
        service.timeline(seeded.claims, {"userId":seeded.user,"opportunityId":opportunity,
            "profileVersionId":seeded.profile,"sourceUrl":"https://example.com/legacy",
            "evidenceVersion":str(uuid4()),"accountScope":{"id":seeded.tenant,"version":1}})


def test_limit_is_explicit_and_constructor_is_lazy(seeded):
    from pilot.opportunity_research import OpportunityResearchError, OpportunityResearchService
    class Lazy:
        def connect(self):
            raise AssertionError("constructor performed I/O")
    OpportunityResearchService(Lazy(), supported_platforms=())
    service = OpportunityResearchService(seeded.database, supported_platforms=())
    originals = [_candidate(seeded, comment=f"limit-{i}") for i in range(1001)]
    with pytest.raises(OpportunityResearchError, match="record_limit_exceeded") as error:
        service.list(seeded.claims)
    assert error.value.status == 409
    assert len(originals) == 1001


def test_recognized_timeline_and_similar_are_bound_read_only(seeded):
    from pilot.opportunity_evidence import evidence_digest
    from pilot.opportunity_research import OpportunityResearchError, OpportunityResearchService
    candidate, version = _candidate(seeded)
    source, opportunity = str(uuid4()), str(uuid4())
    now = datetime.now(UTC).isoformat()
    with seeded.database.connect() as conn:
        content = conn.execute("SELECT content,source_id FROM pilot_candidate_versions WHERE version_id=%s",(version,)).fetchone()
        candidate_source = conn.execute("SELECT source_identity FROM pilot_candidate_sources WHERE source_id=%s",(content[1],)).fetchone()[0]
        body=content[0]["body"]
        payload={"schema_version":"opportunity-source-evidence-v1","opportunity_id":opportunity,"captured_at":now,
            "source":{"platform":"PUBLIC_WEB","kind":"COMMENT","external_source_id":"post-1","external_comment_id":"comment-1",
                "public_url":"https://example.com/post/1","version_id":version,"content_sha256":hashlib.sha256(json.dumps(content[0],ensure_ascii=False,sort_keys=True,separators=(",", ":")).encode()).hexdigest(),
                "title":None,"container_title":"采购咨询","body":body,"author_public_id":"buyer","published_at":"2026-09-10T00:00:00Z","parent":content[0]["parent"]},
            "observation":{"id":str(uuid4()),"observed_at":now,"received_at":now},
            "assessment":{"id":str(uuid4()),"assessed_at":now,"profile_version_id":seeded.profile,"profile_version":1,
                "strategy_version_id":seeded.strategy,"provider":"synthetic","model":"synthetic","rule_version":"test-v1","rule_sha256":"a"*64,
                "citations":[{"dimension":"intent","field":"source.body","quote":"展台搭建"}],"omitted_profile_citations":0},
            "verification":{"method":"HUMAN_REOPENED","status_at_capture":"OPEN","checked_at":now,"opening_method":"DIRECT","contact_method":"COMMENT"}}
        conn.execute("INSERT INTO pilot_sources(source_id,tenant_id,platform,external_id,public_url,published_at) VALUES(%s,%s,'PUBLIC_WEB',%s,'https://example.com/post/1',%s)",(source,seeded.tenant,'recognized-'+candidate,now))
        conn.execute("INSERT INTO pilot_opportunities(opportunity_id,tenant_id,profile_version_id,source_id,import_key,title,buyer,summary,contact_path,public_excerpt,match_reason,action_signal,value_judgment,risk,reviewed_by,reviewed_at,draft_comment,draft_dm) VALUES(%s,%s,%s,%s,%s,'采购咨询','buyer','明确询价','COMMENT',%s,'匹配展台服务','需要报价','待核价','无',%s,%s::timestamptz,'草稿评论','草稿私信')",
            (opportunity,seeded.tenant,seeded.profile,source,'recognized-'+candidate,body,seeded.user,now))
        conn.execute("SET session_replication_role='replica'")
        conn.execute("INSERT INTO pilot_opportunity_evidence VALUES(%s,%s,%s,'synthetic-include',%s::jsonb,%s)",
            (seeded.tenant,opportunity,seeded.user,json.dumps(payload),evidence_digest(payload)))
        conn.execute("SET session_replication_role='origin'")
    service=OpportunityResearchService(seeded.database,supported_platforms=lambda _c:["PUBLIC_WEB","DOUYIN"])
    before={table:None for table in ("pilot_opportunities","pilot_candidate_versions","pilot_followups")}
    with seeded.database.connect() as conn:
        for table in before: before[table]=conn.execute(f"SELECT count(*) FROM {table} WHERE tenant_id=%s",(seeded.tenant,)).fetchone()[0]
    row=next(r for r in service.list(seeded.claims)["records"] if r["opportunity"]["id"]==opportunity)
    assert row["classification"]["category"]=="OPPORTUNITY"
    binding={"userId":seeded.user,"opportunityId":opportunity,"profileVersionId":seeded.profile,
        "sourceUrl":"https://example.com/post/1","evidenceVersion":version,"accountScope":{"id":seeded.tenant,"version":1}}
    timeline=service.timeline(seeded.claims,binding)
    assert timeline["versions"][-1]["id"]==version and timeline["versions"][-1]["observedAt"] is None
    request=str(uuid4()); first=service.similar(seeded.claims,binding,request); second=service.similar(seeded.claims,binding,request)
    assert first["suggestionId"]==second["suggestionId"]
    assert first["keywords"]==["展台搭建"] and first["supportedPlatforms"]==["web"]
    with pytest.raises(OpportunityResearchError,match="binding_conflict"):
        service.timeline(seeded.claims,binding|{"sourceUrl":"https://example.com/other"})
    with seeded.database.connect() as conn:
        after={table:conn.execute(f"SELECT count(*) FROM {table} WHERE tenant_id=%s",(seeded.tenant,)).fetchone()[0] for table in before}
    assert after==before

    import uvicorn
    from pilot.web import build_app
    class Capabilities:
        @staticmethod
        def capability_check(platform, access, configuration):
            return platform == "PUBLIC_WEB" and access == "PUBLIC_WEB"
    token=issue_token(seeded.user,SECRET)
    app=build_app(type("Store",(),{"database":seeded.database,"sessions":service.sessions})(),
        auth_secret=SECRET,dev_login=True,execution_runtime=Capabilities())
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1",0)); listener.listen(32)
        server=uvicorn.Server(uvicorn.Config(app,log_level="critical",access_log=False,lifespan="off"))
        thread=threading.Thread(target=server.run,kwargs={"sockets":[listener]},daemon=True); thread.start()
        try:
            deadline=time.monotonic()+10
            while not server.started and thread.is_alive() and time.monotonic()<deadline: time.sleep(.02)
            assert server.started
            env={key:value for key,value in os.environ.items()
                if "DATABASE" not in key.upper() and not key.upper().startswith("POSTGRES_")}
            env.update(YIKE_RESEARCH_LIVE_BASE=f"http://127.0.0.1:{listener.getsockname()[1]}",
                YIKE_RESEARCH_LIVE_USER=seeded.user,YIKE_RESEARCH_LIVE_TOKEN=token,
                YIKE_RESEARCH_LIVE_OPPORTUNITY=opportunity)
            node="/Users/xingheimac/.nvm/versions/node/v24.19.0/bin/node"
            child=subprocess.run([node,"node_modules/vitest/vitest.mjs","run",
                "tests/integration/opportunity-research-live.test.ts","--maxWorkers=1"],
                cwd=Path(__file__).parents[1]/"desktop",env=env,capture_output=True,text=True,timeout=40)
            output=(child.stdout+child.stderr).replace(token,"[redacted]")
            assert child.returncode==0,output
            assert "1 passed" in output and "skipped" not in output.lower(),output
        finally:
            server.should_exit=True; thread.join(timeout=10); assert not thread.is_alive()
