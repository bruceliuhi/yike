"""Authenticated HTTP facade for confirmed research usage quotations."""
from fastapi import HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool

from app.model_contract import strict_json_object
from pilot.auth import TokenClaims
from pilot.research_quote import ResearchQuoteError


def _error(status, code):
    return HTTPException(status, detail={"code": code}, headers={"Cache-Control": "no-store"})


def register_research_quote_api(router, service, identity, require_session_https):
    @router.post("/research-usage/quote")
    async def quote(request: Request, response: Response):
        require_session_https(request)
        current = await run_in_threadpool(identity, request)
        if not isinstance(current.claims, TokenClaims):
            raise _error(401, "invalid_session")
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
            body = strict_json_object(raw.decode("utf-8", errors="strict"))
            result = await run_in_threadpool(service.quote, current.claims, body)
        except ResearchQuoteError as error:
            raise _error(error.status, error.code) from None
        except (ValueError, TypeError, UnicodeError):
            raise _error(422, "invalid_request") from None
        response.headers["Cache-Control"] = "no-store"
        return result
