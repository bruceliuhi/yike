DO $$ DECLARE target TEXT:=NULLIF(current_setting('yike.app_role',true),''); oid OID; item TEXT; BEGIN
 SELECT r.oid INTO oid FROM pg_roles r WHERE rolname=target AND NOT rolsuper AND NOT rolbypassrls AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolreplication;
 IF oid IS NULL THEN RAISE EXCEPTION 'safe yike.app_role required'; END IF;
 FOREACH item IN ARRAY ARRAY['pilot_structured_followup_revisions','pilot_followup_reply_reads','pilot_followup_operations'] LOOP
  IF pg_has_role(oid,(item::regclass)::oid,'MEMBER') THEN RAISE EXCEPTION 'application role owns followup table'; END IF;
  EXECUTE format('GRANT SELECT,INSERT ON %I TO %I',item,target);
  IF has_table_privilege(oid,item,'UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES') OR has_any_column_privilege(oid,item,'UPDATE,REFERENCES') THEN RAISE EXCEPTION 'excess followup privileges'; END IF;
 END LOOP;
 EXECUTE format('GRANT SELECT ON pilot_users,pilot_opportunities,business_profile_versions,pilot_followups,pilot_reply_events TO %I',target);
 EXECUTE format('GRANT EXECUTE ON FUNCTION yike_followup_members() TO %I',target);
END $$;
