-- Durable owner-private confirmation snapshots; no channel send is performed.
CREATE TABLE IF NOT EXISTS pilot_outreach_confirmations (
    tenant_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    request_id TEXT NOT NULL CHECK (request_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'),
    opportunity_id TEXT NOT NULL CHECK (opportunity_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'),
    source_id TEXT NOT NULL CHECK (source_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'),
    channel TEXT NOT NULL CHECK (channel IN ('comment', 'dm')),
    draft_version INTEGER NOT NULL CHECK (draft_version > 0),
    account_id TEXT NOT NULL CHECK (account_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'),
    connection_version INTEGER NOT NULL CHECK (connection_version > 0),
    recipient_id TEXT NOT NULL CHECK (btrim(recipient_id) = recipient_id AND char_length(recipient_id) BETWEEN 1 AND 512),
    content_sha256 TEXT NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    snapshot JSONB NOT NULL CHECK (
        jsonb_typeof(snapshot) = 'object' AND snapshot->>'schema_version' = 'outreach-confirmation-v1'
        AND snapshot->>'request_id' = request_id AND snapshot->>'opportunity_id' = opportunity_id
        AND snapshot->>'source_id' = source_id AND snapshot->>'channel' = channel
        AND (snapshot->>'version')::integer = draft_version AND snapshot->>'account_id' = account_id
        AND (snapshot->>'connection_version')::integer = connection_version
        AND snapshot->>'recipient_id' = recipient_id AND snapshot->>'content_sha256' = content_sha256
    ),
    snapshot_sha256 TEXT NOT NULL CHECK (snapshot_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, owner_user_id, request_id)
);

CREATE OR REPLACE FUNCTION pilot_outreach_confirmation_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'outreach confirmation is immutable'; END $$;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid='pilot_outreach_confirmations'::regclass AND tgname='outreach_confirmation_immutable') THEN
        CREATE TRIGGER outreach_confirmation_immutable BEFORE UPDATE OR DELETE ON pilot_outreach_confirmations FOR EACH ROW EXECUTE FUNCTION pilot_outreach_confirmation_immutable();
    END IF;
END $$;

ALTER TABLE pilot_outreach_confirmations ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_outreach_confirmations FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname=current_schema() AND tablename='pilot_outreach_confirmations' AND policyname='outreach_confirmation_owner_select') THEN
        CREATE POLICY outreach_confirmation_owner_select ON pilot_outreach_confirmations FOR SELECT USING (tenant_id=current_setting('yike.tenant_id',true) AND owner_user_id=current_setting('yike.user_id',true));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname=current_schema() AND tablename='pilot_outreach_confirmations' AND policyname='outreach_confirmation_owner_insert') THEN
        CREATE POLICY outreach_confirmation_owner_insert ON pilot_outreach_confirmations FOR INSERT WITH CHECK (tenant_id=current_setting('yike.tenant_id',true) AND owner_user_id=current_setting('yike.user_id',true));
    END IF;
END $$;
