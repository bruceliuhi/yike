-- Persistent editable suggestions only: no model dispatch or execution authority.
CREATE TABLE IF NOT EXISTS pilot_search_suggestion_requests (
    tenant_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    request_id TEXT NOT NULL CHECK (request_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
    draft_id TEXT NOT NULL CHECK (draft_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
    draft_revision INTEGER NOT NULL CHECK (draft_revision BETWEEN 0 AND 2147483647),
    profile_version_id TEXT NOT NULL,
    request_sha256 TEXT NOT NULL CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
    profile_sha256 TEXT NOT NULL CHECK (profile_sha256 ~ '^[0-9a-f]{64}$'),
    origin_session_key TEXT NOT NULL CHECK (origin_session_key ~ '^[0-9a-f]{64}$'),
    origin_session_expires_at BIGINT NOT NULL CHECK (origin_session_expires_at BETWEEN 1 AND 253402300799),
    rule_version TEXT NOT NULL CHECK (rule_version='search-suggestion-v1'),
    model_provider TEXT NOT NULL CHECK (model_provider ~ '^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}$'),
    model_name TEXT NOT NULL CHECK (model_name ~ '^[a-zA-Z0-9][a-zA-Z0-9_.:/-]{0,199}$'),
    state TEXT NOT NULL DEFAULT 'PENDING' CHECK (state IN ('PENDING','SUCCEEDED','FAILED','UNKNOWN')),
    result JSONB,
    usage JSONB,
    error_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id,owner_user_id,request_id),
    FOREIGN KEY (tenant_id,owner_user_id) REFERENCES pilot_users(tenant_id,user_id),
    FOREIGN KEY (tenant_id,profile_version_id) REFERENCES business_profile_versions(tenant_id,profile_version_id),
    CHECK ((state='PENDING' AND result IS NULL AND usage IS NULL AND error_code IS NULL)
        OR (state='SUCCEEDED' AND result IS NOT NULL AND jsonb_typeof(result)='object' AND error_code IS NULL)
        OR (state='FAILED' AND result IS NULL AND usage IS NULL AND error_code IS NOT NULL
            AND error_code IN ('invalid_suggestion_result','suggestion_provider_rejected','profile_changed','dispatch_failed'))
        OR (state='UNKNOWN' AND result IS NULL AND usage IS NULL AND error_code IS NOT NULL
            AND error_code='suggestion_result_unknown')),
    CHECK (usage IS NULL OR (jsonb_typeof(usage)='object'
        AND usage ?& ARRAY['prompt_tokens','completion_tokens','total_tokens']
        AND usage-ARRAY['prompt_tokens','completion_tokens','total_tokens']='{}'::jsonb))
);

CREATE TABLE IF NOT EXISTS pilot_search_suggestion_quota_events (
    tenant_id TEXT NOT NULL REFERENCES pilot_tenants(tenant_id),
    quota_event_id TEXT NOT NULL CHECK (quota_event_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id,quota_event_id)
);
CREATE INDEX IF NOT EXISTS pilot_suggestion_quota_window
    ON pilot_search_suggestion_quota_events(tenant_id,created_at);

ALTER TABLE pilot_search_suggestion_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_search_suggestion_requests FORCE ROW LEVEL SECURITY;
ALTER TABLE pilot_search_suggestion_quota_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_search_suggestion_quota_events FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname=current_schema()
        AND tablename='pilot_search_suggestion_requests' AND policyname='suggestion_owner_select') THEN
        CREATE POLICY suggestion_owner_select ON pilot_search_suggestion_requests FOR SELECT USING
            (tenant_id=current_setting('yike.tenant_id',true) AND owner_user_id=current_setting('yike.user_id',true));
        CREATE POLICY suggestion_owner_insert ON pilot_search_suggestion_requests FOR INSERT WITH CHECK
            (tenant_id=current_setting('yike.tenant_id',true) AND owner_user_id=current_setting('yike.user_id',true));
        CREATE POLICY suggestion_owner_update ON pilot_search_suggestion_requests FOR UPDATE USING
            (tenant_id=current_setting('yike.tenant_id',true) AND owner_user_id=current_setting('yike.user_id',true)) WITH CHECK
            (tenant_id=current_setting('yike.tenant_id',true) AND owner_user_id=current_setting('yike.user_id',true));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname=current_schema()
        AND tablename='pilot_search_suggestion_quota_events' AND policyname='suggestion_quota_select') THEN
        CREATE POLICY suggestion_quota_select ON pilot_search_suggestion_quota_events FOR SELECT USING
            (tenant_id=current_setting('yike.tenant_id',true));
        CREATE POLICY suggestion_quota_insert ON pilot_search_suggestion_quota_events FOR INSERT WITH CHECK
            (tenant_id=current_setting('yike.tenant_id',true));
    END IF;
END $$;

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
                NEW.origin_session_expires_at,NEW.rule_version,NEW.model_provider,NEW.model_name,NEW.created_at)
            IS DISTINCT FROM
            ROW(OLD.tenant_id,OLD.owner_user_id,OLD.request_id,OLD.draft_id,OLD.draft_revision,
                OLD.profile_version_id,OLD.request_sha256,OLD.profile_sha256,OLD.origin_session_key,
                OLD.origin_session_expires_at,OLD.rule_version,OLD.model_provider,OLD.model_name,OLD.created_at) THEN
            RAISE EXCEPTION USING ERRCODE='YS001', MESSAGE='suggestion_transition_invalid';
        END IF;
        NEW.updated_at := clock_timestamp();
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS pilot_search_suggestion_transition_guard ON pilot_search_suggestion_requests;
CREATE TRIGGER pilot_search_suggestion_transition_guard BEFORE INSERT OR UPDATE ON pilot_search_suggestion_requests
    FOR EACH ROW EXECUTE FUNCTION pilot_search_suggestion_transition_guard();
