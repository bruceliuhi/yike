"""Bounded queue API. No signature, login state or channel secrets are retained."""
from fastapi import HTTPException, Request
from pydantic import Field, field_validator
from starlette.concurrency import run_in_threadpool

from app.model_contract import strict_json_object
from pilot.contact_drafts import _Input, DraftError
from pilot.device_keys import decode_canonical
from pilot.execution_contract import ExecutionRuntimeError
from pilot.connection_versions import ConnectionOperationError
from pilot.outreach_queue import Confirmation
from pilot.outreach_dispatch import DispatchRequest


class Preparation(_Input):
    request: Confirmation


class Envelope(Preparation):
    signature: str = Field(min_length=86, max_length=86, repr=False)

    @field_validator('signature')
    @classmethod
    def canonical_signature(cls, value):
        decode_canonical(value, 64)
        return value


class DispatchPreparation(_Input):
    request: DispatchRequest


class DispatchEnvelope(Envelope):
    request: DispatchRequest


def register_outreach_queue_api(router, service, identity, require_session_https):
    def current(request):
        require_session_https(request)
        claims = identity(request).claims
        if claims is None:
            raise HTTPException(401, detail={'code':'invalid_session'})
        if service is None:
            raise HTTPException(501, detail={'code':'capability_unavailable'})
        return claims

    async def body(request, model):
        if request.headers.get('content-type','').split(';')[0].strip().lower() != 'application/json':
            raise HTTPException(415, detail={'code':'json_required'})
        raw = bytearray()
        async for chunk in request.stream():
            if len(raw)+len(chunk)>16*1024:
                raise HTTPException(413, detail={'code':'request_too_large'})
            raw.extend(chunk)
        try:
            return model.model_validate(strict_json_object(raw.decode('utf-8')))
        except (ValueError, TypeError, RecursionError):
            raise HTTPException(422, detail={'code':'invalid_confirmation'}) from None

    async def call(method, *args):
        try:
            return await run_in_threadpool(method, *args)
        except (DraftError, ExecutionRuntimeError, ConnectionOperationError) as error:
            raise HTTPException(error.status, detail={'code':error.code}) from None
        except ValueError:
            raise HTTPException(422, detail={'code':'invalid_confirmation'}) from None

    @router.post('/outreach/signing-payload')
    async def prepare(request: Request):
        claims = current(request)
        value = await body(request, Preparation)
        return await call(service.prepare, claims, value.request.model_dump())

    @router.post('/outreach/queue')
    async def confirm(request: Request):
        claims = current(request)
        value = await body(request, Envelope)
        return await call(service.confirm, claims, value.request.model_dump(), value.signature)

    @router.get('/outreach/queue/{request_id}')
    async def original(request_id: str, request: Request):
        return await call(service.original if service else None, current(request), request_id)

    @router.post('/outreach/queue/{request_id}/cancel')
    async def cancel(request_id: str, request: Request):
        return await call(service.original if service else None, current(request), request_id, True)

    @router.post('/outreach/dispatch/signing-payload')
    async def prepare_dispatch(request: Request):
        claims = current(request)
        value = await body(request, DispatchPreparation)
        return await call(service.dispatch.prepare, claims, value.request.model_dump())

    @router.post('/outreach/dispatch')
    async def dispatch(request: Request):
        claims = current(request)
        value = await body(request, DispatchEnvelope)
        return await call(service.dispatch.apply, claims, value.request.model_dump(), value.signature)
