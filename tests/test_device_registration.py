"""Pure registration contract checks; no database or platform activity."""
from contextlib import contextmanager
import time
from uuid import uuid4

import pytest

from pilot.auth import TokenClaims
from pilot.device_keys import DeviceKeyError
from pilot.device_registration import DeviceRegistrationStore


class UnavailableDatabase:
    @contextmanager
    def connect(self):
        raise RuntimeError("sensitive persistence detail")
        yield


def claims():
    return TokenClaims("user-1", int(time.time()) + 3600, "a" * 64)


def valid_payload():
    return {"request_id": str(uuid4()), "device_label": "客户的电脑"}


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"request_id": str(uuid4())},
        {"device_label": "device"},
        {"request_id": str(uuid4()), "device_label": "device", "owner_user_id": "user-1"},
        {"request_id": str(uuid4()).upper(), "device_label": "device"},
        {"request_id": 1, "device_label": "device"},
        {"request_id": str(uuid4()), "device_label": 1},
        {"request_id": str(uuid4()), "device_label": " "},
        {"request_id": str(uuid4()), "device_label": "x" * 129},
        {"request_id": str(uuid4()), "device_label": "bad\x00label"},
        {"request_id": str(uuid4()), "device_label": "bad\ud800label"},
    ],
)
def test_register_rejects_invalid_direct_payload_before_database(payload):
    with pytest.raises(DeviceKeyError) as error:
        DeviceRegistrationStore(UnavailableDatabase()).register(claims(), payload)
    assert (error.value.code, error.value.status) == ("invalid_request", 422)

@pytest.mark.parametrize("method", ["register", "get_receipt", "get_identity"])
def test_persistence_failures_use_fixed_public_error_without_exception_chain(method):
    service = DeviceRegistrationStore(UnavailableDatabase())
    with pytest.raises(DeviceKeyError) as error:
        if method == "register":
            service.register(claims(), valid_payload())
        else:
            getattr(service, method)(claims(), str(uuid4()))
    expected = "registration_outcome_unknown" if method == "register" else "device_registration_unavailable"
    assert (error.value.code, error.value.status) == (expected, 503)
    assert error.value.__cause__ is None
    assert "sensitive" not in str(error.value)


@pytest.mark.parametrize("method", ["get_receipt", "get_identity"])
def test_get_rejects_noncanonical_uuid_before_database(method):
    with pytest.raises(DeviceKeyError) as error:
        getattr(DeviceRegistrationStore(UnavailableDatabase()), method)(claims(), str(uuid4()).upper())
    assert (error.value.code, error.value.status) == ("invalid_request", 422)
