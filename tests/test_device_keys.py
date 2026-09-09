import base64
from uuid import uuid4

import pytest
from nacl.signing import SigningKey
from pydantic import ValidationError

from pilot.device_keys import ChallengeRequest, CompletionProof, DeviceKeyError, verify_signature


def encoded(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def test_real_ed25519_verification():
    key = SigningKey.generate()
    public = encoded(key.verify_key.encode())
    signature = encoded(key.sign(b"server payload").signature)
    verify_signature(public, signature, "server payload")
    with pytest.raises(DeviceKeyError, match="invalid_proof"):
        verify_signature(public, signature, "other payload")


def test_identity_point_forgery_is_not_possession():
    identity = bytes([1]) + bytes(31)
    with pytest.raises(DeviceKeyError, match="invalid_proof"):
        verify_signature(encoded(identity), encoded(identity + bytes(32)), "arbitrary server payload")


@pytest.mark.parametrize("point", [bytes(32), bytes([1]) + bytes(31), bytes([255]) * 32])
def test_invalid_curve_points_are_not_bindable(point):
    with pytest.raises(DeviceKeyError, match="invalid_request"):
        ChallengeRequest(request_id=str(uuid4()), operation="BIND", expected_credential_version=0,
                         public_key=encoded(point))


@pytest.mark.parametrize("change", [
    {"request_id": "not-uuid"}, {"request_id": 1}, {"extra": "rejected"},
    {"expected_credential_version": True}, {"expected_credential_version": "0"},
    {"expected_credential_version": 2147483647}, {"expected_credential_version": -1},
    {"public_key": "a" * 43 + "="}, {"public_key": "a" * 42},
    {"public_key": "a" * 43}, {"operation": "bind"},
])
def test_challenge_strict_contract(change):
    body = dict(request_id=str(uuid4()), operation="BIND", expected_credential_version=0,
                public_key=encoded(SigningKey.generate().verify_key.encode()))
    with pytest.raises((ValidationError, DeviceKeyError)):
        ChallengeRequest(**(body | change))


@pytest.mark.parametrize("body", [
    {"signature": "a" * 86 + "="}, {"signature": "a" * 85},
    {"signature": 123}, {"signature": "a" * 86, "token": "secret"},
])
def test_proof_strict_contract(body):
    with pytest.raises((ValidationError, DeviceKeyError)):
        CompletionProof(**body)
