"""Authenticated strategy preparation/confirmation; never starts collection.

Install on the existing UI router with its HTTPS/session dependencies and
same-Origin middleware. No shared app registration or capability is changed.
"""
from __future__ import annotations

import json
from uuid import UUID

from fastapi import HTTPException, Request
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from pilot.auth import TokenClaims
from pilot.research_strategy_contract import (
    ConfirmStrategyRequest, PrepareStrategyRequest, RevokeStrategyRequest,
    StrategyStoreError,
)

MAX_REQUEST_BYTES = 128 * 1024


def _error(status, code):
    return HTTPException(status, detail={'code': code, 'message': code},
                         headers={'Cache-Control': 'no-store'})


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('duplicate JSON field')
        value[key] = item
    return value


def _constant(_value):
    raise ValueError('non-JSON number')


async def _body(request, model):
    if request.headers.get('content-type', '').split(';', 1)[0].strip().lower() != 'application/json':
        raise _error(415, 'json_required')
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_REQUEST_BYTES:
            raise _error(413, 'request_too_large')
        raw.extend(chunk)
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique, parse_constant=_constant)
        if type(value) is not dict:
            raise ValueError('object required')
        return model.model_validate(value)
    except (ValidationError, ValueError, TypeError, RecursionError):
        pass
    raise _error(422, 'invalid_request')


def _no_query(request):
    if request.query_params:
        raise _error(422, 'invalid_request')


def _uuid(value):
    try:
        if type(value) is not str or len(value) != 36 or str(UUID(value)) != value:
            raise ValueError('canonical UUID required')
        return value
    except (ValueError, TypeError, AttributeError):
        pass
    raise _error(422, 'invalid_request')


def register_research_strategy_api(router, service, identity, require_session_https):
    def current(request):
        require_session_https(request)
        session = identity(request)
        if not isinstance(session.claims, TokenClaims):
            raise _error(401, 'invalid_session')
        if service is None:
            raise _error(501, 'capability_unavailable')
        _no_query(request)
        return session.claims

    def invoke(operation, *args):
        try:
            return operation(*args)
        except StrategyStoreError as error:
            status, code = error.status, error.code
        # Raise outside the handler so the private service exception is not
        # retained as an implicit exception context.
        raise _error(status, code)

    async def mutate(request, model, operation):
        # Session lookup and all database work run off the body reader's event
        # loop; only bounded parsing/validation occurs on the request thread.
        claims = await run_in_threadpool(current, request)
        body = await _body(request, model)
        return await run_in_threadpool(invoke, getattr(service, operation), claims, body)

    @router.post('/research-strategies/prepare')
    async def prepare(request: Request):
        return await mutate(request, PrepareStrategyRequest, 'prepare')

    @router.post('/research-strategies/confirm')
    async def confirm(request: Request):
        return await mutate(request, ConfirmStrategyRequest, 'confirm')

    @router.post('/research-strategies/revoke')
    async def revoke(request: Request):
        return await mutate(request, RevokeStrategyRequest, 'revoke')

    @router.get('/research-strategy-operations/{request_id}')
    def receipt(request_id: str, request: Request):
        claims = current(request)
        return invoke(service.get_receipt, claims, _uuid(request_id))

    @router.get('/research-strategies/{strategy_version_id}')
    def strategy(strategy_version_id: str, request: Request):
        claims = current(request)
        return invoke(service.get_strategy, claims, _uuid(strategy_version_id))
