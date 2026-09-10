"""Owner-private saved monitor plans. Does not grant or dispatch execution."""
from fastapi import Request
from starlette.concurrency import run_in_threadpool

from pilot.auth import TokenClaims
from pilot.monitor_contract import CreateMonitorPlanRequest, SetMonitorPlanStateRequest, MonitorPlanError
from pilot.research_strategy_api import _body, _error, _no_query, _uuid


def register_monitor_api(router, service, identity, require_session_https):
    def current(request):
        require_session_https(request)
        claims = identity(request).claims
        if not isinstance(claims, TokenClaims):
            raise _error(401, 'invalid_session')
        if service is None:
            raise _error(501, 'capability_unavailable')
        _no_query(request)
        return claims

    def invoke(method, *args):
        try:
            return method(*args)
        except MonitorPlanError as error:
            status, code = error.status, error.code
        raise _error(status, code)

    async def mutate(request, model, method):
        claims = await run_in_threadpool(current, request)
        body = await _body(request, model)
        return await run_in_threadpool(invoke, getattr(service, method), claims, body)

    @router.post('/monitor-plans')
    async def create(request: Request):
        return await mutate(request, CreateMonitorPlanRequest, 'create')

    @router.post('/monitor-plans/state')
    async def state(request: Request):
        return await mutate(request, SetMonitorPlanStateRequest, 'set_state')

    @router.get('/monitor-plans')
    def plans(request: Request):
        claims = current(request)
        return invoke(service.list, claims)

    @router.get('/monitor-plan-operations/{request_id}')
    def receipt(request_id: str, request: Request):
        claims = current(request)
        return invoke(service.get_receipt, claims, _uuid(request_id))
