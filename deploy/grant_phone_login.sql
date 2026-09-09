-- Trusted release operation after migration 109. No pilot_users grant.
DO $$
DECLARE
    target_role TEXT := NULLIF(current_setting('yike.app_role',true),'');
    target_oid OID;
BEGIN
    SELECT oid INTO target_oid FROM pg_roles WHERE rolname=target_role
        AND NOT rolsuper AND NOT rolbypassrls AND NOT rolcreaterole;
    IF target_oid IS NULL THEN
        RAISE EXCEPTION 'existing restricted application role is required';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_class WHERE oid IN (
        'public.pilot_phone_bindings'::regclass,
        'public.pilot_phone_challenges'::regclass,
        'public.pilot_phone_rates'::regclass,
        'public.pilot_users'::regclass
    ) AND relowner=target_oid) THEN
        RAISE EXCEPTION 'application role must not own identity registry tables';
    END IF;
    EXECUTE format('REVOKE ALL ON public.pilot_phone_bindings, public.pilot_phone_challenges, public.pilot_phone_rates FROM %I',target_role);
    EXECUTE format('GRANT SELECT ON public.pilot_phone_bindings TO %I',target_role);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE ON public.pilot_phone_challenges, public.pilot_phone_rates TO %I',target_role);
END $$;
