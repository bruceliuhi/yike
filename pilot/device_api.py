"""Thin session-authenticated HTTP surface; no alternate authentication."""
from fastapi import HTTPException, Request

from pilot.device_credentials import DeviceCredentialStore
from pilot.device_keys import ChallengeRequest, CompletionProof, DeviceKeyError


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
