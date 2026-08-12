from dataclasses import dataclass
import json
import os
from typing import Mapping, Protocol

import httpx

from app.model_contract import ScoreDecision


class ModelClient(Protocol):
    provider: str
    model: str

    def complete(
        self, *, source_text: str
    ) -> tuple[dict[str, object], dict[str, object] | None]: ...


@dataclass(frozen=True)
class OpenAICompatibleModelClient:
    base_url: str
    api_key: str
    model: str
    provider: str = "openai-compatible"
    timeout_seconds: float = 30.0
    http_client: httpx.Client | None = None

    def complete(
        self, *, source_text: str
    ) -> tuple[dict[str, object], dict[str, object] | None]:
        request = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "Return only the strict discovery scoring JSON object.",
                },
                {"role": "user", "content": source_text},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "discovery_score",
                    "strict": True,
                    "schema": ScoreDecision.model_json_schema(),
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
