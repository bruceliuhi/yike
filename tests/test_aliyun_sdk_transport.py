"""Exercise installed official SDK signing/serialization without external network."""
import io
import json
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

from pilot.aliyun_sms import configured_sms_sender, SmsProviderError
from tests.test_aliyun_runtime import environment


@pytest.mark.parametrize('timeout', [False, True])
def test_real_sdk_uses_fixed_https_signed_single_attempt(monkeypatch, timeout):
    sent = []

    def send(self, request, **kwargs):
        sent.append(request)
        url = urlsplit(request.url)
        assert url.scheme == 'https' and url.netloc == 'dysmsapi.aliyuncs.com'
        assert request.method == 'POST'
        params = parse_qs(url.query)
        assert params['PhoneNumbers'] == ['19900000001']
        assert json.loads(params['TemplateParam'][0]) == {'code': '012345'}
        assert request.headers['x-acs-action'] == 'SendSms'
        assert request.headers['Authorization'].startswith('ACS3-HMAC-SHA256 ')
        assert kwargs['timeout'] == (5, 10) and kwargs['verify'] is True
        if timeout:
            raise requests.exceptions.ReadTimeout('synthetic-private-error')
        response = requests.Response()
        response.status_code = 200
        response.headers['Content-Type'] = 'application/json'
        response._content = b'{"Code":"OK","RequestId":"synthetic-request"}'
        response.raw = io.BytesIO(response._content)
        return response

    monkeypatch.setattr(requests.Session, 'send', send)
    sender = configured_sms_sender(environment())
    if timeout:
        with pytest.raises(SmsProviderError, match='SMS provider request failed'):
            sender.send_code('19900000001', '012345')
    else:
        assert sender.send_code('19900000001', '012345') is True
    assert len(sent) == 1
