"""Bounded assessment calls use an invocation-local model copy."""
from datetime import UTC, datetime, timedelta

import pytest

from pilot.candidate_assessment_model import AssessmentModelError
from tests.test_candidate_assessment_model import CONTENT, DESCRIPTION, adapter, envelope, internal_client


def test_assess_before_caps_only_the_invocation_timeout():
    seen = []

    def handle(request):
        seen.append(set(request.extensions["timeout"].values()))
        return __import__("httpx").Response(200, json=envelope())

    with internal_client(transport=__import__("httpx").MockTransport(handle)) as client:
        model = adapter(http_client=client, timeout_seconds=30)
        result, usage = model.assess_before(
            datetime.now(UTC) + timedelta(seconds=2),
            description=DESCRIPTION, content=CONTENT,
        )
    assert result.decision == "REVIEW" and usage["total_tokens"] == 20
    assert model.timeout_seconds == 30
    assert len(seen) == 1
    assert 0 < next(iter(seen[0])) <= 2


def test_assess_before_rejects_expired_or_naive_deadline_without_call():
    model = adapter()
    for deadline in (datetime.now(UTC) - timedelta(seconds=1), datetime.now()):
        with pytest.raises(AssessmentModelError, match="assessment_result_unknown"):
            model.assess_before(deadline, description=DESCRIPTION, content=CONTENT)
