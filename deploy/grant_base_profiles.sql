-- Trusted release step for fresh installations; not a role/password provisioner.
-- Complements incremental grants; never grants all tables or changes role flags.
DO $$
DECLARE
    target_role TEXT := NULLIF(current_setting('yike.app_role', true), '');
    target_oid OID;
    reachable_role TEXT;
    relation_name TEXT;
    forbidden_privilege TEXT;
    column_name TEXT;
BEGIN
    SELECT oid INTO target_oid FROM pg_roles WHERE rolname=target_role
        AND NOT rolsuper AND NOT rolbypassrls AND NOT rolcreaterole
        AND NOT rolcreatedb AND NOT rolreplication;
    IF target_oid IS NULL THEN
        RAISE EXCEPTION 'existing restricted application role is required';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles
        WHERE (rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb OR rolreplication)
        AND pg_has_role(target_oid, oid, 'MEMBER')) THEN
        RAISE EXCEPTION 'application role must not reach privileged roles';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_class WHERE relnamespace='public'::regnamespace
        AND pg_has_role(target_oid, relowner, 'MEMBER')) THEN
        RAISE EXCEPTION 'application role must not own application objects';
    END IF;

    EXECUTE format('GRANT USAGE ON SCHEMA public TO %I', target_role);
    EXECUTE format('GRANT SELECT ON public.pilot_users,public.business_profiles,public.business_profile_versions TO %I', target_role);
    EXECUTE format('GRANT INSERT ON public.business_profiles,public.business_profile_versions TO %I', target_role);
    -- Name grants also permit row locking; payloads and identity stay immutable.
    EXECUTE format('GRANT UPDATE(name) ON public.business_profiles TO %I', target_role);
    EXECUTE format('GRANT UPDATE(status,approved_at) ON public.business_profile_versions TO %I', target_role);

    -- Fail closed on existing PUBLIC/membership/column grants, without silently
    -- revoking permissions from an administrator's other roles or workloads.
    FOR reachable_role IN SELECT rolname FROM pg_roles
        WHERE oid=target_oid OR pg_has_role(target_oid, oid, 'MEMBER') LOOP
        IF has_schema_privilege(reachable_role, 'public', 'CREATE') THEN
            RAISE EXCEPTION 'application role has excess schema privileges';
        END IF;
        IF has_any_column_privilege(reachable_role, 'public.pilot_users', 'INSERT,UPDATE') THEN
            RAISE EXCEPTION 'application role has excess identity privileges';
        END IF;
        FOREACH relation_name IN ARRAY ARRAY[
            'pilot_users','business_profiles','business_profile_versions'
        ] LOOP
            FOREACH forbidden_privilege IN ARRAY ARRAY['DELETE','TRUNCATE','REFERENCES','TRIGGER'] LOOP
                IF has_table_privilege(reachable_role, 'public.' || relation_name, forbidden_privilege) THEN
                    RAISE EXCEPTION 'application role has excess base table privileges';
                END IF;
            END LOOP;
            IF has_any_column_privilege(reachable_role, 'public.' || relation_name, 'REFERENCES') THEN
                RAISE EXCEPTION 'application role has excess base column privileges';
            END IF;
            FOR column_name IN SELECT attname FROM pg_attribute
                WHERE attrelid=('public.' || relation_name)::regclass AND attnum>0 AND NOT attisdropped
            LOOP
                IF NOT ((relation_name='business_profiles' AND column_name='name')
                    OR (relation_name='business_profile_versions' AND column_name IN ('status','approved_at')))
                    AND has_column_privilege(reachable_role, 'public.' || relation_name, column_name, 'UPDATE') THEN
                    RAISE EXCEPTION 'application role has excess base update privileges';
                END IF;
            END LOOP;
        END LOOP;
    END LOOP;
END $$;
