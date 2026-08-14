import json
from typing import Literal
import unicodedata

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator


Grade = Literal["A", "B", "C", "D"]
ExclusionReason = Literal[
    "STUDENT_JOB_SEEKING_OR_HOBBY",
    "PEER_PROMOTION",
    "IRRELEVANT",
    "GENERIC_PRAISE",
    "ILLEGAL_AUTOMATION_REQUEST",
    "SOURCE_UNVERIFIABLE",
]


def has_visible_text(value: object) -> bool:
    """Require lexical content, not only whitespace, controls, or punctuation."""
    return isinstance(value, str) and any(
        _is_visible_lexical_character(character) for character in value
    )


def _is_visible_lexical_character(character: str) -> bool:
    return (
        character.isalnum()
        and "FILLER" not in unicodedata.name(character, "")
    )


def _has_content_beyond_marker(value: str, marker: str) -> bool:
    remainder = value.replace(marker, "")
    return sum(_is_visible_lexical_character(character) for character in remainder) >= 2


def strict_json_object(value: str) -> dict[str, object]:
    def object_from_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate JSON object key")
            result[key] = item
        return result

    parsed = json.loads(
        value,
        object_pairs_hook=object_from_pairs,
        parse_constant=lambda constant: (_ for _ in ()).throw(
            ValueError(f"invalid JSON number: {constant}")
        ),
    )
    if not isinstance(parsed, dict):
        raise ValueError("JSON value must be an object")
    return parsed


class DimensionScores(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    business_team_context: int = Field(ge=0, le=2)
    offer_fit: int = Field(ge=0, le=3)
    action_intent: int = Field(ge=0, le=3)
    buying_signal: int = Field(ge=0, le=2)
    contact_context: int = Field(ge=0, le=1)
    evidence_completeness: int = Field(ge=0, le=1)

    def total(self) -> int:
        return sum(self.model_dump().values())


class ScoreDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    grade: Grade
    score: int = Field(ge=0, le=12)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    explicit_industry: str | None
    business_context: str
    pain_summary: str
    intent_summary: str
    evidence_snippets: list[str] = Field(min_length=1)
    dimension_scores: DimensionScores
    exclusion_reasons: list[ExclusionReason]
    recommended_question: str

    @field_validator(
        "business_context",
        "pain_summary",
        "intent_summary",
        "recommended_question",
    )
    @classmethod
    def require_nonblank_text(cls, value: str) -> str:
        if not has_visible_text(value):
            raise ValueError("text must not be blank")
        return value

    @field_validator("explicit_industry")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is not None and not has_visible_text(value):
            raise ValueError("explicit_industry must be null or nonblank")
        return value

    @field_validator("evidence_snippets")
    @classmethod
    def evidence_must_be_verbatim(
        cls, snippets: list[str], info: ValidationInfo
    ) -> list[str]:
        source_text = (info.context or {}).get("source_text")
        if not isinstance(source_text, str):
            raise ValueError("evidence source_text context is required")
        if any(
            not has_visible_text(snippet) or snippet not in source_text
            for snippet in snippets
        ):
            raise ValueError("every evidence snippet must occur verbatim in source text")
        return snippets

    @model_validator(mode="after")
    def validate_score_semantics(self, info: ValidationInfo) -> "ScoreDecision":
        source_verifiable = (info.context or {}).get("source_verifiable")
        if source_verifiable is False:
            if self.exclusion_reasons != ["SOURCE_UNVERIFIABLE"]:
                raise ValueError(
                    "unverifiable source requires SOURCE_UNVERIFIABLE exclusion"
                )
        elif source_verifiable is True and "SOURCE_UNVERIFIABLE" in self.exclusion_reasons:
            raise ValueError("verifiable source cannot be excluded as unverifiable")
        if self.dimension_scores.total() != self.score:
            raise ValueError("dimension score sum must equal total score")
        if self.exclusion_reasons:
            expected_grade = "D"
        elif self.score >= 9:
            if (
                self.dimension_scores.business_team_context == 0
                or self.dimension_scores.offer_fit < 2
            ):
                raise ValueError("grade A requires business context and offer fit")
            expected_grade = "A"
        elif self.score >= 7:
            expected_grade = "B"
        elif self.score >= 4:
            expected_grade = "C"
        else:
            expected_grade = "D"
        if self.grade != expected_grade:
            raise ValueError("grade does not match score threshold or exclusions")
        return self


class DraftDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    body: str = Field(min_length=1, max_length=180)
    source_snippet: str = Field(min_length=1)
    research_purpose_sentence: str = Field(min_length=1)
    diagnostic_question: str = Field(min_length=1)

    @field_validator(
        "body", "source_snippet", "research_purpose_sentence", "diagnostic_question"
    )
    @classmethod
    def require_visible_text(cls, value: str) -> str:
        if not has_visible_text(value):
            raise ValueError("draft text must not be blank")
        return value

    @model_validator(mode="after")
    def validate_draft_contract(self, info: ValidationInfo) -> "DraftDecision":
        source_text = (info.context or {}).get("source_text")
        if not isinstance(source_text, str):
            raise ValueError("draft source_text context is required")
        if self.source_snippet not in source_text or self.source_snippet not in self.body:
            raise ValueError("draft source snippet must occur verbatim")
        if (
            self.research_purpose_sentence not in self.body
            or "研究" not in self.research_purpose_sentence
            or not _has_content_beyond_marker(
                self.research_purpose_sentence, "研究"
            )
        ):
            raise ValueError("draft must contain a research-purpose sentence")
        if (
            self.diagnostic_question not in self.body
            or not self.diagnostic_question.endswith(("?", "？"))
            or sum(
                _is_visible_lexical_character(character)
                for character in self.diagnostic_question[:-1]
            ) < 2
        ):
            raise ValueError("draft must contain a diagnostic question")
        question_marks = self.body.count("?") + self.body.count("？")
        if question_marks != 1:
            raise ValueError("draft must contain exactly one question")
        return self


def valid_persisted_score_fact(
    dimension_scores_json: object,
    total_score: object,
    grade: object,
    confidence: object,
    reason_json: object,
    source_text: object,
    source_verifiable: object,
) -> int:
    """SQLite UDF boundary for a persisted successful score fact."""
    if not all(
        isinstance(value, str)
        for value in (dimension_scores_json, grade, reason_json, source_text)
    ):
        return 0
    try:
        dimensions = strict_json_object(dimension_scores_json)
        reason = strict_json_object(reason_json)
        if "dimension_scores" in reason or source_verifiable not in (0, 1):
            return 0
        if (
            reason.get("score") != total_score
            or reason.get("grade") != grade
            or reason.get("confidence") != confidence
        ):
            return 0
        ScoreDecision.model_validate(
            reason | {"dimension_scores": dimensions},
            context={
                "source_text": source_text,
                "source_verifiable": bool(source_verifiable),
            },
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        return 0
    return 1


def valid_persisted_draft_fact(
    body: object,
    contract_json: object,
    source_text: object,
) -> int:
    """SQLite UDF boundary for a persisted generated draft fact."""
    if not all(isinstance(value, str) for value in (body, contract_json, source_text)):
        return 0
    try:
        contract = strict_json_object(contract_json)
        if contract.get("body") != body:
            return 0
        DraftDecision.model_validate(contract, context={"source_text": source_text})
    except (TypeError, ValueError, json.JSONDecodeError):
        return 0
    return 1
