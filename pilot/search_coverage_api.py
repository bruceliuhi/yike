"""Authenticated fixed route for the read-only search coverage projection."""
from fastapi import HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.model_contract import strict_json_object
from pilot.search_coverage import SearchCoverageError


def register_search_coverage_api(router, service, identity, require_session_https):
    @router.post("/search-coverage")
    async def query(request: Request):
        require_session_https(request)
        current = await run_in_threadpool(identity, request)
        if current.claims is None:
            raise HTTPException(401, detail={"code": "invalid_session"})
        if service is None:
            raise HTTPException(501, detail={"code": "capability_unavailable"})
        if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            raise HTTPException(415, detail={"code": "json_required"})
        raw = bytearray()
        async for chunk in request.stream():
            if len(raw) + len(chunk) > 32 * 1024:
                raise HTTPException(413, detail={"code": "request_too_large"})
            raw.extend(chunk)
        try:
            body = strict_json_object(raw.decode("utf-8"))
            result = await run_in_threadpool(service.query, current.claims, body)
        except SearchCoverageError as error:
            raise HTTPException(error.status, detail={"code": error.code}) from None
        except (ValueError, UnicodeError, TypeError):
            raise HTTPException(422, detail={"code": "invalid_request"}) from None
        return result
