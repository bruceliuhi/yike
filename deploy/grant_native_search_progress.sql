-- Trusted release step after migration 140; target is the restricted app role.
DO $$
DECLARE
    target_role TEXT := NULLIF(current_setting('yike.app_role',true),'');
    target_oid OID;
    reachable_role TEXT;
    forbidden_privilege TEXT;
    immutable_column TEXT;
BEGIN
    SELECT oid INTO target_oid FROM pg_roles WHERE rolname=target_role
        AND NOT rolsuper AND NOT rolbypassrls AND NOT rolcreaterole
        AND NOT rolcreatedb AND NOT rolreplication;
    IF target_oid IS NULL THEN RAISE EXCEPTION 'restricted application role required'; END IF;
    IF EXISTS (
        SELECT 1 FROM pg_roles
         WHERE (rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb OR rolreplication)
           AND pg_has_role(target_oid,oid,'MEMBER')
    ) THEN RAISE EXCEPTION 'application role must not inherit privileged roles'; END IF;
    IF EXISTS (
        SELECT 1 FROM pg_class
         WHERE oid='pilot_native_search_progress'::regclass
           AND pg_has_role(target_oid,relowner,'MEMBER')
    ) THEN RAISE EXCEPTION 'application role must not own native search progress'; END IF;

    REVOKE ALL ON pilot_native_search_progress FROM PUBLIC;
    EXECUTE format('REVOKE ALL ON pilot_native_search_progress FROM %I',target_role);
    EXECUTE format('GRANT SELECT,INSERT ON pilot_native_search_progress TO %I',target_role);
    EXECUTE format(
        'GRANT UPDATE(cursor,revision,head_batch_request_id,updated_at) ON pilot_native_search_progress TO %I',
        target_role
    );
    FOR reachable_role IN
        SELECT rolname FROM pg_roles WHERE oid=target_oid OR pg_has_role(target_oid,oid,'MEMBER')
    LOOP
        FOREACH forbidden_privilege IN ARRAY ARRAY['DELETE','TRUNCATE','TRIGGER','REFERENCES'] LOOP
            IF has_table_privilege(reachable_role,'public.pilot_native_search_progress',forbidden_privilege)
            THEN RAISE EXCEPTION 'excess reachable native progress privileges'; END IF;
        END LOOP;
        FOREACH immutable_column IN ARRAY ARRAY[
            'tenant_id','owner_user_id','plan_id','profile_version_id','strategy_version_id',
            'platform','connection_id','connection_version','adapter_version','query'
        ] LOOP
            IF has_column_privilege(reachable_role,'public.pilot_native_search_progress',immutable_column,'UPDATE')
            THEN RAISE EXCEPTION 'excess reachable native progress update privileges'; END IF;
        END LOOP;
    END LOOP;
END $$;
