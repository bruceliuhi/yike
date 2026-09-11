"""Authenticated no-store HTTP facade for short coach."""
import json
from fastapi import HTTPException, Request, Response
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from pilot.auth import TokenClaims
from pilot.short_coach import CoachInput, GenerateInput, ShortCoachError

MAX_REQUEST_BYTES=32*1024
def _error(status,code): return HTTPException(status,detail={"code":code,"message":code},headers={"Cache-Control":"no-store"})
def _unique(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise ValueError
        result[key]=value
    return result
async def _body(request, schema):
    if request.headers.get("content-type","").split(";",1)[0].strip().lower()!="application/json": raise _error(415,"json_required")
    raw=bytearray()
    async for chunk in request.stream():
        if len(raw)+len(chunk)>MAX_REQUEST_BYTES: raise _error(413,"request_too_large")
        raw.extend(chunk)
    try: return schema.model_validate(json.loads(raw.decode(),object_pairs_hook=_unique,parse_constant=lambda _x:(_ for _ in ()).throw(ValueError()))).model_dump()
    except (ValueError,TypeError,UnicodeError,ValidationError,RecursionError): raise _error(422,"invalid_request") from None
def register_short_coach_api(router,service,identity,require_session_https):
    def claims(request):
        require_session_https(request)
        session=identity(request)
        if not isinstance(session.claims,TokenClaims): raise _error(401,"invalid_session")
        if service is None: raise _error(501,"capability_unavailable")
        if request.query_params: raise _error(422,"invalid_request")
        return session.claims
    def invoke(method,*args):
        try:return method(*args)
        except ShortCoachError as error: raise _error(error.status,error.code) from None
    @router.post("/short-coach/preview")
    async def preview(request:Request,response:Response):
        owner=await run_in_threadpool(claims,request); payload=await _body(request,CoachInput)
        response.headers["Cache-Control"]="no-store"; return await run_in_threadpool(invoke,service.preview,owner,payload)
    @router.post("/short-coach/generate")
    async def generate(request:Request,response:Response):
        owner=await run_in_threadpool(claims,request); payload=await _body(request,GenerateInput)
        response.headers["Cache-Control"]="no-store"; return await run_in_threadpool(invoke,service.generate,owner,payload)
