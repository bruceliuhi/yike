"""Strict P07 inputs; actor, clock and strategy are never caller fields."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError, AfterValidator
from pilot.candidate_ingestion import CandidateIngestionError, _id

class CandidateReviewError(CandidateIngestionError):
    pass

def _uuid(value):
    _id(value)
    return value

def _request(value):
    _id(value, opaque=True)
    return value

def _text(value):
    if not value.strip() or '\x00' in value:
        raise ValueError('text required')
    value.encode('utf-8')
    return value

UUIDText = Annotated[str, AfterValidator(_uuid)]
RequestId = Annotated[str, AfterValidator(_request)]
Text = Annotated[str, Field(min_length=1,max_length=2000), AfterValidator(_text)]

class Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)

class Binding(Strict):
    candidateId: UUIDText
    candidateRevision: Annotated[int, Field(ge=1)]
    sourceVersionId: UUIDText
    profileId: UUIDText
    profileVersion: Annotated[int, Field(ge=1)]

class Evidence(Strict):
    matchReason: Text
    actionSignal: Text
    value: Text
    risk: Text
    unknowns: Text

class Assess(Binding):
    requestId: RequestId
    action: Literal['ASSESS']
    retryOf: RequestId | None = None

class Decision(Binding):
    requestId: RequestId
    action: Literal['INCLUDE','EXCLUDE']
    assessmentId: UUIDText
    evidence: Evidence
    reason: Annotated[str, Field(max_length=2000)]
    humanConfirmed: Literal[True]
    sourceVerificationId: UUIDText | None = None

class Verification(Binding):
    requestId: RequestId
    humanConfirmed: Literal[True]
    status: Literal['OPEN','BLOCKED','EXPIRED','UNVERIFIED']
    openingMethod: Literal['DIRECT','IN_PLATFORM']
    locator: Text
    excerpt: Text
    contactMethod: Literal['COMMENT','DM','PUBLIC_CONTACT','NONE']

def validate_payload(value, *, verification=False):
    try:
        if type(value) is not dict or ('humanConfirmed' in value and value['humanConfirmed'] is not True):
            raise ValueError
        cls = Verification if verification else Assess if value.get('action')=='ASSESS' else Decision
        result = cls.model_validate(value)
        if isinstance(result,Decision):
            result.reason.encode('utf-8')
            if '\x00' in result.reason or (result.action=='EXCLUDE' and not result.reason.strip()):
                raise ValueError
        return result
    except (ValueError, TypeError, ValidationError, UnicodeError):
        raise CandidateReviewError('invalid_request',422) from None

def binding(value):
    return {name:getattr(value,name) for name in Binding.model_fields}
