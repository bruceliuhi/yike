from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from pilot.auth import TokenClaims
from pilot.opportunity_brief import OpportunityBriefError, parse_query


def valid_query(**changes):
    now = datetime.now(UTC)
    value = {"contractVersion": 1, "requestId": str(uuid4()), "userId": str(uuid4()),
             "accountScopeId": str(uuid4()), "scopeVersion": 1,
             "profileId": str(uuid4()), "profileVersion": 1,
             "businessDate": now.date().isoformat(), "timezone": "UTC"}
    value.update(changes)
    return value


def test_query_contract_is_exact_and_uuid_bound():
    value = valid_query()
    assert parse_query(value) == value
    for changed in (value | {"extra": True}, value | {"scopeVersion": 2},
                    value | {"requestId": "not-a-uuid"}, value | {"timezone": "No/Such"}):
        with pytest.raises(OpportunityBriefError, match="invalid_request"):
            parse_query(changed)


def test_authenticated_identity_must_match_request():
    from pilot.opportunity_brief import validate_identity
    value = valid_query()
    claims = TokenClaims(value["userId"], 9999999999, "r")
    validate_identity(claims, value, value["accountScopeId"])
    with pytest.raises(OpportunityBriefError, match="identity_conflict"):
        validate_identity(claims, value | {"userId": str(uuid4())}, value["accountScopeId"])


def test_only_current_business_day_is_supported():
    from pilot.opportunity_brief import validate_business_day
    now = datetime(2026, 9, 11, 1, tzinfo=UTC)
    validate_business_day("2026-09-11", "Asia/Shanghai", now)
    with pytest.raises(OpportunityBriefError, match="business_date_conflict"):
        validate_business_day("2026-09-10", "Asia/Shanghai", now)
