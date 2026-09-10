-- Durable evidence that a consent-bound suggestion request was not submitted.
CREATE TABLE IF NOT EXISTS pilot_search_suggestion_rejections (
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
    disclosure_policy_version TEXT NOT NULL CHECK (disclosure_policy_version='profile-description-v1'),
    reason TEXT NOT NULL CHECK (reason IN ('capability_unavailable','disclosure_mismatch','profile_unavailable',
        'suggestion_busy','suggestion_rate_limited','suggestion_quota_exceeded')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id,owner_user_id,request_id),
    FOREIGN KEY (tenant_id,owner_user_id) REFERENCES pilot_users(tenant_id,user_id)
);

ALTER TABLE pilot_search_suggestion_rejections ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_search_suggestion_rejections FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname=current_schema()
        AND tablename='pilot_search_suggestion_rejections' AND policyname='suggestion_rejection_owner_select') THEN
        CREATE POLICY suggestion_rejection_owner_select ON pilot_search_suggestion_rejections FOR SELECT USING
            (tenant_id=current_setting('yike.tenant_id',true) AND owner_user_id=current_setting('yike.user_id',true));
        CREATE POLICY suggestion_rejection_owner_insert ON pilot_search_suggestion_rejections FOR INSERT WITH CHECK
            (tenant_id=current_setting('yike.tenant_id',true) AND owner_user_id=current_setting('yike.user_id',true));
    END IF;
END $$;

CREATE OR REPLACE FUNCTION pilot_search_suggestion_fact_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE opposite regclass;
BEGIN
    PERFORM pg_advisory_xact_lock(11001,hashtext(NEW.tenant_id));
    IF TG_TABLE_NAME='pilot_search_suggestion_requests' THEN
        opposite := 'pilot_search_suggestion_rejections'::regclass;
    ELSE
        opposite := 'pilot_search_suggestion_requests'::regclass;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_class WHERE oid=opposite) THEN
        IF TG_TABLE_NAME='pilot_search_suggestion_requests' THEN
            PERFORM 1 FROM pilot_search_suggestion_rejections
                WHERE tenant_id=NEW.tenant_id AND owner_user_id=NEW.owner_user_id AND request_id=NEW.request_id;
        ELSE
            PERFORM 1 FROM pilot_search_suggestion_requests
                WHERE tenant_id=NEW.tenant_id AND owner_user_id=NEW.owner_user_id AND request_id=NEW.request_id;
        END IF;
        IF FOUND THEN
            RAISE EXCEPTION USING ERRCODE='YS002', MESSAGE='suggestion_fact_conflict';
        END IF;
    END IF;
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS pilot_search_suggestion_fact_guard ON pilot_search_suggestion_requests;
CREATE TRIGGER pilot_search_suggestion_fact_guard BEFORE INSERT ON pilot_search_suggestion_requests
    FOR EACH ROW EXECUTE FUNCTION pilot_search_suggestion_fact_guard();
DROP TRIGGER IF EXISTS pilot_search_suggestion_rejection_fact_guard ON pilot_search_suggestion_rejections;
CREATE TRIGGER pilot_search_suggestion_rejection_fact_guard BEFORE INSERT ON pilot_search_suggestion_rejections
    FOR EACH ROW EXECUTE FUNCTION pilot_search_suggestion_fact_guard();
