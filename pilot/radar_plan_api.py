"""Local planning through the existing customer session; no search or charging."""
from __future__ import annotations

from uuid import UUID

from fastapi import Request, Response
from starlette.concurrency import run_in_threadpool

from pilot.auth import TokenClaims
from pilot.opportunity_research_api import _body, _error
from pilot.radar_plan import build_search_directions
from pilot.research_context import _DEMAND_SIGNALS


_FIELDS = {"contractVersion", "requestId", "querySeeds", "intentSignals", "exclusions", "region", "demandTypes"}


def preview_plan(payload):
    try:
        if type(payload["contractVersion"]) is not int or payload["contractVersion"] != 1:
            raise ValueError()
        request_id = payload["requestId"]
        if type(request_id) is not str or str(UUID(request_id)) != request_id:
            raise ValueError()
        if not payload["querySeeds"]:
            raise ValueError()
        if type(payload["exclusions"]) is not list:
            raise ValueError()
        if type(payload["region"]) is not str or len(payload["region"]) > 80:
            raise ValueError()
        demand_types = payload["demandTypes"]
        if (type(demand_types) is not list or len(demand_types) > 4
                or any(type(item) is not str or item not in _DEMAND_SIGNALS for item in demand_types)
                or len(set(demand_types)) != len(demand_types)):
            raise ValueError()
        signals = payload["intentSignals"]
        if type(signals) is not list:
            raise ValueError()
        return build_search_directions(
            query_seeds=payload["querySeeds"], intent_signals=signals or [_DEMAND_SIGNALS[item] for item in demand_types],
            exclusions=payload["exclusions"], region=payload["region"],
            max_queries=min(24, max(8, len(payload["querySeeds"]) * 6)),
        )
    except (ValueError, TypeError, KeyError, AttributeError):
        raise _error(422, "invalid_request") from None


def register_radar_plan_api(router, identity, require_session_https):
    def current(request):
        require_session_https(request)
        session = identity(request)
        if not isinstance(session.claims, TokenClaims):
            raise _error(401, "invalid_session")
        if request.query_params:
            raise _error(422, "invalid_request")
        return session

    @router.post("/research-plan/preview")
    async def preview(request: Request, response: Response):
        session = await run_in_threadpool(current, request)
        payload = await _body(request, _FIELDS)
        plan = await run_in_threadpool(preview_plan, payload)
        # Recheck the existing session after planning, including revocation.
        latest = await run_in_threadpool(current, request)
        if (latest.user_id, latest.tenant_id) != (session.user_id, session.tenant_id):
            raise _error(409, "identity_conflict")
        response.headers["Cache-Control"] = "no-store"
        return {"contractVersion": 1, "requestId": payload["requestId"],
                "userId": session.user_id, "accountScope": {"id": session.tenant_id, "version": 1},
                "plan": plan}
