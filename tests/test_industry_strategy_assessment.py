"""Strategy-to-assessment boundaries; synthetic inputs, no semantic quality claim."""
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading

import httpx
import pytest
from psycopg import sql

from pilot.candidate_assessment_model import AssessmentModelError, OpenAICompatibleCandidateAssessmentModel
from tests.test_candidate_assessment_model import DESCRIPTION, CONTENT, assessment, envelope, internal_client
from tests.test_candidate_review_postgres import (BoundaryModel, databases, env, execution_databases,
    execution_env, raw_databases, raw_env, review_payload, seed, store)


def strategy(**changes):
    return {"version": "industry-task-strategy-v1", "sourceTypes": ["SOCIAL_POST"],
        "intentSignals": ["正在寻找供应商"], "counterSignals": ["同行广告"]} | changes


def test_http_adapter_sends_strategy_verbatim_without_changing_evidence_fields():
    calls = []
    async def handle(request):
        body = json.loads(request.content)
        calls.append(body)
        assert json.loads(body["messages"][1]["content"]) == {
            "description": DESCRIPTION, "content": CONTENT, "industry_strategy": strategy()}
        return httpx.Response(200, json=envelope())
    with internal_client(transport=httpx.MockTransport(handle)) as client:
        model = OpenAICompatibleCandidateAssessmentModel(base_url="https://model.example/v1",
            api_key="synthetic", model="synthetic", http_client=client)
        result, _ = model.assess(description=DESCRIPTION, content=CONTENT, industry_strategy=strategy())
    assert result.model_dump() == assessment() and len(calls) == 1
    assert model.industry_strategy_version == "industry-task-strategy-v1"
    assert all(citation["field"] != "industry_strategy" for name in
        ("businessMatch", "intent", "urgency", "actionability")
        for citation in result.model_dump()[name]["citations"])


def test_legacy_adapter_wire_shape_omits_strategy_instead_of_sending_null():
    seen = {}
    async def handle(request):
        seen.update(json.loads(request.content))
        return httpx.Response(200, json=envelope())
    with internal_client(transport=httpx.MockTransport(handle)) as client:
        model = OpenAICompatibleCandidateAssessmentModel(base_url="https://model.example/v1",
            api_key="synthetic", model="synthetic", http_client=client)
        model.assess(description=DESCRIPTION, content=CONTENT)
    assert json.loads(seen["messages"][1]["content"]) == {"description": DESCRIPTION, "content": CONTENT}


@pytest.mark.parametrize("value", [{}, strategy(authority="APPROVED"),
    strategy(intentSignals=[" 采购需求 ", "采购需求"])])
def test_invalid_strategy_is_rejected_before_network(value):
    calls = []
    async def handle(request):
        calls.append(request)
        return httpx.Response(200, json=envelope())
    with internal_client(transport=httpx.MockTransport(handle)) as client:
        model = OpenAICompatibleCandidateAssessmentModel(base_url="https://model.example/v1",
            api_key="synthetic", model="synthetic", http_client=client)
        kwargs = {"industry_strategy": value}
        with pytest.raises(AssessmentModelError, match="invalid_assessment_input") as raised:
            model.assess(description=DESCRIPTION, content=CONTENT, **kwargs)
        assert raised.value.__context__ is None and raised.value.__cause__ is None
    assert calls == []


def test_model_cannot_cite_strategy_as_source_fact():
    forged = deepcopy(assessment())
    forged["intent"]["citations"][0] = {"field": "industry_strategy.intentSignals", "quote": "正在寻找供应商"}
    from pilot.candidate_assessment_model import validate_assessment
    with pytest.raises(AssessmentModelError, match="invalid_assessment_result"):
        validate_assessment(forged, description=DESCRIPTION, content=CONTENT)


def test_real_worker_sends_strategy_to_controlled_local_http():
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append(json.loads(self.rfile.read(int(self.headers["content-length"]))))
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(json.dumps(envelope()).encode())
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        model = OpenAICompatibleCandidateAssessmentModel(base_url=f"http://127.0.0.1:{server.server_port}/v1",
            api_key="synthetic", model="synthetic")
        assert model.assess(description=DESCRIPTION, content=CONTENT,
            industry_strategy=strategy())[0].model_dump() == assessment()
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)
    assert json.loads(requests[0]["messages"][1]["content"])["industry_strategy"] == strategy()


def test_restricted_pg_passes_confirmed_strategy_and_rejects_client_or_unsupported_model(env):
    with env.admin.connect() as connection:
        connection.execute("SELECT set_config('yike.app_role',%s,true)", (env.db.role,))
        connection.execute((Path(__file__).parents[1] / "deploy/grant_materials.sql").read_text())
    confirmed = strategy()
    env.snapshot["configuration"] = {"query": "synthetic", "industryStrategy": confirmed}
    with env.admin.connect() as connection:
        connection.execute("UPDATE business_profile_versions SET payload=%s::jsonb WHERE profile_version_id=%s",
            (json.dumps({"description": DESCRIPTION, "synthetic_strategy": env.snapshot}), env.profile))
    binding = seed(env)

    class StrategyModel(BoundaryModel):
        industry_strategy_version = "industry-task-strategy-v1"
        def assess(self, *, description, content, industry_strategy=None):
            self.received = deepcopy(industry_strategy)
            industry_strategy["intentSignals"].append("模型侧修改")
            return super().assess(description=description, content=content)

    model = StrategyModel()
    result = store(env, model).review(env.claims, review_payload(binding))
    assert result["kind"] == "assessment" and model.received == confirmed
    assert env.snapshot["configuration"]["industryStrategy"] == confirmed

    unsupported = BoundaryModel()
    with env.admin.connect() as connection:
        reserved_before = connection.execute(
            "SELECT COALESCE(sum(reserved_calls),0) FROM pilot_candidate_call_quota WHERE tenant_id=%s",
            (env.tenant,)).fetchone()[0]
    with pytest.raises(Exception, match="assessment_unavailable"):
        store(env, unsupported).review(env.claims, review_payload(binding))
    assert unsupported.calls == 0
    with env.admin.connect() as connection:
        assert connection.execute(
            "SELECT COALESCE(sum(reserved_calls),0) FROM pilot_candidate_call_quota WHERE tenant_id=%s",
            (env.tenant,)).fetchone()[0] == reserved_before
    with pytest.raises(Exception, match="invalid_request"):
        store(env, model).review(env.claims, review_payload(binding) | {"industryStrategy": strategy()})
