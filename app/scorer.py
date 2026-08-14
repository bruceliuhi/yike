from dataclasses import dataclass
import json
from uuid import uuid4

import httpx
from pydantic import ValidationError

from app.model_client import ModelClient
from app.model_contract import ScoreDecision
from app.repository import Repository


PROMPT_VERSION = "DISCOVERY_SCORE_V2"
SCHEMA_VERSION = "DISCOVERY_SCORE_SCHEMA_V2"


@dataclass(frozen=True)
class ScoreResult:
    score_run_id: str
    status: str
    error_code: str | None
    decision: ScoreDecision | None = None


class Scorer:
    def __init__(self, repository: Repository, client: ModelClient | None):
        self.repository = repository
        self.client = client

    def score(self, run_id: str, signal_id: str) -> ScoreResult:
        score_run_id = str(uuid4())
        provider = getattr(self.client, "provider", None)
        model = getattr(self.client, "model", None)
        if self.client is None:
            self.repository.append_score_failure(
                score_run_id=score_run_id,
                run_id=run_id,
                signal_id=signal_id,
                provider=provider,
                model=model,
                prompt_version=PROMPT_VERSION,
                schema_version=SCHEMA_VERSION,
                error_code="MODEL_NOT_CONFIGURED",
            )
            return ScoreResult(score_run_id, "FAILED", "MODEL_NOT_CONFIGURED")

        source = self.repository.get_signal_model_context(run_id, signal_id)
        try:
            payload, token_usage = self.client.complete(source_text=source.model_input)
        except (httpx.HTTPError, TimeoutError, OSError):
            error_code = "MODEL_UNAVAILABLE"
        except Exception:
            error_code = "MODEL_OUTPUT_INVALID"
        else:
            try:
                decision = ScoreDecision.model_validate(
                    payload,
                    context={
                        "source_text": source.source_text,
                        "source_verifiable": source.verifiable,
                    },
                )
            except (ValidationError, TypeError, ValueError, json.JSONDecodeError):
                error_code = "MODEL_OUTPUT_INVALID"
            else:
                self.repository.append_score_success(
                    score_run_id=score_run_id,
                    run_id=run_id,
                    signal_id=signal_id,
                    provider=self.client.provider,
                    model=self.client.model,
                    prompt_version=PROMPT_VERSION,
                    schema_version=SCHEMA_VERSION,
                    decision=decision,
                    token_usage=token_usage,
                )
                return ScoreResult(score_run_id, "SUCCEEDED", None, decision)

        self.repository.append_score_failure(
            score_run_id=score_run_id,
            run_id=run_id,
            signal_id=signal_id,
            provider=provider,
            model=model,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            error_code=error_code,
        )
        return ScoreResult(score_run_id, "FAILED", error_code)
