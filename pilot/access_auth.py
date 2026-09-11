"""Explicit high-entropy access credentials; no SMS or database-owner access."""
from dataclasses import dataclass
from datetime import datetime
import re

import psycopg

from pilot.phone_auth import PhoneAuthStore


class AccessAuthError(ValueError):
    def __init__(self, code='access_auth_failed'):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class AccessIdentity:
    user_id: str
    expires_at: datetime


class AccessAuthStore:
    def __init__(self, database, secret: bytes):
        self.database = database
        self.auth = PhoneAuthStore(database, secret)

    def authenticate(self, access_code: str, peer: str) -> AccessIdentity:
        if not isinstance(peer, str) or not 1 <= len(peer) <= 256 or not peer.isascii() or any(ord(x) <= 32 for x in peer):
            raise AccessAuthError()
        peer_hash = self.auth._digest('temporary-access-peer-v1', peer)
        valid = isinstance(access_code, str) and re.fullmatch(r'YA-[A-Za-z0-9_-]{32}', access_code) is not None
        digest = self.auth._digest('temporary-access-v1', access_code if valid else '')
        result = None
        failure = 'access_auth_failed'
        try:
            with self.database.connect() as c:
                # Serialize rate accounting and activation even across processes.
                c.execute('SELECT pg_advisory_xact_lock(13801,0)')
                c.execute("SELECT set_config('yike.access_peer',%s,true),set_config('yike.access_hash',%s,true)", (peer_hash,digest))
                now = c.execute('SELECT clock_timestamp()').fetchone()[0]
                scopes = (('peer',peer_hash,10), ('global','service',100))
                limited = any(c.execute(
                    "SELECT count(*) FROM pilot_access_rates,unnest(hits) hit WHERE kind=%s AND scope_hash=%s AND hit>%s::timestamptz-interval '5 minutes'",
                    (kind,scope,now)).fetchone()[0] >= maximum for kind,scope,maximum in scopes)
                if limited:
                    failure = 'auth_rate_limited'
                else:
                    for kind,scope,_ in scopes:
                        c.execute("INSERT INTO pilot_access_rates(kind,scope_hash,hits) VALUES (%s,%s,ARRAY[%s::timestamptz]) "
                                  "ON CONFLICT(kind,scope_hash) DO UPDATE SET hits=ARRAY(SELECT hit FROM unnest(pilot_access_rates.hits) hit WHERE hit>%s::timestamptz-interval '5 minutes') || ARRAY[%s::timestamptz]",
                                  (kind,scope,now,now,now))
                    row = c.execute('SELECT user_id,activated_at,expires_at,revoked_at,redeem_before FROM pilot_trial_accounts '
                                    "WHERE credential_kind='TEMPORARY_ACCESS' AND access_code_hash=%s FOR UPDATE", (digest,)).fetchone() if valid else None
                    # Re-read time after waiting on a concurrent operator row lock.
                    now = c.execute('SELECT clock_timestamp()').fetchone()[0]
                    if row and row[3] is None and (row[2] > now if row[1] else row[4] > now):
                        user,activated,expires,_,_ = row
                        if activated is None:
                            expires = c.execute("UPDATE pilot_trial_accounts SET activated_at=%s,expires_at=%s::timestamptz+interval '72 hours',activation_source='TEMPORARY_ACCESS' WHERE user_id=%s RETURNING expires_at",
                                                (now,now,user)).fetchone()[0]
                        result = AccessIdentity(user, expires)
        except psycopg.Error:
            raise AccessAuthError() from None
        # Authentication failures are raised after the rate transaction commits.
        if result is None:
            raise AccessAuthError(failure)
        return result
