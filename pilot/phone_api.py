"""Phone login transport; a verified SMS adapter must be supplied separately."""
from typing import Protocol

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from pilot.auth import issue_token
from pilot.phone_auth import PhoneAuthError
from pilot.sessions import authenticate_session


class SmsSender(Protocol):
    def send_code(self, phone: str, code: str) -> bool:
        """True means provider acceptance, never proof of handset delivery.

        Adapters must use a bounded network timeout and must not retry an
        uncertain send. They are trusted dependencies, not request parameters.
        """
        ...


class CodeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    phone: str = Field(min_length=11, max_length=11, pattern=r"^1[0-9]{10}$")


class PhoneSessionInput(CodeInput):
    code: str = Field(min_length=6, max_length=6, pattern=r"^[0-9]{6}$")
    trial_code: str | None = Field(default=None, min_length=8, max_length=128,
                                   pattern=r"^(?:[A-Z0-9]{8}|YK-[A-Za-z0-9_-]{32,})$")


def _unavailable():
    return HTTPException(501, detail={"code": "capability_unavailable",
                                      "message": "该登录能力尚未接通。"})


def _auth_error(error: PhoneAuthError):
    trial_messages = {
        'trial_required': '请展开试用开通，输入管理员发给你的试用码。',
        'trial_invalid': '试用码无效或不属于此手机号，请核对管理员发放的信息。',
        'trial_expired': '试用已到期或已停用，请联系管理员。',
        'trial_already_used': '该账号已激活，请收起试用开通后使用短信验证码登录。',
    }
    if error.code in trial_messages:
        return HTTPException(403, detail={'code':error.code,'message':trial_messages[error.code]})
    if error.code == "auth_rate_limited":
        return HTTPException(429, detail={"code": "auth_rate_limited",
                                          "message": "操作过于频繁，请稍后重试。"})
    return HTTPException(401, detail={"code": "phone_auth_failed",
                                      "message": "验证码无效或已过期，请重新核对。"})


def register_phone_api(router, store, phone_auth, sender: SmsSender | None,
                       auth_secret: str, require_https) -> bool:
    """Register disabled routes too, so missing capability is explicit.

    Normal CLI startup supplies neither dependency. In-process integration
    tests may supply doubles; doing so is not an SMS delivery acceptance gate.
    """
    available = phone_auth is not None and sender is not None

    @router.post("/auth/sms-code")
    def request_code(body: CodeInput, request: Request):
        require_https(request)
        if not available:
            raise _unavailable()
        try:
            reservation = phone_auth.reserve(body.phone, request.client.host if request.client else "")
        except PhoneAuthError as error:
            raise _auth_error(error) from None
        state = "REJECTED"
        if reservation.eligible:
            try:
                accepted = sender.send_code(body.phone, reservation.code)
                state = "ACCEPTED" if accepted is True else "REJECTED" if accepted is False else "UNKNOWN"
            except Exception:
                # Never echo provider errors, restore the cooldown or retry.
                state = "UNKNOWN"
        phone_auth.settle(body.phone, reservation.challenge_id, state)
        # Same shape for unknown numbers. This is a request acknowledgement,
        # not a claim of registration, SMS acceptance or handset delivery.
        return {"retry_after": 60}

    @router.post("/auth/sms-session")
    def login_phone(body: PhoneSessionInput, request: Request):
        require_https(request)
        if not available or (body.trial_code and not callable(getattr(phone_auth, 'consume_trial', None))):
            raise _unavailable()
        try:
            user_id = (phone_auth.consume_trial(body.phone, body.code, body.trial_code)
                       if body.trial_code else phone_auth.consume(body.phone, body.code))
        except PhoneAuthError as error:
            raise _auth_error(error) from None
        token = issue_token(user_id, auth_secret, auth_source='sms')
        # Resolve tenant/session with the normal restricted app connection.
        current = authenticate_session(store, token, auth_secret)
        response = JSONResponse(current.public_view())
        response.set_cookie("pilot_session", token, httponly=True,
                            secure=request.url.scheme == "https", samesite="strict", max_age=3600)
        return response

    return available
