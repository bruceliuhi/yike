"""Bounded pre-provisioned phone authentication; never a provider integration."""
from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import hmac
import json
import re
import secrets
from uuid import UUID, uuid4

import psycopg


class PhoneAuthError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class PhoneReservation:
    challenge_id: str
    code: str = field(repr=False)
    eligible: bool = field(repr=False)


class PhoneAuthStore:
    def __init__(self, database, secret: bytes):
        if not isinstance(secret, bytes) or not 32 <= len(secret) <= 4096:
            raise PhoneAuthError('phone_auth_failed')
        self.database = database
        self._secret = secret

    def _digest(self, domain, *parts):
        message = json.dumps([domain, *parts], separators=(',', ':')).encode()
        return hmac.new(self._secret, message, hashlib.sha256).hexdigest()

    def _phone(self, phone):
        if not isinstance(phone, str) or len(phone) != 11 or not re.fullmatch(r'1[0-9]{10}', phone):
            raise PhoneAuthError('invalid_phone')
        return self._digest('phone', phone)

    @contextmanager
    def _connection(self, phone_hash, peer_hash=''):
        try:
            with self.database.connect() as c:
                c.execute("SELECT set_config('yike.auth_phone',%s,true), set_config('yike.auth_peer',%s,true)", (phone_hash, peer_hash))
                yield c
        except psycopg.Error:
            raise PhoneAuthError('phone_auth_failed') from None

    def bind_user(self, phone: str, user_id: str) -> None:
        phone_hash = self._phone(phone)
        if not isinstance(user_id, str) or not 1 <= len(user_id) <= 128:
            raise PhoneAuthError('phone_auth_failed')
        with self._connection(phone_hash) as c:
            # Provisioning is explicitly privileged, never available to app connections.
            if not c.execute('SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user').fetchone()[0]:
                raise PhoneAuthError('phone_auth_failed')
            c.execute('SELECT pg_advisory_xact_lock(10901, 0)')
            existing = c.execute('SELECT phone_hash,user_id FROM pilot_phone_bindings WHERE phone_hash=%s OR user_id=%s', (phone_hash, user_id)).fetchall()
            if existing:
                if existing != [(phone_hash, user_id)]:
                    raise PhoneAuthError('phone_auth_failed')
                return
            c.execute('INSERT INTO pilot_phone_bindings(phone_hash,user_id) VALUES (%s,%s)', (phone_hash,user_id))

    def reserve(self, phone: str, peer: str) -> PhoneReservation:
        phone_hash = self._phone(phone)
        if not isinstance(peer, str) or not 1 <= len(peer) <= 256 or not peer.isascii() or any(ord(x) <= 32 or ord(x) == 127 for x in peer):
            raise PhoneAuthError('phone_auth_failed')
        peer_hash = self._digest('peer', peer)
        challenge_id, code = str(uuid4()), f'{secrets.randbelow(1000000):06d}'
        with self._connection(phone_hash, peer_hash) as c:
            c.execute('SELECT pg_advisory_xact_lock(10901, 0)')
            now = c.execute('SELECT clock_timestamp()').fetchone()[0]
            if c.execute("SELECT 1 FROM pilot_phone_challenges WHERE phone_hash=%s AND created_at > %s::timestamptz-interval '60 seconds'", (phone_hash,now)).fetchone():
                raise PhoneAuthError('auth_rate_limited')
            scopes = [('phone',phone_hash,3), ('peer',peer_hash,10), ('global','service',100)]
            for kind, key, limit in scopes:
                row = c.execute("SELECT count(*) FROM pilot_phone_rates, unnest(hits) AS hit WHERE kind=%s AND scope_hash=%s AND hit > %s::timestamptz-interval '1 hour'", (kind,key,now)).fetchone()
                if row[0] >= limit:
                    raise PhoneAuthError('auth_rate_limited')
            for kind, key, _ in scopes:
                c.execute("INSERT INTO pilot_phone_rates(kind,scope_hash,hits) VALUES (%s,%s,ARRAY[%s::timestamptz]) ON CONFLICT(kind,scope_hash) DO UPDATE SET hits=ARRAY(SELECT hit FROM unnest(pilot_phone_rates.hits) AS hit WHERE hit > %s::timestamptz-interval '1 hour') || ARRAY[%s::timestamptz]", (kind,key,now,now,now))
            eligible = c.execute('SELECT user_id FROM pilot_phone_bindings WHERE phone_hash=%s', (phone_hash,)).fetchone() is not None
            otp_hash = self._digest('otp', 'login', phone_hash, challenge_id, code)
            c.execute("INSERT INTO pilot_phone_challenges(phone_hash,challenge_id,otp_hash,created_at,expires_at) VALUES (%s,%s,%s,%s,%s::timestamptz+interval '300 seconds') ON CONFLICT(phone_hash) DO UPDATE SET challenge_id=EXCLUDED.challenge_id,otp_hash=EXCLUDED.otp_hash,created_at=EXCLUDED.created_at,expires_at=EXCLUDED.expires_at,state='PENDING',failures=0,consumed=false", (phone_hash,challenge_id,otp_hash,now,now))
        return PhoneReservation(challenge_id,code,eligible)

    def settle(self, phone: str, challenge_id: str, state: str) -> None:
        phone_hash = self._phone(phone)
        if not isinstance(challenge_id,str) or len(challenge_id) != 36 or state not in ('ACCEPTED','REJECTED','UNKNOWN'):
            raise PhoneAuthError('phone_auth_failed')
        try:
            if str(UUID(challenge_id)) != challenge_id:
                raise ValueError
        except ValueError:
            raise PhoneAuthError('phone_auth_failed') from None
        with self._connection(phone_hash) as c:
            c.execute("UPDATE pilot_phone_challenges SET state=%s WHERE phone_hash=%s AND challenge_id=%s AND state='PENDING' AND expires_at>clock_timestamp()", (state,phone_hash,challenge_id))

    def consume(self, phone: str, code: str, *, on_verified=None) -> str:
        phone_hash = self._phone(phone)
        if not isinstance(code,str) or len(code) != 6 or not re.fullmatch(r'[0-9]{6}',code):
            raise PhoneAuthError('invalid_code')
        user = None
        with self._connection(phone_hash) as c:
            row = c.execute("SELECT challenge_id,otp_hash,state,failures,consumed,expires_at FROM pilot_phone_challenges WHERE phone_hash=%s FOR UPDATE", (phone_hash,)).fetchone()
            # Evaluate time after lock acquisition, not while waiting on another consumer.
            now = c.execute('SELECT clock_timestamp()').fetchone()[0]
            if row and row[2] == 'ACCEPTED' and row[3] < 5 and not row[4] and row[5] > now:
                matches = hmac.compare_digest(row[1],self._digest('otp','login',phone_hash,str(row[0]),code))
                if matches:
                    binding = c.execute('SELECT user_id FROM pilot_phone_bindings WHERE phone_hash=%s',(phone_hash,)).fetchone()
                    user = binding[0] if binding else None
                    if user is not None and on_verified is not None:
                        # Trusted in-process entitlement hook; same transaction
                        # as one-time OTP consumption, never a request callback.
                        on_verified(c, user)
                    c.execute('UPDATE pilot_phone_challenges SET consumed=true WHERE phone_hash=%s',(phone_hash,))
                else:
                    c.execute('UPDATE pilot_phone_challenges SET failures=failures+1 WHERE phone_hash=%s',(phone_hash,))
        # Failed guesses must commit before raising, including across restarts.
        if user is None:
            raise PhoneAuthError('phone_auth_failed')
        return user
