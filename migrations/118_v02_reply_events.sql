-- Owner-private, append-only reply facts. No platform polling or remote read action.
CREATE TABLE IF NOT EXISTS pilot_reply_events (
    tenant_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    event_id TEXT NOT NULL CHECK (event_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'),
    revision INTEGER NOT NULL CHECK (revision > 0),
    kind TEXT NOT NULL CHECK (kind IN ('PLATFORM_REPLY', 'MANUAL_FOLLOWUP')),
    opportunity_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    profile_version_id TEXT NOT NULL,
    outreach_request_id TEXT NOT NULL,
    platform TEXT,
    channel TEXT,
    external_reply_id TEXT,
    sender_public_id TEXT,
    body TEXT,
    received_at TIMESTAMPTZ,
    read_state TEXT,
    read_at TIMESTAMPTZ,
    action TEXT,
    note TEXT,
    occurred_at TIMESTAMPTZ,
    state TEXT NOT NULL CHECK (state IN ('ACTIVE', 'CORRECTED', 'VOID')),
    corrects_event_id TEXT,
    reason TEXT,
    observed_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    payload_sha256 TEXT NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, owner_user_id, event_id, revision),
    UNIQUE (tenant_id, owner_user_id, source_id, outreach_request_id, platform, external_reply_id, revision),
    FOREIGN KEY (tenant_id, owner_user_id) REFERENCES pilot_users(tenant_id, user_id),
    CHECK ((kind='PLATFORM_REPLY' AND platform IS NOT NULL AND channel IS NOT NULL AND external_reply_id IS NOT NULL
        AND sender_public_id IS NOT NULL AND body IS NOT NULL AND received_at IS NOT NULL AND read_state IS NOT NULL
        AND action IS NULL AND note IS NULL AND occurred_at IS NULL)
        OR (kind='MANUAL_FOLLOWUP' AND platform IS NULL AND channel IS NULL AND external_reply_id IS NULL
        AND sender_public_id IS NULL AND body IS NULL AND received_at IS NULL AND read_state IS NULL
        AND action IS NOT NULL AND note IS NOT NULL AND occurred_at IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS pilot_reply_events_lookup
    ON pilot_reply_events (tenant_id, owner_user_id, opportunity_id, observed_at DESC, revision DESC);

CREATE OR REPLACE FUNCTION pilot_reply_events_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'reply event is immutable'; END $$;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid='pilot_reply_events'::regclass AND tgname='reply_events_immutable') THEN
        CREATE TRIGGER reply_events_immutable BEFORE UPDATE OR DELETE ON pilot_reply_events
            FOR EACH ROW EXECUTE FUNCTION pilot_reply_events_immutable();
    END IF;
END $$;

ALTER TABLE pilot_reply_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_reply_events FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname=current_schema() AND tablename='pilot_reply_events' AND policyname='reply_events_owner_select') THEN
        CREATE POLICY reply_events_owner_select ON pilot_reply_events FOR SELECT
            USING (tenant_id=current_setting('yike.tenant_id',true) AND owner_user_id=current_setting('yike.user_id',true));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname=current_schema() AND tablename='pilot_reply_events' AND policyname='reply_events_owner_insert') THEN
        CREATE POLICY reply_events_owner_insert ON pilot_reply_events FOR INSERT
            WITH CHECK (tenant_id=current_setting('yike.tenant_id',true) AND owner_user_id=current_setting('yike.user_id',true));
    END IF;
END $$;
