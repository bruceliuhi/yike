"""Pure contract checks; all identifiers and URLs are synthetic."""
from copy import deepcopy
import hashlib
import importlib
import importlib.util
import json
from uuid import UUID

import pytest
from pydantic import ValidationError


PROFILE = "11111111-1111-4111-8111-111111111111"
STRATEGY = "22222222-2222-4222-8222-222222222222"
REQUEST = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
DRAFT = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


@pytest.fixture
def contract():
    # Assert feature absence explicitly so RED is not an import/collection error.
    assert importlib.util.find_spec("pilot.research_strategy_contract") is not None, (
        "Task 1 requires the research strategy contract module"
    )
    return importlib.import_module("pilot.research_strategy_contract")


def config():
    return dict(
        schema_version="research-strategy-v1", name="跨行业中文研究", source="search",
        keywords=["  设备  采购  ", "CRM 服务"], exclusions=["招聘"],
        links=["https://example.com/公开需求"], mode="once", schedule=None,
        research=dict(version=1, demandTypes=["INQUIRY", "COMPARISON"], maxSoubei=100,
                      limits=dict(sources=20, minutes=30, modelCalls=10),
                      stopAtAnyLimit=True, evidenceOrder="SOURCE_MATCH_CONTEXT"),
    )


def schedule():
    # Etc/UTC is an actual ZoneInfo key, not a local-time fallback.
    return dict(kind="daily", times=["09:00", "18:30"], interval=1.5,
                start="00:00", end="23:59", timezone="Etc/UTC")


@pytest.mark.parametrize('mode', ['once', 'monitor'])
def test_schedule_policy_v1_is_preserved_without_rewriting_legacy_bytes(contract, mode):
    legacy = config() | {'mode': mode, 'schedule': schedule()}
    old_snapshot = snapshot(contract, legacy)
    old_bytes = json.dumps(old_snapshot, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    assert 'policyVersion' not in old_bytes
    assert contract.configuration_digest(old_snapshot) == hashlib.sha256(old_bytes.encode()).hexdigest()
    legacy_request = prepare() | {'configuration': legacy}
    old_request = contract.PrepareStrategyRequest.model_validate(legacy_request).model_dump(mode='json')
    assert old_request == legacy_request
    expected_request_bytes = json.dumps(legacy_request, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    assert hashlib.sha256(contract._json(old_request).encode()).hexdigest() == hashlib.sha256(expected_request_bytes).hexdigest()
    modern = legacy | {'schedule': schedule() | {'policyVersion': 1}}
    try:
        request = contract.PrepareStrategyRequest.model_validate(prepare() | {'configuration': modern})
    except ValidationError:
        pytest.fail('current client schedule policyVersion=1 must round-trip unchanged')
    assert request.model_dump(mode='json')['configuration'] == modern
    assert contract.PrepareStrategyRequest.model_validate(request).model_dump(mode='json') == request.model_dump(mode='json')
    current = snapshot(contract, request.configuration)
    assert current['configuration'] == modern
    assert contract.configuration_digest(current) != contract.configuration_digest(old_snapshot)
    assert json.dumps(snapshot(contract, legacy), ensure_ascii=False, sort_keys=True, separators=(',', ':')) == old_bytes


@pytest.mark.parametrize('policy', [None, True, False, 1.0, 0, 2, '1'])
def test_schedule_policy_rejects_nonexact_version(contract, policy):
    with pytest.raises(ValidationError):
        contract.ResearchStrategyConfiguration.model_validate(config() | {'schedule': schedule() | {'policyVersion': policy}})


@pytest.mark.parametrize('mode', ['once', 'monitor'])
def test_versioned_interval_rejects_equal_bounds_without_changing_legacy(contract, mode):
    legacy = config() | {'mode': mode, 'schedule': schedule() | {'kind': 'interval', 'start': '08:00', 'end': '08:00'}}
    assert contract.ResearchStrategyConfiguration.model_validate(legacy).model_dump(mode='json') == legacy
    modern = legacy | {'schedule': legacy['schedule'] | {'policyVersion': 1}}
    with pytest.raises(ValidationError):
        contract.ResearchStrategyConfiguration.model_validate(modern)
    for changes in ({'end': '07:00'}, {'kind': 'daily'}):
        valid = modern | {'schedule': modern['schedule'] | changes}
        assert contract.ResearchStrategyConfiguration.model_validate(valid).model_dump(mode='json') == valid


def test_policy_schedule_unknown_fields_and_forged_instances_are_rejected(contract):
    data = config() | {'schedule': schedule() | {'policyVersion': 1}}
    with pytest.raises(ValidationError):
        contract.ResearchStrategyConfiguration.model_validate(data | {'schedule': data['schedule'] | {'authority': True}})
    try:
        valid = contract.ResearchStrategyConfiguration.model_validate(data)
    except ValidationError:
        pytest.fail('versioned schedule must be available before instance revalidation')
    forged = valid.model_copy(update={'schedule': valid.schedule.model_copy(update={'policyVersion': True})})
    with pytest.raises(contract.StrategyStoreError, match='invalid_request'):
        snapshot(contract, forged)


def prepare():
    return dict(schema_version="strategy-confirmation-v1", request_id=REQUEST,
                draft_id=DRAFT, draft_revision=1, profile_version_id=PROFILE,
                configuration=config(), platforms=["PUBLIC_WEB", "ZHIHU"],
                max_records=25, max_runtime_seconds=180)


def confirm():
    return dict(schema_version="strategy-confirmation-v1", request_id=REQUEST,
                strategy_version_id=STRATEGY, configuration_sha256="a" * 64,
                human_confirmed=True)


def revoke():
    return dict(schema_version="strategy-confirmation-v1", request_id=REQUEST,
                strategy_version_id=STRATEGY)


def snapshot(contract, configuration=None, **changes):
    values = dict(profile_version_id=PROFILE, strategy_version_id=STRATEGY,
                  configuration=config() if configuration is None else configuration,
                  platforms=["PUBLIC_WEB", "ZHIHU"], max_records=25,
                  max_runtime_seconds=180)
    values.update(changes)
    return contract.strategy_snapshot(**values)


def test_module_and_all_public_interfaces_exist():
    assert importlib.util.find_spec("pilot.research_strategy_contract") is not None, (
        "Task 1 requires the research strategy contract module"
    )
    contract = importlib.import_module("pilot.research_strategy_contract")
    for name in ("ResearchStrategyConfiguration", "PrepareStrategyRequest",
                 "ConfirmStrategyRequest", "RevokeStrategyRequest", "StrategyStoreError",
                 "strategy_snapshot", "configuration_digest"):
        assert hasattr(contract, name)


@pytest.mark.parametrize("name,factory", [
    ("ResearchStrategyConfiguration", config), ("PrepareStrategyRequest", prepare),
    ("ConfirmStrategyRequest", confirm), ("RevokeStrategyRequest", revoke),
])
def test_valid_chinese_configuration_and_operations_round_trip(contract, name, factory):
    model = getattr(contract, name).model_validate(factory())
    assert model.model_dump(mode="json") == factory()
    assert getattr(contract, name).model_validate_json(json.dumps(factory())) == model
    assert model.model_config["strict"] is True
    assert model.model_config["frozen"] is True
    assert model.model_config["extra"] == "forbid"
    assert model.model_config["hide_input_in_errors"] is True
    assert model.model_config["revalidate_instances"] == "always"
    with pytest.raises(ValidationError):
        model.schema_version = "changed"


@pytest.mark.parametrize("name,factory", [
    ("ResearchStrategyConfiguration", config), ("PrepareStrategyRequest", prepare),
    ("ConfirmStrategyRequest", confirm), ("RevokeStrategyRequest", revoke),
])
def test_every_public_field_is_required_and_extras_rejected(contract, name, factory):
    cls = getattr(contract, name)
    for key in factory():
        data = factory()
        del data[key]
        with pytest.raises(ValidationError):
            cls.model_validate(data)
    data = factory()
    data["authority"] = "SYNTHETIC_SECRET_MUST_NOT_APPEAR"
    with pytest.raises(ValidationError) as error:
        cls.model_validate(data)
    assert "SYNTHETIC_SECRET_MUST_NOT_APPEAR" not in str(error.value)


@pytest.mark.parametrize("field,value", [
    ("name", ""), ("name", " " * 2), ("name", "中" * 61), ("name", 1),
    ("name", "第一行\n第二行"), ("name", "bad\x00name"), ("name", "bad\x7fname"),
    ("name", "bad\x85name"), ("name", "bad\ud800name"),
    ("keywords", []), ("keywords", ["a"] * 21), ("keywords", ["x" * 81]),
    ("keywords", [1]), ("keywords", [""]), ("keywords", ["  "]),
    ("keywords", ["a\tb"]), ("keywords", ["a\r\nb"]),
    ("keywords", ["a\u2028b"]), ("keywords", ["a\u200bb"]),
    ("keywords", ["Equipment  BUY", " equipment buy "]),
    ("exclusions", ["A", " a "]), ("exclusions", ["采购"]),
    ("exclusions", ["crm  服务"]), ("exclusions", ["x"] * 21),
    ("source", "PUBLIC_WEB"), ("source", True), ("mode", "repeat"),
    ("links", ["https://example.com/a"] * 2),
    ("links", ["https://example.com/" + str(i) for i in range(101)]),
    ("research", {}), ("research", False), ("schedule", False),
])
def test_invalid_configuration_fields(contract, field, value):
    data = config()
    data[field] = value
    with pytest.raises(ValidationError):
        contract.ResearchStrategyConfiguration.model_validate(data)


@pytest.mark.parametrize("url", [
    "ftp://example.com/a", "https://localhost/a", "https://127.0.0.1/a",
    "https://192.168.1.2/a", "https://[::1]/a", "https://2130706433/a",
    "https://example.com:444/a", "https://user:synthetic@example.com/a",
    "https://example.com/a?token=synthetic", "https://example.com/a%0ab",
    "https://example.com/a\\b", "https://example.com/" + "a" * 2048,
    "https://example.com/\udfff", 123,
])
def test_links_reuse_public_web_url_contract(contract, url):
    from pilot.candidate_contract import _validate_url
    with pytest.raises(ValueError):
        _validate_url(url, "PUBLIC_WEB")
    data = config()
    data["links"] = [url]
    with pytest.raises(ValidationError):
        contract.ResearchStrategyConfiguration.model_validate(data)


def test_source_switch_keeps_inputs_and_changes_digest(contract):
    data = config()
    first = snapshot(contract, data)
    data["source"] = "links"
    second = snapshot(contract, data)
    assert second["configuration"]["keywords"] == first["configuration"]["keywords"]
    assert second["configuration"]["links"] == first["configuration"]["links"]
    assert contract.configuration_digest(first) != contract.configuration_digest(second)
    data["source"] = "search"
    assert snapshot(contract, data) == first
    data["source"], data["keywords"] = "links", []
    assert snapshot(contract, data)["configuration"]["keywords"] == []
    data["links"] = []
    with pytest.raises(ValidationError):
        contract.ResearchStrategyConfiguration.model_validate(data)


@pytest.mark.parametrize("field,value", [
    ("kind", "weekly"), ("times", []), ("times", ["09:00", "09:00"]),
    ("times", ["9:00"]), ("times", ["24:00"]), ("times", ["12:60"]),
    ("times", ["09:00\n"]), ("times", [1]),
    ("interval", True), ("interval", "2"), ("interval", 0), ("interval", 169),
    ("interval", float("nan")), ("interval", float("inf")),
    ("start", "24:01"), ("end", "-1:00"), ("timezone", "Mars/Olympus"),
    ("timezone", "../UTC"), ("timezone", ""), ("timezone", None),
])
def test_invalid_schedule(contract, field, value):
    data = config()
    data["mode"], data["schedule"] = "monitor", schedule()
    data["schedule"][field] = value
    with pytest.raises(ValidationError):
        contract.ResearchStrategyConfiguration.model_validate(data)


def test_schedule_is_required_for_monitor_and_preserved_in_once(contract):
    data = config()
    data["mode"] = "monitor"
    with pytest.raises(ValidationError):
        contract.ResearchStrategyConfiguration.model_validate(data)
    data["mode"], data["schedule"] = "once", schedule()
    assert snapshot(contract, data)["configuration"]["schedule"] == schedule()
    data["schedule"].update(kind="interval", times=[], interval=168)
    assert snapshot(contract, data)["configuration"]["schedule"]["interval"] == 168
    for key in schedule():
        changed = deepcopy(data)
        del changed["schedule"][key]
        with pytest.raises(ValidationError):
            contract.ResearchStrategyConfiguration.model_validate(changed)


@pytest.mark.parametrize("field,value", [
    ("version", True), ("version", 1.0), ("version", "1"), ("version", 2),
    ("demandTypes", []), ("demandTypes", ["INQUIRY", "INQUIRY"]),
    ("demandTypes", ["UNKNOWN"]), ("maxSoubei", True), ("maxSoubei", 1.0),
    ("maxSoubei", 0), ("maxSoubei", 1000001),
    ("stopAtAnyLimit", 1), ("stopAtAnyLimit", False),
    ("evidenceOrder", "CONTEXT_FIRST"), ("provenance", {"verified": True}),
])
def test_research_exact_types_enums_and_provenance_rejection(contract, field, value):
    data = config()
    data["research"][field] = value
    with pytest.raises(ValidationError):
        contract.ResearchStrategyConfiguration.model_validate(data)


@pytest.mark.parametrize("field", ["sources", "minutes", "modelCalls"])
@pytest.mark.parametrize("value", [True, 1.0, "1", 0, 1000001])
def test_all_research_limits_are_independent_strict_bounded_integers(contract, field, value):
    data = config()
    data["research"]["limits"][field] = value
    with pytest.raises(ValidationError):
        contract.ResearchStrategyConfiguration.model_validate(data)


def test_research_all_fields_required_or_whole_research_explicit_null(contract):
    for key in config()["research"]:
        data = config()
        del data["research"][key]
        with pytest.raises(ValidationError):
            contract.ResearchStrategyConfiguration.model_validate(data)
    for key in config()["research"]["limits"]:
        data = config()
        del data["research"]["limits"][key]
        with pytest.raises(ValidationError):
            contract.ResearchStrategyConfiguration.model_validate(data)
    data = config()
    data["research"] = None
    assert snapshot(contract, data)["configuration"]["research"] is None


@pytest.mark.parametrize("field,value", [
    ("draft_revision", True), ("draft_revision", 1.0), ("draft_revision", 0),
    ("draft_revision", 2147483648), ("max_records", True), ("max_records", 1.0),
    ("max_records", "25"), ("max_records", 0), ("max_records", 10001),
    ("max_runtime_seconds", True), ("max_runtime_seconds", 1.0),
    ("max_runtime_seconds", 0), ("max_runtime_seconds", 86401),
    ("platforms", []), ("platforms", ["PUBLIC_WEB", "PUBLIC_WEB"]),
    ("platforms", ["public_web"]), ("platforms", [1]),
    ("request_id", REQUEST.upper()), ("request_id", UUID(REQUEST)),
    ("request_id", REQUEST.replace("-", "")), ("request_id", "{" + REQUEST + "}"),
    ("draft_id", "draft"), ("profile_version_id", "profile"),
])
def test_prepare_requires_exact_identifiers_platforms_and_budgets(contract, field, value):
    data = prepare()
    data[field] = value
    with pytest.raises(ValidationError):
        contract.PrepareStrategyRequest.model_validate(data)


@pytest.mark.parametrize("field,value", [
    ("human_confirmed", 1), ("human_confirmed", "true"), ("human_confirmed", False),
    ("configuration_sha256", "A" * 64), ("configuration_sha256", "g" * 64),
    ("configuration_sha256", "a" * 63), ("configuration_sha256", "a" * 64 + "\n"),
    ("strategy_version_id", "invalid"), ("request_id", REQUEST.upper()),
])
def test_confirmation_is_exact_and_bound(contract, field, value):
    data = confirm()
    data[field] = value
    with pytest.raises(ValidationError):
        contract.ConfirmStrategyRequest.model_validate(data)


def test_nested_instances_and_model_copy_revalidated_before_serialization(contract):
    cls = contract.ResearchStrategyConfiguration
    original = cls.model_validate(config())
    for forged in (
        original.model_copy(update={"research": original.research.model_copy(update={"version": True})}),
        original.model_copy(update={"research": original.research.model_copy(update={"stopAtAnyLimit": 1})}),
        original.model_copy(update={"research": original.research.model_copy(update={
            "limits": original.research.limits.model_copy(update={"sources": True})})}),
        original.model_copy(update={"authority": "APPROVED"}),
        original.model_copy(update={"keywords": ["x", " X "]}),
    ):
        with pytest.raises(ValidationError):
            cls.model_validate(forged)
        data = prepare()
        data["configuration"] = forged
        with pytest.raises(ValidationError):
            contract.PrepareStrategyRequest.model_validate(data)
        with pytest.raises(contract.StrategyStoreError):
            snapshot(contract, forged)
    for name, factory, changes in (
        ("PrepareStrategyRequest", prepare, {"max_records": True}),
        ("ConfirmStrategyRequest", confirm, {"human_confirmed": 1}),
        ("RevokeStrategyRequest", revoke, {"strategy_version_id": "invalid"}),
    ):
        model_cls = getattr(contract, name)
        forged = model_cls.model_validate(factory()).model_copy(update=changes)
        with pytest.raises(ValidationError):
            model_cls.model_validate(forged)


def test_configuration_utf8_byte_limit(contract):
    data = config()
    data["links"] = ["https://example.com/" + str(i) + "/" + "中" * 600 for i in range(40)]
    assert len(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > 65536
    with pytest.raises(ValidationError):
        contract.ResearchStrategyConfiguration.model_validate(data)
    data["links"] = data["links"][:20]
    assert snapshot(contract, data)["configuration"] == data


def test_configuration_exact_65536_byte_boundary(contract):
    data = config()
    data["links"] = [f"https://example.com/{i:03}/" for i in range(32)]
    byte_count = lambda: len(json.dumps(data, ensure_ascii=False, sort_keys=True,
                                       separators=(",", ":"), allow_nan=False).encode("utf-8"))
    for index, link in enumerate(data["links"]):
        data["links"][index] += "a" * min(2048 - len(link), 65536 - byte_count())
    assert byte_count() == 65536
    assert snapshot(contract, data)["configuration"] == data
    data["links"][-1] += "a"
    assert byte_count() == 65537 and len(data["links"][-1]) <= 2048
    with pytest.raises(ValidationError):
        contract.ResearchStrategyConfiguration.model_validate(data)


def test_all_positive_boundaries_and_inactive_empty_arrays(contract):
    data = prepare()
    data.update(draft_revision=2147483647, max_records=10000, max_runtime_seconds=86400,
                platforms=["XIAOHONGSHU", "DOUYIN", "BILIBILI", "ZHIHU", "PUBLIC_WEB"])
    data["configuration"].update(name="中" * 60, links=[], exclusions=[],
                                 keywords=[f"词{i:02}" + "中" * 77 for i in range(20)])
    data["configuration"]["research"].update(
        maxSoubei=1000000, demandTypes=["INQUIRY", "COMPARISON", "REPLACEMENT", "CHANGE"],
        limits=dict(sources=1000000, minutes=1, modelCalls=1000000))
    assert contract.PrepareStrategyRequest.model_validate(data).model_dump(mode="json") == data


def test_nested_extra_fields_and_constructed_instances_are_not_trusted(contract):
    original = contract.ResearchStrategyConfiguration.model_validate(config())
    for forged in (
        original.model_copy(update={"research": original.research.model_copy(update={"provenance": {}})}),
        original.model_copy(update={"research": original.research.model_copy(update={
            "limits": original.research.limits.model_copy(update={"authority": True})})}),
        contract.ResearchStrategyConfiguration.model_construct(name="not fully constructed"),
    ):
        with pytest.raises(ValidationError):
            contract.ResearchStrategyConfiguration.model_validate(forged)
    data = config()
    data["schedule"] = schedule()
    parsed = contract.ResearchStrategyConfiguration.model_validate(data)
    for changes in ({"interval": True}, {"authority": True}):
        forged = parsed.model_copy(update={"schedule": parsed.schedule.model_copy(update=changes)})
        with pytest.raises(ValidationError):
            contract.ResearchStrategyConfiguration.model_validate(forged)


@pytest.mark.parametrize("field,value", [
    ("demandTypes", ["CHANGE"]), ("maxSoubei", 101), ("limits", dict(sources=21, minutes=30, modelCalls=10)),
    ("limits", dict(sources=20, minutes=31, modelCalls=10)),
    ("limits", dict(sources=20, minutes=30, modelCalls=11)),
])
def test_each_research_setting_changes_digest_without_changing_technical_limits(contract, field, value):
    original = snapshot(contract)
    configuration = config()
    configuration["research"][field] = value
    changed = snapshot(contract, configuration)
    assert contract.configuration_digest(changed) != contract.configuration_digest(original)
    assert (changed["max_records"], changed["max_runtime_seconds"]) == (25, 180)


def test_snapshot_and_digest_match_mac_exact_canonical_algorithm(contract):
    from pilot.execution_runtime import _hash
    parsed = contract.ResearchStrategyConfiguration.model_validate(config())
    value = snapshot(contract, parsed, platforms=("PUBLIC_WEB", "ZHIHU"))
    assert set(value) == {"profile_version_id", "strategy_version_id", "configuration",
                          "platforms", "max_records", "max_runtime_seconds"}
    assert value["configuration"] == config()
    assert type(value["platforms"]) is list
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert contract.configuration_digest(value) == _hash(value) == expected
    assert contract.configuration_digest(dict(reversed(list(value.items())))) == expected
    for changes in ({"platforms": ["ZHIHU", "PUBLIC_WEB"]}, {"max_records": 26},
                    {"max_runtime_seconds": 181}, {"strategy_version_id": REQUEST},
                    {"profile_version_id": DRAFT}):
        assert contract.configuration_digest(snapshot(contract, **changes)) != expected
    changed = config()
    changed["research"]["maxSoubei"] += 1
    assert contract.configuration_digest(snapshot(contract, changed)) != expected


@pytest.mark.parametrize("field,value", [
    ("profile_version_id", "bad"), ("strategy_version_id", "bad"),
    ("max_records", True), ("max_records", 1.0), ("max_runtime_seconds", True),
    ("platforms", ["PUBLIC_WEB", "PUBLIC_WEB"]), ("configuration", {"arbitrary": True}),
])
def test_snapshot_revalidates_every_value(contract, field, value):
    with pytest.raises(contract.StrategyStoreError) as error:
        snapshot(contract, **{field: value})
    assert (error.value.code, error.value.status) == ("invalid_request", 422)


def test_digest_rejects_non_json_extra_authority_missing_and_forged_values(contract):
    valid = snapshot(contract)
    invalid = [dict(valid, authority="APPROVED"), dict(valid, max_records=True),
               dict(valid, platforms=("PUBLIC_WEB", "ZHIHU")),
               dict(valid, configuration=contract.ResearchStrategyConfiguration.model_validate(config())),
               dict(valid, max_records=float("nan")), dict(valid, max_runtime_seconds=object()),
               dict(valid, configuration=dict(config(), name="bad\ud800"))]
    for key in valid:
        invalid.append({k: v for k, v in valid.items() if k != key})
    for value in invalid:
        with pytest.raises(contract.StrategyStoreError) as error:
            contract.configuration_digest(value)
        assert (error.value.code, error.value.status) == ("invalid_request", 422)


@pytest.mark.parametrize("code,status", [
    ("invalid_request", 422), ("invalid_session", 401), ("request_not_found", 404),
    ("strategy_not_found", 404), ("request_conflict", 409), ("draft_conflict", 409),
    ("strategy_conflict", 409), ("profile_unavailable", 409), ("strategy_store_unavailable", 503),
])
def test_store_errors_are_sealed(contract, code, status):
    error = contract.StrategyStoreError(code, status)
    assert (error.code, error.status, str(error)) == (code, status, code)
    fallback = contract.StrategyStoreError(code, 200)
    assert (fallback.code, fallback.status) == ("strategy_store_unavailable", 503)


@pytest.mark.parametrize("code,status", [
    ("invalid_request", 422), ("invalid_session", 401), ("request_not_found", 404),
    ("strategy_not_found", 404), ("request_conflict", 409), ("draft_conflict", 409),
    ("strategy_conflict", 409), ("profile_unavailable", 409), ("strategy_store_unavailable", 503),
])
def test_store_error_omitted_status_uses_sealed_code_mapping(contract, code, status):
    error = contract.StrategyStoreError(code)
    assert (error.code, error.status) == (code, status)


@pytest.mark.parametrize("code,status", [
    ("SYNTHETIC_SECRET", 500), ("invalid_request", "422"), ("request_conflict", True),
    ([], 409), (None, None),
])
def test_unknown_or_wrong_status_errors_never_echo_input(contract, code, status):
    error = contract.StrategyStoreError(code, status)
    assert (error.code, error.status, str(error)) == (
        "strategy_store_unavailable", 503, "strategy_store_unavailable")
