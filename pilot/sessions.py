"""Server-side session revocation shared by JSON, HTML and development routes."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from pilot.auth import InvalidPilotToken, TokenClaims, verify_token_claims
from pilot.db import PilotDatabase


@dataclass(frozen=True)
class SessionIdentity:
    user_id: str
    tenant_id: str


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
                tenant = self._tenant(cursor, claims.user_id)
                if tenant is None:
                    raise PermissionError("pilot user is not provisioned")
                cursor.execute(
                    "SELECT 1 FROM pilot_session_revocations WHERE user_id=%s AND revocation_key=%s",
                    (claims.user_id, claims.revocation_key),
                )
                if cursor.fetchone() is not None:
                    raise InvalidPilotToken("invalid pilot token")
                return tenant

    def revoke(self, credentials: list[TokenClaims]) -> None:
        # All credentials in a logout share one transaction, including when
        # Bearer and Cookie refer to different customers. Never persist tokens.
        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                for claims in sorted(set(credentials), key=lambda item: (item.user_id, item.revocation_key)):
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
    return SessionIdentity(claims.user_id, store.sessions.authenticate(claims))


def revoke_session_tokens(store, tokens: list[str | None], secret: str) -> None:
    verified = []
    for token in tokens:
        try:
            verified.append(verify_token_claims(token, secret))
        except InvalidPilotToken:
            continue  # A malformed/expired Bearer must not shadow a valid Cookie.
    if verified:
        store.sessions.revoke(verified)
