"""Browser form policy; synthetic invalid passwords never create sessions."""
from fastapi.testclient import TestClient

from pilot.ops_web import build_ops_app


def test_ops_pages_preserve_same_origin_form_source():
    client = TestClient(build_ops_app(object(), password='synthetic-password',
                                     origin='https://ops.example'),
                        base_url='https://ops.example')
    response = client.get('/ops/login')
    assert response.headers['referrer-policy'] == 'same-origin'
    assert response.headers['cache-control'] == 'no-store'
    for origin in (None, 'null', 'https://evil.example'):
        headers = {} if origin is None else {'Origin': origin}
        assert client.post('/ops/login', data={'password': 'wrong'},
                           headers=headers).status_code == 403
    assert client.post('/ops/login', data={'password': 'wrong'},
                       headers={'Origin': 'https://ops.example'}).status_code == 401
