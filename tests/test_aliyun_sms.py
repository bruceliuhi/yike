import json

import pytest
from alibabacloud_dysmsapi20170525.models import (
    SendSmsResponse,
    SendSmsResponseBody,
)
from alibabacloud_tea_openapi.models import Config
from alibabacloud_tea_util.models import RuntimeOptions

from pilot.aliyun_sms import (
    AliyunSmsSender,
    SmsConfigurationError,
    SmsProviderError,
    configured_sms_sender,
)


ENVIRONMENT = {
    "YIKE_SMS_PROVIDER": "aliyun",
    "YIKE_SMS_SIGN_NAME": "approved sign",
    "YIKE_SMS_TEMPLATE_CODE": "SMS_512095645",
    "YIKE_SMS_CODE_PARAMETER": "code",
    "ALIBABA_CLOUD_ACCESS_KEY_ID": "test-access-key-id",
    "ALIBABA_CLOUD_ACCESS_KEY_SECRET": "test-access-key-secret",
}


class CapturingClient:
    def __init__(self, config):
        assert isinstance(config, Config)
        self.config = config
        self.calls = []
        self.response = SendSmsResponse(status_code=200, body=SendSmsResponseBody(code="OK"))

    def send_sms_with_options(self, request, runtime):
        self.calls.append((request, runtime))
        return self.response


def sender(monkeypatch, environment=None):
    clients = []

    def create_client(config):
        client = CapturingClient(config)
        clients.append(client)
        return client

    monkeypatch.setattr("pilot.aliyun_sms.AliyunClient", create_client)
    configured = configured_sms_sender(environment or ENVIRONMENT)
    assert isinstance(configured, AliyunSmsSender)
    return configured, clients[0]


def test_provider_is_disabled_only_when_not_configured():
    assert configured_sms_sender({}) is None
    assert configured_sms_sender({"YIKE_SMS_PROVIDER": ""}) is None


@pytest.mark.parametrize("provider", ["ALIYUN", "unknown", " aliyun"])
def test_unknown_or_noncanonical_provider_fails_closed(provider):
    with pytest.raises(SmsConfigurationError, match="SMS provider configuration is invalid"):
        configured_sms_sender({"YIKE_SMS_PROVIDER": provider})


@pytest.mark.parametrize("missing", sorted(ENVIRONMENT.keys() - {"YIKE_SMS_PROVIDER"}))
def test_aliyun_provider_requires_every_nonoptional_setting(missing):
    environment = ENVIRONMENT | {missing: ""}
    with pytest.raises(SmsConfigurationError, match="SMS provider configuration is incomplete") as caught:
        configured_sms_sender(environment)
    assert missing not in str(caught.value)
    assert "test-access" not in str(caught.value)


@pytest.mark.parametrize(
    ("setting", "invalid"),
    [
        ("YIKE_SMS_SIGN_NAME", " leading"),
        ("YIKE_SMS_SIGN_NAME", "trailing "),
        ("YIKE_SMS_SIGN_NAME", "control\nname"),
        ("YIKE_SMS_SIGN_NAME", "s" * 101),
        ("YIKE_SMS_TEMPLATE_CODE", "512095645"),
        ("YIKE_SMS_TEMPLATE_CODE", "SMS_abc"),
        ("YIKE_SMS_CODE_PARAMETER", "1code"),
        ("YIKE_SMS_CODE_PARAMETER", "code-name"),
        ("YIKE_SMS_CODE_PARAMETER", "c" * 65),
        ("ALIBABA_CLOUD_ACCESS_KEY_ID", "contains space"),
        ("ALIBABA_CLOUD_ACCESS_KEY_ID", "x" * 129),
        ("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "非ASCII"),
        ("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "x" * 257),
    ],
)
def test_aliyun_provider_rejects_malformed_configuration(setting, invalid):
    with pytest.raises(SmsConfigurationError, match="SMS provider configuration is invalid") as caught:
        configured_sms_sender(ENVIRONMENT | {setting: invalid})
    assert invalid not in str(caught.value)


@pytest.mark.parametrize("token", ["has space", "非ASCII", "x" * 2049])
def test_optional_security_token_is_strict_when_present(token):
    with pytest.raises(SmsConfigurationError, match="SMS provider configuration is invalid"):
        configured_sms_sender(ENVIRONMENT | {"ALIBABA_CLOUD_SECURITY_TOKEN": token})


def test_official_sdk_receives_fixed_transport_and_exact_sms_request(monkeypatch):
    configured, client = sender(
        monkeypatch,
        ENVIRONMENT | {"ALIBABA_CLOUD_SECURITY_TOKEN": "test-security-token"},
    )

    assert configured.send_code("13800138000", "012345") is True

    config = client.config
    assert config.endpoint == "dysmsapi.aliyuncs.com"
    assert config.protocol == "HTTPS"
    assert config.connect_timeout == 5000
    assert config.read_timeout == 10000
    assert config.access_key_id == "test-access-key-id"
    assert config.access_key_secret == "test-access-key-secret"
    assert config.security_token == "test-security-token"
    assert config.retry_options.retryable is False
    assert config.retry_options.max_attempts == 1
    assert len(client.calls) == 1
    request, runtime = client.calls[0]
    assert request.phone_numbers == "13800138000"
    assert request.sign_name == "approved sign"
    assert request.template_code == "SMS_512095645"
    assert json.loads(request.template_param) == {"code": "012345"}
    assert request.out_id is None
    assert isinstance(runtime, RuntimeOptions)
    assert runtime.autoretry is False
    assert runtime.max_attempts == 1
    assert runtime.connect_timeout == 5000
    assert runtime.read_timeout == 10000


@pytest.mark.parametrize("phone", ["", "1380013800", "138001380000", "23800138000", "1380013800a", "13800138000,13900139000"])
def test_send_rejects_invalid_or_multiple_phone_numbers_before_sdk(monkeypatch, phone):
    configured, client = sender(monkeypatch)
    with pytest.raises(ValueError, match="invalid SMS phone number"):
        configured.send_code(phone, "012345")
    assert client.calls == []


@pytest.mark.parametrize("code", ["", "12345", "1234567", "１２３４５６", "12345a"])
def test_send_rejects_non_ascii_six_digit_codes_before_sdk(monkeypatch, code):
    configured, client = sender(monkeypatch)
    with pytest.raises(ValueError, match="invalid SMS verification code"):
        configured.send_code("13800138000", code)
    assert client.calls == []


def test_explicit_business_rejection_is_false_and_not_retried(monkeypatch):
    configured, client = sender(monkeypatch)
    client.response = SendSmsResponse(
        status_code=200,
        body=SendSmsResponseBody(code="isv.BUSINESS_LIMIT_CONTROL", message="contains secret"),
    )
    assert configured.send_code("13800138000", "012345") is False
    assert len(client.calls) == 1


@pytest.mark.parametrize(
    "response",
    [None, SendSmsResponse(), SendSmsResponse(body=SendSmsResponseBody()), SendSmsResponse(body=SendSmsResponseBody(code=""))],
)
def test_unknown_or_malformed_response_raises_fixed_sanitized_error(monkeypatch, response):
    configured, client = sender(monkeypatch)
    client.response = response
    with pytest.raises(SmsProviderError, match="SMS provider response is invalid") as caught:
        configured.send_code("13800138000", "012345")
    assert "13800138000" not in str(caught.value)
    assert "012345" not in str(caught.value)
    assert len(client.calls) == 1


@pytest.mark.parametrize(
    "response",
    [
        SendSmsResponse(status_code=500, body=SendSmsResponseBody(code="OK")),
        SendSmsResponse(status_code=200, body=SendSmsResponseBody(code="SUCCESS")),
        SendSmsResponse(status_code=200, body=SendSmsResponseBody(code="garbage")),
        SendSmsResponse(status_code=200, body=SendSmsResponseBody(code="isv.bad-format")),
    ],
)
def test_non_normal_provider_outcomes_are_unknown_not_business_rejections(monkeypatch, response):
    configured, client = sender(monkeypatch)
    client.response = response
    with pytest.raises(SmsProviderError, match="SMS provider response is invalid"):
        configured.send_code("13800138000", "012345")
    assert len(client.calls) == 1


def test_sdk_exception_is_replaced_without_secret_text_or_retry(monkeypatch):
    configured, client = sender(monkeypatch)

    def fail(request, runtime):
        client.calls.append((request, runtime))
        raise RuntimeError("test-access-key-secret 13800138000 012345")

    client.send_sms_with_options = fail
    with pytest.raises(SmsProviderError, match="SMS provider request failed") as caught:
        configured.send_code("13800138000", "012345")
    assert "test-access" not in str(caught.value)
    assert "13800138000" not in str(caught.value)
    assert "012345" not in str(caught.value)
    assert caught.value.__cause__ is None
    assert len(client.calls) == 1


def test_provider_response_accessor_exception_is_sanitized(monkeypatch):
    configured, client = sender(monkeypatch)

    class BrokenResponse:
        @property
        def body(self):
            raise RuntimeError("13800138000 012345 test-access-key-secret")

    client.response = BrokenResponse()
    with pytest.raises(SmsProviderError, match="SMS provider response is invalid") as caught:
        configured.send_code("13800138000", "012345")
    assert "test-access" not in str(caught.value)
    assert "13800138000" not in str(caught.value)
    assert "012345" not in str(caught.value)
    assert caught.value.__cause__ is None
    assert len(client.calls) == 1


def test_sdk_initialization_exception_is_sanitized(monkeypatch):
    def fail(config):
        raise RuntimeError("test-access-key-secret")

    monkeypatch.setattr("pilot.aliyun_sms.AliyunClient", fail)
    with pytest.raises(SmsProviderError, match="SMS provider initialization failed") as caught:
        configured_sms_sender(ENVIRONMENT)
    assert "test-access" not in str(caught.value)
    assert caught.value.__cause__ is None


@pytest.mark.parametrize("debug", ["sdk", "SDK", "sDk"])
def test_configuration_mapping_rejects_sdk_debug_before_client_initialization(
    monkeypatch, capsys, caplog, debug
):
    initialized = []
    monkeypatch.setattr("pilot.aliyun_sms.AliyunClient", lambda config: initialized.append(config))

    with pytest.raises(SmsConfigurationError, match="SMS SDK debug mode is forbidden"):
        configured_sms_sender(ENVIRONMENT | {"DEBUG": debug})

    assert initialized == []
    captured = capsys.readouterr()
    emitted = captured.out + captured.err + caplog.text
    assert "test-access" not in emitted


def test_process_sdk_debug_rejected_before_client_initialization(monkeypatch, capsys, caplog):
    initialized = []
    monkeypatch.setenv("DEBUG", "sdk")
    monkeypatch.setattr("pilot.aliyun_sms.AliyunClient", lambda config: initialized.append(config))

    with pytest.raises(SmsConfigurationError, match="SMS SDK debug mode is forbidden"):
        configured_sms_sender(ENVIRONMENT)

    assert initialized == []
    captured = capsys.readouterr()
    emitted = captured.out + captured.err + caplog.text
    assert "test-access" not in emitted


def test_debug_enabled_after_construction_is_rejected_before_send(monkeypatch, capsys, caplog):
    monkeypatch.delenv("DEBUG", raising=False)
    configured, client = sender(monkeypatch)
    monkeypatch.setenv("DEBUG", "SDK")

    with pytest.raises(SmsConfigurationError, match="SMS SDK debug mode is forbidden"):
        configured.send_code("13800138000", "012345")

    assert client.calls == []
    captured = capsys.readouterr()
    emitted = captured.out + captured.err + caplog.text
    assert "test-access" not in emitted
    assert "13800138000" not in emitted
    assert "012345" not in emitted


def test_sender_repr_does_not_disclose_credentials_or_message_configuration(monkeypatch):
    configured, _ = sender(monkeypatch)
    displayed = repr(configured)
    for secret in ENVIRONMENT.values():
        assert secret not in displayed
