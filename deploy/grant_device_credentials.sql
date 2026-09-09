-- Trusted release operation after migration 106; never runtime credentials.
DO $$
DECLARE
    target_role TEXT := NULLIF(current_setting('yike.app_role', true), '');
    target_oid OID;
BEGIN
    SELECT oid INTO target_oid FROM pg_roles WHERE rolname=target_role
        AND NOT rolsuper AND NOT rolbypassrls AND NOT rolcreaterole;
    IF target_oid IS NULL THEN
        RAISE EXCEPTION 'existing restricted application role is required';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_class WHERE oid IN (
        'public.pilot_device_credentials'::regclass,
        'public.pilot_device_key_requests'::regclass,
        'public.pilot_devices'::regclass,
        'public.pilot_users'::regclass
    ) AND relowner=target_oid) THEN
        RAISE EXCEPTION 'application role must not own identity registry tables';
    END IF;
    EXECUTE format('GRANT SELECT, INSERT, UPDATE ON TABLE public.pilot_device_credentials TO %I', target_role);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE ON TABLE public.pilot_device_key_requests TO %I', target_role);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE ON TABLE public.pilot_devices TO %I', target_role);
    EXECUTE format('GRANT SELECT ON TABLE public.pilot_users TO %I', target_role);
    EXECUTE format('GRANT SELECT ON TABLE public.pilot_session_revocations TO %I', target_role);
    EXECUTE format('GRANT SELECT, UPDATE ON TABLE public.pilot_platform_connections TO %I', target_role);
    EXECUTE format('GRANT INSERT ON TABLE public.pilot_session_revocations TO %I', target_role);
END $$;
