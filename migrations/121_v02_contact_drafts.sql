-- Manual draft history and original save receipts; not send authorizations.
CREATE TABLE IF NOT EXISTS pilot_contact_drafts (
    tenant_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    opportunity_id TEXT NOT NULL,
    channel TEXT NOT NULL CHECK (channel IN ('comment','dm')),
    draft_version INTEGER NOT NULL CHECK (draft_version > 0),
    content_hash TEXT NOT NULL CHECK (content_hash ~ '^[a-f0-9]{64}$'),
    payload JSONB NOT NULL CHECK ((
        jsonb_typeof(payload)='object'
        AND payload#>>'{binding,requestId}'=request_id
        AND payload#>>'{binding,opportunityId}'=opportunity_id
        AND payload#>>'{binding,channel}'=channel
        AND payload#>>'{binding,contentHash}'=content_hash
        AND payload#>>'{snapshot,draft,opportunityId}'=opportunity_id
        AND payload#>>'{snapshot,draft,channel}'=channel
        AND (payload#>>'{snapshot,draft,version}')::integer=draft_version
        AND payload#>>'{snapshot,draft,content}'=payload#>>'{snapshot,draft,savedContent}'
    ) IS TRUE),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id,owner_user_id,request_id),
    UNIQUE (tenant_id,owner_user_id,opportunity_id,channel,draft_version),
    FOREIGN KEY (tenant_id,opportunity_id) REFERENCES pilot_opportunities(tenant_id,opportunity_id)
);
ALTER TABLE pilot_contact_drafts ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_contact_drafts FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname=current_schema() AND tablename='pilot_contact_drafts' AND policyname='contact_draft_owner_select') THEN
        CREATE POLICY contact_draft_owner_select ON pilot_contact_drafts FOR SELECT
            USING (tenant_id=current_setting('yike.tenant_id',true) AND owner_user_id=current_setting('yike.user_id',true));
        CREATE POLICY contact_draft_owner_insert ON pilot_contact_drafts FOR INSERT
            WITH CHECK (tenant_id=current_setting('yike.tenant_id',true) AND owner_user_id=current_setting('yike.user_id',true));
    END IF;
END $$;
CREATE OR REPLACE FUNCTION pilot_contact_draft_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'contact draft history is immutable'; END $$;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid='pilot_contact_drafts'::regclass AND tgname='contact_draft_immutable') THEN
        CREATE TRIGGER contact_draft_immutable BEFORE UPDATE OR DELETE ON pilot_contact_drafts
            FOR EACH ROW EXECUTE FUNCTION pilot_contact_draft_immutable();
    END IF;
END $$;
