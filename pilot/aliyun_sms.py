"""Aliyun SMS adapter for provider-accepted one-time verification codes."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping

_ENDPOINT = "dysmsapi.aliyuncs.com"
_PHONE_PATTERN = re.compile(r"1[0-9]{10}\Z", re.ASCII)
_CODE_PATTERN = re.compile(r"[0-9]{6}\Z", re.ASCII)
_TEMPLATE_PATTERN = re.compile(r"SMS_[0-9]{1,60}\Z", re.ASCII)
_PARAMETER_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}\Z", re.ASCII)
_BUSINESS_REJECTION_PATTERN = re.compile(r"isv\.[A-Z][A-Z0-9_]{1,127}\Z", re.ASCII)
_REQUIRED_ENVIRONMENT = (
    "YIKE_SMS_SIGN_NAME",
    "YIKE_SMS_TEMPLATE_CODE",
    "YIKE_SMS_CODE_PARAMETER",
    "ALIBABA_CLOUD_ACCESS_KEY_ID",
    "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
)


class SmsConfigurationError(RuntimeError):
    """Raised with a fixed message when private provider configuration is invalid."""


class SmsProviderError(RuntimeError):
    """Raised with a fixed message when provider outcome is unknown."""


def _is_bounded_ascii_secret(value: str, maximum: int) -> bool:
    return isinstance(value, str) and 1 <= len(value) <= maximum and all("!" <= char <= "~" for char in value)


def _is_sign_name(value: str) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 100
        and value == value.strip()
        and all(char >= " " and char != "\x7f" for char in value)
    )


def _reject_sdk_debug(value: object) -> None:
    if isinstance(value, str) and value.casefold() == "sdk":
        raise SmsConfigurationError("SMS SDK debug mode is forbidden")


class AliyunSmsSender:
    """Send a single SMS through the official Aliyun SDK without automatic retry."""

    __slots__ = ("_client", "_runtime", "_sign_name", "_template_code", "_code_parameter")

    def __init__(
        self,
        *,
        access_key_id: str,
        access_key_secret: str,
        security_token: str | None,
        sign_name: str,
        template_code: str,
        code_parameter: str,
    ) -> None:
        # Keep the provider SDK optional for ordinary customer runtimes. It
        # is imported only when the deployment explicitly enables Aliyun SMS;
        # missing SDK/configuration must remain the documented 501 path.
        try:
            from alibabacloud_dysmsapi20170525.client import Client as AliyunClient
            from alibabacloud_dysmsapi20170525.models import SendSmsRequest
            from alibabacloud_tea_openapi.models import Config
            from alibabacloud_tea_util.models import RuntimeOptions
            from darabonba.policy.retry import RetryOptions
        except ImportError:
            raise SmsConfigurationError("SMS provider SDK is unavailable") from None
        _reject_sdk_debug(os.environ.get("DEBUG"))
        values = (access_key_id, access_key_secret, sign_name, template_code, code_parameter)
        if any(not isinstance(value, str) or not value for value in values):
            raise SmsConfigurationError("SMS provider configuration is incomplete")
        valid = (
            _is_bounded_ascii_secret(access_key_id, 128)
            and _is_bounded_ascii_secret(access_key_secret, 256)
            and _is_sign_name(sign_name)
            and _TEMPLATE_PATTERN.fullmatch(template_code) is not None
            and _PARAMETER_PATTERN.fullmatch(code_parameter) is not None
            and (
                security_token is None
                or _is_bounded_ascii_secret(security_token, 2048)
            )
        )
        if not valid:
            raise SmsConfigurationError("SMS provider configuration is invalid")

        config = Config(
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
            security_token=security_token,
            endpoint=_ENDPOINT,
            protocol="HTTPS",
            connect_timeout=5000,
            read_timeout=10000,
            retry_options=RetryOptions(retryable=False, maxAttempts=1),
        )
        try:
            self._client = AliyunClient(config)
        except Exception:
            raise SmsProviderError("SMS provider initialization failed") from None
        self._runtime = RuntimeOptions(
            autoretry=False,
            max_attempts=1,
            connect_timeout=5000,
            read_timeout=10000,
        )
        self._sign_name = sign_name
        self._template_code = template_code
        self._code_parameter = code_parameter

    def __repr__(self) -> str:
        return "AliyunSmsSender(configured=True)"

    def send_code(self, phone: str, code: str) -> bool:
        from alibabacloud_dysmsapi20170525.models import SendSmsRequest

        _reject_sdk_debug(os.environ.get("DEBUG"))
        if not isinstance(phone, str) or _PHONE_PATTERN.fullmatch(phone) is None:
            raise ValueError("invalid SMS phone number")
        if not isinstance(code, str) or _CODE_PATTERN.fullmatch(code) is None:
            raise ValueError("invalid SMS verification code")

        request = SendSmsRequest(
            phone_numbers=phone,
            sign_name=self._sign_name,
            template_code=self._template_code,
            template_param=json.dumps(
                {self._code_parameter: code}, ensure_ascii=True, separators=(",", ":")
            ),
        )
        try:
            response = self._client.send_sms_with_options(request, self._runtime)
        except Exception:
            raise SmsProviderError("SMS provider request failed") from None

        try:
            status_code = getattr(response, "status_code", None)
            body = getattr(response, "body", None)
            provider_code = getattr(body, "code", None)
        except Exception:
            raise SmsProviderError("SMS provider response is invalid") from None
        if type(status_code) is not int or status_code != 200 or not isinstance(provider_code, str):
            raise SmsProviderError("SMS provider response is invalid")
        if provider_code == "OK":
            return True
        if _BUSINESS_REJECTION_PATTERN.fullmatch(provider_code) is not None:
            return False
        raise SmsProviderError("SMS provider response is invalid")


def configured_sms_sender(environment: Mapping[str, str]) -> AliyunSmsSender | None:
    """Build the sender only for a complete, explicitly enabled provider."""

    provider = environment.get("YIKE_SMS_PROVIDER")
    if provider is None or provider == "":
        return None
    _reject_sdk_debug(environment.get("DEBUG"))
    _reject_sdk_debug(os.environ.get("DEBUG"))
    if provider != "aliyun":
        raise SmsConfigurationError("SMS provider configuration is invalid")
    if any(
        not isinstance(environment.get(name), str) or not environment.get(name)
        for name in _REQUIRED_ENVIRONMENT
    ):
        raise SmsConfigurationError("SMS provider configuration is incomplete")

    security_token = environment.get("ALIBABA_CLOUD_SECURITY_TOKEN") or None
    return AliyunSmsSender(
        access_key_id=environment["ALIBABA_CLOUD_ACCESS_KEY_ID"],
        access_key_secret=environment["ALIBABA_CLOUD_ACCESS_KEY_SECRET"],
        security_token=security_token,
        sign_name=environment["YIKE_SMS_SIGN_NAME"],
        template_code=environment["YIKE_SMS_TEMPLATE_CODE"],
        code_parameter=environment["YIKE_SMS_CODE_PARAMETER"],
    )
