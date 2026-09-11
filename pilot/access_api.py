"""Temporary invitation login transport, reusing the existing session cookie."""
import time

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from pilot.access_auth import AccessAuthError
from pilot.auth import issue_token
from pilot.sessions import authenticate_session


class AccessSessionInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    access_code: str = Field(max_length=128)


def register_access_api(router, store, access_auth, auth_secret, require_https):
    @router.post('/auth/access-session')
    def login(body: AccessSessionInput, request: Request):
        require_https(request)
        if access_auth is None:
            raise HTTPException(501, detail={'code':'capability_unavailable','message':'临时访问登录尚未接通。'})
        try:
            user = access_auth.authenticate(body.access_code, request.client.host if request.client else '')
            now = int(time.time())
            ttl = min(72*3600, int(user.expires_at.timestamp())-now)
            if ttl <= 0:
                raise AccessAuthError()
            token = issue_token(user.user_id, auth_secret, now=now, ttl_seconds=ttl, auth_source='temporary_access')
            current = authenticate_session(store, token, auth_secret)
        except (AccessAuthError, PermissionError) as error:
            limited = isinstance(error, AccessAuthError) and error.code == 'auth_rate_limited'
            raise HTTPException(429 if limited else 401, detail={
                'code':'auth_rate_limited' if limited else 'access_auth_failed',
                'message':'尝试过于频繁，请稍后重试。' if limited else '访问码无效、已到期或已停用。',
            }) from None
        response = JSONResponse(current.public_view())
        response.set_cookie('pilot_session',token,httponly=True,secure=True,samesite='strict',max_age=ttl)
        return response

    return access_auth is not None
