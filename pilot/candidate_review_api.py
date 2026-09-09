"""Authenticated P07 facade. Reading a request never starts model/review work."""
import json
import re

from fastapi import HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.model_contract import strict_json_object
from pilot.device_keys import uuid_string
from pilot.source_capabilities import resolve_platform

MAX_BODY_BYTES = 64 * 1024
_REQUEST = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_INTEGER = re.compile(r"[1-9][0-9]{0,8}\Z")
_BINDING = {"candidateId", "candidateRevision", "sourceVersionId", "profileId", "profileVersion", "requestId"}
_REVIEW_FIELDS = _BINDING | {"action", "assessmentId", "evidence", "reason", "humanConfirmed", "sourceVerificationId", "retryOf"}
_SOURCE_FIELDS = _BINDING | {"humanConfirmed", "status", "openingMethod", "locator", "excerpt", "contactMethod"}


def _invalid():
    return HTTPException(422, detail={"code": "invalid_request", "message": "请求字段无效。"})


def _request_id(value):
    if not _REQUEST.fullmatch(value):
        raise _invalid()


async def _body(request, *, verification):
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise HTTPException(415, detail={"code": "json_required", "message": "请使用JSON请求。"})
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_BODY_BYTES:
            raise HTTPException(413, detail={"code": "request_too_large", "message": "请求正文过长。"})
        raw.extend(chunk)
    try:
        value = strict_json_object(raw.decode("utf-8", errors="strict"))
        # Reject overflowing JSON exponents and escaped lone surrogates before
        # the domain sees a payload; don't normalize the caller's actual values.
        json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        allowed = _SOURCE_FIELDS if verification else _REVIEW_FIELDS
        if set(value) - allowed or (not verification and value.get("action") not in ("ASSESS", "INCLUDE", "EXCLUDE")):
            raise ValueError("invalid fields")
    except (ValueError, UnicodeError, RecursionError):
        raise _invalid() from None
    return value  # Preserve raw types: domain validation must not coerce them.


def register_candidate_review_api(router, service, identity, require_session_https):
    def current(request):
        require_session_https(request)
        session = identity(request)
        if session.claims is None:
            raise HTTPException(401, detail={"code": "invalid_session", "message": "请重新登录。"})
        if service is None:
            raise HTTPException(501, detail={"code": "capability_unavailable", "message": "候选判断与复核服务尚未接入，当前操作未执行。"})
        return session.claims

    @router.post("/candidate-reviews")
    async def review(request: Request):
        claims = await run_in_threadpool(current, request)
        payload = await _body(request, verification=False)
        return await run_in_threadpool(service.review, claims, payload)

    @router.post("/candidate-source-verifications")
    async def verify_source(request: Request):
        claims = await run_in_threadpool(current, request)
        payload = await _body(request, verification=True)
        return await run_in_threadpool(service.verify_source, claims, payload)

    @router.get("/candidate-review-requests/{request_id}")
    def receipt(request_id: str, request: Request):
        claims = current(request)
        _request_id(request_id)
        return service.get_request(claims, request_id)

    @router.get("/candidates")
    def candidates(request: Request):
        claims = current(request)
        query = request.query_params
        if (set(query) - {"query", "platform", "status", "ids", "reviewRequestId", "page", "pageSize"}
                or any(len(query.getlist(key)) != 1 for key in query)):
            raise _invalid()
        page, size = query.get("page", "1"), query.get("pageSize", "20")
        if not _INTEGER.fullmatch(page) or not _INTEGER.fullmatch(size) or int(size) > 100:
            raise _invalid()
        text, platform, status = query.get("query"), query.get("platform"), query.get("status")
        if text is not None and (not text.strip() or len(text) > 200):
            raise _invalid()
        if platform is not None:
            try:
                resolve_platform(platform, namespace="service")
            except ValueError:
                raise _invalid() from None
        if status is not None and status not in ("PENDING_REVIEW", "IMPORTED", "EXCLUDED", "DUPLICATE"):
            raise _invalid()
        ids = query["ids"].split(",") if "ids" in query else None
        if ids is not None:
            if not 1 <= len(ids) <= 100 or len(set(ids)) != len(ids):
                raise _invalid()
            for candidate_id in ids:
                uuid_string(candidate_id)
        original = query.get("reviewRequestId")
        if original is not None:
            _request_id(original)
            if ids is None or len(ids) != 1 or page != "1" or size != "1":
                raise _invalid()
        return service.list_candidates(claims, query=text, platform=platform, status=status,
            ids=ids, review_request_id=original, page=int(page), page_size=int(size))
