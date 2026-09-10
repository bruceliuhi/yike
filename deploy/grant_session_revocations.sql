-- Trusted identity-registry release operation AFTER migrations 104 and 105,
-- not part of the Web runtime. The filename is retained for compatibility.
-- Set yike.app_role to the existing application role in the same SQL session.
DO $$
DECLARE
    target_role TEXT := NULLIF(current_setting('yike.app_role', true), '');
    target_oid OID;
BEGIN
    SELECT oid INTO target_oid FROM pg_roles
        WHERE rolname = target_role AND NOT rolsuper AND NOT rolbypassrls
            AND NOT rolcreaterole;
    IF target_oid IS NULL THEN
        RAISE EXCEPTION 'existing restricted application role is required';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_class
        WHERE oid IN (
            'public.pilot_devices'::regclass,
            'public.pilot_platform_connections'::regclass,
            'public.pilot_execution_events'::regclass,
            'public.pilot_session_revocations'::regclass
        ) AND relowner = target_oid
    ) THEN
        RAISE EXCEPTION 'application role must not own identity registry tables';
    END IF;
    EXECUTE format('GRANT SELECT, INSERT, UPDATE ON TABLE public.pilot_devices TO %I', target_role);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE ON TABLE public.pilot_platform_connections TO %I', target_role);
    EXECUTE format('GRANT SELECT, INSERT ON TABLE public.pilot_execution_events TO %I', target_role);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.pilot_session_revocations TO %I', target_role);
END $$;
