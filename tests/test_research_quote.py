from dataclasses import replace
from datetime import UTC, datetime, timedelta
import importlib.util
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pilot.auth import InvalidPilotToken


def implementation():
    assert importlib.util.find_spec("pilot.research_quote") is not None, "missing research quote service"
    from pilot import research_quote
    return research_quote


class FakeStrategies:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def read_snapshot(self, cursor, claims, profile, strategy):
        assert (profile, strategy) == (self.snapshot["profile_version_id"], self.snapshot["strategy_version_id"])
        return self.snapshot


class FakeCursor:
    description = None

    def __init__(self, database):
        self.database = database
        self.connection = SimpleNamespace(autocommit=False)

    def __enter__(self): return self
    def __exit__(self, *_): pass

    def execute(self, statement, params=()):
        self.database.statements.append(str(statement))
        if "clock_timestamp" in str(statement):
            self.row = (self.database.now,)
        elif "pilot_research_strategy_versions" in str(statement):
            self.row = (self.database.draft_id, self.database.revision)
        else:
            self.row = (None, None)
        return self

    def fetchone(self): return self.row


class FakeConnection:
    def __init__(self, database): self.database = database
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def cursor(self): return FakeCursor(self.database)
    def execute(self, statement, params=()): return FakeCursor(self.database).execute(statement, params)


class FakeDatabase:
    def __init__(self, draft_id, revision):
        self.draft_id, self.revision = draft_id, revision
        self.now = datetime(2026, 9, 11, 4, 0, tzinfo=UTC)
        self.statements = []
    def connect(self): return FakeConnection(self)


def fixture():
    module = implementation()
    strategy, profile, draft = str(uuid4()), str(uuid4()), str(uuid4())
    configuration_sha = "a" * 64
    snapshot = {
        "profile_version_id": profile,
        "strategy_version_id": strategy,
        "configuration_sha256": configuration_sha,
        "platforms": ["PUBLIC_WEB"],
        "max_records": 10,
        "max_runtime_seconds": 600,
        "configuration": {"mode": "once", "research": {
            "version": 1, "maxSoubei": 30,
            "limits": {"sources": 10, "minutes": 10, "modelCalls": 10},
        }},
    }
    database = FakeDatabase(draft, 7)
    claims = SimpleNamespace(user_id="user-1")
    request = {
        "contractVersion": 1, "requestId": str(uuid4()), "userId": claims.user_id,
        "accountScopeId": "tenant-1", "accountScopeVersion": 1,
        "draftId": draft, "revision": 7, "configurationHash": "b" * 64,
        "maxSoubei": 30, "strategyBinding": {
            "strategyVersionId": strategy, "profileVersionId": profile,
            "configurationSha256": configuration_sha,
        },
    }
    service = module.ResearchQuoteService(database, FakeStrategies(snapshot),
        rule=module.ResearchQuoteRule("quote-rule-v1", 100, 200, 300),
        signing_secret=b"s" * 32, research_capability=lambda value: True)
    service.sessions.authenticate = lambda value: "tenant-1"
    return module, service, claims, request


def test_quote_binds_confirmed_strategy_and_calculates_ceiling():
    _, service, claims, request = fixture()
    result = service.quote(claims, request)
    assert result["strategyBinding"] == request["strategyBinding"]
    assert result["estimatedSoubei"] == 6
    assert result["expiresAt"] == "2026-09-11T04:05:00.000Z"
    assert "上限" in result["basis"] and "未预留" in result["basis"]
    assert any("REPEATABLE READ READ ONLY" in sql for sql in service.database.statements)


def test_quote_rejects_limit_and_missing_capability():
    module, service, claims, request = fixture()
    service.strategies.snapshot["configuration"]["research"]["maxSoubei"] = 5
    with pytest.raises(module.ResearchQuoteError) as caught:
        service.quote(claims, request | {"maxSoubei": 5})
    assert (caught.value.code, caught.value.status) == ("usage_limit_exceeded", 409)
    service.research_capability = None
    with pytest.raises(module.ResearchQuoteError) as caught:
        service.quote(claims, request)
    assert (caught.value.code, caught.value.status) == ("capability_unavailable", 501)


@pytest.mark.parametrize("change", ["body", "expired", "rule"])
def test_verify_rejects_tampering_expiry_and_rule_change(change):
    module, service, claims, request = fixture()
    quote = service.quote(claims, request)
    token = quote["authorizationToken"]
    now = datetime.fromisoformat(quote["generatedAt"])
    if change == "body":
        token = ("A" if token[0] != "A" else "B") + token[1:]
    elif change == "expired":
        now += timedelta(seconds=301)
    else:
        service.rule = replace(service.rule, sourceMilli=101)
    with pytest.raises(module.ResearchQuoteError) as caught:
        service.verify(token, now=now)
    assert (caught.value.code, caught.value.status) == ("quote_invalid", 409)


def test_verify_returns_complete_response_without_token():
    _, service, claims, request = fixture()
    quote = service.quote(claims, request)
    verified = service.verify(quote["authorizationToken"], now=datetime.fromisoformat(quote["generatedAt"]))
    assert verified == {key: value for key, value in quote.items() if key != "authorizationToken"}


@pytest.mark.parametrize("changed_tenant", [False, True])
def test_quote_rechecks_session_after_snapshot_before_signing(changed_tenant):
    module, service, claims, request = fixture()
    calls = 0
    def active(_claims):
        nonlocal calls
        calls += 1
        if calls == 2 and not changed_tenant:
            raise InvalidPilotToken("revoked during snapshot")
        return "tenant-2" if calls == 2 else "tenant-1"
    service.sessions.authenticate = active
    with pytest.raises(module.ResearchQuoteError) as caught:
        service.quote(claims, request)
    assert calls == 2
    assert (caught.value.code, caught.value.status) == ("invalid_session", 401)


def test_verify_rejects_before_generated_time_and_non_300_second_window():
    module, service, claims, request = fixture()
    quote = service.quote(claims, request)
    generated = datetime.fromisoformat(quote["generatedAt"])
    with pytest.raises(module.ResearchQuoteError, match="quote_invalid"):
        service.verify(quote["authorizationToken"], now=generated - timedelta(microseconds=1))
    decoded = service.verify(quote["authorizationToken"], now=generated)
    assert datetime.fromisoformat(decoded["expiresAt"]) - datetime.fromisoformat(decoded["generatedAt"]) == timedelta(seconds=300)


@pytest.mark.parametrize("field,value", [
    ("expiresAt", "2026-09-11T04:05:01+00:00"),
    ("generatedAt", "2026-09-11T04:00:00"),
    ("expiresAt", "2026-09-11T04:05:00"),
])
def test_verify_rejects_signed_invalid_time_window(field, value):
    import hashlib, hmac
    module, service, claims, request = fixture()
    quote = service.quote(claims, request)
    payload = {key: item for key, item in quote.items() if key != "authorizationToken"} | {field: value}
    raw = module._canonical(payload)
    signature = hmac.new(service.signing_secret, module._TOKEN_DOMAIN + raw, hashlib.sha256).digest()
    token = module._b64_encode(raw) + "." + module._b64_encode(signature)
    with pytest.raises(module.ResearchQuoteError, match="quote_invalid"):
        service.verify(token, now=datetime(2026, 9, 11, 4, 0, tzinfo=UTC))


@pytest.mark.parametrize("value", ["x\u2028y", "x\u2029y", "x\u200by"])
def test_request_rejects_line_paragraph_and_format_separators(value):
    module, service, claims, request = fixture()
    with pytest.raises(module.ResearchQuoteError) as caught:
        service.quote(claims, request | {"accountScopeId": value})
    assert (caught.value.code, caught.value.status) == ("invalid_request", 422)


def test_error_code_and_status_are_allowlisted():
    module = implementation()
    error = module.ResearchQuoteError("client_supplied", 418)
    assert (error.code, error.status) == ("quote_unavailable", 503)
