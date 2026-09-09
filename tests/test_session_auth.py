"""Pure token contracts, not customer login or SMS delivery evidence."""
import base64
import hashlib
import hmac
import json

import pytest

from pilot.auth import InvalidPilotToken, issue_token, verify_token, verify_token_claims


def sign_legacy(payload):
    raw = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=")
    signature = hmac.new(b"test-secret", raw, hashlib.sha256).digest()
    return raw.decode() + "." + base64.urlsafe_b64encode(signature).rstrip(b"=").decode()


def test_same_second_credentials_are_independently_revocable():
    first = issue_token("user-1", "test-secret", now=100)
    second = issue_token("user-1", "test-secret", now=100)
    assert first != second
    assert verify_token(first, "test-secret", now=101) == "user-1"
    assert verify_token(second, "test-secret", now=101) == "user-1"


@pytest.mark.parametrize("payload", [
    {"sub": "", "exp": 1000}, {"sub": "  ", "exp": 1000},
    {"sub": "user-1", "exp": "1000"}, {"sub": "user-1", "exp": 1000.1},
    {"sub": "user-1", "exp": True}, {"sub": "user-1", "exp": 10**50},
])
def test_signed_malformed_identity_is_rejected(payload):
    with pytest.raises(InvalidPilotToken):
        verify_token(sign_legacy(payload), "test-secret", now=0)


def test_legacy_token_without_jti_remains_cryptographically_valid():
    assert verify_token(sign_legacy({"sub": "user-1", "exp": 1000}), "test-secret", now=100) == "user-1"


def test_revocation_key_uses_verified_bytes_and_survives_signature_padding():
    token = issue_token("user-1", "test-secret", now=100)
    claims = verify_token_claims(token, "test-secret", now=101)
    padded = verify_token_claims(token + "=", "test-secret", now=101)
    assert claims == padded
    assert claims.revocation_key == hashlib.sha256(token.split(".")[0].encode()).hexdigest()
    assert token not in repr(claims)


def test_noncanonical_signature_bits_are_rejected():
    token = issue_token("user-1", "test-secret", now=100)
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    variant = token[:-1] + alphabet[alphabet.index(token[-1]) + 1]
    with pytest.raises(InvalidPilotToken):
        verify_token(variant, "test-secret", now=101)


@pytest.mark.parametrize("token", ["broken", "x.y.z", "a.é", "x" * 16_385, None])
def test_malformed_credential_has_generic_error(token):
    with pytest.raises(InvalidPilotToken, match="invalid pilot token"):
        verify_token(token, "test-secret")
