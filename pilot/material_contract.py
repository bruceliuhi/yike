from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

from pilot.outreach_contract import canonical_uuid


class MaterialError(ValueError):
    def __init__(self, code: str, status: int = 409):
        self.code, self.status = code, status
        super().__init__(code)


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)


def _clean(value: str) -> str:
    value.encode("utf-8")
    if "\0" in value or not value.strip():
        raise ValueError("invalid text")
    return value.strip()


Uuid = Annotated[str, AfterValidator(canonical_uuid)]
Id = Annotated[str, Field(min_length=1, max_length=200), AfterValidator(_clean)]
Version = Annotated[int, Field(ge=1, le=2_147_483_647)]
FieldName = Literal["service", "customer", "regions", "preference", "exclusions"]
Purpose = Literal["产品介绍", "真实案例", "服务说明"]


class MaterialInput(_Strict):
    name: Annotated[str, Field(min_length=1, max_length=100), AfterValidator(_clean)]
    text: Annotated[str, Field(min_length=1, max_length=2000), AfterValidator(_clean)]
    purpose: Purpose
    visibility: Literal["internal", "external"]
    fileName: str | None = Field(default=None, max_length=255)
    bytes: int | None = Field(default=None, ge=0, le=200 * 1024)

    @field_validator("fileName")
    @classmethod
    def valid_filename(cls, value):
        if value is not None and "\0" in value:
            raise ValueError("invalid filename")
        return value


class SaveChange(_Strict):
    kind: Literal["save"]
    materialId: Id
    expectedVersion: Version | None
    input: MaterialInput


class ParseChange(_Strict):
    kind: Literal["parse"]
    materialId: Id
    expectedVersion: Version


class ConfirmChange(_Strict):
    kind: Literal["confirm"]
    materialId: Id
    expectedVersion: Version
    extractionId: Id
    fields: dict[FieldName, str]

    @field_validator("fields")
    @classmethod
    def valid_fields(cls, value):
        limits = {"service": 500, "customer": 500, "regions": 500, "preference": 200, "exclusions": 500}
        if not value:
            raise ValueError("at least one field required")
        for key, item in value.items():
            if not isinstance(item, str) or not item.strip() or "\0" in item or len(item) > limits[key]:
                raise ValueError("invalid field")
        return value


class ImpactChange(_Strict):
    kind: Literal["remove", "revoke"]
    materialId: Id
    expectedVersion: Version
    impactToken: Id


MaterialChange = Annotated[Union[SaveChange, ParseChange, ConfirmChange, ImpactChange], Field(discriminator="kind")]


class MaterialRequest(_Strict):
    requestId: Uuid
    profileVersionId: Id
    change: MaterialChange


class MaterialImpactRequest(_Strict):
    profileVersionId: Id
    materialId: Id
    version: Version
    action: Literal["remove", "revoke"]


class Evidence(_Strict):
    field: FieldName
    quote: Annotated[str, Field(min_length=1, max_length=2000), AfterValidator(_clean)]


class Extraction(_Strict):
    fields: dict[FieldName, str]
    evidence: list[Evidence] = Field(min_length=1, max_length=20)

    @field_validator("fields")
    @classmethod
    def validate_fields(cls, value):
        return ConfirmChange.valid_fields(value)


_extraction = TypeAdapter(Extraction)


def validate_extraction(value, text: str) -> dict:
    parsed = _extraction.validate_python(value)
    quotes = {item.field for item in parsed.evidence if item.quote in text}
    if any(item.quote not in text for item in parsed.evidence):
        raise ValueError("invalid extraction evidence")
    if any(field not in quotes for field in parsed.fields):
        raise ValueError("missing extraction evidence")
    return parsed.model_dump(exclude_none=True)
