"""Server-side session revocation shared by JSON, HTML and development routes."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib

from pilot.auth import InvalidPilotToken, TokenClaims, verify_token_claims
from pilot.db import PilotDatabase


@dataclass(frozen=True)
class SessionIdentity:
    user_id: str
    tenant_id: str
    claims: TokenClaims | None = field(default=None, repr=False)

    def public_view(self) -> dict:
        # Same fixed scope contract as contact snapshots. Tenant comes only
        # from the authenticated registry, never from client/resource input.
        return {"authenticated": True, "user_id": self.user_id,
                "account_scope": {"id": str(self.tenant_id), "version": 1}}


class PilotSessionRegistry:
    def __init__(self, database: PilotDatabase):
        self.database = database

    @staticmethod
    def _tenant(cursor, user_id: str) -> str | None:
        cursor.execute("SELECT set_config('yike.user_id', %s, true)", (user_id,))
        # A normal session lookup needs SELECT only. The composite FK acquires
        # the reference lock on revoke and prevents reparenting existing rows.
        cursor.execute("SELECT tenant_id FROM pilot_users WHERE user_id=%s", (user_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        cursor.execute("SELECT set_config('yike.tenant_id', %s, true)", (row[0],))
        return row[0]

    def authenticate(self, claims: TokenClaims) -> str:
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                return self.require_active(cursor, claims)

    @staticmethod
    def _lock_id(claims: TokenClaims) -> int:
        raw = ("yike-session-fence-v1\0" + claims.user_id + "\0" + claims.revocation_key).encode()
        return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big", signed=True)

    @classmethod
    def lock_session(cls, cursor, claims: TokenClaims) -> None:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", (cls._lock_id(claims),))

    def require_active(self, cursor, claims: TokenClaims) -> str:
        self.lock_session(cursor, claims)
        tenant = self._tenant(cursor, claims.user_id)
        if tenant is None:
            raise PermissionError("pilot user is not provisioned")
        cursor.execute(
            "SELECT EXISTS(SELECT 1 FROM pilot_session_revocations WHERE user_id=%s AND revocation_key=%s), "
            "extract(epoch FROM clock_timestamp()) >= %s",
            (claims.user_id, claims.revocation_key, claims.expires_at),
        )
        revoked, expired = cursor.fetchone()
        if revoked or expired:
            raise InvalidPilotToken("invalid pilot token")
        return tenant

    def revoke(self, credentials: list[TokenClaims]) -> None:
        # All credentials in a logout share one transaction, including when
        # Bearer and Cookie refer to different customers. Never persist tokens.
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                ordered = sorted(set(credentials), key=self._lock_id)
                for claims in ordered:
                    self.lock_session(cursor, claims)
                for claims in ordered:
                    tenant = self._tenant(cursor, claims.user_id)
                    if tenant is None:
                        continue  # An unprovisioned identity already cannot access.
                    cursor.execute(
                        "INSERT INTO pilot_session_revocations(tenant_id,user_id,revocation_key,expires_at) "
                        "VALUES (%s,%s,%s,%s) ON CONFLICT (user_id,revocation_key) DO NOTHING",
                        (tenant, claims.user_id, claims.revocation_key, datetime.fromtimestamp(claims.expires_at, UTC)),
                    )


def authenticate_session(store, token: str, secret: str) -> SessionIdentity:
    claims = verify_token_claims(token, secret)
    return SessionIdentity(claims.user_id, store.sessions.authenticate(claims), claims)


def revoke_session_tokens(store, tokens: list[str | None], secret: str) -> None:
    verified = []
    for token in tokens:
        try:
            verified.append(verify_token_claims(token, secret))
        except InvalidPilotToken:
            continue  # A malformed/expired Bearer must not shadow a valid Cookie.
    if verified:
        store.sessions.revoke(verified)
