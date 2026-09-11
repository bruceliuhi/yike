"""SMS entitlement activation remains AFTER phone OTP verification."""
import hmac

from pilot.phone_auth import PhoneAuthError, PhoneAuthStore


class TrialPhoneAuthStore(PhoneAuthStore):
    def consume(self, phone: str, code: str) -> str:
        return self.consume_trial(phone, code, None)

    def consume_trial(self, phone: str, code: str, trial_code: str | None) -> str:
        if trial_code is not None and (not isinstance(trial_code, str) or not 1 <= len(trial_code) <= 128):
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
            if not trial_code:
                raise PhoneAuthError('trial_required')
            if deadline <= now or not hmac.compare_digest(digest, self._digest('trial', trial_code)):
                raise PhoneAuthError('trial_invalid')
            connection.execute(
                "UPDATE pilot_trial_accounts SET activated_at=%s,expires_at=%s::timestamptz + %s * interval '24 hours',activation_source='SMS' WHERE user_id=%s",
                (now, now, days, user_id),
            )
            connection.execute('UPDATE pilot_phone_bindings SET phone_verified_at=COALESCE(phone_verified_at,clock_timestamp()) WHERE user_id=%s', (user_id,))

        return super().consume(phone, code, on_verified=activate)
