"""Restricted operator provisioning. Phone plaintext exists only in ops memory."""
import hashlib
import json
import re
import secrets
from uuid import UUID, uuid4

from nacl.secret import SecretBox
import psycopg

from pilot.phone_auth import PhoneAuthStore


TRIAL_CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
USER_STATES = ('pending', 'active', 'expired', 'revoked', 'no_trial')
AUDIT_ACTIONS = ('ISSUE', 'REISSUE', 'REVOKE', 'ISSUE_ACCESS')
AUDIT_RESULTS = ('SUCCEEDED', 'REJECTED', 'FAILED')
_USER_STATE_FILTERS = {
    'pending': "a.trial_id IS NOT NULL AND a.revoked_at IS NULL AND a.activated_at IS NULL AND a.redeem_before > clock_timestamp()",
    'active': "a.trial_id IS NOT NULL AND a.revoked_at IS NULL AND a.activated_at IS NOT NULL AND (a.expires_at IS NULL OR a.expires_at > clock_timestamp())",
    'expired': "a.trial_id IS NOT NULL AND a.revoked_at IS NULL AND ((a.activated_at IS NOT NULL AND a.expires_at <= clock_timestamp()) OR (a.activated_at IS NULL AND a.redeem_before <= clock_timestamp()))",
    'revoked': "a.revoked_at IS NOT NULL",
    'no_trial': "a.trial_id IS NULL",
}


def new_trial_code() -> str:
    """Return the customer-facing eight-character trial code."""
    return ''.join(secrets.choice(TRIAL_CODE_ALPHABET) for _ in range(8))


class OpsError(ValueError):
    pass


class OpsStore:
    def __init__(self, database, *, phone_secret: bytes, encryption_key: bytes):
        self.database = database
        self.auth = PhoneAuthStore(database, phone_secret)
        if not isinstance(encryption_key, bytes) or len(encryption_key) != SecretBox.KEY_SIZE:
            raise OpsError('invalid_ops_configuration')
        self.box = SecretBox(encryption_key)
        with database.connect() as c:
            unsafe = c.execute(
                "SELECT EXISTS(SELECT 1 FROM pg_roles WHERE pg_has_role(current_user,oid,'MEMBER') "
                "AND (rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb OR rolreplication)) "
                "OR EXISTS(SELECT 1 FROM pg_class WHERE relnamespace='public'::regnamespace "
                "AND pg_has_role(current_user,relowner,'MEMBER')) "
                "OR has_schema_privilege(current_user,'public','CREATE') "
                "OR has_table_privilege(current_user,'public.business_profiles','SELECT') "
                "OR NOT has_column_privilege(current_user,'public.pilot_trial_accounts','phone_ciphertext','SELECT')"
            ).fetchone()[0]
            if unsafe:
                raise OpsError('restricted_ops_database_required')

    @staticmethod
    def _actor_hash(token: str | None) -> str:
        """Hash the operator session; the bearer token never reaches storage."""
        return hashlib.sha256((token or '').encode()).hexdigest()

    @staticmethod
    def _error_code(error: BaseException) -> str:
        value = str(error)
        return value if re.fullmatch(r'[a-z0-9_]{1,64}', value) else 'operation_failed'

    def _audit_insert(self, connection, *, action: str, result: str, actor_hash: str,
                      trial_id: str | None = None, user_id: str | None = None,
                      error_code: str | None = None) -> None:
        if action not in AUDIT_ACTIONS or result not in AUDIT_RESULTS:
            raise OpsError('invalid_audit_event')
        connection.execute(
            'INSERT INTO pilot_ops_audit_events(event_id,action,result,actor_hash,trial_id,user_id,error_code) '
            'VALUES (%s,%s,%s,%s,%s,%s,%s)',
            (str(uuid4()), action, result, actor_hash, trial_id, user_id, error_code),
        )

    def _audit_after_failure(self, *, action: str, result: str, actor_hash: str,
                             trial_id: str | None = None, user_id: str | None = None,
                             error_code: str | None = None) -> None:
        """Best-effort rejection/failure receipt after the business tx rolled back."""
        try:
            with self.database.connect() as connection:
                self._audit_insert(connection, action=action, result=result,
                                   actor_hash=actor_hash, trial_id=trial_id,
                                   user_id=user_id, error_code=error_code)
        except (psycopg.Error, OpsError):
            # A database outage must never be converted into a fabricated audit.
            pass

    def issue(self, phone: str, name: str, days: int = 3, *, actor_token: str | None = None) -> dict:
        action = 'ISSUE'
        actor_hash = self._actor_hash(actor_token)
        user = tenant = trial = None
        try:
            if not isinstance(phone, str) or not re.fullmatch(r'1[0-9]{10}', phone):
                raise OpsError('invalid_phone')
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100 or any(ord(x) < 32 for x in name):
                raise OpsError('invalid_customer_name')
            if type(days) is not int or not 1 <= days <= 30:
                raise OpsError('invalid_trial_days')
            user, tenant, trial = (str(uuid4()) for _ in range(3))
            phone_hash = self.auth._phone(phone)
            code = new_trial_code()
            encrypted = bytes(self.box.encrypt(json.dumps({'phone': phone, 'user_id': user}).encode()))
            with self.database.connect() as c:
                # The same phone cannot create two tenants, including across processes.
                c.execute('SELECT pg_advisory_xact_lock(10901,0)')
                if c.execute('SELECT 1 FROM pilot_phone_bindings WHERE phone_hash=%s', (phone_hash,)).fetchone():
                    raise OpsError('phone_already_registered')
                c.execute('INSERT INTO pilot_tenants(tenant_id,name) VALUES (%s,%s)', (tenant, name.strip()))
                c.execute('INSERT INTO pilot_users(user_id,tenant_id,email) VALUES (%s,%s,%s)', (user,tenant,f'{user}@trial.invalid'))
                c.execute('INSERT INTO pilot_phone_bindings(phone_hash,user_id) VALUES (%s,%s)', (phone_hash,user))
                c.execute('INSERT INTO pilot_trial_accounts(trial_id,user_id,phone_hash,phone_ciphertext,code_hash,days) VALUES (%s,%s,%s,%s,%s,%s)',
                          (trial,user,phone_hash,encrypted,self.auth._digest('trial',code),days))
                self._audit_insert(c, action=action, result='SUCCEEDED', actor_hash=actor_hash,
                                   trial_id=trial, user_id=user)
        except OpsError as error:
            self._audit_after_failure(action=action, result='REJECTED', actor_hash=actor_hash,
                                       trial_id=trial, user_id=user, error_code=self._error_code(error))
            raise
        except psycopg.Error:
            self._audit_after_failure(action=action, result='FAILED', actor_hash=actor_hash,
                                       trial_id=trial, user_id=user, error_code='ops_write_failed')
            raise OpsError('ops_write_failed') from None
        return {'trial_id':trial,'user_id':user,'code':code,'days':days,'activated_at':None}

    def users(self, *, offset: int = 0, query: str = '', state: str = '') -> list[dict]:
        if type(offset) is not int or not 0 <= offset <= 1000000:
            raise OpsError('invalid_page')
        if not isinstance(query, str) or len(query) > 100 or any(ord(char) < 32 for char in query):
            raise OpsError('invalid_user_query')
        if not isinstance(state, str) or state not in ('', *USER_STATES):
            raise OpsError('invalid_user_state')
        query = query.strip()
        clauses: list[str] = []
        params: list[object] = []
        if query:
            # The operator may search customer names without loading the full
            # directory into application memory. Keep wildcard characters
            # literal so the field behaves like a normal substring search.
            pattern = '%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
            clauses.append("t.name ILIKE %s ESCAPE E'\\\\'")
            params.append(pattern)
        if state:
            clauses.append(f'({_USER_STATE_FILTERS[state]})')
        where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
        params.append(offset)
        with self.database.connect() as c:
            rows = c.execute(
                'SELECT u.user_id,t.name,u.created_at,a.trial_id,a.phone_ciphertext,a.days,'
                'a.activated_at,a.expires_at,a.revoked_at,a.redeem_before,clock_timestamp(),a.credential_kind,b.phone_verified_at '
                'FROM pilot_users u JOIN pilot_tenants t ON t.tenant_id=u.tenant_id '
                'LEFT JOIN pilot_trial_accounts a ON a.user_id=u.user_id '
                'LEFT JOIN pilot_phone_bindings b ON b.user_id=u.user_id '
                f'{where} ORDER BY u.created_at DESC,u.user_id LIMIT 50 OFFSET %s', tuple(params)
            ).fetchall()
        result=[]
        for user,name,created,trial,encrypted,days,activated,expires,revoked,deadline,now,kind,verified in rows:
            phone = None
            if encrypted is not None:
                try:
                    value = json.loads(self.box.decrypt(bytes(encrypted)))
                    if value['user_id'] != user:
                        raise ValueError
                    phone = value['phone']
                except Exception:
                    raise OpsError('phone_decryption_failed') from None
            state = '未登记试用' if trial is None else '已停用' if revoked else '已到期' if (expires and expires<=now) or (not activated and deadline<=now) else '试用中' if activated else '待激活'
            result.append(dict(user_id=user,name=name,created_at=created,trial_id=str(trial) if trial else None,
                               phone=phone,days=days,activated_at=activated,expires_at=expires,
                               redeem_before=deadline,state=state,credential_kind=kind,phone_verified_at=verified))
        return result

    def overview(self) -> dict[str, int]:
        """Return operator counts from the restricted management tables.

        The customer runtime role cannot read these tables.  Keep the query
        limited to the columns already granted to the dedicated ops role and
        derive state from one database timestamp so the dashboard does not
        mix rows across a trial-expiry boundary.
        """
        with self.database.connect() as c:
            row = c.execute(
                """
                WITH clock AS (SELECT clock_timestamp() AS now)
                SELECT
                    count(*)::int AS total,
                    count(*) FILTER (WHERE a.trial_id IS NULL)::int AS no_trial,
                    count(*) FILTER (WHERE a.revoked_at IS NOT NULL)::int AS revoked,
                    count(*) FILTER (
                        WHERE a.revoked_at IS NULL AND a.trial_id IS NOT NULL
                          AND a.activated_at IS NULL AND a.redeem_before > clock.now
                    )::int AS pending,
                    count(*) FILTER (
                        WHERE a.revoked_at IS NULL AND a.activated_at IS NOT NULL
                          AND (a.expires_at IS NULL OR a.expires_at > clock.now)
                    )::int AS active,
                    count(*) FILTER (
                        WHERE a.revoked_at IS NULL AND a.trial_id IS NOT NULL
                          AND (
                              (a.activated_at IS NOT NULL AND a.expires_at <= clock.now)
                              OR (a.activated_at IS NULL AND a.redeem_before <= clock.now)
                          )
                    )::int AS expired
                FROM pilot_users u
                CROSS JOIN clock
                LEFT JOIN pilot_trial_accounts a ON a.user_id = u.user_id
                """
            ).fetchone()
        keys = ("total", "no_trial", "revoked", "pending", "active", "expired")
        return dict(zip(keys, (int(value or 0) for value in row), strict=True))

    def revoke(self, trial_id: str, *, actor_token: str | None = None) -> None:
        action = 'REVOKE'
        actor_hash = self._actor_hash(actor_token)
        normalized = None
        try:
            normalized = str(UUID(trial_id))
        except (ValueError, TypeError, AttributeError):
            error = OpsError('invalid_trial')
            self._audit_after_failure(action=action, result='REJECTED', actor_hash=actor_hash,
                                       error_code=self._error_code(error))
            raise error from None
        try:
            with self.database.connect() as c:
                row = c.execute(
                    'UPDATE pilot_trial_accounts SET revoked_at=COALESCE(revoked_at,clock_timestamp()) '
                    'WHERE trial_id=%s AND revoked_at IS NULL RETURNING trial_id,user_id', (normalized,)).fetchone()
                if row is None:
                    # Keep repeated destructive requests visible as a rejected
                    # operator action instead of a misleading second success.
                    exists = c.execute('SELECT 1 FROM pilot_trial_accounts WHERE trial_id=%s', (normalized,)).fetchone()
                    raise OpsError('trial_already_revoked' if exists else 'trial_not_found')
                self._audit_insert(c, action=action, result='SUCCEEDED', actor_hash=actor_hash,
                                   trial_id=normalized, user_id=row[1])
        except OpsError as error:
            self._audit_after_failure(action=action, result='REJECTED', actor_hash=actor_hash,
                                       trial_id=normalized, error_code=self._error_code(error))
            raise
        except psycopg.Error:
            self._audit_after_failure(action=action, result='FAILED', actor_hash=actor_hash,
                                       trial_id=normalized, error_code='ops_write_failed')
            raise OpsError('ops_write_failed') from None

    def reissue(self, trial_id: str, *, actor_token: str | None = None) -> dict:
        action = 'REISSUE'
        actor_hash = self._actor_hash(actor_token)
        normalized = None
        try:
            normalized = str(UUID(trial_id))
        except (ValueError,TypeError,AttributeError):
            error = OpsError('invalid_trial')
            self._audit_after_failure(action=action, result='REJECTED', actor_hash=actor_hash,
                                       error_code=self._error_code(error))
            raise error from None
        code=new_trial_code()
        try:
            with self.database.connect() as c:
                row=c.execute(
                    "UPDATE pilot_trial_accounts SET code_hash=%s,redeem_before=clock_timestamp()+interval '30 days' "
                    "WHERE trial_id=%s AND activated_at IS NULL AND revoked_at IS NULL AND credential_kind='SMS_TRIAL' RETURNING user_id,days",
                    (self.auth._digest('trial',code),normalized),
                ).fetchone()
                if row is None:
                    raise OpsError('trial_not_reissuable')
                self._audit_insert(c, action=action, result='SUCCEEDED', actor_hash=actor_hash,
                                   trial_id=normalized, user_id=row[0])
            return dict(trial_id=normalized,user_id=row[0],days=row[1],code=code)
        except OpsError as error:
            self._audit_after_failure(action=action, result='REJECTED', actor_hash=actor_hash,
                                       trial_id=normalized, error_code=self._error_code(error))
            raise
        except psycopg.Error:
            self._audit_after_failure(action=action, result='FAILED', actor_hash=actor_hash,
                                       trial_id=normalized, error_code='ops_write_failed')
            raise OpsError('ops_write_failed') from None

    def issue_access(self, trial_id: str, *, actor_token: str | None = None) -> dict:
        """Explicit operator conversion/rotation, never reuse an SMS invitation."""
        action = 'ISSUE_ACCESS'
        actor_hash = self._actor_hash(actor_token)
        normalized = None
        try:
            normalized = str(UUID(trial_id))
        except (ValueError,TypeError,AttributeError):
            error = OpsError('invalid_trial')
            self._audit_after_failure(action=action, result='REJECTED', actor_hash=actor_hash,
                                       error_code=self._error_code(error))
            raise error from None
        code = 'YA-' + secrets.token_urlsafe(24)
        try:
            with self.database.connect() as c:
                row = c.execute(
                    "UPDATE pilot_trial_accounts SET credential_kind='TEMPORARY_ACCESS',access_code_hash=%s,"
                    "access_issued_at=clock_timestamp(),code_hash=%s,redeem_before=clock_timestamp()+interval '30 days',days=3 "
                    "WHERE trial_id=%s AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at>clock_timestamp()) "
                    "AND (activated_at IS NULL OR credential_kind='TEMPORARY_ACCESS') RETURNING user_id",
                    (self.auth._digest('temporary-access-v1',code),self.auth._digest('retired-trial-v1',secrets.token_urlsafe(24)),normalized),
                ).fetchone()
                if row is None:
                    raise OpsError('access_not_issuable')
                self._audit_insert(c, action=action, result='SUCCEEDED', actor_hash=actor_hash,
                                   trial_id=normalized, user_id=row[0])
            return {'trial_id':normalized,'user_id':row[0],'code':code}
        except OpsError as error:
            self._audit_after_failure(action=action, result='REJECTED', actor_hash=actor_hash,
                                       trial_id=normalized, error_code=self._error_code(error))
            raise
        except psycopg.Error:
            self._audit_after_failure(action=action, result='FAILED', actor_hash=actor_hash,
                                       trial_id=normalized, error_code='ops_write_failed')
            raise OpsError('ops_write_failed') from None

    def audit_events(self, *, offset: int = 0, action: str = '', result: str = '') -> list[dict]:
        if type(offset) is not int or not 0 <= offset <= 1000000:
            raise OpsError('invalid_page')
        if action not in ('', *AUDIT_ACTIONS) or result not in ('', *AUDIT_RESULTS):
            raise OpsError('invalid_audit_filter')
        clauses = []
        params: list[object] = []
        if action:
            clauses.append('action=%s')
            params.append(action)
        if result:
            clauses.append('result=%s')
            params.append(result)
        where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
        params.append(offset)
        with self.database.connect() as c:
            rows = c.execute(
                'SELECT created_at,action,result,actor_hash,trial_id,user_id,error_code '
                f'FROM pilot_ops_audit_events{where} ORDER BY created_at DESC,event_id DESC LIMIT 50 OFFSET %s',
                tuple(params),
            ).fetchall()
        return [dict(created_at=row[0], action=row[1], result=row[2], actor_hash=row[3],
                     trial_id=str(row[4]) if row[4] else None, user_id=row[5], error_code=row[6])
                for row in rows]

    @staticmethod
    def _session_hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def new_session(self) -> str:
        token = secrets.token_urlsafe(32)
        with self.database.connect() as c:
            c.execute('DELETE FROM pilot_ops_sessions WHERE expires_at<=clock_timestamp()')
            c.execute("INSERT INTO pilot_ops_sessions(token_hash,expires_at) VALUES (%s,clock_timestamp()+interval '2 hours')", (self._session_hash(token),))
        return token

    def session_valid(self, token: str | None) -> bool:
        if not token or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            return False
        with self.database.connect() as c:
            return c.execute('SELECT 1 FROM pilot_ops_sessions WHERE token_hash=%s AND expires_at>clock_timestamp()', (self._session_hash(token),)).fetchone() is not None

    def logout(self, token: str) -> None:
        with self.database.connect() as c:
            c.execute('DELETE FROM pilot_ops_sessions WHERE token_hash=%s', (self._session_hash(token),))
