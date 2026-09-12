-- Migration/admin path only; never give the runtime an administrator DSN.
DO $$ DECLARE target_role TEXT:=current_setting('yike.app_role',true); BEGIN
 IF target_role IS NULL OR target_role='' OR NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=target_role) THEN
  RAISE EXCEPTION 'yike.app_role must name an existing runtime role';
 END IF;
 EXECUTE format('GRANT SELECT,INSERT ON public.pilot_customer_research_contexts TO %I',target_role);
 EXECUTE format('GRANT SELECT ON public.pilot_candidate_sources,public.pilot_candidate_versions,
  public.pilot_candidate_projections,public.pilot_candidate_review_requests,public.pilot_candidate_reviews,
  public.pilot_structured_followup_revisions,public.pilot_outreach_queue,public.pilot_outreach_results TO %I',target_role);
END $$;
