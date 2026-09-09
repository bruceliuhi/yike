"""Thin routes under the existing HTTPS, Origin and session middleware."""
from fastapi import HTTPException, Request

from pilot.connection_versions import ConnectionOperation, ConnectionOperationError, ConnectionOperationStore


def register_connection_api(router, store, identity, require_session_https):
    def run(request, operation):
        require_session_https(request)
        try:
            current = identity(request)
            if current.claims is None:
                raise ConnectionOperationError("invalid_session", 401)
            return operation(ConnectionOperationStore(store.database), current.claims)
        except PermissionError:
            raise ConnectionOperationError("invalid_session", 401) from None
        except HTTPException as error:
            if error.status_code == 401:
                raise ConnectionOperationError("invalid_session", 401) from None
            raise

    @router.post("/connection-operations")
    def apply(body: ConnectionOperation, request: Request):
        return run(request, lambda service, claims: service.apply(claims, body))

    @router.get("/connection-operations/{request_id}")
    def receipt(request_id: str, request: Request):
        return run(request, lambda service, claims: service.get_receipt(claims, request_id))
