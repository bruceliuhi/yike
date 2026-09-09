-- Administrator-only repeatable grant after migration 112; never run in Web.
DO $$
DECLARE target_role TEXT := NULLIF(current_setting('yike.app_role',true),''); target_oid OID; item TEXT;
BEGIN
    SELECT oid INTO target_oid FROM pg_roles WHERE rolname=target_role AND NOT rolsuper AND NOT rolbypassrls AND NOT rolcreaterole;
    IF target_oid IS NULL THEN RAISE EXCEPTION 'existing restricted application role is required'; END IF;
    FOREACH item IN ARRAY ARRAY['pilot_candidate_batches','pilot_candidate_sources','pilot_candidate_versions','pilot_candidate_projections','pilot_candidate_observations'] LOOP
        IF EXISTS (SELECT 1 FROM pg_class WHERE oid=item::regclass AND relowner=target_oid) THEN
            RAISE EXCEPTION 'application role must not own candidate tables';
        END IF;
        EXECUTE format('REVOKE ALL ON TABLE public.%I FROM %I',item,target_role);
        EXECUTE format('GRANT SELECT,INSERT ON TABLE public.%I TO %I',item,target_role);
    END LOOP;
    EXECUTE format('GRANT UPDATE(version_id,current_observation_id,revision,ambiguous,latest_observed_at) ON pilot_candidate_projections TO %I',target_role);
END $$;
