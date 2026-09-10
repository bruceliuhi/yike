"""Bounded authenticated manual-draft API; no platform execution."""
from fastapi import HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.model_contract import strict_json_object
from pilot.contact_drafts import DraftError, DraftSaveBinding, DraftSaveInput


def register_contact_draft_api(router, service, identity, require_session_https):
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
            if len(raw)+len(chunk)>96*1024:
                raise HTTPException(413, detail={'code':'request_too_large'})
            raw.extend(chunk)
        try:
            return model.model_validate(strict_json_object(raw.decode('utf-8')))
        except (ValueError, TypeError, RecursionError):
            raise HTTPException(422, detail={'code':'invalid_draft_request'}) from None

    async def call(method, *args):
        try:
            return await run_in_threadpool(method, *args)
        except DraftError as error:
            raise HTTPException(error.status, detail={'code':error.code}) from None

    @router.post('/contact-drafts')
    async def save(request: Request):
        claims = current(request)
        value = await body(request, DraftSaveInput)
        return await call(service.save, claims, value.model_dump())

    @router.post('/contact-drafts/operation')
    async def operation(request: Request):
        claims = current(request)
        binding = await body(request, DraftSaveBinding)
        return await call(service.operation, claims, binding.model_dump())

    @router.get('/opportunities/{opportunity_id}/contact-drafts/{channel}')
    async def latest(opportunity_id: str, channel: str, request: Request):
        claims = current(request)
        return await call(service.latest, claims, opportunity_id, channel)
