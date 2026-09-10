-- Explicit profile-description disclosure snapshot for model-backed suggestions.
ALTER TABLE pilot_search_suggestion_requests
    ADD COLUMN IF NOT EXISTS disclosure_policy_version TEXT;

ALTER TABLE pilot_search_suggestion_requests
    DROP CONSTRAINT IF EXISTS pilot_search_suggestion_requests_disclosure_policy_version_check;
ALTER TABLE pilot_search_suggestion_requests
    ADD CONSTRAINT pilot_search_suggestion_requests_disclosure_policy_version_check
    CHECK (disclosure_policy_version IS NULL OR disclosure_policy_version='profile-description-v1');

CREATE OR REPLACE FUNCTION pilot_search_suggestion_transition_guard() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN
    IF TG_OP='INSERT' THEN
        IF NEW.state <> 'PENDING' THEN
            RAISE EXCEPTION USING ERRCODE='YS001', MESSAGE='suggestion_transition_invalid';
        END IF;
    ELSE
        IF OLD.state <> 'PENDING' OR NEW.state='PENDING' OR
            ROW(NEW.tenant_id,NEW.owner_user_id,NEW.request_id,NEW.draft_id,NEW.draft_revision,
                NEW.profile_version_id,NEW.request_sha256,NEW.profile_sha256,NEW.origin_session_key,
                NEW.origin_session_expires_at,NEW.rule_version,NEW.model_provider,NEW.model_name,
                NEW.disclosure_policy_version,NEW.created_at)
            IS DISTINCT FROM
            ROW(OLD.tenant_id,OLD.owner_user_id,OLD.request_id,OLD.draft_id,OLD.draft_revision,
                OLD.profile_version_id,OLD.request_sha256,OLD.profile_sha256,OLD.origin_session_key,
                OLD.origin_session_expires_at,OLD.rule_version,OLD.model_provider,OLD.model_name,
                OLD.disclosure_policy_version,OLD.created_at) THEN
            RAISE EXCEPTION USING ERRCODE='YS001', MESSAGE='suggestion_transition_invalid';
        END IF;
        NEW.updated_at := clock_timestamp();
    END IF;
    RETURN NEW;
END $$;
