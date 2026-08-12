from typing import Literal

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
        if not value.strip():
            raise ValueError("text must not be blank")
        return value

    @field_validator("explicit_industry")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
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
        if any(not snippet.strip() or snippet not in source_text for snippet in snippets):
            raise ValueError("every evidence snippet must occur verbatim in source text")
        return snippets

    @model_validator(mode="after")
    def validate_score_semantics(self) -> "ScoreDecision":
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
        if not value.strip():
            raise ValueError("draft text must not be blank")
        return value

    @model_validator(mode="after")
    def validate_draft_contract(self, info: ValidationInfo) -> "DraftDecision":
        source_text = (info.context or {}).get("source_text")
        if not isinstance(source_text, str):
            raise ValueError("draft source_text context is required")
        if self.source_snippet not in source_text or self.source_snippet not in self.body:
            raise ValueError("draft source snippet must occur verbatim")
        if self.research_purpose_sentence not in self.body or "研究" not in self.research_purpose_sentence:
            raise ValueError("draft must contain a research-purpose sentence")
        if self.diagnostic_question not in self.body or not self.diagnostic_question.endswith(
            ("?", "？")
        ):
            raise ValueError("draft must contain a diagnostic question")
        question_marks = self.body.count("?") + self.body.count("？")
        if question_marks != 1:
            raise ValueError("draft must contain exactly one question")
        return self
