from uuid import uuid4

import pytest
from pydantic import ValidationError


def body(**changes):
    return dict(request_id=str(uuid4()), action="REGISTER", device_id=str(uuid4()),
                connection_id=None, expected_connection_version=0, platform="BILIBILI",
                account_public_id="synthetic-id", session_ref="vault://synthetic") | changes


@pytest.mark.parametrize("changes", [
    {"unexpected": "private-marker"}, {"expected_connection_version": True},
    {"expected_connection_version": "1"}, {"expected_connection_version": -1},
    {"expected_connection_version": 2147483648}, {"device_id": "not-uuid"},
    {"request_id": str(uuid4()).upper()}, {"platform": "bilibili"},
    {"platform": "UNKNOWN"}, {"session_ref": "vault://cookie=private-marker"},
    {"session_ref": None}, {"session_ref": "vault://" + "x" * 600},
    {"account_public_id": "private\nmarker"}, {"account_public_id": "  "},
    {"action": "DISCONNECT"}, {"connection_id": str(uuid4())},
    {"account_public_id": "synthetic\u0085marker"},
])
def test_strict_request(changes):
    from pilot.connection_versions import ConnectionOperation, ConnectionOperationError
    with pytest.raises((ValidationError, ConnectionOperationError)) as caught:
        ConnectionOperation(**body(**changes))
    assert "private-marker" not in str(caught.value)


def test_private_reference_hidden_and_material_strings_preserved():
    from pilot.connection_versions import ConnectionOperation
    request = ConnectionOperation(**body(account_public_id="synthetic-id"))
    assert "vault://synthetic" not in repr(request)
    assert request.account_public_id == "synthetic-id"


@pytest.mark.parametrize("changes", [{"platform": []}, {"platform": None},
    {"connection_version": True}, {"connection_version": 0}, {"connection_version": "1"}])
def test_checker_structural_errors_are_stable(changes):
    from pilot.connection_versions import ConnectionOperationStore, ConnectionOperationError
    service = ConnectionOperationStore(None)
    with pytest.raises(ConnectionOperationError, match="invalid_request"):
        service.lock_current(None, None, **(dict(device_id=str(uuid4()), connection_id=str(uuid4()),
            connection_version=1, platform="BILIBILI") | changes))
