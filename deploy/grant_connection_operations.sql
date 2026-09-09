-- Trusted release operation after107. Never runtime/admin credential mixing.
DO $$
DECLARE target_role TEXT := NULLIF(current_setting('yike.app_role',true),''); target_oid OID;
BEGIN
    SELECT oid INTO target_oid FROM pg_roles WHERE rolname=target_role
        AND NOT rolsuper AND NOT rolbypassrls AND NOT rolcreaterole;
    IF target_oid IS NULL THEN
        RAISE EXCEPTION 'existing restricted application role is required';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_class WHERE oid IN (
        'public.pilot_connection_operations'::regclass, 'public.pilot_platform_connections'::regclass,
        'public.pilot_devices'::regclass, 'public.pilot_users'::regclass
    ) AND relowner=target_oid) THEN
        RAISE EXCEPTION 'application role must not own connection registry tables';
    END IF;
    EXECUTE format('GRANT SELECT, INSERT ON TABLE public.pilot_connection_operations TO %I',target_role);
END $$;
