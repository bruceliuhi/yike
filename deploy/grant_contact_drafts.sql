-- Administrator release step; never grant mutation of draft history.
DO $$ DECLARE target_role TEXT:=NULLIF(current_setting('yike.app_role',true),''); target_oid OID;
BEGIN
    SELECT oid INTO target_oid FROM pg_roles WHERE rolname=target_role
        AND NOT rolsuper AND NOT rolbypassrls AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolreplication;
    IF target_oid IS NULL THEN RAISE EXCEPTION 'restricted application role required'; END IF;
    IF EXISTS (SELECT 1 FROM pg_class WHERE oid='public.pilot_contact_drafts'::regclass AND pg_has_role(target_oid,relowner,'MEMBER')) THEN
        RAISE EXCEPTION 'application role must not own contact drafts';
    END IF;
    EXECUTE format('GRANT SELECT,INSERT ON public.pilot_contact_drafts TO %I',target_role);
    IF EXISTS (SELECT 1 FROM pg_class WHERE oid='public.pilot_material_revisions'::regclass AND pg_has_role(target_oid,relowner,'MEMBER')) THEN
        RAISE EXCEPTION 'application role must not own material revisions';
    END IF;
    EXECUTE format('GRANT SELECT ON public.pilot_material_revisions TO %I',target_role);
    IF has_table_privilege(target_oid,'public.pilot_contact_drafts','UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES')
        OR has_any_column_privilege(target_oid,'public.pilot_contact_drafts','UPDATE,REFERENCES') THEN
        RAISE EXCEPTION 'excess contact draft privileges';
    END IF;
END $$;
