-- Trusted release step after migration 126.
DO $$ DECLARE target_role TEXT:=NULLIF(current_setting('yike.app_role',true),''); target_oid OID;
BEGIN
 SELECT oid INTO target_oid FROM pg_roles WHERE rolname=target_role AND NOT rolsuper AND NOT rolbypassrls AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolreplication;
 IF target_oid IS NULL THEN RAISE EXCEPTION 'restricted application role required'; END IF;
 IF EXISTS (SELECT 1 FROM pg_class WHERE oid IN (to_regclass('public.pilot_monitor_plans'),to_regclass('public.pilot_monitor_plan_operations')) AND pg_has_role(target_oid,relowner,'MEMBER')) THEN RAISE EXCEPTION 'application role must not own monitor tables'; END IF;
 REVOKE ALL ON pilot_monitor_plans,pilot_monitor_plan_operations FROM PUBLIC;
 EXECUTE format('REVOKE ALL ON pilot_monitor_plans,pilot_monitor_plan_operations FROM %I',target_role);
 EXECUTE format('GRANT SELECT,INSERT ON pilot_monitor_plans,pilot_monitor_plan_operations TO %I',target_role);
 EXECUTE format('GRANT UPDATE(state,revision,next_due_at,updated_at) ON pilot_monitor_plans TO %I',target_role);
 IF has_table_privilege(target_oid,'pilot_monitor_plan_operations','UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES') OR has_table_privilege(target_oid,'pilot_monitor_plans','DELETE,TRUNCATE,TRIGGER,REFERENCES') THEN RAISE EXCEPTION 'excess monitor privileges'; END IF;
END $$;
