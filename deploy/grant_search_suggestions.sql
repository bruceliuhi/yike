-- Trusted migration-time operation. Set yike.app_role; never run as application.
DO $$
DECLARE
    target_role TEXT := NULLIF(current_setting('yike.app_role',true),'');
    target_oid OID;
    reachable_role TEXT;
    relation_name TEXT;
    forbidden_privilege TEXT;
BEGIN
    SELECT oid INTO target_oid FROM pg_roles WHERE rolname=target_role
        AND NOT rolsuper AND NOT rolbypassrls AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolreplication;
    IF target_oid IS NULL THEN
        RAISE EXCEPTION 'existing restricted application role is required';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE (rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb OR rolreplication)
        AND pg_has_role(target_oid,oid,'MEMBER')) THEN
        RAISE EXCEPTION 'application role must not inherit privileged roles';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_class WHERE oid IN (
        'public.pilot_search_suggestion_requests'::regclass, 'public.pilot_search_suggestion_quota_events'::regclass,
        'public.pilot_search_suggestion_rejections'::regclass,
        'public.pilot_users'::regclass, 'public.pilot_session_revocations'::regclass,
        'public.business_profiles'::regclass, 'public.business_profile_versions'::regclass
    ) AND pg_has_role(target_oid,relowner,'MEMBER')) THEN
        RAISE EXCEPTION 'application role must not own suggestion or identity/profile tables';
    END IF;
    EXECUTE format('REVOKE ALL ON public.pilot_search_suggestion_requests,public.pilot_search_suggestion_quota_events,public.pilot_search_suggestion_rejections FROM %I',target_role);
    EXECUTE format('GRANT SELECT,INSERT,UPDATE ON public.pilot_search_suggestion_requests TO %I',target_role);
    EXECUTE format('GRANT SELECT,INSERT ON public.pilot_search_suggestion_quota_events TO %I',target_role);
    EXECUTE format('GRANT SELECT,INSERT ON public.pilot_search_suggestion_rejections TO %I',target_role);
    -- NOINHERIT suppresses current ACLs but does not prevent SET ROLE. MEMBER
    -- covers the transitive membership closure on PG15/16; conservatively reject
    -- excess parent ACLs even where a newer server disables SET on a membership.
    FOR reachable_role IN SELECT rolname FROM pg_roles
        WHERE oid=target_oid OR pg_has_role(target_oid,oid,'MEMBER') LOOP
        FOREACH relation_name IN ARRAY ARRAY['public.pilot_search_suggestion_requests','public.pilot_search_suggestion_quota_events','public.pilot_search_suggestion_rejections'] LOOP
            FOREACH forbidden_privilege IN ARRAY ARRAY['DELETE','TRUNCATE','REFERENCES','TRIGGER'] LOOP
                IF has_table_privilege(reachable_role,relation_name,forbidden_privilege) THEN
                    RAISE EXCEPTION 'application role has excess reachable suggestion privileges';
                END IF;
            END LOOP;
            -- Direct REVOKE cannot remove column ACLs inherited from PUBLIC/roles.
            IF has_any_column_privilege(reachable_role,relation_name,'REFERENCES') THEN
                RAISE EXCEPTION 'application role has excess reachable suggestion column privileges';
            END IF;
        END LOOP;
        IF has_any_column_privilege(reachable_role,'public.pilot_search_suggestion_quota_events','UPDATE') THEN
            RAISE EXCEPTION 'application role has excess reachable quota privileges';
        END IF;
        IF has_any_column_privilege(reachable_role,'public.pilot_search_suggestion_rejections','UPDATE') THEN
            RAISE EXCEPTION 'application role has excess reachable rejection privileges';
        END IF;
    END LOOP;
END $$;
