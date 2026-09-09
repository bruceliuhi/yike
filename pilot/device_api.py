"""Thin session-authenticated HTTP surface; no alternate authentication."""
import json

from fastapi import HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.model_contract import strict_json_object
from pilot.device_credentials import DeviceCredentialStore
from pilot.device_keys import ChallengeRequest, CompletionProof, DeviceKeyError
from pilot.device_registration import DeviceRegistrationStore


MAX_REGISTRATION_BYTES = 4096


def _invalid_request():
    return HTTPException(422, {"code": "invalid_request", "message": "invalid_request"})


async def _registration_body(request):
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise HTTPException(415, {"code": "json_required", "message": "json_required"})
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_REGISTRATION_BYTES:
            raise HTTPException(413, {"code": "request_too_large", "message": "request_too_large"})
        raw.extend(chunk)
    try:
        payload = strict_json_object(raw.decode("utf-8", errors="strict"))
        json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        return payload
    except (ValueError, UnicodeError, RecursionError):
        raise _invalid_request() from None


def register_device_api(router, store, identity, require_session_https):
    def run(request, operation):
        require_session_https(request)
        try:
            current = identity(request)
            if current.claims is None:
                raise DeviceKeyError("invalid_session", 401)
            # Construct lazily: pre-existing transport-only stores need no DB.
            return operation(DeviceCredentialStore(store.database), current.claims)
        except DeviceKeyError as error:
            raise HTTPException(error.status, {"code": error.code, "message": error.code}) from None
        except PermissionError:
            raise HTTPException(401, {"code": "invalid_session", "message": "invalid_session"}) from None
        except HTTPException as error:
            if error.status_code == 401:
                raise HTTPException(401, {"code": "invalid_session", "message": "invalid_session"}) from None
            raise

    @router.post("/devices/{device_id}/key-challenges")
    def create(device_id: str, body: ChallengeRequest, request: Request):
        return run(request, lambda service, claims: service.create_challenge(claims, device_id, body))

    @router.post("/devices/{device_id}/key-challenges/{challenge_id}/complete")
    def complete(device_id: str, challenge_id: str, body: CompletionProof, request: Request):
        return run(request, lambda service, claims: service.complete_challenge(claims, device_id, challenge_id, body))

    @router.get("/device-key-requests/{request_id}")
    def receipt(request_id: str, request: Request):
        return run(request, lambda service, claims: service.get_receipt(claims, request_id))

    def registration_claims(request):
        require_session_https(request)
        try:
            current = identity(request)
            if current.claims is None:
                raise DeviceKeyError("invalid_session", 401)
            return current.claims
        except DeviceKeyError as error:
            raise HTTPException(error.status, {"code": error.code, "message": error.code}) from None
        except PermissionError:
            raise HTTPException(401, {"code": "invalid_session", "message": "invalid_session"}) from None
        except HTTPException as error:
            if error.status_code == 401:
                raise HTTPException(401, {"code": "invalid_session", "message": "invalid_session"}) from None
            raise

    def registration_call(operation):
        try:
            return operation(DeviceRegistrationStore(store.database))
        except DeviceKeyError as error:
            raise HTTPException(error.status, {"code": error.code, "message": error.code}) from None

    @router.post("/device-registrations", status_code=201)
    async def register_device(request: Request):
        claims = await run_in_threadpool(registration_claims, request)
        body = await _registration_body(request)
        return await run_in_threadpool(
            registration_call, lambda service: service.register(claims, body)
        )

    @router.get("/device-registration-requests/{request_id}")
    async def registration_receipt(request_id: str, request: Request):
        claims = await run_in_threadpool(registration_claims, request)
        return await run_in_threadpool(
            registration_call, lambda service: service.get_receipt(claims, request_id)
        )

    @router.get("/devices/{device_id}/identity")
    async def device_identity(device_id: str, request: Request):
        claims = await run_in_threadpool(registration_claims, request)
        return await run_in_threadpool(
            registration_call, lambda service: service.get_identity(claims, device_id)
        )
