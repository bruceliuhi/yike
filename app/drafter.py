from dataclasses import dataclass
import json
from uuid import uuid4

import httpx
from pydantic import ValidationError

from app.model_client import ModelClient
from app.model_contract import DraftDecision
from app.repository import Repository


PROMPT_VERSION = "DISCOVERY_DRAFT_V1"


@dataclass(frozen=True)
class DraftResult:
    draft_run_id: str
    status: str
    error_code: str | None
    decision: DraftDecision | None = None


class DraftGenerator:
    def __init__(self, repository: Repository, client: ModelClient | None):
        self.repository = repository
        self.client = client

    def generate(self, run_id: str, signal_id: str) -> DraftResult:
        draft_run_id = str(uuid4())
        provider = getattr(self.client, "provider", None)
        model = getattr(self.client, "model", None)
        if self.client is None:
            return self._failure(
                draft_run_id, run_id, signal_id, provider, model,
                "MODEL_NOT_CONFIGURED",
            )
        source_text = self.repository.get_signal_source_text(run_id, signal_id)
        try:
            payload, token_usage = self.client.generate_draft(source_text=source_text)
        except httpx.HTTPError:
            return self._failure(
                draft_run_id, run_id, signal_id, provider, model,
                "MODEL_UNAVAILABLE",
            )
        except Exception:
            return self._failure(
                draft_run_id, run_id, signal_id, provider, model,
                "MODEL_OUTPUT_INVALID",
            )
        try:
            decision = DraftDecision.model_validate(
                payload, context={"source_text": source_text}
            )
        except (ValidationError, TypeError, ValueError, json.JSONDecodeError):
            return self._failure(
                draft_run_id, run_id, signal_id, provider, model,
                "MODEL_OUTPUT_INVALID",
            )
        self.repository.append_draft_success(
            draft_run_id=draft_run_id,
            run_id=run_id,
            signal_id=signal_id,
            provider=self.client.provider,
            model=self.client.model,
            prompt_version=PROMPT_VERSION,
            decision=decision,
            token_usage=token_usage,
        )
        return DraftResult(draft_run_id, "SUCCEEDED", None, decision)

    def _failure(
        self,
        draft_run_id: str,
        run_id: str,
        signal_id: str,
        provider: str | None,
        model: str | None,
        error_code: str,
    ) -> DraftResult:
        self.repository.append_draft_failure(
            draft_run_id=draft_run_id,
            run_id=run_id,
            signal_id=signal_id,
            provider=provider,
            model=model,
            prompt_version=PROMPT_VERSION,
            error_code=error_code,
        )
        return DraftResult(draft_run_id, "FAILED", error_code)
