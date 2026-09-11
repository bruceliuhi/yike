from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass


class InvalidPilotToken(PermissionError):
    pass


@dataclass(frozen=True)
class TokenClaims:
    user_id: str
    expires_at: int
    revocation_key: str
    auth_source: str = 'legacy'


def issue_token(user_id: str, secret: str, *, ttl_seconds: int = 3600, now: int | None = None, auth_source: str = 'legacy') -> str:
    if auth_source not in {'legacy','sms','temporary_access'}:
        raise ValueError('invalid authentication source')
    payload = {"sub": user_id, "exp": (now if now is not None else int(time.time())) + ttl_seconds, "jti": secrets.token_urlsafe(24)}
    if auth_source != 'legacy':
        payload['auth_source'] = auth_source
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).rstrip(b"=")
    signature = hmac.new(secret.encode(), raw, hashlib.sha256).digest()
    return raw.decode() + "." + base64.urlsafe_b64encode(signature).rstrip(b"=").decode()


def verify_token(token: str, secret: str, *, now: int | None = None) -> str:
    """Signature/expiry only; HTTP access must also check the session registry."""
    return verify_token_claims(token, secret, now=now).user_id


def verify_token_claims(token: str, secret: str, *, now: int | None = None) -> TokenClaims:
    try:
        if not isinstance(token, str) or not 1 <= len(token) <= 16_384:
            raise InvalidPilotToken("invalid pilot token")
        encoded, encoded_sig = token.split(".", 1)
        raw = encoded.encode("ascii")
        expected = hmac.new(secret.encode(), raw, hashlib.sha256).digest()
        supplied = base64.b64decode(encoded_sig + "=" * (-len(encoded_sig) % 4), altchars=b"-_", validate=True)
        if base64.urlsafe_b64encode(supplied).rstrip(b"=").decode() != encoded_sig.rstrip("="):
            raise InvalidPilotToken("invalid pilot token")
        if not hmac.compare_digest(expected, supplied):
            raise InvalidPilotToken("invalid pilot token")
        payload = json.loads(base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True))
        if not isinstance(payload, dict):
            raise InvalidPilotToken("invalid pilot token")
        user_id, expires_at = payload.get("sub"), payload.get("exp")
        if (not isinstance(user_id, str) or not 1 <= len(user_id) <= 256
                or user_id != user_id.strip() or any(ord(char) < 32 for char in user_id)
                or type(expires_at) is not int or not 0 < expires_at <= 253_402_300_799):
            raise InvalidPilotToken("invalid pilot token")
        if expires_at <= (now if now is not None else int(time.time())):
            raise InvalidPilotToken("invalid pilot token")
        # Hash the exact verified signed bytes, not a re-serialized JSON object
        # or the signature spelling (which can have equivalent base64 padding).
        source = payload.get('auth_source', 'legacy')
        if source not in {'legacy','sms','temporary_access'}:
            raise InvalidPilotToken('invalid pilot token')
        return TokenClaims(user_id, expires_at, hashlib.sha256(raw).hexdigest(), source)
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, base64.binascii.Error) as error:
        raise InvalidPilotToken("invalid pilot token") from error
