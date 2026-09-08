from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time


class InvalidPilotToken(PermissionError):
    pass


def issue_token(user_id: str, secret: str, *, ttl_seconds: int = 3600, now: int | None = None) -> str:
    payload = {"sub": user_id, "exp": (now if now is not None else int(time.time())) + ttl_seconds}
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).rstrip(b"=")
    signature = hmac.new(secret.encode(), raw, hashlib.sha256).digest()
    return raw.decode() + "." + base64.urlsafe_b64encode(signature).rstrip(b"=").decode()


def verify_token(token: str, secret: str, *, now: int | None = None) -> str:
    try:
        encoded, encoded_sig = token.split(".", 1)
        raw = encoded.encode()
        expected = hmac.new(secret.encode(), raw, hashlib.sha256).digest()
        supplied = base64.urlsafe_b64decode(encoded_sig + "=" * (-len(encoded_sig) % 4))
        if not hmac.compare_digest(expected, supplied):
            raise InvalidPilotToken("invalid pilot token")
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if not isinstance(payload, dict) or not isinstance(payload.get("sub"), str) or int(payload.get("exp", 0)) <= (now if now is not None else int(time.time())):
            raise InvalidPilotToken("expired pilot token")
        return payload["sub"]
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, base64.binascii.Error) as error:
        raise InvalidPilotToken("invalid pilot token") from error
