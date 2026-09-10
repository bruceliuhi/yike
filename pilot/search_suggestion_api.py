"""Authenticated HTTP facade for explicit-consent search suggestions."""
from __future__ import annotations

import json
from uuid import UUID

from fastapi import HTTPException, Request, Response
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from pilot.auth import TokenClaims
from pilot.search_suggestion_service import SearchSuggestionServiceError, Submission
from pilot.search_suggestions import SearchSuggestionStoreError

MAX_REQUEST_BYTES = 32 * 1024


def _error(status, code):
    return HTTPException(status, detail={"code": code, "message": code}, headers={"Cache-Control": "no-store"})


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate")
        value[key] = item
    return value


async def _body(request):
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise _error(415, "json_required")
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_REQUEST_BYTES:
            raise _error(413, "request_too_large")
        raw.extend(chunk)
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                           parse_constant=lambda value: (_ for _ in ()).throw(ValueError("number")))
        return Submission.model_validate(value).model_dump()
    except (UnicodeError, ValueError, TypeError, ValidationError, RecursionError):
        raise _error(422, "invalid_request") from None


def _uuid(value):
    try:
        if type(value) is not str or len(value) != 36 or str(UUID(value)) != value:
            raise ValueError()
        return value
    except (ValueError, TypeError, AttributeError):
        raise _error(422, "invalid_request") from None


def register_search_suggestion_api(router, service, identity, require_session_https):
    def current(request, *, query=True):
        require_session_https(request)
        session = identity(request)
        if not isinstance(session.claims, TokenClaims):
            raise _error(401, "invalid_session")
        if service is None:
            raise _error(501, "capability_unavailable")
        if not query and request.query_params:
            raise _error(422, "invalid_request")
        return session.claims

    def invoke(method, *args):
        try:
            return method(*args)
        except (SearchSuggestionServiceError, SearchSuggestionStoreError) as error:
            status, code = error.status, error.code
        raise _error(status, code)

    @router.get("/search-suggestions/preview")
    async def preview(request: Request, response: Response):
        claims = await run_in_threadpool(current, request)
        query = request.query_params
        if set(query) != {"profileVersionId"} or len(query.getlist("profileVersionId")) != 1:
            raise _error(422, "invalid_request")
        response.headers["Cache-Control"] = "no-store"
        return await run_in_threadpool(invoke, service.preview, claims, _uuid(query["profileVersionId"]))

    @router.post("/search-suggestions")
    async def submit(request: Request, response: Response):
        claims = await run_in_threadpool(current, request, query=False)
        payload = await _body(request)
        response.headers["Cache-Control"] = "no-store"
        return await run_in_threadpool(invoke, service.submit, claims, payload)

    @router.get("/search-suggestions/{request_id}")
    async def receipt(request_id: str, request: Request, response: Response):
        claims = await run_in_threadpool(current, request, query=False)
        response.headers["Cache-Control"] = "no-store"
        return await run_in_threadpool(invoke, service.get_receipt, claims, _uuid(request_id))
