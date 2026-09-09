-- Administrator-only, repeatable release step after migration 111.
DO $$
DECLARE target_role TEXT := NULLIF(current_setting('yike.app_role',true),''); target_oid OID; item TEXT;
BEGIN
    SELECT oid INTO target_oid FROM pg_roles WHERE rolname=target_role AND NOT rolsuper
        AND NOT rolbypassrls AND NOT rolcreaterole;
    IF target_oid IS NULL THEN RAISE EXCEPTION 'existing restricted application role is required'; END IF;
    IF EXISTS (SELECT 1 FROM pg_class WHERE relowner=target_oid AND oid IN
        ('pilot_collection_tasks'::regclass,'pilot_collection_runs'::regclass,
         'pilot_collection_platform_runs'::regclass,'pilot_execution_operations'::regclass,
         'pilot_devices'::regclass,'pilot_users'::regclass,'business_profile_versions'::regclass)) THEN
        RAISE EXCEPTION 'application role must not own execution registry tables';
    END IF;
    FOREACH item IN ARRAY ARRAY['pilot_collection_tasks','pilot_collection_runs','pilot_collection_platform_runs','pilot_execution_operations'] LOOP
        EXECUTE format('REVOKE ALL ON TABLE public.%I FROM %I',item,target_role);
        EXECUTE format('GRANT SELECT, INSERT ON TABLE public.%I TO %I',item,target_role);
    END LOOP;
    EXECUTE format('GRANT UPDATE(status) ON public.pilot_collection_tasks, public.pilot_collection_runs TO %I',target_role);
    EXECUTE format('GRANT UPDATE(status,credential_version,lease_id,execution_generation,lease_expires_at,records_used) ON public.pilot_collection_platform_runs TO %I',target_role);
END $$;
