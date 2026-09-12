"""Fixed execution routes; installation is not proof of a usable collector."""
from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from pilot.device_keys import decode_canonical, uuid_string
from pilot.execution_contract import ExecutionOperation, ExecutionRuntimeError
from pilot.foreground_collection import foreground_collection_support


class ExecutionEnvelope(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)
    request: ExecutionOperation
    signature: str = Field(min_length=86, max_length=86, repr=False)

    @field_validator("signature")
    @classmethod
    def valid_signature(cls, value):
        decode_canonical(value, 64)
        return value


class ExecutionSigningEnvelope(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)
    request: ExecutionOperation


def register_execution_api(router, runtime, identity, require_session_https):
    def run(request, operation):
        require_session_https(request)
        current = identity(request)
        if current.claims is None:
            raise ExecutionRuntimeError("invalid_session", 401)
        if runtime is None:
            raise HTTPException(501, detail={
                "code": "capability_unavailable",
                "message": "执行服务尚未接入，当前操作未执行。",
            })
        return operation(runtime, current.claims)

    @router.get('/execution-support')
    def support(request: Request):
        def supported(service, claims):
            result = foreground_collection_support(service, claims)
            query = list(request.query_params.multi_items())
            if not query:
                return result
            if query in ([('sampling_version', '1')], [('sampling_version', '2')]):
                if result.get('public_monitor') is True:
                    return result | {'public_sampling': 'committed-round-v1' if query[0][1] == '1'
                                     else 'committed-round-revisit-v2'}
                return result
            if query == [('native_progress_version', '1')]:
                from pilot.native_search_progress import native_search_progress_supported
                if native_search_progress_supported(service.capability_check):
                    return result | {'native_progress': ['BILIBILI']}
                return result
            raise ExecutionRuntimeError('invalid_request', 422)
        return run(request, supported)

    @router.post("/execution-signing-payload")
    def signing_payload(body: ExecutionSigningEnvelope, request: Request):
        return run(request, lambda service, claims: service.prepare_signing_payload(claims, body.request))

    @router.post("/execution-operations")
    def apply(body: ExecutionEnvelope, request: Request):
        return run(request, lambda service, claims: service.apply(claims, body.request, body.signature))

    @router.get("/execution-operations/{request_id}")
    def receipt(request_id: str, request: Request):
        uuid_string(request_id)
        return run(request, lambda service, claims: service.get_receipt(claims, request_id))

    @router.get("/execution-tasks/{task_id}")
    def task(task_id: str, request: Request):
        uuid_string(task_id)
        return run(request, lambda service, claims: service.get_task(claims, task_id))

    @router.get("/execution-task-feed")
    def task_feed(request: Request, limit: int = 20, cursor: str | None = None):
        return run(request, lambda service, claims: service.get_task_feed(
            claims, limit=limit, cursor=cursor,
            query_fields=set(request.query_params.keys()),
        ))

    @router.get("/execution-task-feed/{task_id}")
    def task_feed_item(task_id: str, request: Request):
        return run(request, lambda service, claims: {
            "schema_version": "execution-task-feed-item-v1",
            "item": service.get_task_feed_item(claims, uuid_string(task_id)),
        })
