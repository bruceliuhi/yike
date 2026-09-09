import pytest
from pydantic import ValidationError

from pilot.source_capabilities import CapabilityDeclaration, SourceCapabilities, default_capabilities, resolve_platform


@pytest.mark.parametrize("frontend,service,collector", [
    ("xhs", "XIAOHONGSHU", "xhs"), ("douyin", "DOUYIN", "dy"),
    ("bilibili", "BILIBILI", "bili"), ("zhihu", "ZHIHU", "zhihu"),
    ("web", "PUBLIC_WEB", None),
])
def test_platform_namespaces_are_exact(frontend, service, collector):
    spec = resolve_platform(frontend, namespace="frontend")
    assert (spec.frontend_id, spec.service_id, spec.collector_id) == (frontend, service, collector)
    assert resolve_platform(service, namespace="service") == spec
    if collector:
        assert resolve_platform(collector, namespace="collector") == spec


@pytest.mark.parametrize("value,namespace", [("dy", "frontend"), ("DOUYIN", "frontend"),
    ("douyin", "service"), ("bili", "frontend"), ("web", "collector"),
    ("unknown", "frontend"), ("xhs", "guess")])
def test_platform_namespaces_do_not_guess(value, namespace):
    with pytest.raises(ValueError):
        resolve_platform(value, namespace=namespace)

def test_platform_namespace_type_error_is_stable():
    with pytest.raises(ValueError):
        resolve_platform("xhs", namespace=[])


def test_default_capabilities_are_frozen_and_not_implemented():
    caps = default_capabilities("DOUYIN")
    for name in ("search", "read_content", "read_comments", "monitor", "send", "read_replies"):
        declaration = getattr(caps, name)
        assert declaration.state == "NOT_IMPLEMENTED" and declaration.evidence_ref is None
        with pytest.raises(ValidationError): declaration.state = "VERIFIED"
    with pytest.raises(ValidationError): caps.platform = "PUBLIC_WEB"


def test_non_initial_capability_requires_safe_opaque_evidence():
    with pytest.raises(ValidationError): CapabilityDeclaration(state="VERIFIED", evidence_ref=None)
    with pytest.raises(ValidationError): CapabilityDeclaration(state="UNAVAILABLE", evidence_ref="https://x.test/token=x")
    assert CapabilityDeclaration(state="UNVERIFIED", evidence_ref="review-2026.09")
    with pytest.raises(ValidationError): CapabilityDeclaration(state="NOT_IMPLEMENTED", surprise=True)
    data = default_capabilities("PUBLIC_WEB").model_dump(); data["approved"] = True
    with pytest.raises(ValidationError): SourceCapabilities.model_validate(data)
