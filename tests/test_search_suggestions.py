"""Strict input contract for the persistent suggestion store (no model calls)."""
import importlib
import importlib.util
from uuid import uuid4

import pytest
from pydantic import ValidationError


def implementation():
    assert importlib.util.find_spec("pilot.search_suggestions") is not None, "missing persistent suggestion module"
    return importlib.import_module("pilot.search_suggestions")


def body(**changes):
    return {"request_id": str(uuid4()), "draft_id": str(uuid4()),
            "profile_version_id": str(uuid4()), "draft_revision": 0} | changes


def test_request_contract_is_frozen_strict_and_version_bounded():
    request = implementation().SearchSuggestionRequest(**body(draft_revision=2147483647))
    with pytest.raises(ValidationError):
        request.draft_revision = 2


@pytest.mark.parametrize("name", ["request_id", "draft_id", "profile_version_id"])
@pytest.mark.parametrize("value", [None, 1, b"x", "", "bad", "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA",
                                   "00000000000000000000000000000000"])
def test_request_rejects_noncanonical_ids(name, value):
    api = implementation()
    with pytest.raises((ValidationError, api.SearchSuggestionStoreError)):
        api.SearchSuggestionRequest(**body(**{name: value}))


@pytest.mark.parametrize("revision", [-1, True, "1", 1.5, None, 2147483648])
def test_request_rejects_invalid_revision(revision):
    with pytest.raises(ValidationError):
        implementation().SearchSuggestionRequest(**body(draft_revision=revision))


@pytest.mark.parametrize("name", ["tenant_id", "user_id", "description", "provider", "model", "cost", "base_url"])
def test_request_rejects_client_owned_server_fields(name):
    with pytest.raises(ValidationError):
        implementation().SearchSuggestionRequest(**body(**{name: "client-claim"}))
