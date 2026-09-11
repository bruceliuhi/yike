"""Authenticated, bounded facade for the structured follow-up workspace."""
import json

from fastapi import HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool

from pilot.auth import TokenClaims
from pilot.followup_service import FollowupError, parse_binding, parse_mutation

MAX_REQUEST_BYTES = 32 * 1024


def _error(status, code):
    return HTTPException(status, detail={"code": code, "message": code}, headers={"Cache-Control": "no-store"})


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError
        result[key] = value
    return result


async def _body(request):
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise _error(415, "json_required")
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_REQUEST_BYTES:
            raise _error(413, "request_too_large")
        raw.extend(chunk)
    try:
        value = json.loads(raw.decode(), object_pairs_hook=_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if type(value) is not dict:
            raise ValueError
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise _error(422, "invalid_request") from None


def register_followup_api(router, service, identity, require_session_https):
    def current(request):
        require_session_https(request)
        session = identity(request)
        if not isinstance(session.claims, TokenClaims):
            raise _error(401, "invalid_session")
        if service is None:
            raise _error(501, "capability_unavailable")
        return session.claims

    def invoke(method, *args):
        try:
            return method(*args)
        except FollowupError as error:
            raise _error(error.status, error.code) from None

    @router.get("/followup-workspace")
    async def workspace(request: Request, response: Response):
        if request.query_params:
            raise _error(422, "invalid_request")
        claims = await run_in_threadpool(current, request)
        response.headers["Cache-Control"] = "no-store"
        return await run_in_threadpool(invoke, service.list, claims)

    @router.get("/followup-workspace/replies")
    async def replies(request: Request, response: Response):
        claims = await run_in_threadpool(current, request)
        if set(request.query_params) - {"opportunityId"} or len(request.query_params.getlist("opportunityId")) > 1:
            raise _error(422, "invalid_request")
        opportunity_id = request.query_params.get("opportunityId")
        response.headers["Cache-Control"] = "no-store"
        return await run_in_threadpool(invoke, service.replies, claims, opportunity_id)

    @router.post("/followup-workspace/mutate")
    async def mutate(request: Request, response: Response):
        claims = await run_in_threadpool(current, request)
        raw = await _body(request)
        try:
            parse_mutation(raw)
        except FollowupError as error:
            raise _error(error.status, error.code) from None
        response.headers["Cache-Control"] = "no-store"
        return await run_in_threadpool(invoke, service.mutate, claims, raw)

    @router.post("/followup-workspace/operation")
    async def operation(request: Request, response: Response):
        claims = await run_in_threadpool(current, request)
        raw = await _body(request)
        try:
            binding = parse_binding(raw)
        except FollowupError as error:
            raise _error(error.status, error.code) from None
        response.headers["Cache-Control"] = "no-store"
        return await run_in_threadpool(invoke, service.operation, claims, binding)
