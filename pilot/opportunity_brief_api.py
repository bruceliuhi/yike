"""Bounded authenticated HTTP facade for the opportunity brief."""
import json

from fastapi import HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool

from pilot.auth import TokenClaims
from pilot.opportunity_brief import OpportunityBriefError, parse_query

MAX_REQUEST_BYTES = 16 * 1024


def _error(status, code):
    return HTTPException(status, detail={"code":code,"message":code}, headers={"Cache-Control":"no-store"})


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result: raise ValueError
        result[key] = value
    return result


async def _body(request):
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise _error(415, "json_required")
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_REQUEST_BYTES: raise _error(413, "request_too_large")
        raw.extend(chunk)
    try:
        value = json.loads(raw.decode(), object_pairs_hook=_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        return parse_query(value)
    except OpportunityBriefError as error:
        raise _error(error.status, error.code) from None
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise _error(422, "invalid_request") from None


def register_opportunity_brief_api(router, service, identity, require_session_https):
    def current(request):
        require_session_https(request)
        session = identity(request)
        if not isinstance(session.claims, TokenClaims): raise _error(401, "invalid_session")
        if service is None: raise _error(501, "capability_unavailable")
        return session.claims

    @router.post("/opportunity-brief/query")
    async def query(request: Request, response: Response):
        claims = await run_in_threadpool(current, request)
        raw = await _body(request)
        try:
            result = await run_in_threadpool(service.query, claims, raw)
        except OpportunityBriefError as error:
            raise _error(error.status, error.code) from None
        response.headers["Cache-Control"] = "no-store"
        return result
