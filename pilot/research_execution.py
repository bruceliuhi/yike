"""Atomic research START reservation; no worker, spending, or settlement."""
from __future__ import annotations

import hashlib
import json
from uuid import uuid4

import psycopg

from pilot.execution_contract import ExecutionOperation, ExecutionRuntimeError, canonical_uuid
from pilot.research_quote import ResearchQuoteError


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


class ResearchExecutionService:
    def __init__(self, runtime, quotes):
        self.runtime, self.quotes = runtime, quotes

    def start(self, claims, request, signature, authorization_token):
        if not isinstance(request, ExecutionOperation) or request.operation != "START":
            raise ExecutionRuntimeError("invalid_request", 422)
        token_sha256 = hashlib.sha256(authorization_token.encode("utf-8")).hexdigest()

        def reserve(cursor, tenant, operation, execution, previous, snapshot=None):
            if previous is not None:
                if type(previous) is not dict:
                    raise ExecutionRuntimeError("request_conflict", 409)
                cursor.execute("SELECT authorization_token_sha256 FROM pilot_research_reservations "
                    "WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s",
                    (tenant, claims.user_id, operation.request_id))
                row = cursor.fetchone()
                if not row or row[0] != token_sha256:
                    raise ExecutionRuntimeError("request_conflict", 409)
                return previous
            try:
                quote = self.quotes.verify(authorization_token, now=self.runtime._now(cursor))
            except ResearchQuoteError as error:
                raise ExecutionRuntimeError(error.code, error.status) from None
            binding = quote.get("strategyBinding")
            configuration = snapshot.get("configuration")
            research = configuration.get("research") if type(configuration) is dict else None
            limits = research.get("limits") if type(research) is dict else None
            platforms = snapshot.get("platforms")
            if (quote.get("userId") != claims.user_id
                    or quote.get("accountScopeId") != tenant
                    or quote.get("accountScopeVersion") != 1
                    or type(binding) is not dict
                    or binding.get("strategyVersionId") != operation.strategy_version_id
                    or binding.get("profileVersionId") != operation.profile_version_id
                    or binding.get("configurationSha256") != operation.configuration_sha256
                    or type(platforms) is not list
                    or set(platforms) != {target.platform for target in operation.targets}
                    or len(platforms) != len(operation.targets)
                    or type(limits) is not dict
                    or quote.get("maxSoubei") != research.get("maxSoubei")
                    or quote.get("estimatedSoubei", 0) > quote.get("maxSoubei", -1)):
                raise ExecutionRuntimeError("strategy_conflict", 409)
            cursor.execute("SELECT draft_id,draft_revision FROM pilot_research_strategy_versions "
                "WHERE tenant_id=%s AND owner_user_id=%s AND strategy_version_id=%s FOR UPDATE",
                (tenant, claims.user_id, operation.strategy_version_id))
            if cursor.fetchone() != (quote.get("draftId"), quote.get("revision")):
                raise ExecutionRuntimeError("strategy_conflict", 409)
            try:
                capable = self.quotes.research_capability(snapshot)
            except Exception:
                capable = False
            if capable is not True:
                raise ExecutionRuntimeError("capability_unavailable", 501)
            reservation = {
                "reservation_id": str(uuid4()), "quote_id": quote["quoteId"],
                "strategy_version_id": operation.strategy_version_id,
                "profile_version_id": operation.profile_version_id,
                "configuration_sha256": operation.configuration_sha256,
                "rule_version": quote["ruleVersion"], "rule_sha256": quote["ruleSha256"],
                "estimated_soubei": quote["estimatedSoubei"], "max_soubei": quote["maxSoubei"],
                "limits": {key: limits[key] for key in ("sources", "minutes", "modelCalls")},
                "status": "RESERVED",
            }
            receipt = {"schema_version": "research-execution-v1", "execution": {
                **execution, "schema_version": "execution-runtime-v1",
                "request_id": operation.request_id, "operation": "START"},
                "reservation": reservation}
            quote_summary = {key: value for key, value in quote.items() if key != "authorizationToken"}
            cursor.execute("INSERT INTO pilot_research_reservations(tenant_id,owner_user_id,reservation_id,"
                "quote_id,request_id,task_id,run_id,draft_id,draft_revision,strategy_version_id,profile_version_id,"
                "configuration_sha256,configuration_hash,rule_version,rule_sha256,quote_sha256,"
                "authorization_token_sha256,estimated_soubei,max_soubei,source_limit,minute_limit,model_call_limit,"
                "status,receipt) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
                "%s,%s::jsonb)", (tenant, claims.user_id, reservation["reservation_id"], quote["quoteId"],
                operation.request_id, execution["task_id"], execution["run_id"], quote["draftId"],
                quote["revision"], operation.strategy_version_id, operation.profile_version_id,
                operation.configuration_sha256, quote["configurationHash"], quote["ruleVersion"],
                quote["ruleSha256"], hashlib.sha256(_canonical(quote_summary)).hexdigest(), token_sha256,
                quote["estimatedSoubei"], quote["maxSoubei"], limits["sources"], limits["minutes"],
                limits["modelCalls"], "RESERVED", _canonical(receipt).decode("utf-8")))
            return receipt

        try:
            return self.runtime.apply_research(claims, request, signature, reserve)
        except psycopg.errors.UniqueViolation:
            raise ExecutionRuntimeError("request_conflict", 409) from None
        except psycopg.Error:
            raise ExecutionRuntimeError("research_unavailable", 503) from None

    def get_receipt(self, claims, request_id):
        canonical_uuid(request_id)
        try:
            with self.runtime.database.connect() as connection, connection.cursor() as cursor:
                tenant = self.runtime._active(cursor, claims)
                cursor.execute("SELECT receipt FROM pilot_research_reservations WHERE tenant_id=%s "
                    "AND owner_user_id=%s AND request_id=%s", (tenant, claims.user_id, request_id))
                row = cursor.fetchone()
                self.runtime._active(cursor, claims)
                if not row:
                    raise ExecutionRuntimeError("request_not_found", 404)
                return row[0]
        except psycopg.Error:
            raise ExecutionRuntimeError("research_unavailable", 503) from None
