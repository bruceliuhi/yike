"""Bounded raw upload and inbox facade; no implicit collection or review."""
import json
import re

from fastapi import HTTPException, Request
from starlette.concurrency import run_in_threadpool

from pilot.candidate_contract import CandidateContractError
from pilot.device_keys import DeviceKeyError, decode_canonical, uuid_string
from pilot.execution_contract import ExecutionRuntimeError
from pilot.source_capabilities import resolve_platform

MAX_UPLOAD_BYTES = 4 * 1024 * 1024
_REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_INTEGER = re.compile(r"[1-9][0-9]{0,8}\Z")


def _invalid():
    return HTTPException(422, detail={"code": "invalid_request", "message": "请求字段无效。"})


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def _reject_constant(_value):
    raise ValueError("non-JSON number")


async def _bounded_json(request):
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise HTTPException(415, detail={"code": "json_required", "message": "请使用 JSON 请求。"})
    # Count actual bytes before decoding. A client-supplied Content-Length is
    # neither an authorization nor a reliable bound for chunked requests.
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, detail={"code": "request_too_large", "message": "请拆分上传批次。"})
        raw.extend(chunk)
    try:
        body = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        return body
    except (ValueError, RecursionError):
        raise _invalid() from None


async def _upload_envelope(request):
    body = await _bounded_json(request)
    try:
        if (type(body) is not dict or set(body) != {"batch", "signature"}
                or type(body["batch"]) is not dict or type(body["signature"]) is not str):
            raise ValueError("invalid envelope")
        decode_canonical(body["signature"], 64)
    except (ValueError, RecursionError, DeviceKeyError):
        raise _invalid() from None
    return body


async def _submission_envelope(request):
    body = await _bounded_json(request)
    if type(body) is not dict or set(body) != {"batch"} or type(body["batch"]) is not dict:
        raise _invalid()
    return body


def register_candidate_api(router, service, identity, require_session_https):
    def current(request):
        require_session_https(request)
        session = identity(request)
        if session.claims is None:
            raise ExecutionRuntimeError("invalid_session", 401)
        if service is None:
            raise HTTPException(501, detail={
                "code": "capability_unavailable", "message": "候选入库服务尚未接入，当前操作未执行。",
            })
        return session.claims

    def invoke(operation, *args, **kwargs):
        try:
            return operation(*args, **kwargs)
        except CandidateContractError as error:
            raise HTTPException(422, detail={"code": error.code, "message": error.code}) from None

    @router.post("/candidate-batches")
    async def upload(request: Request):
        # Session registration may hit PostgreSQL; neither it nor ingestion may
        # block the async request-body reader's event loop.
        claims = await run_in_threadpool(current, request)
        body = await _upload_envelope(request)
        return await run_in_threadpool(invoke, service.ingest, claims, body["batch"], body["signature"])

    @router.post("/candidate-submission-signing-payload")
    async def signing_payload(request: Request):
        claims = await run_in_threadpool(current, request)
        body = await _submission_envelope(request)
        return await run_in_threadpool(invoke, service.prepare_signing_payload, claims, body["batch"])

    @router.get("/candidate-batches/{platform_run_id}/{request_id}")
    def receipt(platform_run_id: str, request_id: str, request: Request):
        claims = current(request)
        uuid_string(platform_run_id)
        if not _REQUEST_ID.fullmatch(request_id):
            raise _invalid()
        return invoke(service.get_receipt, claims, platform_run_id, request_id)

    @router.get("/raw-candidates")
    def candidates(request: Request):
        claims = current(request)
        query = request.query_params
        if (set(query) - {"task_id", "platform", "page", "page_size"}
                or any(len(query.getlist(key)) != 1 for key in query)):
            raise _invalid()
        task_id, platform = query.get("task_id"), query.get("platform")
        if task_id is not None:
            uuid_string(task_id)
        if platform is not None:
            try:
                resolve_platform(platform, namespace="service")
            except ValueError:
                raise _invalid() from None
        page, page_size = query.get("page", "1"), query.get("page_size", "20")
        if not _INTEGER.fullmatch(page) or not _INTEGER.fullmatch(page_size) or int(page_size) > 100:
            raise _invalid()
        return invoke(service.list_candidates, claims, task_id=task_id, platform=platform,
                      page=int(page), page_size=int(page_size))

    @router.get("/raw-candidates/{candidate_id}")
    def detail(candidate_id: str, request: Request):
        claims = current(request)
        uuid_string(candidate_id)
        return invoke(service.get_candidate, claims, candidate_id)
