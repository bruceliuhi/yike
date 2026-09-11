"""Private one-request child; credentials arrive only through bounded stdin.

Not a public CLI or configurable worker. Parent owns termination and reaping.
"""
import json
import sys

from pilot.candidate_assessment_model import (
    AssessmentModelError, OpenAICompatibleCandidateAssessmentModel, _PIPE_LIMIT, _read_json,
)


def main() -> None:
    reply = {"error": "invalid_assessment_input", "status": 400}
    try:
        raw = sys.stdin.buffer.read(_PIPE_LIMIT + 1)
        if len(raw) > _PIPE_LIMIT:
            raise ValueError("bounded input required")
        payload = _read_json(raw.decode("utf-8"))
        legacy = {"base_url", "api_key", "model", "timeout_seconds", "description", "content", "rule_version", "rule_sha256"}
        if set(payload) not in (legacy, legacy | {"industry_strategy"}):
            raise ValueError("invalid worker input")
        model = OpenAICompatibleCandidateAssessmentModel(**{key: payload[key]
            for key in ("base_url", "api_key", "model", "timeout_seconds")})
        if payload["rule_version"] != model.rule_version or payload["rule_sha256"] != model.rule_sha256:
            raise AssessmentModelError("assessment_rules_unavailable", 503)
        if "industry_strategy" in payload:
            from pilot.research_strategy_contract import IndustryTaskStrategy
            if payload["industry_strategy"] is None:
                raise ValueError("invalid industry strategy")
            strategy = IndustryTaskStrategy.model_validate(payload["industry_strategy"]).model_dump(mode="json")
        else:
            strategy = None
        result, usage = model._assess_in_process(description=payload["description"], content=payload["content"],
                                                 industry_strategy=strategy)
        reply = {"assessment": result.model_dump(), "usage": usage,
                 "rule_version": model.rule_version, "rule_sha256": model.rule_sha256}
    except AssessmentModelError as error:
        reply = {"error": error.code, "status": error.status}
    except (ValueError, TypeError, UnicodeError, RecursionError):
        pass
    except Exception:
        reply = {"error": "assessment_result_unknown", "status": 504}
    encoded = json.dumps(reply, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > _PIPE_LIMIT:
        encoded = b'{"error":"invalid_assessment_result","status":502}'
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
