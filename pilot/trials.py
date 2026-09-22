"""SMS entitlement activation remains AFTER phone OTP verification."""
import hmac
import re
import psycopg

from pilot.phone_auth import PhoneAuthError, PhoneAuthStore


_NEW_TRIAL_CODE = re.compile(r'^[A-Z0-9]{8}$')
_LEGACY_TRIAL_CODE = re.compile(r'^YK-[A-Za-z0-9_-]{32,}$')


def valid_trial_code(value: str) -> bool:
    """Accept current eight-character codes and already-issued legacy codes."""
    return bool(_NEW_TRIAL_CODE.fullmatch(value) or _LEGACY_TRIAL_CODE.fullmatch(value))


class TrialPhoneAuthStore(PhoneAuthStore):
    self_registration = True
    def consume(self, phone: str, code: str) -> str:
        return self.consume_trial(phone, code, None)

    def consume_trial(self, phone: str, code: str, trial_code: str | None) -> str:
        if trial_code is not None and (not isinstance(trial_code, str) or not valid_trial_code(trial_code)):
            raise PhoneAuthError('trial_invalid')

        def activate(connection, user_id):
            connection.execute("SELECT set_config('yike.user_id',%s,true)", (user_id,))
            row = connection.execute(
                'SELECT code_hash,days,activated_at,expires_at,revoked_at,redeem_before,credential_kind '
                'FROM pilot_trial_accounts WHERE user_id=%s FOR UPDATE', (user_id,)
            ).fetchone()
            now = connection.execute('SELECT clock_timestamp()').fetchone()[0]
            if row is None:
                if trial_code:
                    raise PhoneAuthError('trial_invalid')
                connection.execute('UPDATE pilot_phone_bindings SET phone_verified_at=COALESCE(phone_verified_at,clock_timestamp()) WHERE user_id=%s', (user_id,))
                return  # Existing non-trial accounts retain their own access.
            digest, days, activated, expires, revoked, deadline, kind = row
            if revoked is not None or (expires is not None and expires <= now):
                raise PhoneAuthError('trial_expired')
            if activated is not None:
                if trial_code:
                    raise PhoneAuthError('trial_already_used')
                connection.execute('UPDATE pilot_phone_bindings SET phone_verified_at=COALESCE(phone_verified_at,clock_timestamp()) WHERE user_id=%s', (user_id,))
                return
            if kind != 'SMS_TRIAL':
                raise PhoneAuthError('trial_invalid')
            # SMS verification is the self-service activation proof. Pending
            # operator invitations remain compatible with this path: the
            # atomic 72-hour activation is performed by the registration
            # function before this entitlement hook runs.
            if not trial_code:
                connection.execute('UPDATE pilot_phone_bindings SET phone_verified_at=COALESCE(phone_verified_at,clock_timestamp()) WHERE user_id=%s', (user_id,))
                return
            if deadline <= now or not hmac.compare_digest(digest, self._digest('trial', trial_code)):
                raise PhoneAuthError('trial_invalid')
            connection.execute(
                "UPDATE pilot_trial_accounts SET activated_at=%s,expires_at=%s::timestamptz + %s * interval '24 hours',activation_source='SMS' WHERE user_id=%s",
                (now, now, days, user_id),
            )
            connection.execute('UPDATE pilot_phone_bindings SET phone_verified_at=COALESCE(phone_verified_at,clock_timestamp()) WHERE user_id=%s', (user_id,))

        def register(connection, phone_hash, challenge, otp_hash):
            try:
                return connection.execute('SELECT public.pilot_register_sms_trial(%s,%s,%s)',
                                          (phone_hash,challenge,otp_hash)).fetchone()[0]
            except psycopg.Error as error:
                if error.sqlstate == 'YK003':
                    raise PhoneAuthError('trial_expired') from None
                raise

        return super().consume(phone, code, on_verified=activate,
                               resolve_verified=register if trial_code is None else None)
