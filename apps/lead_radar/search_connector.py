from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


MAX_RESPONSE_BYTES = 4_000_000
TIMEOUT_SECONDS = 12
CONNECTOR_ID = "authorized_search_api"
_PROOF_CHECKS = ("url_reopen", "published_at", "save_boundary", "retry_idempotency")
_PROOF_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class SearchConnectorError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


def _config() -> tuple[str, str, str, bool]:
    endpoint = os.environ.get("LEAD_RADAR_SEARCH_ENDPOINT", "").strip()
    token = os.environ.get("LEAD_RADAR_SEARCH_TOKEN", "").strip()
    provider = os.environ.get("LEAD_RADAR_SEARCH_PROVIDER", "authorized-search-api").strip() or "authorized-search-api"
    reopen_proof = os.environ.get("LEAD_RADAR_SEARCH_REOPEN_PROOF", "").strip().lower() in {"1", "true", "yes"}
    return endpoint, token, provider, reopen_proof


def _proof_configuration(endpoint: str, provider: str) -> tuple[bool, dict[str, Any], str]:
    """Read the non-secret production evidence required to expose a connector.

    A boolean environment flag is deliberately not treated as proof.  The operator
    must bind a review reference, digest, timestamp and every required check to the
    exact endpoint/provider.  This keeps a copied demo configuration in a truthful
    ``REQUIRES_PROOF`` state until someone supplies the review artifact.
    """
    reference = os.environ.get("LEAD_RADAR_SEARCH_PROOF_REF", "").strip()
    digest = os.environ.get("LEAD_RADAR_SEARCH_PROOF_SHA256", "").strip().lower()
    checked_at = os.environ.get("LEAD_RADAR_SEARCH_PROOF_CHECKED_AT", "").strip()
    checked_endpoint = os.environ.get("LEAD_RADAR_SEARCH_PROOF_ENDPOINT", "").strip()
    checked_provider = os.environ.get("LEAD_RADAR_SEARCH_PROOF_PROVIDER", "").strip()
    raw_checks = os.environ.get("LEAD_RADAR_SEARCH_PROOF_CHECKS", "").strip()
    checks: dict[str, Any] = {}
    try:
        parsed_checks = json.loads(raw_checks) if raw_checks else {}
        if isinstance(parsed_checks, dict):
            checks = {key: parsed_checks.get(key) is True for key in _PROOF_CHECKS}
    except (TypeError, json.JSONDecodeError):
        checks = {}
    parsed_time: datetime | None = None
    if checked_at:
        try:
            parsed_time = datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
            if parsed_time.tzinfo is None:
                parsed_time = parsed_time.replace(tzinfo=timezone.utc)
            parsed_time = parsed_time.astimezone(timezone.utc)
        except ValueError:
            parsed_time = None
    valid = bool(
        reference
        and _PROOF_DIGEST.fullmatch(digest)
        and parsed_time is not None
        and parsed_time <= datetime.now(timezone.utc)
        and checked_endpoint == (urlparse(endpoint).hostname or "")
        and checked_provider == provider
        and all(checks.get(key) is True for key in _PROOF_CHECKS)
    )
    proof = {
        "reference": reference or None,
        "sha256": digest or None,
        "checked_at": parsed_time.isoformat(timespec="seconds") if parsed_time else None,
        "endpoint_host": checked_endpoint or None,
        "provider": checked_provider or None,
        "checks": checks,
    }
    if not reference:
        reason = "等待来源重开与保存边界审查记录（proof reference）。"
    elif not _PROOF_DIGEST.fullmatch(digest):
        reason = "来源生产门禁需要 proof artifact 的 SHA-256 摘要。"
    elif parsed_time is None or parsed_time > datetime.now(timezone.utc):
        reason = "来源生产门禁需要有效的 UTC 核验时间。"
    elif checked_endpoint != (urlparse(endpoint).hostname or "") or checked_provider != provider:
        reason = "proof artifact 与当前 endpoint/provider 不匹配。"
    elif not all(checks.get(key) is True for key in _PROOF_CHECKS):
        missing = "、".join(key for key in _PROOF_CHECKS if checks.get(key) is not True)
        reason = f"proof artifact 尚未覆盖：{missing}。"
    else:
        reason = "来源 proof artifact 已满足必要检查。"
    return valid, proof, reason


def capability() -> dict[str, Any]:
    endpoint, token, provider, reopen_proof = _config()
    parsed = urlparse(endpoint) if endpoint else None
    endpoint_ok = bool(parsed and parsed.scheme == "https" and parsed.hostname)
    if not endpoint or not token:
        status = "REQUIRES_AUTH"
        note = "等待用户配置有权利证明的搜索 API endpoint 和 Token。"
    elif not endpoint_ok:
        status = "REQUIRES_PROOF"
        note = "搜索 API 必须使用 HTTPS endpoint。"
    elif not reopen_proof:
        status = "REQUIRES_PROOF"
        note = "已配置搜索 API，但尚未声明来源重开、发布时间、保存边界和重试幂等证明。"
    else:
        proof_ready, proof, proof_note = _proof_configuration(endpoint, provider)
        status = "READY" if proof_ready else "REQUIRES_PROOF"
        note = (f"已配置 {provider} 授权搜索 API；结果仍按证据状态进入人工复核。"
                if proof_ready else proof_note)
    proof = _proof_configuration(endpoint, provider)[1] if endpoint else {
        "reference": None, "sha256": None, "checked_at": None,
        "endpoint_host": None, "provider": None, "checks": {},
    }
    return {
        "id": CONNECTOR_ID,
        "name": "授权搜索 API",
        "status": status,
        "tier": "A",
        "access": "official_api",
        "can_search": status == "READY",
        "can_store_original": False,
        "can_write_back": False,
        "provider": provider,
        "endpoint_host": parsed.hostname if parsed and parsed.hostname else None,
        "proof": proof,
        "note": note,
    }


def _required_text(item: dict[str, Any], field: str) -> str:
    value = str(item.get(field, "")).strip()
    if not value:
        raise SearchConnectorError("provider_item_invalid", f"provider item missing {field}")
    return value


def _normalize_item(item: Any, provider: str) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise SearchConnectorError("provider_item_invalid", "provider item must be an object")
    title = _required_text(item, "title")
    source_url = _required_text(item, "source_url")
    snippet = _required_text(item, "snippet")
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise SearchConnectorError("provider_item_invalid", "provider source_url must be an HTTPS URL")
    return {
        "title": title[:240],
        "author": str(item.get("author", "")).strip() or None,
        "published_at": str(item.get("published_at", "")).strip() or None,
        "intent_type": str(item.get("intent_type", "")).strip() or None,
        "industry_location": str(item.get("industry_location", "")).strip() or None,
        "entity_name": str(item.get("entity_name") or item.get("company_name") or "").strip() or None,
        "entity_type": str(item.get("entity_type", "organization")).strip() or "organization",
        "source_kind": CONNECTOR_ID,
        "source_url": source_url,
        "snippet": snippet[:1200],
        "evidence_level": "PROVIDER_ATTESTED",
        "source_permission": "authorized_api",
        "evidence_type": "authorized_search_result",
        "evidence_metadata": {
            "provider": provider,
            "provider_result_id": item.get("id") or item.get("result_id"),
            "capture_method": "authorized_search_api",
        },
    }


class AuthorizedSearchConnector:
    """Small, strict adapter for an official or customer-authorized search API.

    The endpoint must return ``{"items": [{"title", "source_url", "snippet", ...}]}``.
    Platform-specific authentication and legal proof stay outside the Lead Radar core.
    """

    def __init__(self, endpoint: str | None = None, token: str | None = None, provider: str | None = None) -> None:
        configured_endpoint, configured_token, configured_provider, _ = _config()
        self.endpoint = (endpoint or configured_endpoint).strip()
        self.token = (token or configured_token).strip()
        self.provider = (provider or configured_provider).strip() or "authorized-search-api"

    def preflight(self) -> dict[str, Any]:
        return capability()

    def search(
        self,
        plan: dict[str, Any],
        mode: str = "quick",
        *,
        request_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self.endpoint or not self.token:
            raise SearchConnectorError("source_requires_auth", "授权搜索 API 尚未配置", retryable=False)
        parsed = urlparse(self.endpoint)
        if parsed.scheme != "https" or not parsed.hostname:
            raise SearchConnectorError("source_requires_proof", "授权搜索 API 必须使用 HTTPS endpoint", retryable=False)
        strategies = {strategy.get("id"): strategy for strategy in plan.get("strategies", [])}
        strategy = strategies.get(mode) or strategies.get("quick") or {}
        request_body = {
            "queries": strategy.get("queries", []),
            "filters": plan.get("hard_filters", {}),
            "limit": int(plan.get("requested_limit", 10)),
            "mode": mode,
            "output_contract": plan.get("output_contract", []),
        }
        if request_id:
            request_body["request_id"] = request_id
        request_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
            "User-Agent": "LeadRadar/0.1 (+authorized-search-connector)",
        }
        if request_id:
            request_headers["X-Request-ID"] = request_id
        if idempotency_key:
            request_headers["Idempotency-Key"] = idempotency_key
        request = Request(
            self.endpoint,
            data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
            headers=request_headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise SearchConnectorError("provider_response_too_large", "搜索 API 响应超过 4 MB")
                payload = json.loads(body.decode("utf-8"))
        except SearchConnectorError:
            raise
        except HTTPError as exc:
            retryable = exc.code == 429 or exc.code >= 500
            raise SearchConnectorError("provider_http_error", f"搜索 API 返回 HTTP {exc.code}", retryable=retryable) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise SearchConnectorError("provider_unavailable", "搜索 API 暂时不可用", retryable=True) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SearchConnectorError("provider_invalid_json", "搜索 API 未返回合法 JSON") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise SearchConnectorError("provider_contract_invalid", "搜索 API 必须返回 items 数组")
        normalized: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for raw_item in payload["items"]:
            item = _normalize_item(raw_item, self.provider)
            key = (item["source_url"].strip().lower(), item["title"].strip().lower())
            if key in seen:
                continue
            seen.add(key)
            normalized.append(item)
            if len(normalized) >= int(plan.get("requested_limit", 10)):
                break
        return normalized


def result_digest(items: list[dict[str, Any]]) -> str:
    """Stable, non-sensitive digest for run audit events and reconciliation."""
    canonical = json.dumps(items, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()
