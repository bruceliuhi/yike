"""Authenticated bounded HTTP facade for read-only opportunity research."""
from __future__ import annotations

import json

from fastapi import HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool

from pilot.auth import TokenClaims
from pilot.opportunity_research import OpportunityResearchError


MAX_REQUEST_BYTES = 32 * 1024


def _error(status,code):
    return HTTPException(status,detail={"code":code,"message":code},headers={"Cache-Control":"no-store"})


def _pairs(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise ValueError
        result[key]=value
    return result


async def _body(request,fields):
    if request.headers.get("content-type","").split(";",1)[0].strip().lower()!="application/json":
        raise _error(415,"json_required")
    raw=bytearray()
    async for chunk in request.stream():
        if len(raw)+len(chunk)>MAX_REQUEST_BYTES: raise _error(413,"request_too_large")
        raw.extend(chunk)
    try:
        value=json.loads(raw.decode("utf-8"),object_pairs_hook=_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if type(value) is not dict or set(value)!=fields: raise ValueError
        json.dumps(value,ensure_ascii=False,allow_nan=False).encode()
        return value
    except (ValueError,TypeError,UnicodeError,RecursionError):
        raise _error(422,"invalid_request") from None


def register_opportunity_research_api(router,service,identity,require_session_https):
    def current(request):
        require_session_https(request)
        session=identity(request)
        if not isinstance(session.claims,TokenClaims): raise _error(401,"invalid_session")
        if service is None: raise _error(501,"capability_unavailable")
        if request.query_params: raise _error(422,"invalid_request")
        return session.claims

    def invoke(method,*args):
        try:
            return method(*args)
        except OpportunityResearchError as error:
            status,code=error.status,error.code
        raise _error(status,code)

    @router.get("/opportunity-research")
    async def collection(request:Request,response:Response):
        claims=await run_in_threadpool(current,request)
        response.headers["Cache-Control"]="no-store"
        return await run_in_threadpool(invoke,service.list,claims)

    @router.post("/opportunity-research/timeline")
    async def timeline(request:Request,response:Response):
        claims=await run_in_threadpool(current,request); body=await _body(request,{"binding"})
        response.headers["Cache-Control"]="no-store"
        return await run_in_threadpool(invoke,service.timeline,claims,body["binding"])

    @router.post("/opportunity-research/similar")
    async def similar(request:Request,response:Response):
        claims=await run_in_threadpool(current,request); body=await _body(request,{"binding","requestId"})
        response.headers["Cache-Control"]="no-store"
        return await run_in_threadpool(invoke,service.similar,claims,body["binding"],body["requestId"])
