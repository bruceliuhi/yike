-- Trusted, repeatable release step after migration 115.
DO $$
DECLARE
    target_role TEXT := NULLIF(current_setting('yike.app_role',true),'');
    target_oid OID;
    forbidden_privilege TEXT;
BEGIN
    SELECT oid INTO target_oid
    FROM pg_roles
    WHERE rolname=target_role
      AND NOT rolsuper
      AND NOT rolbypassrls
      AND NOT rolcreaterole
      AND NOT rolcreatedb
      AND NOT rolreplication;
    IF target_oid IS NULL THEN
        RAISE EXCEPTION 'existing restricted application role is required';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_class
        WHERE oid='public.pilot_opportunity_evidence'::regclass
          AND pg_has_role(target_oid,relowner,'MEMBER')
    ) THEN
        RAISE EXCEPTION 'application role must not own opportunity evidence table';
    END IF;

    EXECUTE format(
        'REVOKE ALL ON TABLE public.pilot_opportunity_evidence FROM %I',
        target_role
    );
    EXECUTE format(
        'GRANT SELECT,INSERT ON TABLE public.pilot_opportunity_evidence TO %I',
        target_role
    );

    FOREACH forbidden_privilege IN ARRAY ARRAY[
        'UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER'
    ] LOOP
        IF has_table_privilege(
            target_role,
            'public.pilot_opportunity_evidence',
            forbidden_privilege
        ) THEN
            RAISE EXCEPTION 'application role has excess opportunity evidence privileges';
        END IF;
    END LOOP;
    IF has_any_column_privilege(
        target_role,
        'public.pilot_opportunity_evidence',
        'UPDATE,REFERENCES'
    ) THEN
        RAISE EXCEPTION 'application role has excess opportunity evidence column privileges';
    END IF;
END $$;
