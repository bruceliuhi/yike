"""Real restricted database/runtime + SDK boundary double, never real SMS."""
import json

from fastapi.testclient import TestClient

from tests.test_ops_trials import databases, env, SECRET  # noqa: F401 - shared isolated PG fixtures
from tests.test_aliyun_runtime import environment


def test_aliyun_runtime_request_otp_trial_activation_and_revoked_session(env, monkeypatch, caplog):
    from alibabacloud_dysmsapi20170525.client import Client
    from alibabacloud_dysmsapi20170525.models import SendSmsResponse, SendSmsResponseBody
    from pilot.runtime import build_runtime_app
    _, appdb, ops, _, phone, invite = env
    requests = []

    def accepted(self, request, runtime):
        requests.append(request)
        assert request.phone_numbers == phone
        assert runtime.autoretry is False
        return SendSmsResponse(status_code=200, body=SendSmsResponseBody(code='OK', request_id='synthetic-request'))

    monkeypatch.setattr(Client, 'send_sms_with_options', accepted)
    config = environment() | {'YIKE_PILOT_PHONE_AUTH_SECRET': SECRET.decode()}
    app = build_runtime_app(appdb, auth_secret='synthetic-session', environment=config)
    with TestClient(app, base_url='https://pilot.example') as client:
        assert not requests
        assert client.post('/api/ui/auth/sms-code', json={'phone': phone}).status_code == 200
        assert len(requests) == 1
        code = json.loads(requests[0].template_param)['code']
        login = client.post('/api/ui/auth/sms-session', json={'phone':phone, 'code':code, 'trial_code':invite['code']})
        assert login.status_code == 200
        assert login.json()['user_id'] == invite['user_id']
        assert client.get('/api/ui/profiles').status_code == 200
        ops.revoke(invite['trial_id'])
        assert client.get('/api/ui/session').status_code == 401
        assert len(requests) == 1
    for sensitive in (phone, code, invite['code'], config['ALIBABA_CLOUD_ACCESS_KEY_SECRET']):
        assert sensitive not in caplog.text
