"""Browser form policy; synthetic invalid passwords never create sessions."""
from fastapi.testclient import TestClient

from pilot.ops_store import OpsError
from pilot.ops_web import build_ops_app


class _ActionErrorStore:
    """Small session/action double for operator error-page contracts."""

    def __init__(self):
        self.token = None

    def session_valid(self, token):
        return token == self.token

    def new_session(self):
        self.token = 'A' * 43
        return self.token

    def logout(self, token):
        self.token = None

    def revoke(self, trial_id):
        raise OpsError('trial_not_found')


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


def test_revoke_state_error_is_actionable_400_not_generic_503():
    store = _ActionErrorStore()
    client = TestClient(build_ops_app(store, password='synthetic-password',
                                      origin='https://ops.example'),
                        base_url='https://ops.example', follow_redirects=False)
    headers = {'Origin': 'https://ops.example'}
    assert client.post('/ops/login', data={'password': 'synthetic-password'},
                       headers=headers).status_code == 303
    page = client.get('/ops/revoke?trial_id=not-a-real-trial')
    assert page.status_code == 200
    import re
    csrf = re.search(r'name="csrf" value="([^"]+)"', page.text)[1]
    response = client.post('/ops/revoke',
                           data={'trial_id': 'not-a-real-trial', 'csrf': csrf},
                           headers=headers)
    assert response.status_code == 400
    assert '无法停用' in response.text
    assert '服务暂不可用' not in response.text
