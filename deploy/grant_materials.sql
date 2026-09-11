-- Trusted release step after migration 125.
DO $$ DECLARE target_role TEXT:=NULLIF(current_setting('yike.app_role',true),''); target_oid OID; item TEXT;
BEGIN
  SELECT oid INTO target_oid FROM pg_roles WHERE rolname=target_role AND NOT rolsuper AND NOT rolbypassrls AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolreplication;
  IF target_oid IS NULL THEN RAISE EXCEPTION 'restricted application role required'; END IF;
  FOREACH item IN ARRAY ARRAY['pilot_material_revisions','pilot_material_operations','pilot_material_impact_tokens'] LOOP
    IF EXISTS (SELECT 1 FROM pg_class WHERE oid=to_regclass('public.'||item) AND pg_has_role(target_oid,relowner,'MEMBER')) THEN RAISE EXCEPTION 'application role must not own material tables'; END IF;
    EXECUTE format('REVOKE ALL ON public.%I FROM %I',item,target_role);
    EXECUTE format('GRANT SELECT,INSERT ON public.%I TO %I',item,target_role);
  END LOOP;
  EXECUTE format('GRANT UPDATE(consumed_at) ON public.pilot_material_impact_tokens TO %I',target_role);
  EXECUTE format('REVOKE ALL ON public.pilot_material_profile_references FROM %I',target_role);
  EXECUTE format('GRANT SELECT,INSERT ON public.pilot_material_profile_references TO %I',target_role);
  EXECUTE format('GRANT UPDATE(valid,invalidated_at,invalidation_reason) ON public.pilot_material_profile_references TO %I',target_role);
  IF EXISTS (SELECT 1 FROM pg_class WHERE oid='public.pilot_contact_drafts'::regclass AND pg_has_role(target_oid,relowner,'MEMBER')) THEN RAISE EXCEPTION 'application role must not own contact drafts'; END IF;
  EXECUTE format('GRANT SELECT ON public.pilot_contact_drafts TO %I',target_role);
  IF has_table_privilege(target_oid,'public.pilot_material_revisions','UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES')
     OR has_table_privilege(target_oid,'public.pilot_material_operations','UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES')
     OR has_any_column_privilege(target_oid,'public.pilot_material_revisions','UPDATE,REFERENCES')
     OR has_any_column_privilege(target_oid,'public.pilot_material_operations','UPDATE,REFERENCES')
     OR has_table_privilege(target_oid,'public.pilot_material_impact_tokens','DELETE,TRUNCATE,TRIGGER,REFERENCES') THEN
    RAISE EXCEPTION 'excess material privileges';
  END IF;
END $$;
