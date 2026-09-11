"""Authenticated transport for atomic research starts and recovery."""
from fastapi import HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
import psycopg
from starlette.concurrency import run_in_threadpool

from app.model_contract import strict_json_object
from pilot.auth import TokenClaims
from pilot.execution_api import ExecutionEnvelope
from pilot.execution_contract import ExecutionOperation, ExecutionRuntimeError, canonical_uuid


class ResearchStartEnvelope(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)
    request: ExecutionOperation
    signature: str = Field(min_length=86, max_length=86, repr=False)
    authorization_token: str = Field(min_length=1, max_length=8192, repr=False)

    @model_validator(mode="after")
    def start_only(self):
        if self.request.operation != "START":
            raise ValueError("START required")
        # Reuse the existing canonical signature validation without changing signed bytes.
        ExecutionEnvelope(request=self.request, signature=self.signature)
        return self


def _error(status, code):
    return HTTPException(status, detail={"code": code}, headers={"Cache-Control": "no-store"})


def register_research_execution_api(router, service, identity, require_session_https):
    def authenticate(request):
        require_session_https(request)
        try:
            current = identity(request)
        except psycopg.Error:
            raise _error(503, "capability_unavailable") from None
        if not isinstance(current.claims, TokenClaims):
            raise _error(401, "invalid_session")
        return current.claims

    @router.post("/research-execution/start")
    async def start(request: Request, response: Response):
        claims = await run_in_threadpool(authenticate, request)
        if service is None:
            raise _error(501, "capability_unavailable")
        if request.query_params:
            raise _error(422, "invalid_request")
        if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            raise _error(415, "json_required")
        raw = bytearray()
        async for chunk in request.stream():
            if len(raw) + len(chunk) > 32 * 1024:
                raise _error(413, "request_too_large")
            raw.extend(chunk)
        try:
            value = ResearchStartEnvelope.model_validate(strict_json_object(raw.decode("utf-8", errors="strict")))
            result = await run_in_threadpool(service.start, claims, value.request,
                                             value.signature, value.authorization_token)
        except ExecutionRuntimeError as error:
            raise _error(error.status, error.code) from None
        except (ValueError, TypeError, UnicodeError):
            raise _error(422, "invalid_request") from None
        response.headers["Cache-Control"] = "no-store"
        return result

    @router.get("/research-execution/operations/{request_id}")
    async def receipt(request_id: str, request: Request, response: Response):
        claims = await run_in_threadpool(authenticate, request)
        if service is None:
            raise _error(501, "capability_unavailable")
        if request.query_params:
            raise _error(422, "invalid_request")
        try:
            result = await run_in_threadpool(service.get_receipt, claims, canonical_uuid(request_id))
        except ExecutionRuntimeError as error:
            raise _error(error.status, error.code) from None
        response.headers["Cache-Control"] = "no-store"
        return result
