-- Trusted release operation AFTER migration 105, not part of the Web runtime.
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
    IF EXISTS (SELECT 1 FROM pg_class WHERE oid = 'public.pilot_session_revocations'::regclass AND relowner = target_oid) THEN
        RAISE EXCEPTION 'application role must not own the session table';
    END IF;
    EXECUTE format('GRANT SELECT, INSERT ON TABLE public.pilot_session_revocations TO %I', target_role);
END $$;
