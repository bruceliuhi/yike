"""Real runtime composition; provider delivery is deliberately not exercised."""
import socket

import pytest
from fastapi.testclient import TestClient

from pilot.runtime import build_runtime_app


def environment():
    return {
        'YIKE_SMS_PROVIDER': 'aliyun',
        'YIKE_SMS_SIGN_NAME': '合成测试签名',
        'YIKE_SMS_TEMPLATE_CODE': 'SMS_123456789',
        'YIKE_SMS_CODE_PARAMETER': 'code',
        'ALIBABA_CLOUD_ACCESS_KEY_ID': 'synthetic-access-id',
        'ALIBABA_CLOUD_ACCESS_KEY_SECRET': 'synthetic-access-secret',
        'YIKE_PILOT_PHONE_AUTH_SECRET': 'synthetic-phone-auth-secret-32-characters',
    }


def test_complete_aliyun_configuration_enables_real_runtime_route_without_sending(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('assembling the runtime must not send SMS')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    app = build_runtime_app(object(), auth_secret='synthetic-secret', environment=environment())
    with TestClient(app, base_url='https://pilot.example') as client:
        capabilities = client.get('/api/ui/capabilities').json()['capabilities']
    assert capabilities['sms_login'] == {'available': True}


def test_enabled_provider_requires_separate_phone_auth_secret():
    env = environment()
    del env['YIKE_PILOT_PHONE_AUTH_SECRET']
    with pytest.raises(RuntimeError, match='phone_auth_configuration_required'):
        build_runtime_app(object(), auth_secret='synthetic-secret', environment=env)


def test_explicit_provider_cannot_silently_override_injected_sender():
    with pytest.raises(RuntimeError, match='conflicting_sms_configuration'):
        build_runtime_app(object(), auth_secret='synthetic-secret', environment=environment(), sms_sender=object())
