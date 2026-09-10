"""Authenticated reply/follow-up facts facade.

This endpoint records facts supplied by an authorised connector or operator;
it never polls a platform or sends a message.
"""
import json

from fastapi import HTTPException, Request
from starlette.concurrency import run_in_threadpool
from pydantic import Field, field_validator

from app.model_contract import strict_json_object
from pilot.reply_contract import parse_reply_event
from pilot.reply_store import ReplyStoreError
from pilot.contact_drafts import _Input, DraftError
from pilot.execution_contract import ExecutionRuntimeError
from pilot.device_keys import decode_canonical
from pilot.signed_replies import SignedReplyRequest, ReplySyncContextRequest

MAX_BODY_BYTES = 256 * 1024


class ReplyPreparation(_Input):
    request: SignedReplyRequest


class ReplyEnvelope(ReplyPreparation):
    signature: str = Field(min_length=86,max_length=86,repr=False)

    @field_validator('signature')
    @classmethod
    def valid_signature(cls,value):
        decode_canonical(value,64)
        return value


async def _body(request: Request, model=None):
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
        return parse_reply_event(value) if model is None else model.model_validate(value)
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

    def signed_service():
        signed=getattr(service,'signed',None)
        if signed is None:
            raise HTTPException(501,detail={'code':'capability_unavailable'})
        return signed

    async def signed_call(method,*args):
        try:
            return await run_in_threadpool(method,*args)
        except (ReplyStoreError,DraftError,ExecutionRuntimeError) as error:
            raise HTTPException(error.status,detail={'code':error.code}) from None
        except ValueError:
            raise HTTPException(422,detail={'code':'invalid_reply_request'}) from None

    @router.post('/replies/signing-payload')
    async def prepare_signed_reply(request: Request):
        claims=current(request)
        signed=signed_service()
        value=await _body(request,ReplyPreparation)
        return await signed_call(signed.prepare,claims,value.request.model_dump())

    @router.post('/replies/signed')
    async def signed_reply(request: Request):
        claims=current(request)
        signed=signed_service()
        value=await _body(request,ReplyEnvelope)
        return await signed_call(signed.record,claims,value.request.model_dump(),value.signature)

    @router.post('/replies/sync-context')
    async def reply_sync_context(request: Request):
        claims=current(request)
        value=await _body(request,ReplySyncContextRequest)
        return await signed_call(signed_service().sync_context,claims,value.model_dump())

    @router.get('/opportunities/{opportunity_id}/replies/evidence')
    async def reply_evidence(opportunity_id: str,request: Request):
        claims=current(request)
        return await signed_call(signed_service().list_evidence,claims,opportunity_id)

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
