"""Online scheduling handoff; a pulse cannot sign or execute a collection."""
from fastapi import Request
from starlette.concurrency import run_in_threadpool

from pilot.auth import TokenClaims
from pilot.execution_contract import ExecutionRuntimeError
from pilot.monitor_runtime_contract import MonitorPulseRequest
from pilot.research_strategy_api import _body, _error, _no_query


def register_monitor_runtime_api(router, service, identity, require_session_https):
    def current(request):
        require_session_https(request)
        claims = identity(request).claims
        if not isinstance(claims, TokenClaims):
            raise _error(401, 'invalid_session')
        if service is None:
            raise _error(501, 'capability_unavailable')
        _no_query(request)
        return claims

    def invoke(claims, body):
        try:
            return service.pulse(claims, body)
        except ExecutionRuntimeError as error:
            status, code = error.status, error.code
        raise _error(status, code)

    @router.post('/monitor-runtime/pulse')
    async def pulse(request: Request):
        claims = await run_in_threadpool(current, request)
        body = await _body(request, MonitorPulseRequest)
        return await run_in_threadpool(invoke, claims, body)
