"""Authenticated, bounded material routes; no caller-provided identity."""
from fastapi import HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.model_contract import strict_json_object
from pilot.material_contract import MaterialError, MaterialRequest, MaterialImpactRequest


def register_material_api(router, service, identity, require_session_https):
    def current(request):
        require_session_https(request)
        claims = identity(request).claims
        if claims is None:
            raise HTTPException(401, detail={'code': 'invalid_session'})
        if service is None:
            raise HTTPException(501, detail={'code': 'capability_unavailable'})
        return claims

    async def body(request, model):
        if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
            raise HTTPException(415, detail={'code': 'json_required'})
        raw = bytearray()
        async for chunk in request.stream():
            if len(raw) + len(chunk) > 32 * 1024:
                raise HTTPException(413, detail={'code': 'request_too_large'})
            raw.extend(chunk)
        try:
            return model.model_validate(strict_json_object(raw.decode('utf-8'))).model_dump(exclude_unset=True)
        except (ValueError, TypeError, RecursionError):
            raise HTTPException(422, detail={'code': 'invalid_material_request'}) from None

    async def call(method, *args):
        try:
            return await run_in_threadpool(method, *args)
        except MaterialError as error:
            raise HTTPException(error.status, detail={'code': error.code}) from None

    @router.get('/materials')
    async def materials(request: Request, profileVersionId: str):
        claims = current(request)
        return await call(service.list, claims, profileVersionId)

    @router.post('/materials/mutate')
    async def mutate(request: Request):
        claims = current(request)
        return await call(service.mutate, claims, await body(request, MaterialRequest))

    @router.get('/materials/operation')
    async def operation(request: Request, profileVersionId: str, requestId: str):
        claims = current(request)
        return await call(service.operation, claims, profileVersionId, requestId)

    @router.post('/materials/impact')
    async def impact(request: Request):
        claims = current(request)
        value = await body(request, MaterialImpactRequest)
        return await call(service.impact, claims, value['profileVersionId'], value['materialId'],
                          value['version'], value['action'])
