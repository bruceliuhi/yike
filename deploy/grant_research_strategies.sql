-- Trusted explicit release step after 114 and 132; never use runtime/admin credentials together.
DO $$
DECLARE target_role TEXT := NULLIF(current_setting('yike.app_role',true),''); target_oid OID;
    reachable_role TEXT; relation_name TEXT; forbidden_privilege TEXT;
BEGIN
    SELECT oid INTO target_oid FROM pg_roles WHERE rolname=target_role AND NOT rolsuper
        AND NOT rolbypassrls AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolreplication;
    IF target_oid IS NULL THEN RAISE EXCEPTION 'existing restricted application role is required'; END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE (rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb OR rolreplication)
        AND pg_has_role(target_oid,oid,'MEMBER')) THEN
        RAISE EXCEPTION 'application role must not inherit privileged roles';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_class WHERE oid IN (
        'public.pilot_research_strategy_drafts'::regclass,'public.pilot_research_strategy_versions'::regclass,
        'public.pilot_research_strategy_operations'::regclass,'public.pilot_users'::regclass,
        'public.pilot_session_revocations'::regclass,'public.business_profiles'::regclass,'public.business_profile_versions'::regclass,
        'public.pilot_material_profile_references'::regclass
    ) AND pg_has_role(target_oid,relowner,'MEMBER')) THEN
        RAISE EXCEPTION 'application role must not own strategy or identity/profile tables';
    END IF;
    EXECUTE format('REVOKE ALL ON public.pilot_research_strategy_drafts,public.pilot_research_strategy_versions,public.pilot_research_strategy_operations FROM %I',target_role);
    EXECUTE format('GRANT SELECT,INSERT,UPDATE ON public.pilot_research_strategy_drafts,public.pilot_research_strategy_versions TO %I',target_role);
    EXECUTE format('GRANT SELECT,INSERT ON public.pilot_research_strategy_operations TO %I',target_role);
    -- Qualification metadata only: never grants access to the private source material body.
    EXECUTE format('GRANT SELECT (tenant_id,target_profile_version_id,field_name,source_owner_user_id,source_profile_version_id,material_id,material_version,extraction_id,adopted_value_sha256,valid) ON public.pilot_material_profile_references TO %I',target_role);
    -- NOINHERIT does not prevent SET ROLE; inspect every reachable membership.
    FOR reachable_role IN SELECT rolname FROM pg_roles WHERE oid=target_oid OR pg_has_role(target_oid,oid,'MEMBER') LOOP
        FOREACH relation_name IN ARRAY ARRAY['public.pilot_research_strategy_drafts','public.pilot_research_strategy_versions','public.pilot_research_strategy_operations'] LOOP
            FOREACH forbidden_privilege IN ARRAY ARRAY['DELETE','TRUNCATE','REFERENCES','TRIGGER'] LOOP
                IF has_table_privilege(reachable_role,relation_name,forbidden_privilege) THEN
                    RAISE EXCEPTION 'application role has excess reachable strategy privileges';
                END IF;
            END LOOP;
            IF has_any_column_privilege(reachable_role,relation_name,'REFERENCES') THEN
                RAISE EXCEPTION 'application role has excess reachable strategy column privileges';
            END IF;
        END LOOP;
        IF has_any_column_privilege(reachable_role,'public.pilot_research_strategy_operations','UPDATE') THEN
            RAISE EXCEPTION 'application role has excess reachable operation privileges';
        END IF;
    END LOOP;
END $$;
