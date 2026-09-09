"""Offline registry of platform identifiers and source capabilities."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

class PlatformSpec(_FrozenModel):
    frontend_id: str
    service_id: str
    collector_id: str | None

def _is_opaque_id(value: object, maximum: int = 128) -> bool:
    return (isinstance(value, str) and 1 <= len(value) <= maximum
            and value[0].isascii() and value[0].isalnum()
            and all(ch.isascii() and (ch.isalnum() or ch in "_.:-") for ch in value))

class CapabilityDeclaration(_FrozenModel):
    state: Literal["NOT_IMPLEMENTED", "UNVERIFIED", "VERIFIED", "UNAVAILABLE"]
    evidence_ref: str | None = None

    @field_validator("evidence_ref")
    @classmethod
    def validate_evidence(cls, value):
        if value is not None and not _is_opaque_id(value):
            raise ValueError("invalid evidence reference")
        return value

    @model_validator(mode="after")
    def validate_state(self):
        if (self.state == "NOT_IMPLEMENTED") != (self.evidence_ref is None):
            raise ValueError("evidence does not match capability state")
        return self

class SourceCapabilities(_FrozenModel):
    platform: Literal["XIAOHONGSHU", "DOUYIN", "BILIBILI", "ZHIHU", "PUBLIC_WEB"]
    search: CapabilityDeclaration
    read_content: CapabilityDeclaration
    read_comments: CapabilityDeclaration
    monitor: CapabilityDeclaration
    send: CapabilityDeclaration
    read_replies: CapabilityDeclaration

_PLATFORMS = (
    PlatformSpec(frontend_id="xhs", service_id="XIAOHONGSHU", collector_id="xhs"),
    PlatformSpec(frontend_id="douyin", service_id="DOUYIN", collector_id="dy"),
    PlatformSpec(frontend_id="bilibili", service_id="BILIBILI", collector_id="bili"),
    PlatformSpec(frontend_id="zhihu", service_id="ZHIHU", collector_id="zhihu"),
    PlatformSpec(frontend_id="web", service_id="PUBLIC_WEB", collector_id=None),
)

def resolve_platform(value: str, *, namespace: str) -> PlatformSpec:
    if not isinstance(value, str) or not isinstance(namespace, str):
        raise ValueError("invalid platform identifier")
    attribute = {"frontend":"frontend_id", "service":"service_id", "collector":"collector_id"}.get(namespace)
    if attribute is None:
        raise ValueError("invalid platform namespace")
    for spec in _PLATFORMS:
        if getattr(spec, attribute) == value:
            return spec
    raise ValueError("unknown platform identifier")

def default_capabilities(platform: str) -> SourceCapabilities:
    service = resolve_platform(platform, namespace="service").service_id
    item = CapabilityDeclaration(state="NOT_IMPLEMENTED")
    return SourceCapabilities(platform=service, search=item, read_content=item, read_comments=item,
                              monitor=item, send=item, read_replies=item)
