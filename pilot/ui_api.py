"""Authenticated JSON facade for the existing customer-pilot store.

This module does not implement collection, platform login, sending, or a task
executor. The capability responses make those missing boundaries explicit.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pilot.auth import InvalidPilotToken, renew_sms_token, SMS_SESSION_SECONDS
from pilot.candidate_api import register_candidate_api
from pilot.candidate_ingestion import CandidateIngestionError
from pilot.connection_api import register_connection_api
from pilot.connection_versions import ConnectionOperationError
from pilot.device_api import register_device_api
from pilot.device_keys import DeviceKeyError
from pilot.execution_api import register_execution_api
from pilot.execution_contract import ExecutionRuntimeError
from pilot.identity import IdentityValidationError
from pilot.outreach_contract import canonical_uuid
from pilot.sessions import SessionIdentity, authenticate_session, revoke_session_tokens
from pilot.store import PilotStore


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SessionInput(_Input):
    token: str = Field(min_length=1, max_length=16_384)


class ProfileInput(_Input):
    description: str = Field(min_length=1, max_length=8_000)
    baseProfileVersionId: str | None = None
    materialReferences: list[dict] | None = Field(default=None, max_length=5)
    profileEntityId: str | None = None
    newBusiness: dict | None = None

    @field_validator("description")
    @classmethod
    def nonempty_description(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("description is required")
        return value

    @field_validator("baseProfileVersionId")
    @classmethod
    def valid_base_profile_version(cls, value):
        return canonical_uuid(value) if value is not None else value

    @field_validator("profileEntityId")
    @classmethod
    def valid_profile_entity(cls, value):
        if value is None:
            return value
        return PilotStore._profile_entity_id(value)

    @field_validator("newBusiness")
    @classmethod
    def valid_new_business(cls, value):
        if value is None:
            return value
        if type(value) is not dict or set(value) != {"requestId", "name"}:
            raise ValueError("invalid new business")
        return {"requestId": canonical_uuid(value["requestId"]),
                "name": PilotStore._profile_name(value["name"])}

    @field_validator("materialReferences")
    @classmethod
    def valid_references(cls, value):
        if value is None:
            return value
        allowed_fields = {"service", "customer", "regions", "preference", "exclusions"}
        seen = set()
        for item in value:
            if type(item) is not dict or item.get("field") not in allowed_fields or item["field"] in seen:
                raise ValueError("invalid material references")
            seen.add(item["field"])
            keys = set(item)
            if keys == {"field", "referenceId"}:
                canonical_uuid(item["referenceId"])
            elif keys == {"field", "sourceProfileVersionId", "materialId", "materialVersion", "extractionId"}:
                if any(not isinstance(item[key], str) or not item[key].strip() for key in
                       ("sourceProfileVersionId", "materialId", "extractionId")):
                    raise ValueError("invalid material reference")
                if type(item["materialVersion"]) is not int or not 1 <= item["materialVersion"] <= 2147483647:
                    raise ValueError("invalid material reference")
            else:
                raise ValueError("invalid material reference")
        return value

    @model_validator(mode="after")
    def inheritance_has_base(self):
        if any("referenceId" in item for item in (self.materialReferences or [])) and not self.baseProfileVersionId:
            raise ValueError("base profile version required")
        if self.profileEntityId is not None and self.newBusiness is not None:
            raise ValueError("profile entity choice is mutually exclusive")
        return self


class FollowupInput(_Input):
    opportunity_id: str = Field(min_length=1, max_length=128)
    status: Literal["CONTACTED", "REPLIED", "MEETING", "QUOTED", "LOST", "WON"]
    note: str = Field(min_length=1, max_length=8_000)

    @field_validator("opportunity_id", "note")
    @classmethod
    def nonempty_value(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value is required")
        return value


class DeviceInput(_Input):
    device_label: str = Field(min_length=1, max_length=128)

    @field_validator("device_label")
    @classmethod
    def nonempty_label(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("device_label is required")
        return value.strip()


class ConnectionInput(_Input):
    platform: str = Field(min_length=1, max_length=32)
    device_id: str = Field(min_length=1, max_length=256)
    account_public_id: str = Field(min_length=1, max_length=256)
    session_ref: str = Field(min_length=1, max_length=512)


class ExecutionEventInput(_Input):
    device_id: str = Field(min_length=1, max_length=256)
    connection_id: str = Field(min_length=1, max_length=256)
    execution_generation: int = Field(ge=1)
    event_type: str = Field(min_length=1, max_length=64)
    payload: dict = Field(default_factory=dict)
    task_id: str | None = Field(default=None, max_length=256)


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


class _UiRoute(APIRoute):
    """Keep JSON errors generic, and never echo rejected tokens or inputs."""

    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request):
            try:
                response = await original(request)
            except RequestValidationError:
                response = JSONResponse(
                    {"detail": {"code": "invalid_request", "message": "请求字段无效，请检查后重试。"}},
                    status_code=422,
                )
            except (DeviceKeyError, ConnectionOperationError, ExecutionRuntimeError, CandidateIngestionError) as error:
                response = JSONResponse(
                    {"detail": {"code": error.code, "message": error.code}}, status_code=error.status,
                )
            except InvalidPilotToken:
                response = JSONResponse(
                    {"detail": {"code": "invalid_session", "message": "invalid_session"}}, status_code=401,
                )
            except HTTPException as error:
                response = JSONResponse({"detail": error.detail}, status_code=error.status_code, headers=error.headers)
            except PermissionError:
                response = JSONResponse(
                    {"detail": {"code": "user_not_provisioned", "message": "当前账号尚未开通客户空间。"}},
                    status_code=403,
                )
            except Exception:
                response = JSONResponse(
                    {"detail": {"code": "internal_error", "message": "服务暂时无法完成请求。"}},
                    status_code=500,
                )
            response.headers["cache-control"] = "no-store"
            return response

        return handler


_CAPABILITIES = {
    "pilot_token_session": True,
    "profiles": True,
    "opportunities": True,
    "manual_followups": True,
    "sms_login": False,
    "access_login": False,
    "platform_connections": False,
    "task_execution": False,
    "search_suggestions": False,
    "outreach": False,
    "replies": False,
}


def register_ui_api(app: FastAPI, store, *, auth_secret: str, dev_login: bool = False,
                    phone_auth=None, sms_sender=None, access_auth=None, execution_runtime=None, candidate_ingestion=None,
                    candidate_review=None, research_strategies=None, reply_store=None, contact_drafts=None,
                    outreach_queue=None, materials=None, monitor_plans=None, monitor_runtime=None,
                    search_suggestions=None, short_coach=None, structured_followups=None, opportunity_brief=None,
                    research_quotes=None, research_execution=None, research_runtime=None) -> None:
    # The enclosing pilot app retains its same-Origin middleware and security
    # headers. This router deliberately does not install a permissive CORS rule.
    router = APIRouter(prefix="/api/ui", route_class=_UiRoute)

    def token_identity(token: str) -> SessionIdentity:
        try:
            return authenticate_session(store, token, auth_secret)
        except InvalidPilotToken as error:
            raise _error(401, "invalid_session", "访问凭证已失效，请重新登录。") from error

    def identity(request: Request) -> SessionIdentity:
        authorization = request.headers.get("authorization")
        token = authorization[7:].strip() if authorization and authorization.startswith("Bearer ") else request.cookies.get("pilot_session")
        if not token:
            raise _error(401, "authentication_required", "请先登录。")
        return token_identity(token)

    def require_session_https(request: Request) -> None:
        if not dev_login and request.url.scheme != "https":
            raise _error(400, "https_required", "登录会话需要 HTTPS 连接。")

    @router.get("/session")
    def session(request: Request, response: Response):
        current = identity(request)
        # Never turn a Bearer credential into a browser session implicitly.
        if not request.headers.get('authorization') and current.claims is not None:
            renewed = renew_sms_token(current.claims, auth_secret)
            if renewed:
                require_session_https(request)
                response.set_cookie('pilot_session', renewed, httponly=True,
                                    secure=request.url.scheme == 'https', samesite='strict',
                                    max_age=SMS_SESSION_SECONDS)
        return current.public_view()

    @router.post("/session")
    def exchange_session(body: SessionInput, request: Request, response: Response):
        require_session_https(request)
        current = token_identity(body.token.strip())
        response.set_cookie(
            "pilot_session", body.token.strip(), httponly=True,
            secure=request.url.scheme == "https", samesite="strict", max_age=3600,
        )
        return current.public_view()

    @router.delete("/session")
    def logout(request: Request, response: Response):
        require_session_https(request)
        authorization = request.headers.get("authorization")
        bearer = authorization[7:].strip() if authorization and authorization.startswith("Bearer ") else None
        revoke_session_tokens(store, [bearer, request.cookies.get("pilot_session")], auth_secret)
        # Do not return success or clear the cookie before the transaction commits.
        response.delete_cookie("pilot_session", httponly=True, secure=request.url.scheme == "https", samesite="strict")
        return {"authenticated": False}

    @router.get("/devices")
    def devices(request: Request):
        current = identity(request)
        return {"items": store.list_devices(current.user_id)}

    @router.post("/devices", status_code=201)
    def register_device(body: DeviceInput, request: Request):
        current = identity(request)
        try:
            return store.register_device(current.user_id, body.device_label)
        except ValueError as error:
            raise _error(400, "invalid_device", "设备信息无效。") from error

    @router.post("/devices/{device_id}/revoke")
    def revoke_device(device_id: str, request: Request):
        current = identity(request)
        if not store.revoke_device(current.user_id, device_id, claims=current.claims):
            raise _error(404, "device_not_found", "未找到可撤销的设备。")
        return {"device_id": device_id, "status": "REVOKED"}

    @router.get("/connections")
    def connections(request: Request):
        current = identity(request)
        return {"items": store.list_connections(current.user_id)}

    @router.post("/connections", status_code=201)
    def connect_platform(body: ConnectionInput, request: Request):
        current = identity(request)
        try:
            return store.connect_platform(current.user_id, body.platform, body.device_id, body.account_public_id, body.session_ref, claims=current.claims)
        except IdentityValidationError as error:
            raise _error(400, "invalid_connection", "平台连接信息无效。") from error
        except KeyError as error:
            raise _error(404, "device_not_found", "设备不存在或不属于当前客户空间。") from error
        except ValueError as error:
            raise _error(409, "device_unavailable", "设备当前不可用于平台连接。") from error

    @router.post("/connections/{connection_id}/disconnect")
    def disconnect_platform(connection_id: str, request: Request):
        current = identity(request)
        if not store.disconnect_platform(current.user_id, connection_id, claims=current.claims):
            raise _error(404, "connection_not_found", "未找到可断开的平台连接。")
        return {"connection_id": connection_id, "status": "DISCONNECTED"}

    @router.post("/execution-events", status_code=201)
    def execution_event(body: ExecutionEventInput, request: Request):
        current = identity(request)
        try:
            return store.append_execution_event(current.user_id, body.device_id, body.connection_id, body.execution_generation, body.event_type, body.payload, body.task_id)
        except IdentityValidationError as error:
            raise _error(400, "invalid_execution_event", "执行事件无效。") from error
        except KeyError as error:
            raise _error(404, "connection_not_found", "设备或平台连接不存在。") from error
        except ValueError as error:
            raise _error(409, "connection_unavailable", "设备或平台连接当前不可用。") from error

    @router.get("/profiles")
    def profiles(request: Request):
        current = identity(request)
        if hasattr(store, "list_profiles"):
            return {"items": store.list_profiles(current.user_id)}
        # PilotStore has version lookup but no list method. Keep this read in the
        # facade, with the same server-derived tenant setting and SQL predicate.
        with store.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('yike.tenant_id', %s, false)", (current.tenant_id,))
                cursor.execute(
                    "SELECT profile_id, profile_version_id AS version_id, version, payload, status "
                    "FROM business_profile_versions WHERE tenant_id=%s ORDER BY version DESC",
                    (current.tenant_id,),
                )
                columns = [column.name for column in cursor.description]
                rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return {"items": rows}

    @router.post("/profiles")
    def save_profile(body: ProfileInput, request: Request):
        current = identity(request)
        try:
            if (body.baseProfileVersionId is None and body.materialReferences is None
                    and body.profileEntityId is None and body.newBusiness is None):
                result = store.save_profile(current.user_id, {"description": body.description})
            else:
                result = store.save_profile(current.user_id, {"description": body.description},
                    base_profile_version_id=body.baseProfileVersionId, material_references=body.materialReferences,
                    profile_entity_id=body.profileEntityId, new_business=body.newBusiness)
        except KeyError as error:
            raise _error(404, "profile_not_found", "未找到该业务画像。") from error
        except ValueError as error:
            raise _error(400, "invalid_profile", "业务描述无效。") from error
        if result["status"] == "REVOKED":
            raise _error(409, "profile_revoked", "该内容对应已撤销版本，请修改业务描述。")
        return result

    @router.post("/profiles/{version_id}/confirm")
    def confirm_profile(version_id: str, request: Request):
        current = identity(request)
        try:
            store.confirm_profile(current.user_id, version_id)
            return store.get_profile_version(current.user_id, version_id)
        except KeyError as error:
            raise _error(404, "profile_not_found", "未找到该画像版本。") from error
        except ValueError as error:
            raise _error(400, "profile_not_confirmable", "该画像版本无法确认。") from error

    @router.get("/opportunities")
    def opportunities(request: Request):
        current = identity(request)
        return {"items": store.list_opportunities(current.user_id)}

    @router.get("/opportunities/{opportunity_id}")
    def opportunity(opportunity_id: str, request: Request):
        current = identity(request)
        from pilot.candidate_review_api import _evidence_version
        extended = _evidence_version(request)
        try:
            result = store.get_opportunity(current.user_id, opportunity_id)
        except KeyError as error:
            raise _error(404, "opportunity_not_found", "未找到该机会。") from error
        verification = (result.get('source_evidence',{}).get('snapshot') or {}).get('verification',{})
        if verification.get('demandEvidence') and not extended:
            raise _error(409,'client_upgrade_required','该商机包含人工需求补证，请升级客户端后查看。')
        return {"opportunity": result, "followups": store.list_followups(current.user_id, opportunity_id)}

    @router.get("/followups")
    def followups(request: Request):
        current = identity(request)
        return {"items": store.list_all_followups(current.user_id)}

    @router.post("/followups", status_code=201)
    def save_followup(body: FollowupInput, request: Request):
        current = identity(request)
        try:
            return store.record_followup(current.user_id, body.opportunity_id, body.status, body.note)
        except KeyError as error:
            raise _error(404, "opportunity_not_found", "未找到该机会。") from error
        except ValueError as error:
            raise _error(400, "invalid_followup", "跟进记录无效。") from error

    @router.get("/capabilities")
    def capabilities():
        state = dict(capabilities_state)
        state["search_suggestions"] = bool(search_suggestions is not None and search_suggestions.available)
        return {"capabilities": {name: {"available": available} for name, available in state.items()}}

    @router.post("/capabilities/{capability}")
    def unavailable_capability(capability: str, request: Request):
        available = (bool(search_suggestions is not None and search_suggestions.available)
                     if capability == "search_suggestions" else capabilities_state.get(capability, False))
        if capability not in capabilities_state or available:
            raise _error(404, "capability_not_found", "未找到该能力入口。")
        if capability != "sms_login":
            identity(request)
        raise _error(501, "capability_unavailable", "该能力尚未接入，当前操作未执行。")

    register_device_api(router, store, identity, require_session_https)
    register_connection_api(router, store, identity, require_session_https)
    register_execution_api(router, execution_runtime, identity, require_session_https)
    register_candidate_api(router, candidate_ingestion, identity, require_session_https)
    from pilot.candidate_review_api import register_candidate_review_api
    register_candidate_review_api(router, candidate_review, identity, require_session_https)
    from pilot.research_strategy_api import register_research_strategy_api
    register_research_strategy_api(router, research_strategies, identity, require_session_https)
    from pilot.research_quote_api import register_research_quote_api
    register_research_quote_api(router, research_quotes, identity, require_session_https)
    from pilot.research_execution_api import register_research_execution_api
    register_research_execution_api(router, research_execution, identity, require_session_https, runtime=research_runtime)
    from pilot.monitor_api import register_monitor_api
    register_monitor_api(router, monitor_plans, identity, require_session_https)
    from pilot.monitor_runtime_api import register_monitor_runtime_api
    register_monitor_runtime_api(router, monitor_runtime, identity, require_session_https)
    from pilot.reply_api import register_reply_api
    register_reply_api(router, reply_store, identity, require_session_https)
    from pilot.contact_draft_api import register_contact_draft_api
    register_contact_draft_api(router, contact_drafts, identity, require_session_https)
    from pilot.short_coach_api import register_short_coach_api
    register_short_coach_api(router, short_coach, identity, require_session_https)
    from pilot.followup_api import register_followup_api
    register_followup_api(router, structured_followups, identity, require_session_https)
    from pilot.opportunity_brief_api import register_opportunity_brief_api
    register_opportunity_brief_api(router, opportunity_brief, identity, require_session_https)
    from pilot.material_api import register_material_api
    register_material_api(router, materials, identity, require_session_https)
    from pilot.search_suggestion_api import register_search_suggestion_api
    register_search_suggestion_api(router, search_suggestions, identity, require_session_https)
    from pilot.opportunity_research import OpportunityResearchService
    from pilot.opportunity_research_api import register_opportunity_research_api

    def research_platforms(configuration):
        check = getattr(execution_runtime, 'capability_check', None)
        if check is None:
            return []
        return [client for server, client in (
            ('XIAOHONGSHU', 'xhs'), ('DOUYIN', 'douyin'), ('BILIBILI', 'bilibili'),
            ('ZHIHU', 'zhihu'), ('PUBLIC_WEB', 'web'),
        ) if check(server, 'PUBLIC_ANONYMOUS' if server == 'PUBLIC_WEB' else 'PLATFORM_ACCOUNT', configuration)]

    register_opportunity_research_api(router,
        OpportunityResearchService(store, supported_platforms=research_platforms),
        identity, require_session_https)
    from pilot.search_coverage import SearchCoverageService
    from pilot.search_coverage_api import register_search_coverage_api
    register_search_coverage_api(router, SearchCoverageService(store), identity, require_session_https)
    from pilot.outreach_queue_api import register_outreach_queue_api
    register_outreach_queue_api(router, outreach_queue, identity, require_session_https)
    from pilot.phone_api import register_phone_api
    capabilities_state = dict(_CAPABILITIES)
    capabilities_state["sms_login"] = register_phone_api(
        router, store, phone_auth, sms_sender, auth_secret, require_session_https)
    from pilot.access_api import register_access_api
    capabilities_state['access_login'] = register_access_api(router, store, access_auth, auth_secret, require_session_https)
    app.include_router(router)
