"""Read-only, confirmed-strategy-bound research usage quotations."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import base64
import hashlib
import hmac
import json
import re
import unicodedata
from uuid import UUID, uuid4

import psycopg

from pilot.auth import InvalidPilotToken
from pilot.execution_contract import ExecutionRuntimeError
from pilot.sessions import PilotSessionRegistry


_SHA256 = re.compile(r"[0-9a-f]{64}")
_REQUEST_KEYS = {"contractVersion", "requestId", "userId", "accountScopeId",
    "accountScopeVersion", "draftId", "revision", "configurationHash", "maxSoubei",
    "strategyBinding"}
_BINDING_KEYS = {"strategyVersionId", "profileVersionId", "configurationSha256"}
_TOKEN_DOMAIN = b"yike-research-quote-v1\0"


def _utc_instant(value: datetime) -> str:
    """Emit one browser-safe, unambiguous UTC timestamp for quote deadlines."""
    aware = value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    return aware.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class ResearchQuoteError(ValueError):
    def __init__(self, code: str, status: int = 409):
        allowed = {"invalid_request": 422, "invalid_session": 401, "strategy_conflict": 409,
            "usage_limit_exceeded": 409, "capability_unavailable": 501,
            "quote_unavailable": 503, "quote_invalid": 409}
        self.code = code if allowed.get(code) == status else "quote_unavailable"
        self.status = status if self.code == code else 503
        super().__init__(self.code)


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _visible(value: object, maximum: int) -> bool:
    forbidden = {"Cc", "Cf", "Cs", "Zl", "Zp"}
    return (type(value) is str and 0 < len(value) <= maximum and value.strip() == value
            and any(unicodedata.category(ch) not in forbidden and not ch.isspace() for ch in value)
            and all(unicodedata.category(ch) not in forbidden for ch in value))


def _uuid(value: object) -> bool:
    try:
        return type(value) is str and len(value) == 36 and str(UUID(value)) == value
    except (TypeError, ValueError):
        return False


def _b64_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64_decode(value: str) -> bytes:
    return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)


@dataclass(frozen=True)
class ResearchQuoteRule:
    ruleVersion: str
    sourceMilli: int
    minuteMilli: int
    modelCallMilli: int

    def __post_init__(self):
        if (not _visible(self.ruleVersion, 512)
                or any(type(value) is not int or not 1 <= value <= 1_000_000
                       for value in (self.sourceMilli, self.minuteMilli, self.modelCallMilli))):
            raise ValueError("invalid research quote rule")

    def public(self) -> dict:
        return {"ruleVersion": self.ruleVersion, "sourceMilli": self.sourceMilli,
                "minuteMilli": self.minuteMilli, "modelCallMilli": self.modelCallMilli}

    def digest(self) -> str:
        return hashlib.sha256(_canonical(self.public())).hexdigest()


class ResearchQuoteService:
    def __init__(self, database, strategies, rule=None, signing_secret=None, research_capability=None):
        self.database = getattr(database, "database", database)
        self.strategies = strategies
        self.rule = rule
        self.signing_secret = signing_secret
        self.research_capability = research_capability
        self.sessions = PilotSessionRegistry(self.database)

    @staticmethod
    def _request(value):
        try:
            if type(value) is not dict or set(value) != _REQUEST_KEYS:
                raise ValueError
            binding = value["strategyBinding"]
            if type(binding) is not dict or set(binding) != _BINDING_KEYS:
                raise ValueError
            if (type(value["contractVersion"]) is not int or value["contractVersion"] != 1
                    or type(value["accountScopeVersion"]) is not int or value["accountScopeVersion"] != 1
                    or not _uuid(value["requestId"]) or not _uuid(binding["strategyVersionId"])
                    or not _uuid(binding["profileVersionId"])
                    or not _visible(value["userId"], 512) or not _visible(value["accountScopeId"], 512)
                    or not _visible(value["draftId"], 512)
                    or type(value["revision"]) is not int or not 1 <= value["revision"] <= 1_000_000
                    or type(value["maxSoubei"]) is not int or not 1 <= value["maxSoubei"] <= 1_000_000
                    or type(value["configurationHash"]) is not str
                    or not _SHA256.fullmatch(value["configurationHash"])
                    or type(binding["configurationSha256"]) is not str
                    or not _SHA256.fullmatch(binding["configurationSha256"])):
                raise ValueError
        except (KeyError, TypeError, ValueError, UnicodeError):
            raise ResearchQuoteError("invalid_request", 422) from None
        return value

    def _available(self):
        return (isinstance(self.rule, ResearchQuoteRule)
                and type(self.signing_secret) is bytes and len(self.signing_secret) >= 32
                and callable(self.research_capability))

    def quote(self, claims, raw_request) -> dict:
        request = self._request(raw_request)
        try:
            tenant = self.sessions.authenticate(claims)
        except (InvalidPilotToken, PermissionError):
            raise ResearchQuoteError("invalid_session", 401) from None
        except psycopg.Error:
            raise ResearchQuoteError("quote_unavailable", 503) from None
        if not self._available():
            raise ResearchQuoteError("capability_unavailable", 501)
        if request["userId"] != claims.user_id or request["accountScopeId"] != tenant:
            raise ResearchQuoteError("strategy_conflict", 409)
        binding = request["strategyBinding"]
        try:
            with self.database.connect() as connection:
                connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                connection.execute("SELECT set_config('yike.user_id',%s,true),set_config('yike.tenant_id',%s,true)",
                                   (claims.user_id, tenant))
                with connection.cursor() as cursor:
                    snapshot = self.strategies.read_snapshot(cursor, claims,
                        binding["profileVersionId"], binding["strategyVersionId"])
                    cursor.execute("SELECT draft_id,draft_revision FROM pilot_research_strategy_versions "
                        "WHERE tenant_id=%s AND owner_user_id=%s AND strategy_version_id=%s",
                        (tenant, claims.user_id, binding["strategyVersionId"]))
                    row = cursor.fetchone()
                    cursor.execute("SELECT clock_timestamp()")
                    generated = cursor.fetchone()[0]
        except ExecutionRuntimeError as error:
            status = 401 if error.code == "invalid_session" else 503 if error.status == 503 else 409
            code = "invalid_session" if status == 401 else "quote_unavailable" if status == 503 else "strategy_conflict"
            raise ResearchQuoteError(code, status) from None
        except psycopg.Error:
            raise ResearchQuoteError("quote_unavailable", 503) from None
        try:
            current_tenant = self.sessions.authenticate(claims)
        except (InvalidPilotToken, PermissionError):
            raise ResearchQuoteError("invalid_session", 401) from None
        except psycopg.Error:
            raise ResearchQuoteError("quote_unavailable", 503) from None
        if current_tenant != tenant:
            raise ResearchQuoteError("invalid_session", 401)
        if (row != (request["draftId"], request["revision"])
                or snapshot.get("configuration_sha256") != binding["configurationSha256"]):
            raise ResearchQuoteError("strategy_conflict", 409)
        configuration = snapshot.get("configuration")
        research = configuration.get("research") if type(configuration) is dict else None
        limits = research.get("limits") if type(research) is dict else None
        if (not isinstance(generated, datetime) or type(configuration) is not dict
                or configuration.get("mode") != "once" or type(research) is not dict
                or type(limits) is not dict or set(limits) != {"sources", "minutes", "modelCalls"}
                or research.get("maxSoubei") != request["maxSoubei"]
                or any(type(limits.get(key)) is not int or not 1 <= limits[key] <= 1_000_000
                       for key in ("sources", "minutes", "modelCalls"))):
            raise ResearchQuoteError("strategy_conflict", 409)
        try:
            capable = self.research_capability(snapshot)
        except Exception:
            capable = False
        if capable is not True:
            raise ResearchQuoteError("capability_unavailable", 501)
        total = (limits["sources"] * self.rule.sourceMilli
                 + limits["minutes"] * self.rule.minuteMilli
                 + limits["modelCalls"] * self.rule.modelCallMilli)
        estimated = (total + 999) // 1000
        if estimated > request["maxSoubei"]:
            raise ResearchQuoteError("usage_limit_exceeded", 409)
        generated = generated.astimezone(UTC) if generated.tzinfo else generated.replace(tzinfo=UTC)
        response = dict(request)
        response.update(quoteId=str(uuid4()), ruleVersion=self.rule.ruleVersion,
            ruleSha256=self.rule.digest(), estimatedSoubei=estimated,
            generatedAt=_utc_instant(generated), expiresAt=_utc_instant(generated + timedelta(seconds=300)),
            basis="按确认策略各项限制计算的资源上限；未预留资源，也不是实际消耗预测。")
        payload = _canonical(response)
        signature = hmac.new(self.signing_secret, _TOKEN_DOMAIN + payload, hashlib.sha256).digest()
        response["authorizationToken"] = _b64_encode(payload) + "." + _b64_encode(signature)
        if len(response["authorizationToken"]) > 8192:
            raise ResearchQuoteError("quote_unavailable", 503)
        return response

    def verify(self, authorization_token, now=None) -> dict:
        try:
            if not self._available() or type(authorization_token) is not str or not authorization_token or len(authorization_token) > 8192:
                raise ValueError
            encoded, signed = authorization_token.split(".")
            payload, signature = _b64_decode(encoded), _b64_decode(signed)
            expected = hmac.new(self.signing_secret, _TOKEN_DOMAIN + payload, hashlib.sha256).digest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError
            value = json.loads(payload.decode("utf-8"))
            if type(value) is not dict or value.get("ruleVersion") != self.rule.ruleVersion or value.get("ruleSha256") != self.rule.digest():
                raise ValueError
            current = now or datetime.now(UTC)
            generated, expires = datetime.fromisoformat(value["generatedAt"]), datetime.fromisoformat(value["expiresAt"])
            if (current.tzinfo is None or generated.tzinfo is None or expires.tzinfo is None
                    or expires - generated != timedelta(seconds=300)
                    or current < generated or current >= expires):
                raise ValueError
            # Canonical re-encoding also rejects alternative JSON bytes hidden behind a valid shape.
            if _canonical(value) != payload:
                raise ValueError
            return value
        except (ValueError, TypeError, KeyError, UnicodeError, json.JSONDecodeError):
            raise ResearchQuoteError("quote_invalid", 409) from None
