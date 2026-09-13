-- No public application table-write privileges are added for registration.
ALTER TABLE public.pilot_trial_accounts DROP CONSTRAINT IF EXISTS pilot_trial_accounts_credential_kind_check;
ALTER TABLE public.pilot_trial_accounts ADD CONSTRAINT pilot_trial_accounts_credential_kind_check
 CHECK (credential_kind IN ('SMS_TRIAL','TEMPORARY_ACCESS','SELF_SERVICE_SMS'));
ALTER TABLE public.pilot_trial_accounts ALTER COLUMN phone_ciphertext DROP NOT NULL;
ALTER TABLE public.pilot_trial_accounts ALTER COLUMN code_hash DROP NOT NULL;
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='trial_registration_shape' AND conrelid='public.pilot_trial_accounts'::regclass) THEN
  ALTER TABLE public.pilot_trial_accounts ADD CONSTRAINT trial_registration_shape CHECK (
   (credential_kind='SELF_SERVICE_SMS' AND days=3 AND activation_source='SMS' AND activated_at IS NOT NULL
     AND phone_ciphertext IS NULL AND code_hash IS NULL)
   OR (credential_kind<>'SELF_SERVICE_SMS' AND phone_ciphertext IS NOT NULL AND code_hash IS NOT NULL));
 END IF;
END $$;

CREATE OR REPLACE FUNCTION public.pilot_register_sms_trial(p_phone text, p_challenge uuid, p_otp_hash text)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE selected_user text; new_tenant text; stamp timestamptz; trial record;
BEGIN
 IF p_phone IS NULL OR p_phone !~ '^[a-f0-9]{64}$' OR p_phone IS DISTINCT FROM current_setting('yike.auth_phone',true)
    OR p_otp_hash IS NULL OR p_otp_hash !~ '^[a-f0-9]{64}$' THEN
  RAISE EXCEPTION 'invalid registration context';
 END IF;
 PERFORM pg_advisory_xact_lock(10901,0);
 PERFORM 1 FROM public.pilot_phone_challenges WHERE phone_hash=p_phone AND challenge_id=p_challenge
  AND otp_hash=p_otp_hash AND state='ACCEPTED' AND failures<5 AND NOT consumed
  AND expires_at>clock_timestamp() FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'invalid registration challenge'; END IF;
 stamp := clock_timestamp();
 SELECT user_id INTO selected_user FROM public.pilot_phone_bindings WHERE phone_hash=p_phone;
 IF selected_user IS NOT NULL THEN
  SELECT * INTO trial FROM public.pilot_trial_accounts WHERE user_id=selected_user FOR UPDATE;
  IF FOUND THEN
   IF trial.revoked_at IS NOT NULL OR trial.expires_at<=stamp
      OR (trial.activated_at IS NULL AND trial.redeem_before<=stamp) THEN
    RAISE EXCEPTION 'trial expired' USING ERRCODE='YK003';
   END IF;
   IF trial.activated_at IS NULL THEN
    IF trial.credential_kind<>'SMS_TRIAL' THEN RAISE EXCEPTION 'trial unavailable'; END IF;
    UPDATE public.pilot_trial_accounts SET days=3,activated_at=stamp,
      expires_at=stamp+interval '72 hours',activation_source='SMS' WHERE user_id=selected_user;
   END IF;
  END IF;
 ELSE
  selected_user := gen_random_uuid()::text;
  new_tenant := gen_random_uuid()::text;
  INSERT INTO public.pilot_tenants(tenant_id,name) VALUES(new_tenant,'短信注册客户');
  INSERT INTO public.pilot_users(user_id,tenant_id,email) VALUES(selected_user,new_tenant,selected_user||'@trial.invalid');
  INSERT INTO public.pilot_phone_bindings(phone_hash,user_id,phone_verified_at) VALUES(p_phone,selected_user,stamp);
  INSERT INTO public.pilot_trial_accounts(trial_id,user_id,phone_hash,days,activated_at,expires_at,credential_kind,activation_source)
   VALUES(gen_random_uuid(),selected_user,p_phone,3,stamp,stamp+interval '72 hours','SELF_SERVICE_SMS','SMS');
 END IF;
 RETURN selected_user;
END $$;
REVOKE ALL ON FUNCTION public.pilot_register_sms_trial(text,uuid,text) FROM PUBLIC;
