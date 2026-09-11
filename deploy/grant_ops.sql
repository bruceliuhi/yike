-- Trusted migration connection only. Set yike.ops_role to a NEW dedicated
-- LOGIN role (NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB NOREPLICATION).
DO $$
DECLARE target_role TEXT := NULLIF(current_setting('yike.ops_role',true),''); target_oid OID; relation TEXT;
BEGIN
    SELECT oid INTO target_oid FROM pg_roles WHERE rolname=target_role;
    IF target_oid IS NULL OR EXISTS (
      SELECT 1 FROM pg_roles WHERE pg_has_role(target_oid,oid,'MEMBER')
        AND (rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb OR rolreplication)
    ) OR EXISTS (
      SELECT 1 FROM pg_class WHERE relnamespace='public'::regnamespace
        AND pg_has_role(target_oid,relowner,'MEMBER')
    ) OR has_schema_privilege(target_role,'public','CREATE') THEN
      RAISE EXCEPTION 'dedicated restricted non-owner ops role required';
    END IF;
    -- Sharing the runtime role would expose all registered phone numbers.
    IF has_table_privilege(target_role,'public.business_profiles','SELECT') THEN
      RAISE EXCEPTION 'ops and customer runtime roles must be separate';
    END IF;
    EXECUTE format('GRANT USAGE ON SCHEMA public TO %I',target_role);
    EXECUTE format('GRANT SELECT,INSERT ON public.pilot_tenants,public.pilot_users,public.pilot_phone_bindings,public.pilot_trial_accounts TO %I',target_role);
    EXECUTE format('GRANT UPDATE(revoked_at,code_hash,redeem_before) ON public.pilot_trial_accounts TO %I',target_role);
    EXECUTE format('GRANT SELECT,INSERT,DELETE ON public.pilot_ops_sessions TO %I',target_role);
    FOREACH relation IN ARRAY ARRAY['pilot_tenants','pilot_users','pilot_phone_bindings','pilot_trial_accounts','pilot_ops_sessions'] LOOP
      EXECUTE format('DROP POLICY IF EXISTS ops_operator ON public.%I',relation);
      EXECUTE format('CREATE POLICY ops_operator ON public.%I TO %I USING (true) WITH CHECK (true)',relation,target_role);
    END LOOP;
END $$;
