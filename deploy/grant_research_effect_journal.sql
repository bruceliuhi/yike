-- Admin provisioning only. No runtime administrator DSN.
DO $$ DECLARE target_role TEXT:=current_setting('yike.app_role',true); BEGIN
 IF target_role IS NULL OR target_role='' OR NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=target_role) THEN
  RAISE EXCEPTION 'yike.app_role must name an existing runtime role';
 END IF;
 EXECUTE format('GRANT SELECT,INSERT ON public.pilot_research_effect_journal TO %I',target_role);
 EXECUTE format('GRANT UPDATE(status,result,output_sha256) ON public.pilot_research_effect_journal TO %I',target_role);
END $$;
