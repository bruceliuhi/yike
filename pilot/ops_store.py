"""Restricted operator provisioning. Phone plaintext exists only in ops memory."""
import hashlib
import json
import re
import secrets
from uuid import UUID, uuid4

from nacl.secret import SecretBox
import psycopg

from pilot.phone_auth import PhoneAuthStore


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

    def issue(self, phone: str, name: str, days: int = 3) -> dict:
        if not isinstance(phone, str) or not re.fullmatch(r'1[0-9]{10}', phone):
            raise OpsError('invalid_phone')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100 or any(ord(x) < 32 for x in name):
            raise OpsError('invalid_customer_name')
        if type(days) is not int or not 1 <= days <= 30:
            raise OpsError('invalid_trial_days')
        user, tenant, trial = (str(uuid4()) for _ in range(3))
        phone_hash = self.auth._phone(phone)
        code = 'YK-' + secrets.token_urlsafe(24)
        encrypted = bytes(self.box.encrypt(json.dumps({'phone': phone, 'user_id': user}).encode()))
        try:
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
        except psycopg.Error:
            raise OpsError('ops_write_failed') from None
        return {'trial_id':trial,'user_id':user,'code':code,'days':days,'activated_at':None}

    def users(self, *, offset: int = 0) -> list[dict]:
        if type(offset) is not int or not 0 <= offset <= 1000000:
            raise OpsError('invalid_page')
        with self.database.connect() as c:
            rows = c.execute(
                'SELECT u.user_id,t.name,u.created_at,a.trial_id,a.phone_ciphertext,a.days,'
                'a.activated_at,a.expires_at,a.revoked_at,a.redeem_before,clock_timestamp() '
                'FROM pilot_users u JOIN pilot_tenants t ON t.tenant_id=u.tenant_id '
                'LEFT JOIN pilot_trial_accounts a ON a.user_id=u.user_id '
                'ORDER BY u.created_at DESC,u.user_id LIMIT 50 OFFSET %s', (offset,)
            ).fetchall()
        result=[]
        for user,name,created,trial,encrypted,days,activated,expires,revoked,deadline,now in rows:
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
                               redeem_before=deadline,state=state))
        return result

    def revoke(self, trial_id: str) -> None:
        try:
            trial_id = str(UUID(trial_id))
        except (ValueError, TypeError, AttributeError):
            raise OpsError('invalid_trial') from None
        with self.database.connect() as c:
            row = c.execute('UPDATE pilot_trial_accounts SET revoked_at=COALESCE(revoked_at,clock_timestamp()) WHERE trial_id=%s RETURNING trial_id', (trial_id,)).fetchone()
            if row is None:
                raise OpsError('trial_not_found')

    def reissue(self, trial_id: str) -> dict:
        try:
            trial_id=str(UUID(trial_id))
        except (ValueError,TypeError,AttributeError):
            raise OpsError('invalid_trial') from None
        code='YK-'+secrets.token_urlsafe(24)
        with self.database.connect() as c:
            row=c.execute(
                "UPDATE pilot_trial_accounts SET code_hash=%s,redeem_before=clock_timestamp()+interval '30 days' "
                'WHERE trial_id=%s AND activated_at IS NULL AND revoked_at IS NULL RETURNING user_id,days',
                (self.auth._digest('trial',code),trial_id),
            ).fetchone()
            if row is None:
                raise OpsError('trial_not_reissuable')
        return dict(trial_id=trial_id,user_id=row[0],days=row[1],code=code)

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
