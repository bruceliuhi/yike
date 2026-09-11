DO $$ DECLARE target TEXT:=NULLIF(current_setting('yike.app_role',true),''); oid OID; BEGIN
 SELECT r.oid INTO oid FROM pg_roles r WHERE rolname=target AND NOT rolsuper AND NOT rolbypassrls AND NOT rolcreaterole AND NOT rolcreatedb;
 IF oid IS NULL THEN RAISE EXCEPTION 'restricted application role required'; END IF;
 EXECUTE format('REVOKE ALL ON public.pilot_short_coach_requests,public.pilot_short_coach_daily_quota FROM %I',target);
 EXECUTE format('GRANT SELECT,INSERT,UPDATE ON public.pilot_short_coach_requests TO %I',target);
 EXECUTE format('GRANT SELECT,INSERT,UPDATE ON public.pilot_short_coach_daily_quota TO %I',target);
 IF has_table_privilege(target,'public.pilot_short_coach_requests','DELETE') OR has_table_privilege(target,'public.pilot_short_coach_requests','TRUNCATE') OR has_table_privilege(target,'public.pilot_short_coach_requests','TRIGGER') THEN RAISE EXCEPTION 'excess short coach privileges'; END IF;
 IF has_table_privilege(target,'public.pilot_short_coach_daily_quota','DELETE') OR has_table_privilege(target,'public.pilot_short_coach_daily_quota','TRUNCATE') OR has_table_privilege(target,'public.pilot_short_coach_daily_quota','TRIGGER') THEN RAISE EXCEPTION 'excess short coach quota privileges'; END IF;
END $$;
