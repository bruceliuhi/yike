-- After 123 and queue grant: immutable claim/result history only.
DO $$ DECLARE target_role TEXT:=NULLIF(current_setting('yike.app_role',true),''); target_oid OID; table_name TEXT;
BEGIN
    SELECT oid INTO target_oid FROM pg_roles WHERE rolname=target_role
        AND NOT rolsuper AND NOT rolbypassrls AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolreplication;
    IF target_oid IS NULL THEN RAISE EXCEPTION 'restricted application role required'; END IF;
    FOREACH table_name IN ARRAY ARRAY['pilot_outreach_claims','pilot_outreach_results'] LOOP
        IF EXISTS (SELECT 1 FROM pg_class WHERE oid=table_name::regclass AND pg_has_role(target_oid,relowner,'MEMBER')) THEN
            RAISE EXCEPTION 'application role must not own dispatch history';
        END IF;
        EXECUTE format('GRANT SELECT,INSERT ON public.%I TO %I',table_name,target_role);
        IF has_table_privilege(target_oid,table_name,'UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES')
            OR has_any_column_privilege(target_oid,table_name,'UPDATE,REFERENCES') THEN
            RAISE EXCEPTION 'excess outreach dispatch privileges';
        END IF;
    END LOOP;
END $$;
