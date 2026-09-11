-- Trusted migration connection, yike.app_role set by grant_runtime.sql.
DO $$
DECLARE target_role TEXT := NULLIF(current_setting('yike.app_role',true),''); target_oid OID;
BEGIN
    SELECT oid INTO target_oid FROM pg_roles WHERE rolname=target_role
      AND NOT rolsuper AND NOT rolbypassrls AND NOT rolcreaterole AND NOT rolcreatedb;
    IF target_oid IS NULL OR EXISTS (
        SELECT 1 FROM pg_class WHERE oid='public.pilot_trial_accounts'::regclass
        AND pg_has_role(target_oid,relowner,'MEMBER')
    ) THEN RAISE EXCEPTION 'restricted non-owner runtime role required'; END IF;
    EXECUTE format('GRANT SELECT(trial_id,user_id,code_hash,days,redeem_before,activated_at,expires_at,revoked_at) ON public.pilot_trial_accounts TO %I',target_role);
    EXECUTE format('GRANT UPDATE(activated_at,expires_at) ON public.pilot_trial_accounts TO %I',target_role);
END $$;
