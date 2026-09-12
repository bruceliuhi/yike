-- Administrator-only, repeatable; runtime never receives schema ownership.
DO $$ DECLARE target_role TEXT := NULLIF(current_setting('yike.app_role',true),''); target_oid OID; item TEXT; BEGIN
 SELECT oid INTO target_oid FROM pg_roles WHERE rolname=target_role AND NOT rolsuper AND NOT rolbypassrls AND NOT rolcreaterole;
 IF target_oid IS NULL THEN RAISE EXCEPTION 'existing restricted application role is required'; END IF;
 FOREACH item IN ARRAY ARRAY['pilot_candidate_review_requests','pilot_candidate_assessments','pilot_candidate_source_verifications','pilot_candidate_reviews','pilot_candidate_call_quota','pilot_candidate_model_usage_events'] LOOP
  IF EXISTS(SELECT 1 FROM pg_class WHERE oid=item::regclass AND relowner=target_oid) THEN RAISE EXCEPTION 'application role must not own review tables'; END IF;
  EXECUTE format('REVOKE ALL ON TABLE public.%I FROM %I',item,target_role);
  EXECUTE format('GRANT SELECT,INSERT ON TABLE public.%I TO %I',item,target_role);
 END LOOP;
 EXECUTE format('GRANT UPDATE(status,result) ON pilot_candidate_review_requests TO %I',target_role);
 EXECUTE format('GRANT UPDATE(reserved_calls) ON pilot_candidate_call_quota TO %I',target_role);
 -- Existing same-transaction importer and tenant-shared opportunity read path.
 EXECUTE format('GRANT SELECT,INSERT ON pilot_sources,pilot_source_versions,pilot_source_observations,pilot_opportunities TO %I',target_role);
 EXECUTE format('GRANT SELECT ON pilot_followups TO %I',target_role);
 EXECUTE format('GRANT UPDATE(health) ON pilot_sources TO %I',target_role);
 EXECUTE format('GRANT UPDATE(title) ON pilot_source_versions TO %I',target_role);
 EXECUTE format('GRANT UPDATE(source_status) ON pilot_opportunities TO %I',target_role);
END $$;
