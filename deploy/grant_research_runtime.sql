-- Trusted release step after migration 137; target must be the restricted app role.
DO $$ DECLARE target_role TEXT := NULLIF(current_setting('yike.app_role',true),''); target_oid OID; BEGIN
    SELECT oid INTO target_oid FROM pg_roles WHERE rolname=target_role AND NOT rolsuper
        AND NOT rolbypassrls AND NOT rolcreaterole;
    IF target_oid IS NULL THEN RAISE EXCEPTION 'existing restricted application role is required'; END IF;
    IF EXISTS (SELECT 1 FROM pg_class WHERE relowner=target_oid
        AND oid='pilot_research_runtime'::regclass) THEN
        RAISE EXCEPTION 'application role must not own research runtime table';
    END IF;
    EXECUTE format('REVOKE ALL ON TABLE public.pilot_research_runtime FROM %I',target_role);
    EXECUTE format('GRANT SELECT,INSERT ON TABLE public.pilot_research_runtime TO %I',target_role);
    EXECUTE format('GRANT UPDATE(generation,current_owner,lease_expires_at,phase,stop_code,updated_at) '
        'ON public.pilot_research_runtime TO %I',target_role);
END $$;
