from dataclasses import dataclass, field
import os
from typing import Mapping, Protocol
from urllib.parse import urlsplit

import httpx

from app.model_contract import DraftDecision, ScoreDecision, strict_json_object


class ModelClient(Protocol):
    provider: str
    model: str

    def complete(
        self, *, source_text: str
    ) -> tuple[dict[str, object], dict[str, object] | None]: ...

    def generate_draft(
        self, *, source_text: str
    ) -> tuple[dict[str, object], dict[str, object] | None]: ...


@dataclass(frozen=True)
class OpenAICompatibleModelClient:
    base_url: str
    api_key: str = field(repr=False, compare=False)
    model: str
    provider: str = "openai-compatible"
    timeout_seconds: float = 30.0
    http_client: httpx.Client | None = None

    def __post_init__(self) -> None:
        try:
            parsed = urlsplit(self.base_url)
            _ = parsed.port
        except ValueError as error:
            raise ValueError("model base URL is invalid") from error
        local_http_hosts = {"127.0.0.1", "::1"}
        if (
            not parsed.hostname
            or parsed.scheme not in {"http", "https"}
            or (parsed.scheme == "http" and parsed.hostname not in local_http_hosts)
            or parsed.username is not None
            or parsed.password is not None
            or bool(parsed.query)
            or bool(parsed.fragment)
        ):
            raise ValueError("model base URL must be HTTPS or loopback HTTP")

    def complete(
        self, *, source_text: str
    ) -> tuple[dict[str, object], dict[str, object] | None]:
        return self._request(
            source_text=source_text,
            system=(
                "Return only the strict discovery scoring JSON object. "
                "The only Offer is 意客AI, a B2B sales-agent product for 中小企业 "
                "that finds intent in authorized public comments, prepares a reply "
                "for 人工发送, and measures the route to the business account and "
                "enterprise WeChat. Score only the supplied source envelope. Rubric: "
                "business_team_context 0-2; offer_fit 0-3; action_intent 0-3; "
                "buying_signal 0-2; contact_context 0-1; evidence_completeness 0-1. "
                "Grades: A: 9-12 only when business_team_context > 0 and "
                "offer_fit >= 2; B: 7-8; C: 4-6; D: 0-3. Any exclusion forces D. "
                "Hard exclusions are STUDENT_JOB_SEEKING_OR_HOBBY, PEER_PROMOTION, "
                "IRRELEVANT, GENERIC_PRAISE, ILLEGAL_AUTOMATION_REQUEST, and "
                "SOURCE_UNVERIFIABLE. "
                "If verifiable is false, use only SOURCE_UNVERIFIABLE and grade D. "
                "Evidence snippets must be exact text from source_text. Never infer "
                "identity, budget, contact details, or facts absent from the envelope."
            ),
            schema_name="discovery_score",
            schema=ScoreDecision.model_json_schema(),
        )

    def generate_draft(
        self, *, source_text: str
    ) -> tuple[dict[str, object], dict[str, object] | None]:
        return self._request(
            source_text=source_text,
            system=(
                "Return only strict discovery draft JSON. Keep body within 180 "
                "characters, quote one source snippet verbatim, state the research "
                "purpose, and ask exactly one diagnostic question."
            ),
            schema_name="discovery_draft",
            schema=DraftDecision.model_json_schema(),
        )

    def _request(
        self,
        *,
        source_text: str,
        system: str,
        schema_name: str,
        schema: dict[str, object],
    ) -> tuple[dict[str, object], dict[str, object] | None]:
        request = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": system,
                },
                {"role": "user", "content": source_text},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        client = self.http_client or httpx.Client(timeout=self.timeout_seconds)
        close_client = self.http_client is None
        try:
            response = client.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=request,
            )
            response.raise_for_status()
            payload = response.json()
        finally:
            if close_client:
                client.close()
        content = payload["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("model content must be a JSON string")
        parsed = strict_json_object(content)
        usage = payload.get("usage")
        return parsed, usage if isinstance(usage, dict) else None


def model_client_from_env(
    environ: Mapping[str, str] | None = None,
) -> OpenAICompatibleModelClient | None:
    values = os.environ if environ is None else environ
    base_url = values.get("DISCOVERY_MODEL_BASE_URL", "").strip()
    api_key = values.get("DISCOVERY_MODEL_API_KEY", "").strip()
    model = values.get("DISCOVERY_MODEL_NAME", "").strip()
    if not base_url or not api_key or not model:
        return None
    return OpenAICompatibleModelClient(base_url=base_url, api_key=api_key, model=model)
