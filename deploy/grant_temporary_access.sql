-- Trusted administrator only, after migration 138 and existing trial grants.
DO $$
DECLARE target_role TEXT := NULLIF(current_setting('yike.app_role',true),''); target_oid OID;
BEGIN
    SELECT oid INTO target_oid FROM pg_roles WHERE rolname=target_role;
    IF target_oid IS NULL OR EXISTS (
        SELECT 1 FROM pg_roles WHERE pg_has_role(target_oid,oid,'MEMBER')
        AND (rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb OR rolreplication)
    ) OR EXISTS (
        SELECT 1 FROM pg_class WHERE oid IN ('public.pilot_trial_accounts'::regclass,
            'public.pilot_access_rates'::regclass,'public.pilot_phone_bindings'::regclass)
        AND pg_has_role(target_oid,relowner,'MEMBER')
    ) THEN RAISE EXCEPTION 'restricted non-owner runtime role required'; END IF;
    EXECUTE format('GRANT SELECT(credential_kind,access_code_hash,access_issued_at,activation_source) ON public.pilot_trial_accounts TO %I',target_role);
    EXECUTE format('GRANT UPDATE(activation_source) ON public.pilot_trial_accounts TO %I',target_role);
    EXECUTE format('GRANT UPDATE(phone_verified_at) ON public.pilot_phone_bindings TO %I',target_role);
    EXECUTE format('GRANT SELECT,INSERT,UPDATE ON public.pilot_access_rates TO %I',target_role);
END $$;
