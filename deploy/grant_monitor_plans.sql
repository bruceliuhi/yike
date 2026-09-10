-- Trusted release step after migration 126.
DO $$ DECLARE target_role TEXT:=NULLIF(current_setting('yike.app_role',true),''); target_oid OID;
 reachable_role TEXT; relation_name TEXT; forbidden_privilege TEXT; immutable_column TEXT;
BEGIN
 SELECT oid INTO target_oid FROM pg_roles WHERE rolname=target_role AND NOT rolsuper AND NOT rolbypassrls AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolreplication;
 IF target_oid IS NULL THEN RAISE EXCEPTION 'restricted application role required'; END IF;
 IF EXISTS (SELECT 1 FROM pg_roles WHERE (rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb OR rolreplication)
   AND pg_has_role(target_oid,oid,'MEMBER')) THEN RAISE EXCEPTION 'application role must not inherit privileged roles'; END IF;
 IF EXISTS (SELECT 1 FROM pg_class WHERE oid IN (to_regclass('public.pilot_monitor_plans'),to_regclass('public.pilot_monitor_plan_operations')) AND pg_has_role(target_oid,relowner,'MEMBER')) THEN RAISE EXCEPTION 'application role must not own monitor tables'; END IF;
 REVOKE ALL ON pilot_monitor_plans,pilot_monitor_plan_operations FROM PUBLIC;
 EXECUTE format('REVOKE ALL ON pilot_monitor_plans,pilot_monitor_plan_operations FROM %I',target_role);
 EXECUTE format('GRANT SELECT,INSERT ON pilot_monitor_plans,pilot_monitor_plan_operations TO %I',target_role);
 EXECUTE format('GRANT UPDATE(state,revision,next_due_at,updated_at) ON pilot_monitor_plans TO %I',target_role);
 -- NOINHERIT membership still permits SET ROLE. Audit every reachable role,
 -- including privileges retained outside this script's direct target grants.
 FOR reachable_role IN SELECT rolname FROM pg_roles WHERE oid=target_oid OR pg_has_role(target_oid,oid,'MEMBER') LOOP
  FOREACH relation_name IN ARRAY ARRAY['public.pilot_monitor_plans','public.pilot_monitor_plan_operations'] LOOP
   FOREACH forbidden_privilege IN ARRAY ARRAY['DELETE','TRUNCATE','TRIGGER','REFERENCES'] LOOP
    IF has_table_privilege(reachable_role,relation_name,forbidden_privilege) THEN RAISE EXCEPTION 'excess reachable monitor privileges'; END IF;
   END LOOP;
   IF has_any_column_privilege(reachable_role,relation_name,'REFERENCES') THEN RAISE EXCEPTION 'excess reachable monitor privileges'; END IF;
  END LOOP;
  FOREACH immutable_column IN ARRAY ARRAY['tenant_id','owner_user_id','plan_id','profile_version_id','strategy_version_id','configuration_sha256','schedule','created_at'] LOOP
   IF has_column_privilege(reachable_role,'public.pilot_monitor_plans',immutable_column,'UPDATE') THEN RAISE EXCEPTION 'excess reachable monitor plan update privileges'; END IF;
  END LOOP;
  IF has_any_column_privilege(reachable_role,'public.pilot_monitor_plan_operations','UPDATE') THEN RAISE EXCEPTION 'excess reachable monitor receipt privileges'; END IF;
 END LOOP;
END $$;
