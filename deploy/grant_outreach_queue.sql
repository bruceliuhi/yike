-- Restricted runtime may append confirmations and cancel, never rewrite them.
DO $$ DECLARE target_role TEXT:=NULLIF(current_setting('yike.app_role',true),''); target_oid OID;
BEGIN
    SELECT oid INTO target_oid FROM pg_roles WHERE rolname=target_role
        AND NOT rolsuper AND NOT rolbypassrls AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolreplication;
    IF target_oid IS NULL THEN RAISE EXCEPTION 'restricted application role required'; END IF;
    IF EXISTS (SELECT 1 FROM pg_class WHERE oid='public.pilot_outreach_queue'::regclass AND pg_has_role(target_oid,relowner,'MEMBER')) THEN
        RAISE EXCEPTION 'application role must not own outreach queue';
    END IF;
    EXECUTE format('GRANT SELECT,INSERT ON public.pilot_outreach_queue TO %I',target_role);
    EXECUTE format('GRANT UPDATE(state) ON public.pilot_outreach_queue TO %I',target_role);
    IF has_table_privilege(target_oid,'public.pilot_outreach_queue','UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES')
        OR has_any_column_privilege(target_oid,'public.pilot_outreach_queue','REFERENCES')
        OR EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid='public.pilot_outreach_queue'::regclass
            AND attnum>0 AND NOT attisdropped AND attname<>'state'
            AND has_column_privilege(target_oid,'public.pilot_outreach_queue',attname,'UPDATE')) THEN
        RAISE EXCEPTION 'excess outreach queue privileges';
    END IF;
END $$;
