"""Authenticated reply/follow-up facts facade.

This endpoint records facts supplied by an authorised connector or operator;
it never polls a platform or sends a message.
"""
import json

from fastapi import HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.model_contract import strict_json_object
from pilot.reply_contract import parse_reply_event

MAX_BODY_BYTES = 256 * 1024


async def _body(request: Request):
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise HTTPException(415, detail={"code": "json_required", "message": "请使用JSON请求。"})
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_BODY_BYTES:
            raise HTTPException(413, detail={"code": "request_too_large", "message": "请求正文过长。"})
        raw.extend(chunk)
    try:
        value = strict_json_object(raw.decode("utf-8", errors="strict"))
        json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        return parse_reply_event(value)
    except Exception:
        raise HTTPException(422, detail={"code": "invalid_reply_event", "message": "回复事件格式无效。"}) from None


def register_reply_api(router, service, identity, require_session_https):
    def current(request: Request):
        require_session_https(request)
        session = identity(request)
        if session.claims is None:
            raise HTTPException(401, detail={"code": "invalid_session", "message": "请重新登录。"})
        if service is None:
            raise HTTPException(501, detail={"code": "capability_unavailable", "message": "回复服务尚未接入。"})
        return session.claims

    @router.post("/replies")
    async def record(request: Request):
        claims = current(request)
        event = await _body(request)
        try:
            return await run_in_threadpool(service.record, claims, event)
        except ValueError as error:
            code = getattr(error, "code", "invalid_reply_event")
            status = getattr(error, "status", 409)
            raise HTTPException(status, detail={"code": code, "message": "回复事件未记录。"}) from error

    @router.get("/opportunities/{opportunity_id}/replies")
    def list_replies(opportunity_id: str, request: Request):
        claims = current(request)
        if not opportunity_id.strip() or len(opportunity_id) > 128:
            raise HTTPException(422, detail={"code": "invalid_opportunity_id", "message": "商机标识无效。"})
        return service.list_for_opportunity(claims, opportunity_id)

