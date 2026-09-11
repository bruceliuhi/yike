-- psql -X -v ON_ERROR_STOP=1 -v app_role=EXISTING_RESTRICTED_ROLE -f deploy/grant_runtime.sql
-- Run AFTER all migrations, with a separate administrator connection.
-- Any failure rolls the entire release grant transaction back.
\set ON_ERROR_STOP on
BEGIN;
SELECT set_config('yike.app_role', :'app_role', true);
\ir grant_base_profiles.sql
\ir grant_session_revocations.sql
\ir grant_device_credentials.sql
\ir grant_connection_operations.sql
\ir grant_phone_login.sql
\ir grant_trials.sql
\ir grant_temporary_access.sql
\ir grant_search_suggestions.sql
\ir grant_execution_runtime.sql
\ir grant_candidate_ingestion.sql
\ir grant_candidate_review.sql
\ir grant_research_strategies.sql
\ir grant_research_execution.sql
\ir grant_research_resources.sql
\ir grant_research_runtime.sql
\ir grant_opportunity_evidence.sql
\ir grant_device_registration.sql
\ir grant_reply_events.sql
\ir grant_outreach_contract.sql
\ir grant_contact_drafts.sql
\ir grant_outreach_queue.sql
\ir grant_outreach_dispatch.sql
\ir grant_materials.sql
\ir grant_monitor_plans.sql
\ir grant_monitor_runtime.sql
\ir grant_short_coach.sql
\ir grant_structured_followups.sql
COMMIT;
