from dataclasses import dataclass, field
import json
import os
from typing import Mapping, Protocol

import httpx

from app.model_contract import DraftDecision, ScoreDecision


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

    def complete(
        self, *, source_text: str
    ) -> tuple[dict[str, object], dict[str, object] | None]:
        return self._request(
            source_text=source_text,
            system="Return only the strict discovery scoring JSON object.",
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
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("model output must be a JSON object")
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
