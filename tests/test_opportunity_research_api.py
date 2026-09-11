from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from pilot.auth import issue_token, verify_token_claims
from pilot.opportunity_research import OpportunityResearchError
from pilot.opportunity_research_api import register_opportunity_research_api
from pilot.sessions import SessionIdentity


class Service:
    def __init__(self): self.calls=[]
    def list(self,claims): self.calls.append(("list",claims.user_id)); return {"records":[]}
    def timeline(self,claims,binding): self.calls.append(("timeline",binding)); raise OpportunityResearchError("binding_conflict",409)
    def similar(self,claims,binding,request): self.calls.append(("similar",binding,request)); return {"eligible":False}


def client():
    app=FastAPI(); router=APIRouter(prefix="/api/ui"); service=Service()
    claims=verify_token_claims(issue_token("user-1","secret"),"secret")
    identity=lambda _r: SessionIdentity("user-1","tenant-1",claims)
    register_opportunity_research_api(router,service,identity,lambda _r: None)
    app.include_router(router)
    return TestClient(app),service


def test_routes_are_no_store_strict_and_map_safe_errors():
    http,service=client()
    listed=http.get("/api/ui/opportunity-research")
    assert listed.status_code==200 and listed.headers["cache-control"]=="no-store"
    invalid=http.post("/api/ui/opportunity-research/timeline",json={"binding":{},"extra":"private"})
    assert invalid.status_code==422 and service.calls==[("list","user-1")]
    conflict=http.post("/api/ui/opportunity-research/timeline",json={"binding":{}})
    assert conflict.status_code==409 and conflict.json()["detail"]=={"code":"binding_conflict","message":"binding_conflict"}
    assert conflict.headers["cache-control"]=="no-store"


def test_similar_is_a_read_preview_with_exact_body():
    http,service=client()
    response=http.post("/api/ui/opportunity-research/similar",json={"binding":{"x":"y"},"requestId":"request"})
    assert response.status_code==200 and response.json()=={"eligible":False}
    assert service.calls==[("similar",{"x":"y"},"request")]
    assert response.headers["cache-control"]=="no-store"
