"""HTTP boundaries on a synthetic service; durable store is tested separately."""
from types import SimpleNamespace
from uuid import uuid4

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from pilot.material_api import register_material_api
from pilot.material_contract import MaterialError


PROFILE = str(uuid4())


class Service:
    def __init__(self):
        self.calls = []

    def list(self, claims, profile):
        self.calls.append(('list', claims, profile))
        return []

    def mutate(self, claims, value):
        self.calls.append(('mutate', claims, value))
        return {'synthetic': True}

    def operation(self, claims, profile, request):
        raise MaterialError('material_operation_not_found', 404)

    def impact(self, claims, profile, material, version, action):
        self.calls.append(('impact', claims, profile, material, version, action))
        return {'references': []}


def client(service):
    app = FastAPI()
    router = APIRouter()
    register_material_api(router, service,
        lambda _: SimpleNamespace(claims='synthetic-claims'), lambda _: None)
    app.include_router(router)
    return TestClient(app)


def test_fixed_routes_and_payload_keep_authenticated_claims_and_raw_dtos():
    service = Service()
    http = client(service)
    assert http.get('/materials', params={'profileVersionId': PROFILE}).json() == []
    body = {'requestId': str(uuid4()), 'profileVersionId': PROFILE, 'change': {
        'kind': 'save', 'materialId': 'local-' + 'a'*64, 'expectedVersion': None,
        'input': {'name': '介绍', 'text': '系统开发', 'purpose': '产品介绍', 'visibility': 'internal'}}}
    assert http.post('/materials/mutate', json=body).json() == {'synthetic': True}
    assert service.calls[-1] == ('mutate', 'synthetic-claims', body)
    assert http.get('/materials/operation', params={
        'profileVersionId': PROFILE, 'requestId': str(uuid4())}).status_code == 404
    assert http.post('/materials/impact', json={'profileVersionId': PROFILE,
        'materialId': 'test', 'version': 1, 'action': 'revoke'}).json() == {'references': []}


def test_untrusted_body_is_bounded_strict_and_not_dispatched():
    service = Service()
    http = client(service)
    assert http.post('/materials/mutate', content=b'x'*(32*1024+1),
        headers={'Content-Type': 'application/json'}).status_code == 413
    assert http.post('/materials/mutate', content='{"requestId":1,"requestId":2}',
        headers={'Content-Type': 'application/json'}).status_code == 422
    assert http.post('/materials/mutate', json={'owner': 'other'}).status_code == 422
    assert http.post('/materials/impact', content='{}').status_code == 415
    assert not service.calls


def test_unavailable_service_does_not_pretend_empty():
    assert client(None).get('/materials', params={'profileVersionId': PROFILE}).status_code == 501
